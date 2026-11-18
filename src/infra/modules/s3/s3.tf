resource "aws_s3_bucket" "claims" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "claims" {
  bucket = aws_s3_bucket.claims.id

  versioning_configuration {
    status = "Enabled"
  }
}
