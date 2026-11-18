module "infra" {
  source = "../../../"

  env                       = var.env
  project                   = var.project
  region                    = var.region
  ingestion_lambda_zip_path = var.ingestion_lambda_zip_path
  coverage_lambda_zip_path  = var.coverage_lambda_zip_path
}