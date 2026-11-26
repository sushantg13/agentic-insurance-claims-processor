output "inbox_bucket" {
  value = module.infra.inbox_bucket
}

output "evidence_bucket" {
  value = module.infra.evidence_bucket
}

output "claims_table" {
  value = module.infra.claims_table
}

output "policies_table" {
  value = module.infra.policies_table
}

output "intake_log_table" {
  value = module.infra.intake_log_table
}

output "assessment_queue_url" {
  value = module.infra.assessment_queue_url
}

output "dead_letter_queue_urls" {
  value = module.infra.dead_letter_queue_urls
}

output "log_groups" {
  value = module.infra.log_groups
}
