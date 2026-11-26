# Root module: wires the parts of the intake architecture together.
# Each module owns its resources and the IAM role that goes with them.

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  prefix     = "${var.project}-${var.env}"

  # Both Lambdas ship from one zip of src/app; each has its own handler.
  package = {
    path = data.archive_file.app.output_path
    hash = data.archive_file.app.output_base64sha256
  }
}

data "archive_file" "app" {
  type        = "zip"
  source_dir  = "${path.module}/../app"
  output_path = "${path.module}/.build/app.zip"
  excludes    = ["__pycache__", "claims/__pycache__"]
}

module "storage" {
  source = "./modules/storage"

  prefix                  = local.prefix
  account_id              = local.account_id
  inbox_retention_days    = var.inbox_retention_days
  evidence_lock_mode      = var.evidence_lock_mode
  evidence_retention_days = var.evidence_retention_days
}

module "database" {
  source = "./modules/database"

  prefix              = local.prefix
  deletion_protection = var.deletion_protection
}

module "queues" {
  source = "./modules/queues"

  prefix                                = local.prefix
  assessment_visibility_timeout_seconds = var.worker_timeout_seconds * 6
  assessment_max_receive_count          = var.assessment_max_receive_count
}

module "intake" {
  source = "./modules/intake"

  prefix             = local.prefix
  account_id         = local.account_id
  package            = local.package
  timeout_seconds    = var.intake_timeout_seconds
  log_retention_days = var.log_retention_days
  inbox_bucket       = module.storage.inbox_bucket
  evidence_bucket    = module.storage.evidence_bucket
  claims_table       = module.database.claims_table
  policies_table     = module.database.policies_table
  intake_log_table   = module.database.intake_log_table
  failure_queue_arn  = module.queues.intake_failures.arn
}

module "claims_pipe" {
  source = "./modules/claims_pipe"

  prefix                = local.prefix
  account_id            = local.account_id
  claims_stream_arn     = module.database.claims_table.stream_arn
  target_queue_arn      = module.queues.assessment.arn
  dead_letter_queue_arn = module.queues.pipe_dlq.arn
}

module "worker" {
  source = "./modules/worker"

  prefix               = local.prefix
  package              = local.package
  timeout_seconds      = var.worker_timeout_seconds
  log_retention_days   = var.log_retention_days
  max_concurrency      = var.worker_max_concurrency
  claims_table         = module.database.claims_table
  assessment_queue_arn = module.queues.assessment.arn
}
