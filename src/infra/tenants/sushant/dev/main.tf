module "infra" {
  source = "../../../"

  project = var.project
  env     = var.env
  region  = var.region
}
