# What outlives every cluster: the images, the backups and the alarms on
# spend. This stack is created once and never destroyed; teardown destroys
# only ../cluster. prevent_destroy makes a `terraform destroy` here fail
# instead of deleting the images and the backups with it.

data "aws_caller_identity" "current" {}

locals {
  # The account id makes the bucket name unique without a random suffix,
  # so the same root always computes the same name.
  backups_bucket = "${var.name}-backups-${data.aws_caller_identity.current.account_id}"
}

resource "aws_ecr_repository" "this" {
  for_each = toset(var.ecr_repositories)

  region               = var.region
  name                 = "${var.name}/${each.value}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

# Untagged images are what a re-pushed tag leaves behind; tagged ones pile
# up with every release. Both cost storage nobody reads.
resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  region     = var.region
  repository = each.value.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_expire_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the newest tagged images"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = var.ecr_tagged_keep
        }
        action = { type = "expire" }
      },
    ]
  })
}

resource "aws_s3_bucket" "backups" {
  region = var.region
  bucket = local.backups_bucket
  tags   = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  region = var.region
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Versioning keeps a deleted or overwritten backup for a month, not forever.
resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  region = var.region
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.backups]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  region = var.region
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  region = var.region
  bucket = aws_s3_bucket.backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backups" {
  region = var.region
  bucket = aws_s3_bucket.backups.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Account-wide on purpose: a budget filtered by a cost allocation tag reads
# zero until someone with billing access activates the tag, and a budget that
# reads zero is silent exactly when it should speak.
resource "aws_budgets_budget" "monthly" {
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_monthly_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  tags         = var.tags

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_emails
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_emails
  }
}

resource "aws_budgets_budget" "daily" {
  name         = "${var.name}-daily"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_daily_usd)
  limit_unit   = "USD"
  time_unit    = "DAILY"
  tags         = var.tags

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_emails
  }
}
