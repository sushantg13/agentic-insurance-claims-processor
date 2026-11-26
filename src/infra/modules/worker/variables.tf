variable "prefix" {
  description = "Name prefix for every resource."
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

variable "max_concurrency" {
  description = "Most worker instances SQS may run at once. Minimum 2."
  type        = number
}

variable "claims_table" {
  type = object({ name = string, arn = string })
}

variable "assessment_queue_arn" {
  description = "Queue of claim ids waiting for assessment."
  type        = string
}
