variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
}

variable "account_id" {
  description = "AWS account id, used to scope the S3 invoke permission."
  type        = string
}

variable "package" {
  description = "The Lambda zip built from src/app: its local path and base64 SHA-256."
  type        = object({ path = string, hash = string })
}

variable "timeout_seconds" {
  type = number
}

variable "log_retention_days" {
  type = number
}

variable "inbox_bucket" {
  description = "Bucket whose .json uploads trigger intake."
  type        = object({ id = string, arn = string })
}

variable "evidence_bucket" {
  description = "Write-once bucket that receives accepted claims."
  type        = object({ id = string, arn = string })
}

variable "claims_table" {
  type = object({ name = string, arn = string })
}

variable "policies_table" {
  type = object({ name = string, arn = string })
}

variable "intake_log_table" {
  type = object({ name = string, arn = string })
}

variable "failure_queue_arn" {
  description = "Queue that receives intake events still failing after Lambda's retries."
  type        = string
}
