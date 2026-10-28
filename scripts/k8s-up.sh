#!/usr/bin/env bash
# =============================================================================
# scripts/k8s-up.sh — bring the whole base up on a local kind cluster
# =============================================================================
#
# Usage:
#   scripts/k8s-up.sh <instance-dir>
#   scripts/k8s-up.sh deploy/helmfile/reference-instance     the base alone
#
# <instance-dir> holds what one deployment decides (ADAPTATION §10):
#   .env                    the secret values, KEY=value lines; never committed
#   .env.required           one line per required variable:
#                             <VARIABLE> <namespace> [<namespace>...]
#                           each is refused when unset or empty, then written
#                           into Secret k8s-secrets of each namespace named
#   values/common/<release>.yaml, values/kind/<release>.yaml
#                           helm values per release (deploy/helmfile)
#   images.txt              the images to build (scripts/k8s-images.sh)
#   configmaps/<namespace>/<name>/   optional: each directory becomes
#                           ConfigMap <name> in <namespace>, one key per file
#
# The layer charts come from the sibling checkouts, as compose.base.yaml takes
# the layers: ${BASE_ROOT:-..}/base-<layer>/deploy/chart. A layer without a
# chart is named and refused; the harness never fakes a layer.
#
# Every step is idempotent: run it again on a live cluster and it upgrades in
# place (each chart's migration hook runs once more, under its own lock).
#
# cloud-provider-kind runs the Gateway; it is started here when not running.
# On macOS its default mode wants sudo; with --enable-lb-port-mapping it does
# not, and the Gateway is published on an ephemeral localhost port instead.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER=base
CONTEXT="kind-$CLUSTER"
REGISTRY=kind-registry
REGISTRY_PORT=5001
# registry:3, digest checked with `docker buildx imagetools inspect` on 2026-10-28.
REGISTRY_IMAGE=registry@sha256:d4032d4cc323c1731c707931ecada07a53076eac38e3b61ae57533f170f2c6c3
# Gateway API v1, the standard channel; cloud-provider-kind v0.12.0 conforms to v1.6.1.
GATEWAY_API_URL=https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml
GATEWAY_API_SHA256=24d931f22abd8e40c973264319ead7cfa09d0fb7716b7ab1ee2ff174cb063a73  # gitleaks:allow published release checksum, not a secret
NAMESPACES="interface agents knowledge inference edge"
LAYERS="interface knowledge agents inference"

die() { echo "k8s-up: $*" >&2; exit 1; }
step() { echo "── $*"; }

[ $# -eq 1 ] || die "usage: scripts/k8s-up.sh <instance-dir>"
[ -d "$1" ] || die "no instance directory at $1"
INSTANCE="$(cd "$1" && pwd)"
BASE_ROOT="$(cd "${BASE_ROOT:-$ROOT/..}" && pwd)"
export BASE_ROOT

# ── 1. The instance, before anything touches a cluster ──────────────────────

[ -f "$INSTANCE/.env" ] || die "no $INSTANCE/.env (copy .env.example and fill it in)"
[ -f "$INSTANCE/.env.required" ] || die "no $INSTANCE/.env.required"

# The value of a KEY=value line of .env, or nothing. The file is read, never
# sourced: a value is data, not shell.
env_value() {
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            "$1="*) printf '%s' "${line#*=}"; return 0 ;;
        esac
    done < "$INSTANCE/.env"
}

missing=""
while read -r var _; do
    case "$var" in ''|'#'*) continue ;; esac
    [ -n "$(env_value "$var")" ] || missing="$missing $var"
done < "$INSTANCE/.env.required"
[ -z "$missing" ] || die "required variable(s) unset or empty in $INSTANCE/.env:$missing"

case "${BASE_CHART_SOURCE:-local}" in
    local) ;;
    *) die "BASE_CHART_SOURCE=$BASE_CHART_SOURCE: only local charts are implemented" ;;
esac
no_chart=0
for layer in $LAYERS; do
    chart="$BASE_ROOT/base-$layer/deploy/chart"
    if [ ! -f "$chart/Chart.yaml" ]; then
        echo "k8s-up: layer $layer: no chart at $chart" >&2
        no_chart=1
    fi
done
[ "$no_chart" -eq 0 ] || die "set BASE_ROOT to the directory that holds the base-* checkouts"

step "tools"
for tool in kind kubectl helm helmfile docker cloud-provider-kind; do
    command -v "$tool" >/dev/null || die "$tool is not installed"
done

# ── 2. The cluster and its registry ─────────────────────────────────────────

step "registry $REGISTRY on localhost:$REGISTRY_PORT"
if [ "$(docker inspect -f '{{.State.Running}}' "$REGISTRY" 2>/dev/null || true)" != true ]; then
    docker rm -f "$REGISTRY" >/dev/null 2>&1 || true
    docker run -d --restart=always -p "127.0.0.1:$REGISTRY_PORT:5000" --network bridge \
        --name "$REGISTRY" "$REGISTRY_IMAGE" >/dev/null
fi

step "cluster $CLUSTER"
if ! kind get clusters | grep -qx "$CLUSTER"; then
    kind create cluster --config "$ROOT/deploy/kind/cluster.yaml"
fi
for node in $(kind get nodes --name "$CLUSTER"); do
    docker exec "$node" mkdir -p "/etc/containerd/certs.d/localhost:$REGISTRY_PORT"
    printf '[host."http://%s:5000"]\n' "$REGISTRY" |
        docker exec -i "$node" cp /dev/stdin "/etc/containerd/certs.d/localhost:$REGISTRY_PORT/hosts.toml"
