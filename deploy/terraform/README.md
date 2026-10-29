# deploy/terraform — the managed cluster

Two Terraform modules an instance calls from its own roots, one root per
module, so the two have separate state:

| Module | What it creates | Lifetime |
|---|---|---|
| `persistent/` | ECR repositories, the backups bucket (versioned, encrypted, private), a monthly and a daily cost budget | created once, never destroyed (`prevent_destroy` on the repositories and the bucket) |
| `cluster/` | EKS Auto Mode cluster, the arm64 and optional GPU node pools, StorageClass `base-rwo`, GatewayClass `base-alb`, network policy enforcement, External Secrets Operator's Pod Identity role | the stack teardown destroys |

Nothing here installs an application: helmfile installs the charts, on this
cluster as on kind (docs/ADAPTATION.md §10). Nothing here names an account,
a region or an instance either: the caller passes them.

## Interface

`persistent`

| Variable | Type | Default |
|---|---|---|
| `name` | string | — prefix of every resource |
| `region` | string | — |
| `tags` | map(string) | `{}` |
| `ecr_repositories` | list(string) | `[]` — each becomes `<name>/<entry>` |
| `budget_monthly_usd` | number | — mails at 80% actual and 100% forecast |
| `budget_daily_usd` | number | — mails at 100% actual |
| `budget_emails` | list(string) | — must not be empty |

Outputs: `ecr_repository_urls` (map, entry → URL), `backups_bucket`
(`<name>-backups-<account id>`).

The budgets cover the whole account. A budget filtered by a cost allocation
tag reads zero until someone with billing access activates the tag, and then
it stays silent exactly when it should warn.

`cluster`

| Variable | Type | Default |
|---|---|---|
| `name` | string | — cluster name |
| `region` | string | — |
| `tags` | map(string) | `{}` |
| `kubernetes_version` | string | `"1.36"` |
| `vpc_id` | string | `null` → the region's default VPC |
| `subnet_ids` | list(string) | `[]` → the default VPC's public subnets outside `excluded_zone_ids`; give with `vpc_id` |
| `excluded_zone_ids` | list(string) | the zone ids where EKS refuses a control plane |
| `cpu_pool_cpu_limit` | number | `32` |
| `gpu_node_pool` | bool | `false` |
| `gpu_instance_types` | list(string) | `["g6.xlarge"]` |
| `gpu_pool_cpu_limit` | number | `8` |
| `eso_namespace` | string | `"external-secrets"` |
| `eso_service_account` | string | `"external-secrets"` |
| `secrets_prefix` | string | — non-empty, no `*` |

Outputs: `cluster_name`, `cluster_endpoint`,
`cluster_certificate_authority_data`, `oidc_issuer`, `storage_class`
(`base-rwo`), `gateway_class` (`base-alb`), `eso_role_arn`.

## Providers

Neither module configures a provider; the root does. `cluster` needs two:
`hashicorp/aws`, and `alekc/kubectl` pointed at the cluster it creates. The
kubectl provider must load lazily (`lazy_load = true`, from 2.4.0): the
endpoint is unknown until the cluster exists, and without it the first plan
fails with "no configuration has been provided".

```hcl
provider "aws" {
  region = var.region
}

provider "kubectl" {
  host                   = module.cluster.cluster_endpoint
  cluster_ca_certificate = base64decode(module.cluster.cluster_certificate_authority_data)
  load_config_file       = false
  lazy_load              = true
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.cluster.cluster_name, "--region", var.region]
  }
}
```

The machine that applies `cluster` needs `aws` (aws-cli 2.38.6 or newer) on
`PATH`, for the token above and for the Gateway API step below.

## What `cluster` does, and why

- **Auto Mode, built-in `system` pool only.** At least one built-in pool must
  be on for EKS to create the `default` NodeClass the custom pools use. The
  other built-in pool, `general-purpose`, is amd64 only; an arm64 image
  scheduled there fails with `exec format error`. `system` is tainted
  `CriticalAddonsOnly` and takes only cluster add-ons.
- **NodePool `arm64`** (Graviton, on demand, families c/m/r of generation 6
  or newer): the only untainted pool, so every workload lands there.
- **NodePool `gpu`** (when `gpu_node_pool = true`): amd64, on demand,
  `gpu_instance_types`, tainted `nvidia.com/gpu:NoSchedule`. Auto Mode brings
  the NVIDIA driver and device plugin.
