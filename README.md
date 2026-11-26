# agentic-insurance-claims-processor

Agentic claim assessment for Claurich home and motor insurance, on AWS, provisioned with Terraform.

This stage covers **claim intake**: a claim dropped into S3 is checked, stored as write-once evidence,
recorded in DynamoDB and queued for assessment. The assessment worker is a placeholder that marks the
claim as being assessed; the AI pipeline replaces it later.

## How a claim flows

```
claim folder ──upload──▶ inbox bucket ──ObjectCreated (.json)──▶ intake Lambda
                                                                   │ checks shape, policy, attachments
                                                                   │ duplicate / conflict detection
                                                                   ├─▶ evidence bucket (Object Lock, versioned)
                                                                   ├─▶ claims table (status RECEIVED)
                                                                   └─▶ intake-log table (every decision + reasons)
claims table stream ──EventBridge Pipe (new RECEIVED items)──▶ assessment queue ──▶ worker Lambda (status ASSESSING)
```

| Resource | Purpose |
|---|---|
| Inbox bucket | Where claim folders are dropped. Uploads expire after 30 days. |
| Evidence bucket | The submission and attachments exactly as received, under `claims/<claim_id>/<sha256>/`. Object Lock in governance mode. |
| `claims` table | One item per lodged claim: status, policy, PDS id, hashes and evidence locations. Its stream feeds the queue. |
| `policies` table | The policy register, seeded from a JSON file. |
| `intake-log` table | Every intake decision: accepted, duplicate, conflict or rejected, with reasons. |
| Assessment queue | Claim ids waiting for the worker. Dead-letter queue after 3 failed attempts. |
| Failure queues | Intake events that failed after Lambda's retries, and stream records the pipe could not deliver. |

Intake outcomes:

- **Accepted**: valid, policy belongs to the policyholder, attachments present. Stored and queued.
- **Duplicate**: the claim id is already lodged with identical content. Nothing changes.
- **Conflict**: the claim id is already lodged with different content. The original is kept.
- **Rejected**: invalid JSON or shape, unknown policy, wrong policyholder, or a missing attachment.
- **Ignored**: any file not named `claim-*.json`, such as an answer key.

## Layout

```
src/
├── app/                      # Lambda code, one zip, built by Terraform
│   ├── claims/               # intake, validation, assessment and logging logic
│   ├── intake_handler.py     # S3 event → claims.intake
│   └── worker_handler.py     # SQS message → claims.assessment
└── infra/                    # Terraform root module: wires the modules together
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    ├── provider.tf
    ├── modules/
    │   ├── storage/          # inbox and evidence buckets
    │   ├── database/         # claims, policies and intake-log tables
    │   ├── queues/           # assessment queue and the failure queues
    │   ├── intake/           # intake Lambda, its S3 trigger and its IAM role
    │   ├── claims_pipe/      # claims stream → assessment queue, and its IAM role
    │   └── worker/           # worker Lambda, its SQS trigger and its IAM role
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

The Lambda zip is built from `src/app` during plan; there is no separate build step.

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
