output "inbox_bucket" {
  description = "Drop claim folders here."
  value       = module.s3.inbox_bucket.id
}

output "evidence_bucket" {
  description = "Write-once copies of accepted submissions and attachments."
  value       = module.s3.evidence_bucket.id
}

output "claims_table" {
  value = module.dynamodb.claims_table.name
}

output "policies_table" {
  value = module.dynamodb.policies_table.name
}

output "intake_log_table" {
  value = module.dynamodb.intake_log_table.name
}

output "precheck_queue_url" {
  value = module.sqs.precheck.url
}

output "assessment_queue_url" {
  value = module.sqs.assessment.url
}

output "dead_letter_queue_urls" {
  value = {
    precheck        = module.sqs.precheck_dlq.url
    assessment      = module.sqs.assessment_dlq.url
    intake_failures = module.sqs.intake_failures.url
    pipe            = module.sqs.pipe_dlq.url
  }
}

output "log_groups" {
  value = {
    intake   = module.intake_lambda.log_group
    precheck = module.precheck_lambda.log_group
    worker   = module.worker_lambda.log_group
  }
}
