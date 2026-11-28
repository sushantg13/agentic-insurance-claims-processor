variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
}

variable "package" {
  description = "This Lambda's zip: its local path and base64 SHA-256."
  type        = object({ path = string, hash = string })
}

variable "timeout_seconds" {
  type = number
}

variable "log_retention_days" {
  type = number
}

variable "max_concurrency" {
  description = "Most precheck instances SQS may run at once. Minimum 2."
  type        = number
}

variable "evidence_bucket" {
  description = "Write-once bucket holding the claim copy that the checks read."
  type        = object({ id = string, arn = string })
}

variable "claims_table" {
  type = object({ name = string, arn = string })
}

variable "policies_table" {
  type = object({ name = string, arn = string })
}

variable "precheck_queue_arn" {
  description = "Queue of newly lodged claim ids."
  type        = string
}
