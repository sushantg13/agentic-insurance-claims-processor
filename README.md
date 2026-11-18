# agentic-insurance-claims-processor

Agentic insurance claims processing on AWS. Step Functions orchestrates Lambda agents that extract claim and policy text with Amazon Textract and decide coverage with Amazon Bedrock (Nova Lite). Everything is provisioned with Terraform.

> A learning project built while following a video course. Not production-ready: the IAM policies are deliberately broad (`Resource = "*"`) and will be tightened later.

## Architecture

1. A claim file is uploaded to S3 (trigger Lambda: not built yet).
2. Step Functions runs the workflow:
   - **Ingestion agent** (Lambda): extracts text from the claim and its policy document with Textract.
   - **Coverage agent** (Lambda): asks Bedrock whether the claim is covered and returns a decision with a summary.

Planned: payout agent, join step and decision agent.

## Project layout

```
src/
├── agents/
│   ├── ingestion/            # Lambda: Textract text extraction
│   └── coverage/             # Lambda: Bedrock coverage decision
├── step_functions/           # Workflow definition (ASL)
└── infra/
    ├── modules/              # iam, s3, lambda, step_functions
    ├── tenants/<name>/dev/   # Entry point and tfvars per tenant and environment
    ├── main.tf
    ├── provider.tf
    └── variables.tf
```

## Getting started

Prerequisites: Terraform, Python 3.12, the AWS CLI configured with credentials (`aws sts get-caller-identity` should work).

1. Build the Lambda zips (they are git-ignored):

   ```bash
   cd src/agents/ingestion && zip ingestion.zip main.py
   cd ../coverage && zip coverage.zip main.py
   ```

2. Plan and apply from the tenant folder:

   ```bash
   cd src/infra/tenants/sushant/dev
   terraform init
   terraform plan
   ```

## Status

- [x] IAM, S3, Lambda and Step Functions modules
- [x] Ingestion and coverage agent code
- [ ] Deploy and test end to end
- [ ] S3 upload trigger Lambda
- [ ] Payout and decision agents
