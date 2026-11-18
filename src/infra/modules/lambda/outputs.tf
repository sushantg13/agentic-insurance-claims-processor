output "ingestion_lambda_arn" {
  value = aws_lambda_function.ingestion.arn
}

output "ingestion_lambda_name" {
  value = aws_lambda_function.ingestion.function_name
}

output "coverage_lambda_arn" {
  value = aws_lambda_function.coverage.arn
}

output "coverage_lambda_name" {
  value = aws_lambda_function.coverage.function_name
}
