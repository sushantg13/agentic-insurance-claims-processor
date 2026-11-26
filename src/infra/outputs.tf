output "inbox_bucket" {
  description = "Drop claim folders here."
  value       = module.storage.inbox_bucket.id
}

output "evidence_bucket" {
  description = "Write-once copies of accepted submissions and attachments."
  value       = module.storage.evidence_bucket.id
}

output "claims_table" {
  value = module.database.claims_table.name
}

output "policies_table" {
  value = module.database.policies_table.name
}

output "intake_log_table" {
  value = module.database.intake_log_table.name
}

output "assessment_queue_url" {
  value = module.queues.assessment.url
}

output "dead_letter_queue_urls" {
  value = {
    assessment      = module.queues.assessment_dlq.url
    intake_failures = module.queues.intake_failures.url
    pipe            = module.queues.pipe_dlq.url
  }
}

output "log_groups" {
  value = {
    intake = module.intake.log_group
    worker = module.worker.log_group
  }
}
