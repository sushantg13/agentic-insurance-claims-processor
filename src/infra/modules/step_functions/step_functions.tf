resource "aws_sfn_state_machine" "this" {
  name       = "${var.project}-${var.env}"
  role_arn   = var.role_arn
  definition = var.definition
}
