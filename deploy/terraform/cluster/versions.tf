terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.59, < 7.0"
    }
    # kubectl_manifest applies a manifest without reading the cluster's API
    # at plan time, which kubernetes_manifest needs and a cluster created in
    # the same apply cannot give. README.md, "Providers".
    kubectl = {
      source  = "alekc/kubectl"
      version = ">= 2.4, < 3.0"
    }
  }
}
