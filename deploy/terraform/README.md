# deploy/terraform — the managed cluster

Two Terraform modules an instance calls from its own roots, one root per
module, so the two have separate state:

| Module | What it creates | Lifetime |
|---|---|---|
| `persistent/` | ECR repositories with a lifecycle policy, the backups bucket (versioned, encrypted, private, old versions expire), a monthly and a daily cost budget | created once, never destroyed (`prevent_destroy` on the repositories and the bucket) |
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
| `ecr_untagged_expire_days` | number | `7` — untagged images deleted after this |
| `ecr_tagged_keep` | number | `20` — newest tagged images kept per repository |
| `budget_monthly_usd` | number | — mails at 80% actual and 100% forecast |
| `budget_daily_usd` | number | — mails at 100% actual |
| `budget_emails` | list(string) | — must not be empty |

Outputs: `ecr_repository_urls` (map, entry → URL), `backups_bucket`
(`<name>-backups-<account id>`). In the bucket, a noncurrent (overwritten or
deleted) version expires after 30 days and an incomplete multipart upload is
aborted after 7.

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
| `endpoint_public_access_cidrs` | list(string) | `["0.0.0.0/0"]` — who may reach the API endpoint |
| `control_plane_logs` | list(string) | `[]` — no control plane logs, no log group |
| `control_plane_log_retention_days` | number | `7` — when logs are on |
| `vpc_id` | string | `null` → the region's default VPC |
| `subnet_ids` | list(string) | `[]` → the default VPC's public subnets outside `excluded_zone_ids`; give with `vpc_id` |
| `excluded_zone_ids` | list(string) | the zone ids where EKS refuses a control plane |
| `gateway_scheme` | string | `"internet-facing"` — or `"internal"` |
| `cpu_pool_cpu_limit` | number | `32` |
| `cpu_pool_consolidation` | string | `"WhenEmpty"` — or `"WhenEmptyOrUnderutilized"` |
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
`PATH`, for the token above and for the Gateway API step below. Both run
with the **ambient** AWS credentials (environment variables, `AWS_PROFILE`,
the SSO cache), not with the aws provider's `profile` or `assume_role`: a
root that reaches the account only through the provider's `assume_role`
must also export credentials for that role before `apply`.

## What `cluster` does, and why

- **Auto Mode, built-in `system` pool only.** `system` is tainted
  `CriticalAddonsOnly` and takes only cluster add-ons; having a built-in pool
  on also makes EKS create the access entry for the Auto Mode node role. The
  other built-in pool, `general-purpose`, is amd64 only; an arm64 image
  scheduled there fails with `exec format error`.
- **NodeClass `base`**, used by both custom pools instead of Auto Mode's
  `default`: the same node role (so the access entry EKS created for it
  holds, and no other is needed), the cluster's subnets and security group,
  `associatePublicIPAddress: true` (no NAT, so a public address is how nodes
  reach ECR; inbound stays closed by the security group), and `tags = var.tags`
  on every instance. The EKS module's default `enable_auto_mode_custom_tags`
  gives the cluster role the permission to tag.
- **NodePool `arm64`** (Graviton, on demand, families c/m/r of generation 6
  or newer): the only untainted pool, so every workload lands there. Its
  consolidation is `WhenEmpty` by default: Karpenter removes empty nodes but
  never evicts pods to pack busy ones, so nothing restarts in the middle of
  a demo.
- **NodePool `gpu`** (when `gpu_node_pool = true`): amd64, on demand,
  `gpu_instance_types`, tainted `nvidia.com/gpu:NoSchedule`. Auto Mode brings
  the NVIDIA driver and device plugin.
