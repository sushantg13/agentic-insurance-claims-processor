output "claims_table" {
  value = {
    name       = aws_dynamodb_table.claims.name
    arn        = aws_dynamodb_table.claims.arn
    stream_arn = aws_dynamodb_table.claims.stream_arn
  }
}

output "policies_table" {
  value = { name = aws_dynamodb_table.policies.name, arn = aws_dynamodb_table.policies.arn }
}

output "intake_log_table" {
  value = { name = aws_dynamodb_table.intake_log.name, arn = aws_dynamodb_table.intake_log.arn }
}
