variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
}

variable "account_id" {
  description = "AWS account id, appended to bucket names to keep them globally unique."
  type        = string
}

variable "inbox_retention_days" {
  description = "Days before files dropped in the inbox expire."
  type        = number
}

variable "evidence_lock_mode" {
  description = "Object Lock mode for evidence: GOVERNANCE or COMPLIANCE."
  type        = string
}

variable "evidence_retention_days" {
  description = "Default Object Lock retention for evidence objects."
  type        = number
}
