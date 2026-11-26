# Intake: an upload to the inbox triggers this function, which checks the claim,
# stores it as evidence and lodges it in the claims table.

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.prefix}-intake"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.prefix}-intake"
  role             = aws_iam_role.this.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "intake.handler.handler"
  filename         = var.package.path
  source_code_hash = var.package.hash
  timeout          = var.timeout_seconds
  memory_size      = 256

  environment {
    variables = {
      EVIDENCE_BUCKET  = var.evidence_bucket.id
      CLAIMS_TABLE     = var.claims_table.name
      POLICIES_TABLE   = var.policies_table.name
      INTAKE_LOG_TABLE = var.intake_log_table.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

# --- Trigger: S3 calls the function for every .json upload to the inbox ---

resource "aws_lambda_permission" "inbox" {
  statement_id   = "AllowInboxBucketInvoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.this.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = var.inbox_bucket.arn
  source_account = var.account_id
}

resource "aws_s3_bucket_notification" "inbox" {
  bucket = var.inbox_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.this.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.inbox]
}

# S3 invokes asynchronously. After two retries, the failed event goes to a queue.
resource "aws_lambda_function_event_invoke_config" "this" {
  function_name                = aws_lambda_function.this.function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600

  destination_config {
    on_failure {
      destination = var.failure_queue_arn
    }
  }
}

# --- Permissions: every statement names its resources ---

resource "aws_iam_role" "this" {
  name               = "${var.prefix}-intake"
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
  name   = "intake"
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
    sid       = "ReadInbox"
    actions   = ["s3:GetObject"]
    resources = ["${var.inbox_bucket.arn}/*"]
  }

  statement {
    sid       = "WriteEvidence"
    actions   = ["s3:PutObject"]
    resources = ["${var.evidence_bucket.arn}/claims/*"]
  }

  statement {
    sid       = "LodgeClaims"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [var.claims_table.arn]
  }

  statement {
    sid       = "ReadPolicies"
    actions   = ["dynamodb:GetItem"]
    resources = [var.policies_table.arn]
  }

  statement {
    sid       = "RecordIntakeDecisions"
    actions   = ["dynamodb:PutItem"]
    resources = [var.intake_log_table.arn]
  }

  statement {
    sid       = "SendFailedEvents"
    actions   = ["sqs:SendMessage"]
    resources = [var.failure_queue_arn]
  }
}
