# The managed cluster the base charts run on: EKS Auto Mode, public subnets
# and no NAT gateway, a Graviton (arm64) node pool for every workload, an
# optional amd64 GPU pool, and the few cluster objects the charts assume
# (docs/ADAPTATION.md §10, "The managed cluster"). Applications are never
# installed here: helmfile installs them, as on kind.
#
# The kubectl provider is configured by the caller from this module's
# outputs (README.md, "Providers"); the aws provider too.

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

# ── Network: the default VPC's public subnets unless the caller names some ──

data "aws_vpc" "default" {
  count = var.vpc_id == null ? 1 : 0

  region  = var.region
  default = true
}

data "aws_availability_zones" "eks" {
  count = length(var.subnet_ids) == 0 ? 1 : 0

  region           = var.region
  state            = "available"
  exclude_zone_ids = var.excluded_zone_ids

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

data "aws_subnets" "public" {
  count = length(var.subnet_ids) == 0 ? 1 : 0

  region = var.region

  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }

  filter {
    name   = "availability-zone-id"
    values = data.aws_availability_zones.eks[0].zone_ids
  }
}

locals {
  vpc_id     = var.vpc_id != null ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.public[0].ids

  storage_class = "base-rwo"
  gateway_class = "base-alb"
}

# Auto Mode places an internet-facing load balancer only in a subnet tagged
# for it. The tag goes away with this stack.
resource "aws_ec2_tag" "elb" {
  for_each = toset(local.subnet_ids)

  region      = var.region
  resource_id = each.value
  key         = "kubernetes.io/role/elb"
  value       = "1"
}

# ── The cluster ──────────────────────────────────────────────────────────────

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "21.29.0"

  region             = var.region
  name               = var.name
  kubernetes_version = var.kubernetes_version

  # The operator's kubectl and helmfile reach the API from outside the VPC.
  endpoint_public_access                   = true
  enable_cluster_creator_admin_permissions = true

  # Only the built-in `system` pool (tainted CriticalAddonsOnly, both
  # architectures): it brings the `default` NodeClass the pools below use.
  # The built-in general-purpose pool is amd64 only, and an arm64 image
  # would fail there with `exec format error`.
  compute_config = {
    enabled    = true
    node_pools = ["system"]
  }

  vpc_id     = local.vpc_id
  subnet_ids = local.subnet_ids

  tags = var.tags
}

# The Gateway API, with AWS owning the CRDs (at Gateway API v1). The aws
# provider has no argument for it yet (checked on 6.71.0), so the EKS API is
# called once per cluster; needs aws-cli 2.38.6 or newer. Temporary: replace
# with the provider's argument when it has one.
resource "terraform_data" "gateway_api" {
  triggers_replace = [module.eks.cluster_arn]

  provisioner "local-exec" {
    command = "${path.module}/enable-gateway-api.sh '${module.eks.cluster_name}' '${var.region}'"
  }
}

# ── Cluster objects the charts assume ────────────────────────────────────────

# docs/ADAPTATION.md §10, rule 5: the charts name `base-rwo`; Auto Mode
# creates no StorageClass of its own.
resource "kubectl_manifest" "storage_class" {
  yaml_body = yamlencode({
    apiVersion        = "storage.k8s.io/v1"
    kind              = "StorageClass"
    metadata          = { name = local.storage_class }
    provisioner       = "ebs.csi.eks.amazonaws.com"
    volumeBindingMode = "WaitForFirstConsumer"
    reclaimPolicy     = "Delete"
    parameters        = { type = "gp3", encrypted = "true" }
    allowedTopologies = [{
      matchLabelExpressions = [{ key = "eks.amazonaws.com/compute-type", values = ["auto"] }]
    }]
  })

  depends_on = [module.eks]
}

# Auto Mode enforces NetworkPolicy only once this is set (rule 3).
# Server-side apply, so it works whether or not the ConfigMap exists.
resource "kubectl_manifest" "network_policy" {
  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "ConfigMap"
    metadata   = { name = "amazon-vpc-cni", namespace = "kube-system" }
    data       = { "enable-network-policy-controller" = "true" }
  })
  server_side_apply = true
  force_conflicts   = true

  depends_on = [module.eks]
}

resource "kubectl_manifest" "gateway_class" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "GatewayClass"
    metadata   = { name = local.gateway_class }
    spec       = { controllerName = "eks.amazonaws.com/gateway-alb" }
  })

  depends_on = [terraform_data.gateway_api]
}

# Every workload lands here: the only pool without a taint.
resource "kubectl_manifest" "cpu_pool" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "arm64" }
    spec = {
      template = {
        spec = {
          nodeClassRef = { group = "eks.amazonaws.com", kind = "NodeClass", name = "default" }
          requirements = [
            { key = "kubernetes.io/arch", operator = "In", values = ["arm64"] },
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["on-demand"] },
            { key = "eks.amazonaws.com/instance-category", operator = "In", values = ["c", "m", "r"] },
            { key = "eks.amazonaws.com/instance-generation", operator = "Gt", values = ["5"] },
          ]
        }
      }
      limits     = { cpu = tostring(var.cpu_pool_cpu_limit) }
      disruption = { consolidationPolicy = "WhenEmptyOrUnderutilized", consolidateAfter = "1m" }
    }
  })

  depends_on = [module.eks]
}

# Only pods that tolerate nvidia.com/gpu land here (inference's GPU workers).
resource "kubectl_manifest" "gpu_pool" {
  count = var.gpu_node_pool ? 1 : 0

  yaml_body = yamlencode({
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "gpu" }
    spec = {
      template = {
        spec = {
          nodeClassRef = { group = "eks.amazonaws.com", kind = "NodeClass", name = "default" }
          requirements = [
            { key = "kubernetes.io/arch", operator = "In", values = ["amd64"] },
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["on-demand"] },
            { key = "node.kubernetes.io/instance-type", operator = "In", values = var.gpu_instance_types },
          ]
          taints = [{ key = "nvidia.com/gpu", effect = "NoSchedule" }]
        }
      }
      limits     = { cpu = tostring(var.gpu_pool_cpu_limit) }
      disruption = { consolidationPolicy = "WhenEmpty", consolidateAfter = "10m" }
    }
  })

  depends_on = [module.eks]
}

# ── External Secrets Operator's identity ─────────────────────────────────────
# EKS Pod Identity: the role is bound to (namespace, ServiceAccount) in the
# EKS API, so the operator's chart carries no AWS annotation (rule 8). It
# reads secrets under secrets_prefix and nothing else.

data "aws_iam_policy_document" "eso_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "eso_read" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["arn:${data.aws_partition.current.partition}:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:${var.secrets_prefix}*"]
  }
}

resource "aws_iam_role" "eso" {
  name               = "${var.name}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.eso_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "eso" {
  name   = "read-secrets-under-prefix"
  role   = aws_iam_role.eso.id
  policy = data.aws_iam_policy_document.eso_read.json
}

resource "aws_eks_pod_identity_association" "eso" {
  region          = var.region
  cluster_name    = module.eks.cluster_name
  namespace       = var.eso_namespace
  service_account = var.eso_service_account
  role_arn        = aws_iam_role.eso.arn
  tags            = var.tags
}
