resource "aws_lambda_function" "ingestion" {
  function_name    = "${var.project}-${var.env}-ingestion"
  role             = var.ingestion_lambda_role_arn
  handler          = "main.handler"
  runtime          = "python3.12"
  timeout          = 300
  filename         = var.ingestion_lambda_zip_path
  source_code_hash = filebase64sha256(var.ingestion_lambda_zip_path)

  environment {
    variables = {
      BUCKET_NAME = var.bucket_name
    }
  }
}

resource "aws_lambda_function" "coverage" {
  function_name    = "${var.project}-${var.env}-coverage"
  role             = var.coverage_lambda_role_arn
  handler          = "main.handler"
  runtime          = "python3.12"
  timeout          = 60
  filename         = var.coverage_lambda_zip_path
  source_code_hash = filebase64sha256(var.coverage_lambda_zip_path)

  environment {
    variables = {
      BUCKET_NAME = var.bucket_name
    }
  }
}