- **StorageClass `base-rwo`**: provisioner `ebs.csi.eks.amazonaws.com` (Auto
  Mode's, not the self-managed `ebs.csi.aws.com`), gp3, encrypted,
  `WaitForFirstConsumer`, only on Auto Mode nodes, with the caller's tags
  as `tagSpecification_<n>` parameters. Auto Mode creates no
  StorageClass of its own. Volumes are not deleted with the cluster: delete
  the PVCs before `terraform destroy`, or the EBS volumes keep billing.
- **Network policy**: ConfigMap `kube-system/amazon-vpc-cni` with
  `enable-network-policy-controller: "true"`. Without it Auto Mode accepts
  every NetworkPolicy and enforces none. Applied server-side, so it works
  whether or not the ConfigMap already exists.
- **Gateway API**: GatewayClass `base-alb`, controller
  `eks.amazonaws.com/gateway-alb` (one ALB per Gateway), whose
  `parametersRef` points at LoadBalancerConfiguration `kube-system/base-alb`
  (`gateway.k8s.aws/v1`) with `scheme: <gateway_scheme>`, internet-facing by
  default. Without it the ALB is internal, the controller's default, and a
  browser outside the VPC cannot reach the edge. Sources: Auto Mode reuses
  the AWS Load Balancer Controller's `LoadBalancerConfiguration` "at the
  Gateway or GatewayClass level"
  (https://docs.aws.amazon.com/eks/latest/userguide/auto-configure-gateway-api.html);
  `scheme`, default `internal`
  (https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/gateway/loadbalancerconfig/). The cluster setting
  that turns the Gateway API on (`elasticLoadBalancing.gatewayApi.crds.managed`,
  AWS owning the CRDs at Gateway API v1) has no argument in the aws provider
  yet, so `enable-gateway-api.sh` calls `aws eks update-cluster-config` once
  per cluster and waits for the update. It is idempotent: it exits at once
  when `describe-cluster` already shows the setting, and waits for an update
  already in progress instead of starting a second one (EKS refuses that).
  **Temporary**: replace it with the provider's argument when there is one.
- **Subnets**: the default VPC's subnets that map a public IP on launch, in
  the zones EKS accepts; no NAT gateway. Each gets the tag
  `kubernetes.io/role/elb=1`, which Auto Mode requires before it places an
  internet-facing load balancer. `terraform destroy` removes the tag again,
  so a subnet the caller also uses for something else loses it too.
- **External Secrets Operator**: an IAM role that may only
  `secretsmanager:GetSecretValue` on `secret:<secrets_prefix>*` in this
  account and region, assumable only by Pod Identity acting for this account
  (`aws:SourceAccount`), bound by EKS Pod Identity to
  `<eso_namespace>/<eso_service_account>`. The ServiceAccount carries no
  annotation, so the operator's chart stays cloud-neutral.

- **No customer KMS key**: Kubernetes secrets keep EKS's default envelope
  encryption with an AWS-owned key. A customer key costs a monthly fee and,
  after every teardown, waits 7 to 30 days pending deletion; the default
  needs neither.
- **No control plane logs by default**, and so no log group. With
  `control_plane_logs` set, the module creates the group with
  `control_plane_log_retention_days` (7) of retention, so EKS does not
  create one that keeps logs forever.

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
  a read-only `plan` (58 resources with the GPU pool and two ECR
  repositories) are what was checked.
- That the Gateway API CRDs exist the moment the cluster update reports
  `Successful`. If they lag, the GatewayClass apply fails; apply again.
- That NodeClass `base` launches nodes that join: it reuses the node role
  whose access entry EKS creates (create-node-class says so), and the
  cluster primary security group, which is what Auto Mode's `default`
  NodeClass is understood to use; neither seen on a live cluster.
- That Auto Mode's EBS driver honours `tagSpecification_<n>` on the
  StorageClass. It is the self-managed EBS CSI driver's parameter; the Auto
  Mode StorageClass page does not list it. If ignored, volumes are untagged
  and the cost report cannot attribute them.
- That Auto Mode installs the `gateway.k8s.aws` CRDs (LoadBalancerConfiguration)
  when the Gateway API is on with managed CRDs; if not, its apply fails with
  "no matches for kind". And that Auto Mode honours a GatewayClass-level
  `parametersRef` with a `namespace` (the AWS page says GatewayClass level;
  its examples attach at the Gateway). If either fails, the edge Gateway's
  `infrastructure.parametersRef` is the fallback, in the instance.
- Two risks of `enable-gateway-api.sh`: (1) that `describe-cluster` prints
  `True` for the managed setting under `--output text` (if it prints
  something else, the script calls `update-cluster-config` again, which EKS
  may refuse as "no changes"); (2) that `list-updates` reports an update
  started by Terraform's own `aws_eks_cluster` changes as `InProgress`
  before this script runs, rather than starting just after it.
- Whether External Secrets Operator needs more than `GetSecretValue` (for
  instance `DescribeSecret`) for the stores the instance writes.

## Checks

`tests/test_terraform.py` runs `terraform fmt -check`, and per module
`terraform init -backend=false -lockfile=readonly`, `terraform validate` and
`terraform test` (cluster/tests renders the GatewayClass and its
LoadBalancerConfiguration with every provider mocked: no AWS, no cluster),
and refuses an account id, a region outside a variable default, or an
instance name in these files. The gate workflow installs a pinned Terraform
for it.