- **StorageClass `base-rwo`**: provisioner `ebs.csi.eks.amazonaws.com` (Auto
  Mode's, not the self-managed `ebs.csi.aws.com`), gp3, encrypted,
  `WaitForFirstConsumer`, only on Auto Mode nodes. Auto Mode creates no
  StorageClass of its own. Volumes are not deleted with the cluster: delete
  the PVCs before `terraform destroy`, or the EBS volumes keep billing.
- **Network policy**: ConfigMap `kube-system/amazon-vpc-cni` with
  `enable-network-policy-controller: "true"`. Without it Auto Mode accepts
  every NetworkPolicy and enforces none. Applied server-side, so it works
  whether or not the ConfigMap already exists.
- **Gateway API**: GatewayClass `base-alb`, controller
  `eks.amazonaws.com/gateway-alb` (one ALB per Gateway). The cluster setting
  that turns the Gateway API on (`elasticLoadBalancing.gatewayApi.crds.managed`,
  AWS owning the CRDs at Gateway API v1) has no argument in the aws provider
  yet, so `enable-gateway-api.sh` calls `aws eks update-cluster-config` once
  per cluster and waits for the update. **Temporary**: replace it with the
  provider's argument when there is one.
- **Subnets**: the default VPC's subnets that map a public IP on launch, in
  the zones EKS accepts; no NAT gateway. Each gets the tag
  `kubernetes.io/role/elb=1`, which Auto Mode requires before it places an
  internet-facing load balancer; the tag is removed on destroy.
- **External Secrets Operator**: an IAM role that may only
  `secretsmanager:GetSecretValue` on `secret:<secrets_prefix>*` in this
  account and region, bound by EKS Pod Identity to
  `<eso_namespace>/<eso_service_account>`. The ServiceAccount carries no
  annotation, so the operator's chart stays cloud-neutral.

The EKS module also creates a KMS key for secret encryption and a CloudWatch
log group for the control plane; both go with the stack.

## Versions, and why

Checked on 2026-10-28.

| What | Pinned | Source | Why |
|---|---|---|---|
| Terraform | `>= 1.10` (tested 1.17.1) | checkpoint-api.hashicorp.com | the S3 backend's `use_lockfile` needs 1.10 |
| `terraform-aws-modules/eks/aws` | `21.29.0` exactly | registry.terraform.io, published 2026-10-07 | latest; v21 takes `compute_config` (Auto Mode) and per-resource `region`; needs aws ≥ 6.59 |
| `hashicorp/aws` | `>= 6.59, < 7.0`, lock 6.71.0 | registry.terraform.io | the EKS module's floor; 6.71.0 was the latest. Its `aws_eks_cluster` has no Gateway API argument (docs and source checked) |
| `alekc/kubectl` | `>= 2.4, < 3.0`, lock 2.4.1 | registry and GitHub releases | `kubectl_manifest` plans without the cluster's API (`kubernetes_manifest` cannot, for a cluster created in the same apply); `lazy_load` arrived in 2.4.0; 3.0 is still beta |
| aws-cli | 2.38.6 or newer | aws-cli CHANGELOG ("EKS management of Gateway API CRDs") | older versions refuse `gatewayApi` |
| Kubernetes | `1.36` | EKS Kubernetes versions page (1.34–1.37 supported) | the version the charts are validated against (kubeconform in the gate) |

The lock files (`.terraform.lock.hcl`) hold hashes for linux_amd64,
linux_arm64, darwin_arm64 and darwin_amd64; after changing a provider,
regenerate them with
`terraform providers lock -platform=linux_amd64 -platform=linux_arm64 -platform=darwin_arm64 -platform=darwin_amd64`.
The `alekc/kubectl` provider is signed by its author's key, not HashiCorp's.

AWS facts this module relies on, from the EKS user guide: built-in node pools
(set-builtin-node-pools), NodePool samples with `kubernetes.io/arch` and a
GPU pool (create-node-pool, auto-accelerated), StorageClass
(create-storage-class), network policy (auto-net-pol), Gateway API
(auto-configure-gateway-api), subnet tags (tag-subnets-auto), zones EKS
refuses (network-reqs).

## Not verified

- No `apply` has run: nothing here has created a cluster yet. `validate` and
  a read-only `plan` (59 resources with the GPU pool) are what was checked.
- That the Gateway API CRDs exist the moment the cluster update reports
  `Successful`. If they lag, the GatewayClass apply fails; apply again.
- That the `default` NodeClass places nodes in the cluster's (public)
  subnets with a public IP. The AWS pages say the NodeClass follows the
  subnet's `MapPublicIpOnLaunch`; not seen on a live cluster.
- Whether External Secrets Operator needs more than `GetSecretValue` (for
  instance `DescribeSecret`) for the stores the instance writes.

## Checks

`tests/test_terraform.py` runs `terraform fmt -check`, and per module
`terraform init -backend=false -lockfile=readonly` and `terraform validate`,
and refuses an account id, a region outside a variable default, or an
instance name in these files. The gate workflow installs a pinned Terraform
for it.
