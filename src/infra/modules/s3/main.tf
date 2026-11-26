# Inbox: claims are dropped here as folders (claim JSON plus docs/). Not locked,
# so junk or rejected uploads can expire. Intake copies accepted claims to evidence.
resource "aws_s3_bucket" "inbox" {
  bucket        = "${var.prefix}-inbox-${var.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "inbox" {
  bucket                  = aws_s3_bucket.inbox.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "inbox" {
  bucket = aws_s3_bucket.inbox.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "inbox" {
  bucket = aws_s3_bucket.inbox.id

  rule {
    id     = "expire-inbox-uploads"
    status = "Enabled"

    filter {}

    expiration {
      days = var.inbox_retention_days
    }
  }
}

resource "aws_s3_bucket_policy" "inbox" {
  bucket     = aws_s3_bucket.inbox.id
  policy     = data.aws_iam_policy_document.tls_only["inbox"].json
  depends_on = [aws_s3_bucket_public_access_block.inbox]
}

# Evidence: the submission and attachments exactly as received, write-once.
# Object Lock can only be switched on when the bucket is created.
resource "aws_s3_bucket" "evidence" {
  bucket              = "${var.prefix}-evidence-${var.account_id}"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    default_retention {
      mode = var.evidence_lock_mode
      days = var.evidence_retention_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.evidence]
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "evidence" {
  bucket     = aws_s3_bucket.evidence.id
  policy     = data.aws_iam_policy_document.tls_only["evidence"].json
  depends_on = [aws_s3_bucket_public_access_block.evidence]
}

# Both buckets refuse any request that does not use TLS.
data "aws_iam_policy_document" "tls_only" {
  for_each = {
    inbox    = aws_s3_bucket.inbox.arn
    evidence = aws_s3_bucket.evidence.arn
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [each.value, "${each.value}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
