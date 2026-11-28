variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
}

variable "name" {
  description = "Short name for this pipe, such as claims-to-precheck."
  type        = string
}

variable "description" {
  type = string
}

variable "filter_pattern" {
  description = "EventBridge pattern a stream record must match to be sent on."
  type        = any
}

variable "account_id" {
  description = "AWS account id, used to scope who may assume the pipe's role."
  type        = string
}

variable "claims_stream_arn" {
  description = "Stream of the claims table."
  type        = string
}

variable "target_queue_arn" {
  description = "Queue that receives the matching claim ids."
  type        = string
}

variable "dead_letter_queue_arn" {
  description = "Queue for stream records the pipe cannot deliver."
  type        = string
}
