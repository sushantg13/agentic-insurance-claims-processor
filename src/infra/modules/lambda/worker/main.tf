# Worker: takes prechecked claim ids off the assessment queue. For now it only marks the
# claim as being assessed; the AI pipeline replaces its handler later.

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.prefix}-worker"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.prefix}-worker"
  role             = aws_iam_role.this.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "worker.handler.handler"
  filename         = var.package.path
  source_code_hash = var.package.hash
  timeout          = var.timeout_seconds
  memory_size      = 256

  environment {
    variables = {
      CLAIMS_TABLE = var.claims_table.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

# --- Trigger: SQS delivers one claim id per invocation ---

resource "aws_lambda_event_source_mapping" "assessment" {
  event_source_arn        = var.assessment_queue_arn
  function_name           = aws_lambda_function.this.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.max_concurrency
  }
}

# --- Permissions: every statement names its resources ---

resource "aws_iam_role" "this" {
  name               = "${var.prefix}-worker"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "worker"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }

  statement {
    sid = "ConsumeAssessmentQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.assessment_queue_arn]
  }

  statement {
    sid       = "UpdateClaimStatus"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [var.claims_table.arn]
  }
}
