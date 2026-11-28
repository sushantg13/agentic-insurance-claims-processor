# One item per lodged claim. Its stream feeds status changes to the pipes,
# which move each claim to its next queue.
resource "aws_dynamodb_table" "claims" {
  name                        = "${var.prefix}-claims"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "claim_id"
  stream_enabled              = true
  stream_view_type            = "NEW_IMAGE"
  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "claim_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# Policy register: the stand-in for Claurich's policy system, seeded from a file.
resource "aws_dynamodb_table" "policies" {
  name                        = "${var.prefix}-policies"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "policy_id"
  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "policy_id"
    type = "S"
  }
}

# Every intake decision, keyed by the inbox object and S3 event sequencer:
# accepted, duplicate, conflict or rejected, with reasons.
resource "aws_dynamodb_table" "intake_log" {
  name                        = "${var.prefix}-intake-log"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "intake_id"
  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "intake_id"
    type = "S"
  }
}
