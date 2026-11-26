output "inbox_bucket" {
  value = { id = aws_s3_bucket.inbox.id, arn = aws_s3_bucket.inbox.arn }
}

output "evidence_bucket" {
  value = { id = aws_s3_bucket.evidence.id, arn = aws_s3_bucket.evidence.arn }
}
