data "aws_caller_identity" "current" {}

module "iam" {
  source = "./modules/iam"
}

module "s3" {
  source = "./modules/s3"

  bucket_name = "${var.project}-${var.env}-${data.aws_caller_identity.current.account_id}"
}

module "lambda" {
  source = "./modules/lambda"

  project                   = var.project
  env                       = var.env
  bucket_name               = module.s3.bucket_name
  ingestion_lambda_role_arn = module.iam.ingestion_lambda_role_arn
  coverage_lambda_role_arn  = module.iam.coverage_lambda_role_arn
  ingestion_lambda_zip_path = var.ingestion_lambda_zip_path
  coverage_lambda_zip_path  = var.coverage_lambda_zip_path
}

module "step_functions" {
  source = "./modules/step_functions"

  project  = var.project
  env      = var.env
  role_arn = module.iam.step_functions_role_arn

  definition = templatefile("${path.module}/../step_functions/claims_workflow.asl.json", {
    ingestion_lambda_arn = module.lambda.ingestion_lambda_arn
    coverage_lambda_arn  = module.lambda.coverage_lambda_arn
  })
}
