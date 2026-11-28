# Newly lodged claims waiting for the precheck. Messages carry only the claim id.
resource "aws_sqs_queue" "precheck" {
  name                       = "${var.prefix}-precheck"
  visibility_timeout_seconds = var.precheck_visibility_timeout_seconds
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.precheck_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue" "precheck_dlq" {
  name                      = "${var.prefix}-precheck-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# Prechecked claims waiting for assessment. Messages carry only the claim id.
resource "aws_sqs_queue" "assessment" {
  name                       = "${var.prefix}-assessment"
  visibility_timeout_seconds = var.assessment_visibility_timeout_seconds
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.assessment_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue" "assessment_dlq" {
  name                      = "${var.prefix}-assessment-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# Intake invocations that still fail after Lambda's async retries.
resource "aws_sqs_queue" "intake_failures" {
  name                      = "${var.prefix}-intake-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# Stream records either pipe could not deliver to its queue.
resource "aws_sqs_queue" "pipe_dlq" {
  name                      = "${var.prefix}-pipe-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
