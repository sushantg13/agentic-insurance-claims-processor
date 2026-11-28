# Claim changes on the stream that match the filter become messages on the
# target queue. A queue only hears about a claim after its item is safely in
# DynamoDB, so no code has to write the item and send a message as two steps.
resource "aws_pipes_pipe" "this" {
  name          = "${var.prefix}-${var.name}"
  description   = var.description
  role_arn      = aws_iam_role.this.arn
  source        = var.claims_stream_arn
  target        = var.target_queue_arn
  desired_state = "RUNNING"

  source_parameters {
    dynamodb_stream_parameters {
      starting_position      = "LATEST"
      batch_size             = 1
      maximum_retry_attempts = 3
      # Set explicitly: the provider otherwise sends 0, which AWS rejects on update.
      # 24 hours matches how long the stream itself keeps records.
      maximum_record_age_in_seconds = 86400

      dead_letter_config {
        arn = var.dead_letter_queue_arn
      }
    }

    filter_criteria {
      filter {
        pattern = jsonencode(var.filter_pattern)
      }
    }
  }

  target_parameters {
    input_template = "{\"claim_id\": \"<$.dynamodb.Keys.claim_id.S>\"}"
  }

  depends_on = [aws_iam_role_policy.this]
}

# --- Permissions: every statement names its resources ---

resource "aws_iam_role" "this" {
  name               = "${var.prefix}-${var.name}-pipe"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["pipes.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "${var.name}-pipe"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid = "ReadClaimsStream"
    actions = [
      "dynamodb:DescribeStream",
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:ListStreams",
    ]
    resources = [var.claims_stream_arn]
  }

  statement {
    sid       = "SendToQueues"
    actions   = ["sqs:SendMessage"]
    resources = [var.target_queue_arn, var.dead_letter_queue_arn]
  }
}