done
if [ "$(docker inspect -f '{{json .NetworkSettings.Networks.kind}}' "$REGISTRY")" = null ]; then
    docker network connect kind "$REGISTRY"
fi
kc() { kubectl --context "$CONTEXT" "$@"; }
kc apply -f - >/dev/null <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:$REGISTRY_PORT"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF
kc apply -f "$ROOT/deploy/kind/storageclass.yaml"

step "Gateway API CRDs (v1.6.1, standard)"
crds="$(mktemp)"
trap 'rm -f "$crds"' EXIT
curl -fsSL -o "$crds" "$GATEWAY_API_URL"
got="$(shasum -a 256 "$crds" | cut -d' ' -f1)"
[ "$got" = "$GATEWAY_API_SHA256" ] || die "Gateway API CRDs: sha256 $got, expected $GATEWAY_API_SHA256"
kc apply --server-side --force-conflicts -f "$crds" >/dev/null

step "cloud-provider-kind"
if pgrep -f cloud-provider-kind >/dev/null; then
    echo "already running"
else
    log="${TMPDIR:-/tmp}/cloud-provider-kind.log"
    # No sudo: port mapping publishes the Gateway on localhost instead of
    # assigning its address to the host (which is what wants sudo on macOS).
    echo "starting: cloud-provider-kind --enable-lb-port-mapping=true (log: $log)"
    nohup cloud-provider-kind --enable-lb-port-mapping=true >"$log" 2>&1 &
fi

step "namespaces"
for ns in $NAMESPACES; do
    kc create namespace "$ns" --dry-run=client -o yaml | kc apply -f - >/dev/null
    kc label namespace "$ns" "base.layer=$ns" --overwrite >/dev/null
done

step "Gateway base in edge"
for _ in $(seq 60); do
    kc get gatewayclass cloud-provider-kind >/dev/null 2>&1 && break
    sleep 2
done
kc get gatewayclass cloud-provider-kind >/dev/null || die "cloud-provider-kind registered no GatewayClass (log: ${TMPDIR:-/tmp}/cloud-provider-kind.log)"
kc apply -f "$ROOT/deploy/kind/gateway.yaml"

# ── 3. Secrets and ConfigMaps from the instance ─────────────────────────────

step "secrets k8s-secrets"
for ns in $NAMESPACES; do
    file="$(mktemp)"
    while read -r var namespaces; do
        case "$var" in ''|'#'*) continue ;; esac
        for want in $namespaces; do
            [ "$want" = "$ns" ] && printf '%s=%s\n' "$var" "$(env_value "$var")" >> "$file"
        done
    done < "$INSTANCE/.env.required"
    if [ -s "$file" ]; then
        kc -n "$ns" create secret generic k8s-secrets --from-env-file="$file" \
            --dry-run=client -o yaml | kc apply -f - >/dev/null
        echo "$ns: $(cut -d= -f1 "$file" | tr '\n' ' ')"
    fi
    rm -f "$file"
done

if [ -d "$INSTANCE/configmaps" ]; then
    step "instance ConfigMaps"
    for dir in "$INSTANCE"/configmaps/*/*/; do
        [ -d "$dir" ] || continue
        name="$(basename "$dir")"
        ns="$(basename "$(dirname "$dir")")"
        kc -n "$ns" create configmap "$name" --from-file="$dir" \
            --dry-run=client -o yaml | kc apply -f - >/dev/null
        echo "$ns/$name"
    done
fi

# ── 4. Images, releases, tests ──────────────────────────────────────────────

KIND_NETWORK_CIDR="$(docker network inspect kind \
    --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' | grep -m1 '\.')" ||
    die "the kind docker network has no IPv4 subnet"
K8S_INSTANCE_DIR="$INSTANCE"
export KIND_NETWORK_CIDR K8S_INSTANCE_DIR

step "images"
"$ROOT/scripts/k8s-images.sh" "$INSTANCE"

# sync, not apply: apply needs the helm-diff plugin and changes nothing here
# that sync does not, since every release is upgraded in `needs` order anyway.
step "helmfile sync"
helmfile -f "$ROOT/deploy/helmfile/helmfile.yaml.gotmpl" -e kind --kube-context "$CONTEXT" sync

step "helm test"
for layer in $LAYERS; do
    helm --kube-context "$CONTEXT" test "$layer" -n "$layer" --timeout 5m
done

step "Gateway"
for _ in $(seq 60); do
    [ "$(kc -n edge get gateway base -o jsonpath='{.status.conditions[?(@.type=="Programmed")].status}')" = True ] && break
    sleep 2
done
address="$(kc -n edge get gateway base -o jsonpath='{.status.addresses[0].value}')"
[ -n "$address" ] || die "Gateway base has no address (log: ${TMPDIR:-/tmp}/cloud-provider-kind.log)"
proxy="$(docker ps -q --filter "label=io.x-k8s.cloud-provider-kind.gateway.name=$CLUSTER/edge/base")"
published="$( [ -z "$proxy" ] || docker port "$proxy" 80/tcp 2>/dev/null | grep -m1 '0.0.0.0' | sed 's/.*://')"
echo "Gateway base: http://$address/ on the kind network"
[ -z "$published" ] || echo "              http://localhost:$published/ from this machine"
