variable "name" {
  description = "Cluster name, and prefix of the IAM roles this stack creates."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}[a-z0-9]$", var.name))
    error_message = "name must be 3-32 characters of lowercase letters, digits and hyphens."
  }
}

variable "region" {
  description = "AWS region of the cluster."
  type        = string
}

variable "tags" {
  description = "Tags on every AWS resource, e.g. {project = \"<name>\"}. The caller owns them."
  type        = map(string)
  default     = {}
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version."
  type        = string
  default     = "1.36"
}

variable "vpc_id" {
  description = "VPC of the cluster. Null means the region's default VPC."
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Public subnets of the cluster and its load balancers. Empty means the default VPC's public subnets outside excluded_zone_ids. Given with vpc_id."
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.subnet_ids) == 0 || var.vpc_id != null
    error_message = "subnet_ids was given without vpc_id: give both, or neither for the default VPC."
  }
}

variable "excluded_zone_ids" {
  description = "Availability Zone ids where EKS refuses a control plane (EKS network requirements page). Only used to pick the default VPC's subnets."
  type        = list(string)
  default     = ["use1-az3", "usw1-az2", "cac1-az3"]
}

variable "cpu_pool_cpu_limit" {
  description = "Most vCPUs the arm64 CPU node pool may run at once."
  type        = number
  default     = 32
}

variable "gpu_node_pool" {
  description = "Create the amd64 GPU node pool (tainted nvidia.com/gpu)."
  type        = bool
  default     = false
}

variable "gpu_instance_types" {
  description = "Instance types the GPU node pool may launch, on demand."
  type        = list(string)
  default     = ["g6.xlarge"]
}

variable "gpu_pool_cpu_limit" {
  description = "Most vCPUs the GPU node pool may run at once (a g6.xlarge has 4)."
  type        = number
  default     = 8
}

variable "eso_namespace" {
  description = "Namespace of External Secrets Operator's ServiceAccount."
  type        = string
  default     = "external-secrets"
}

variable "eso_service_account" {
  description = "External Secrets Operator's ServiceAccount, the one its controller runs as."
  type        = string
  default     = "external-secrets"
}

variable "secrets_prefix" {
  description = "Secrets Manager name prefix External Secrets Operator may read: the role allows GetSecretValue on secret:<prefix>* only."
  type        = string

  validation {
    condition     = length(trimspace(var.secrets_prefix)) > 0 && !strcontains(var.secrets_prefix, "*")
    error_message = "secrets_prefix must be a non-empty name prefix without '*': an empty one would let the operator read every secret in the account."
  }
}
