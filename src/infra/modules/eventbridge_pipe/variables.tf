variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
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
  description = "Assessment queue that receives new claim ids."
  type        = string
}

variable "dead_letter_queue_arn" {
  description = "Queue for stream records the pipe cannot deliver."
  type        = string
}
