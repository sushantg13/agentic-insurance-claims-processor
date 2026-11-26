output "assessment" {
  value = { arn = aws_sqs_queue.assessment.arn, url = aws_sqs_queue.assessment.url }
}

output "assessment_dlq" {
  value = { arn = aws_sqs_queue.assessment_dlq.arn, url = aws_sqs_queue.assessment_dlq.url }
}

output "intake_failures" {
  value = { arn = aws_sqs_queue.intake_failures.arn, url = aws_sqs_queue.intake_failures.url }
}

output "pipe_dlq" {
  value = { arn = aws_sqs_queue.pipe_dlq.arn, url = aws_sqs_queue.pipe_dlq.url }
}
