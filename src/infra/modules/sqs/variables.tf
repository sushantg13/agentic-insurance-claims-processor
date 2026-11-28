variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
}

variable "precheck_visibility_timeout_seconds" {
  description = "How long a claim message stays hidden while the precheck processes it. Keep it at least six times the precheck timeout."
  type        = number
}

variable "assessment_visibility_timeout_seconds" {
  description = "How long a claim message stays hidden while a worker processes it. Keep it at least six times the worker timeout."
  type        = number
}

variable "max_receive_count" {
  description = "Delivery attempts before a claim message moves to its queue's dead-letter queue."
  type        = number
}
