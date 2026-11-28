# agentic-insurance-claims-processor

Agentic claim assessment for Claurich home and motor insurance, on AWS, provisioned with Terraform.

This stage covers **claim intake** and the **precheck**. A claim dropped into S3 is checked, stored as
write-once evidence and recorded in DynamoDB. The precheck then runs the eligibility checks that need no
model and sets the always-route flags. The assessment worker is a placeholder that marks the claim as
being assessed; the AI pipeline replaces it later.

## How a claim flows

```
claim folder ──upload──▶ inbox bucket ──ObjectCreated (.json)──▶ intake Lambda
                                                                   │ checks shape, policy, attachments
                                                                   │ duplicate / conflict detection
                                                                   ├─▶ evidence bucket (Object Lock, versioned)
                                                                   ├─▶ claims table (status RECEIVED)
                                                                   └─▶ intake-log table (every decision + reasons)
claims table stream ──Pipe (new RECEIVED items)──▶ precheck queue ──▶ precheck Lambda
                                                                   │ re-reads the evidence copy, checks its hash
                                                                   │ policy, PDS version, policy term, flags
                                                                   └─▶ claims table (PRECHECKED, INELIGIBLE or NEEDS_REVIEW)
claims table stream ──Pipe (updates to PRECHECKED)──▶ assessment queue ──▶ worker Lambda (status ASSESSING)
```

The claim's status drives the flow. Each pipe watches the claims table's stream for one status and
queues the claim for the next Lambda, so no Lambda sends messages to the next one itself.

| Resource | Purpose |
|---|---|
| Inbox bucket | Where claim folders are dropped. Uploads expire after 30 days. |
| Evidence bucket | The submission and attachments exactly as received, under `claims/<claim_id>/<sha256>/`. Object Lock in governance mode. |
| `claims` table | One item per lodged claim: status, policy, PDS id, hashes and evidence locations. Its stream feeds the queue. |
| `policies` table | The policy register, seeded from a JSON file. |
| `intake-log` table | Every intake decision: accepted, duplicate, conflict or rejected, with reasons. |
| Precheck queue | Claim ids waiting for the precheck. Dead-letter queue after 3 failed attempts. |
| Assessment queue | Claim ids waiting for the worker. Dead-letter queue after 3 failed attempts. |
| Failure queues | Intake events that failed after Lambda's retries, and stream records either pipe could not deliver. |

Intake outcomes:

- **Accepted**: valid, policy belongs to the policyholder, attachments present. Stored and queued.
- **Duplicate**: the claim id is already lodged with identical content. Nothing changes.
- **Conflict**: the claim id is already lodged with different content. The original is kept.
- **Rejected**: invalid JSON or shape, unknown policy, wrong policyholder, or a missing attachment.
- **Ignored**: any file not named `claim-*.json`, such as an answer key.

Precheck outcomes, each stored on the claim with every check and its result:

- **PRECHECKED**: eligible. Goes on to assessment with any flags attached.
- **INELIGIBLE**: the incident's local date is outside the policy term. The assessment does not run.
- **NEEDS_REVIEW**: the data is wrong: evidence altered, policy missing or malformed, or a PDS that does
  not apply to the policy. A person must look first.

Flags never stop a claim. `high_value` (over $50,000) and `environmental_event` (storm, flood,
earthquake) are the always-route rules. `claim_value_unknown`, `claimed_exceeds_sum_insured`,
`incident_on_term_boundary` and `event_type_unusual_for_product` are for the assessment to weigh. The
waiting period is recorded as deferred: it is set per Insured Event, so it is checked once the cover is
known.

## Layout

```
src/
├── lambdas/                  # Python code; Terraform zips each Lambda separately
│   ├── intake/               # intake Lambda
│   │   ├── handler.py        # entry point: S3 event → process.py
│   │   └── process.py        # the intake checks, evidence copy and table writes
│   ├── precheck/             # precheck Lambda
│   │   ├── handler.py        # entry point: SQS message → process.py
│   │   ├── process.py        # loads the evidence copy and policy, stores the result
│   │   ├── checks.py         # the checks and flags, pure code
│   │   └── pds_catalog.py    # known PDS versions and when each applies
│   ├── worker/               # worker Lambda
│   │   ├── handler.py        # entry point: SQS message → assessment.py
│   │   └── assessment.py     # moves the claim to ASSESSING (the AI pipeline goes here)
│   └── shared/               # copied into every Lambda's zip
│       ├── log.py            # one JSON log line per event
│       └── validation.py     # shape checks on the claim JSON
└── infra/                    # Terraform root module: wires the modules together
    ├── main.tf               # builds the zips and calls the modules
    ├── variables.tf
    ├── outputs.tf
    ├── provider.tf
    ├── modules/              # one folder per AWS service
    │   ├── s3/               # inbox and evidence buckets
    │   ├── dynamodb/         # claims, policies and intake-log tables
    │   ├── sqs/              # precheck and assessment queues, and the failure queues
    │   ├── eventbridge_pipe/ # claims stream → a queue, by status; used twice
    │   └── lambda/
    │       ├── intake/       # intake Lambda, its S3 trigger and its IAM role
    │       ├── precheck/     # precheck Lambda, its SQS trigger and its IAM role
    │       └── worker/       # worker Lambda, its SQS trigger and its IAM role
    └── tenants/sushant/dev/  # entry point, tfvars and local state
scripts/
├── seed_policies.py          # load a policy register into the policies table
└── upload_claims.py          # upload claim folders: attachments first, claim JSON last
tests/                        # pytest suite against moto; makes no AWS calls
```

Each module that runs something owns its IAM role, so its permissions sit next to the resources that use them.

## Prerequisites

Terraform 1.6 or later, Python 3.12, and the AWS CLI with credentials (`aws sts get-caller-identity` should work).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

## Run the tests

```bash
.venv/bin/python -m pytest
```

## Deploy

```bash
cd src/infra/tenants/sushant/dev
terraform init
terraform plan
terraform apply
```

Each Lambda's zip is built during plan from its own folder in `src/lambdas` plus `src/lambdas/shared`; there is no separate build step.

## Use it

From the repository root:

```bash
TF="terraform -chdir=src/infra/tenants/sushant/dev"

# 1. Load the policy register.
.venv/bin/python scripts/seed_policies.py --register path/to/policy-register.json --table "$($TF output -raw policies_table)"

# 2. Upload claim folders (a folder of claim folders works too). expected.json is never uploaded.
.venv/bin/python scripts/upload_claims.py --bucket "$($TF output -raw inbox_bucket)" path/to/claims/

# 3. See what happened.
aws dynamodb scan --table-name "$($TF output -raw intake_log_table)"
aws dynamodb scan --table-name "$($TF output -raw claims_table)"
aws logs tail "/aws/lambda/insurance-claims-workflow-dev-intake" --follow
```

Add `--dry-run` to the upload script to see the upload order without uploading.

## Tearing down

Evidence objects are locked for `evidence_retention_days` (1 day in dev). The evidence bucket cannot be
deleted until every locked object's retention has passed, or until an administrator removes the objects
with governance bypass. Use `COMPLIANCE` mode only in production: nobody, including the root account,
can delete those objects early.
