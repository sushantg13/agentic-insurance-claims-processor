variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
}

variable "deletion_protection" {
  description = "Turn on DynamoDB deletion protection."
  type        = bool
}
