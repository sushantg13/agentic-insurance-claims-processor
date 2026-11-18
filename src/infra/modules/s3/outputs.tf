output "bucket_name" {
  value = aws_s3_bucket.claims.id
}

output "bucket_arn" {
  value = aws_s3_bucket.claims.arn
}
