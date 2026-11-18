output "ingestion_lambda_role_arn" {
  value = aws_iam_role.ingestion_lambda.arn
}

output "ingestion_lambda_role_name" {
  value = aws_iam_role.ingestion_lambda.name
}

output "coverage_lambda_role_arn" {
  value = aws_iam_role.coverage_lambda.arn
}

output "coverage_lambda_role_name" {
  value = aws_iam_role.coverage_lambda.name
}

output "step_functions_role_arn" {
  value = aws_iam_role.step_functions.arn
}

output "step_functions_role_name" {
  value = aws_iam_role.step_functions.name
}