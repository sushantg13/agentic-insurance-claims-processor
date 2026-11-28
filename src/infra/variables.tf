variable "project" {
  description = "Project name, used as the prefix for every resource name."
  type        = string
}

variable "env" {
  description = "Environment name, for example dev."
  type        = string
}

variable "region" {
  description = "AWS region. Set explicitly; ap-southeast-2 keeps data in Australia."
  type        = string
}

variable "evidence_lock_mode" {
  description = "Object Lock mode for the evidence bucket. GOVERNANCE can be bypassed by an admin; COMPLIANCE cannot be bypassed by anyone, including root."
  type        = string
  default     = "GOVERNANCE"

  validation {
    condition     = contains(["GOVERNANCE", "COMPLIANCE"], var.evidence_lock_mode)
    error_message = "evidence_lock_mode must be GOVERNANCE or COMPLIANCE."
  }
}

variable "evidence_retention_days" {
  description = "Default Object Lock retention for evidence objects. Keep this short in dev: the bucket cannot be deleted while objects are locked."
  type        = number
  default     = 1
}

variable "inbox_retention_days" {
  description = "Days before files dropped in the inbox bucket expire. The evidence bucket holds the permanent copy."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the Lambda functions."
  type        = number
  default     = 30
}

variable "intake_timeout_seconds" {
  description = "Timeout for the intake Lambda."
  type        = number
  default     = 30
}

variable "precheck_timeout_seconds" {
  description = "Timeout for the precheck Lambda. The precheck queue's visibility timeout is six times this."
  type        = number
  default     = 30
}

variable "precheck_max_concurrency" {
  description = "Most precheck Lambdas that SQS may run at once. It makes no model calls, so this can be higher than the worker's. Minimum 2."
  type        = number
  default     = 5
}

variable "worker_timeout_seconds" {
  description = "Timeout for the assessment worker Lambda. The queue's visibility timeout is six times this."
  type        = number
  default     = 60
}

variable "worker_max_concurrency" {
  description = "Most worker Lambdas that SQS may run at once. Size this to the model API rate limit once the AI pipeline exists. Minimum 2."
  type        = number
  default     = 2
}

variable "max_receive_count" {
  description = "Delivery attempts before a claim message moves to its queue's dead-letter queue."
  type        = number
  default     = 3
}

variable "deletion_protection" {
  description = "Turn on DynamoDB deletion protection. Leave off in dev so the stack can be torn down."
  type        = bool
  default     = false
}
