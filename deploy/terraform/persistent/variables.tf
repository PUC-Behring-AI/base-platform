variable "name" {
  description = "Prefix of every resource this stack creates: the deployment's name."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}[a-z0-9]$", var.name))
    error_message = "name must be 3-32 characters of lowercase letters, digits and hyphens: it prefixes an S3 bucket and ECR repositories."
  }
}

variable "region" {
  description = "AWS region of the ECR repositories and the backups bucket."
  type        = string
}

variable "tags" {
  description = "Tags on every resource, e.g. {project = \"<name>\"}. The caller owns them."
  type        = map(string)
  default     = {}
}

variable "ecr_repositories" {
  description = "ECR repositories to create, one per image, each named <name>/<entry>."
  type        = list(string)
  default     = []
}

variable "budget_monthly_usd" {
  description = "Monthly cost budget for the whole account, in USD. Mails at 80% actual and 100% forecast."
  type        = number
}

variable "budget_daily_usd" {
  description = "Daily cost budget for the whole account, in USD. Mails at 100% actual (AWS Budgets has no forecast for a daily budget)."
  type        = number
}

variable "budget_emails" {
  description = "Addresses the budget alerts go to."
  type        = list(string)

  validation {
    condition     = length(var.budget_emails) > 0
    error_message = "budget_emails is empty: a budget nobody hears from protects nothing."
  }
}

variable "ecr_untagged_expire_days" {
  description = "Days after which an untagged image (a layer left by a re-pushed tag) is deleted."
  type        = number
  default     = 7
}

variable "ecr_tagged_keep" {
  description = "Tagged images kept per repository; older ones are deleted."
  type        = number
  default     = 20
}
