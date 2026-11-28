# Root module: wires the parts of the intake architecture together.
# Each module owns its resources and the IAM role that goes with them.

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  prefix     = "${var.project}-${var.env}"

  # Each Lambda ships only its own folder in src/lambdas, plus the shared folder.
  lambdas_dir = "${path.module}/../lambdas"
  lambdas     = ["intake", "precheck", "worker"]

  packages = {
    for name in local.lambdas : name => {
      path = data.archive_file.lambda[name].output_path
      hash = data.archive_file.lambda[name].output_base64sha256
    }
  }
}

data "archive_file" "lambda" {
  for_each = toset(local.lambdas)

  type        = "zip"
  output_path = "${path.module}/.build/${each.key}.zip"

  dynamic "source" {
    for_each = fileset(local.lambdas_dir, "{${each.key},shared}/*.py")
    content {
      content  = file("${local.lambdas_dir}/${source.value}")
      filename = source.value
    }
  }
}

module "s3" {
  source = "./modules/s3"

  prefix                  = local.prefix
  account_id              = local.account_id
  inbox_retention_days    = var.inbox_retention_days
  evidence_lock_mode      = var.evidence_lock_mode
  evidence_retention_days = var.evidence_retention_days
}

module "dynamodb" {
  source = "./modules/dynamodb"

  prefix              = local.prefix
  deletion_protection = var.deletion_protection
}

module "sqs" {
  source = "./modules/sqs"

  prefix                                = local.prefix
  precheck_visibility_timeout_seconds   = var.precheck_timeout_seconds * 6
  assessment_visibility_timeout_seconds = var.worker_timeout_seconds * 6
  max_receive_count                     = var.max_receive_count
}

module "intake_lambda" {
  source = "./modules/lambda/intake"

  prefix             = local.prefix
  account_id         = local.account_id
  package            = local.packages["intake"]
  timeout_seconds    = var.intake_timeout_seconds
  log_retention_days = var.log_retention_days
  inbox_bucket       = module.s3.inbox_bucket
  evidence_bucket    = module.s3.evidence_bucket
  claims_table       = module.dynamodb.claims_table
  policies_table     = module.dynamodb.policies_table
  intake_log_table   = module.dynamodb.intake_log_table
  failure_queue_arn  = module.sqs.intake_failures.arn
}

# Claim status drives the flow: each pipe watches the claims stream for one
# status and queues the claim for the next Lambda.
#   RECEIVED (new item)   -> precheck queue   -> precheck Lambda
#   PRECHECKED (update)   -> assessment queue -> worker Lambda
module "precheck_pipe" {
  source = "./modules/eventbridge_pipe"

  prefix      = local.prefix
  account_id  = local.account_id
  name        = "claims-to-precheck"
  description = "Newly lodged claims to the precheck queue"
  filter_pattern = {
    eventName = ["INSERT"]
    dynamodb  = { NewImage = { status = { S = ["RECEIVED"] } } }
  }
  claims_stream_arn     = module.dynamodb.claims_table.stream_arn
  target_queue_arn      = module.sqs.precheck.arn
  dead_letter_queue_arn = module.sqs.pipe_dlq.arn
}

module "precheck_lambda" {
  source = "./modules/lambda/precheck"

  prefix             = local.prefix
  package            = local.packages["precheck"]
  timeout_seconds    = var.precheck_timeout_seconds
  log_retention_days = var.log_retention_days
  max_concurrency    = var.precheck_max_concurrency
  evidence_bucket    = module.s3.evidence_bucket
  claims_table       = module.dynamodb.claims_table
  policies_table     = module.dynamodb.policies_table
  precheck_queue_arn = module.sqs.precheck.arn
}

# Only the update that sets PRECHECKED matches. The precheck writes the status
# and its record in one update, and nothing else changes a PRECHECKED claim
# before the worker moves it on, so each claim is queued once. A duplicate
# would be harmless: the worker only starts a claim that is still PRECHECKED.
module "assessment_pipe" {
  source = "./modules/eventbridge_pipe"

  prefix      = local.prefix
  account_id  = local.account_id
  name        = "claims-to-assessment"
  description = "Prechecked claims to the assessment queue"
  filter_pattern = {
    eventName = ["MODIFY"]
    dynamodb  = { NewImage = { status = { S = ["PRECHECKED"] } } }
  }
  claims_stream_arn     = module.dynamodb.claims_table.stream_arn
  target_queue_arn      = module.sqs.assessment.arn
  dead_letter_queue_arn = module.sqs.pipe_dlq.arn
}

module "worker_lambda" {
  source = "./modules/lambda/worker"

  prefix               = local.prefix
  package              = local.packages["worker"]
  timeout_seconds      = var.worker_timeout_seconds
  log_retention_days   = var.log_retention_days
  max_concurrency      = var.worker_max_concurrency
  claims_table         = module.dynamodb.claims_table
  assessment_queue_arn = module.sqs.assessment.arn
}

# The modules were renamed after first apply. These blocks tell Terraform the
# resources moved address, so it renames them in state instead of recreating them.
moved {
  from = module.storage
  to   = module.s3
}

moved {
  from = module.database
  to   = module.dynamodb
}

moved {
  from = module.queues
  to   = module.sqs
}

moved {
  from = module.claims_pipe
  to   = module.eventbridge_pipe
}

moved {
  from = module.eventbridge_pipe
  to   = module.assessment_pipe
}

moved {
  from = module.intake
  to   = module.intake_lambda
}

moved {
  from = module.worker
  to   = module.worker_lambda
}
