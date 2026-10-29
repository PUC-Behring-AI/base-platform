output "ecr_repository_urls" {
  description = "Repository URL per entry of ecr_repositories."
  value       = { for k, repo in aws_ecr_repository.this : k => repo.repository_url }
}

output "backups_bucket" {
  description = "Name of the versioned, encrypted, private backups bucket."
  value       = aws_s3_bucket.backups.bucket
}
