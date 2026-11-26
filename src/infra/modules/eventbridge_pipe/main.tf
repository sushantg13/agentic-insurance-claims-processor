# New claim items on the stream become messages on the assessment queue.
# The queue only hears about a claim after its item is safely in DynamoDB.
resource "aws_pipes_pipe" "this" {
  name          = "${var.prefix}-claims-to-assessment"
  role_arn      = aws_iam_role.this.arn
  source        = var.claims_stream_arn
  target        = var.target_queue_arn
  desired_state = "RUNNING"

  source_parameters {
    dynamodb_stream_parameters {
      starting_position      = "LATEST"
      batch_size             = 1
      maximum_retry_attempts = 3

      dead_letter_config {
        arn = var.dead_letter_queue_arn
      }
    }

    filter_criteria {
      filter {
        pattern = jsonencode({
          eventName = ["INSERT"]
          dynamodb = {
            NewImage = {
              status = { S = ["RECEIVED"] }
            }
          }
        })
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
  name               = "${var.prefix}-claims-pipe"
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
  name   = "claims-pipe"
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
