#!/usr/bin/env bash
# =============================================================================
# scripts/k8s-images.sh — build an instance's images for the kind cluster
# =============================================================================
#
# Usage:
#   scripts/k8s-images.sh <instance-dir>
#
# Builds each image <instance-dir>/images.txt names, in order, and pushes it
# to the kind registry (localhost:5001); then checks that every other image
# the releases name has a variant for the node's architecture. An image built
# or published for another architecture is refused, naming it: the node would
# otherwise run it emulated, slowly and silently, or not at all.
#
# images.txt: <image> <build context> [<Dockerfile, relative to the context>]
# per line; $BASE_ROOT in a context is the directory holding the base-*
# checkouts (default: beside this one), and a relative context is relative to
# the instance directory. Called by k8s-up.sh, after the cluster exists.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT=kind-base

die() { echo "k8s-images: $*" >&2; exit 1; }

[ $# -eq 1 ] || die "usage: scripts/k8s-images.sh <instance-dir>"
[ -f "$1/images.txt" ] || die "no $1/images.txt"
INSTANCE="$(cd "$1" && pwd)"
BASE_ROOT="$(cd "${BASE_ROOT:-$ROOT/..}" && pwd)"

arch="$(kubectl --context "$CONTEXT" get nodes -o jsonpath='{.items[0].status.nodeInfo.architecture}')" ||
    die "cannot read the node's architecture from context $CONTEXT"
[ -n "$arch" ] || die "the cluster reports no node architecture"

built=" "
while read -r image context dockerfile; do
    case "$image" in ''|'#'*) continue ;; esac
    context="${context//\$BASE_ROOT/$BASE_ROOT}"
    case "$context" in /*) ;; *) context="$INSTANCE/$context" ;; esac
    [ -d "$context" ] || die "$image: no build context at $context"
    echo "build $image ($context)"
    if [ -n "$dockerfile" ]; then
        docker build --platform "linux/$arch" -t "$image" -f "$context/$dockerfile" "$context"
    else
        docker build --platform "linux/$arch" -t "$image" "$context"
    fi
    got="$(docker image inspect --format '{{.Architecture}}' "$image")"
    [ "$got" = "$arch" ] || die "$image is linux/$got, the node is linux/$arch"
    docker push "$image" >/dev/null
    built="$built$image "
done < "$INSTANCE/images.txt"

# Every image the releases name that is not built above comes from a public
# registry: its index must list the node's platform.
K8S_INSTANCE_DIR="$INSTANCE"
KIND_NETWORK_CIDR="${KIND_NETWORK_CIDR:-$(docker network inspect kind \
    --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' | grep -m1 '\.')}"
export BASE_ROOT K8S_INSTANCE_DIR KIND_NETWORK_CIDR
images="$(helmfile -f "$ROOT/deploy/helmfile/helmfile.yaml.gotmpl" -e kind template \
    --skip-deps | sed -n 's/^ *image: *"\{0,1\}\([^"]*\)"\{0,1\} *$/\1/p' | sort -u)" ||
    die "helmfile template failed (above)"
for image in $images; do
    case "$built" in *" $image "*) continue ;; esac
    # Captured first: `grep -q` stops reading early, and under pipefail the
    # writer's broken pipe would fail an image that has the variant.
    index="$(docker buildx imagetools inspect "$image")" || die "cannot inspect $image"
    grep -Eq "Platform: +linux/$arch(/|\$)" <<<"$index" ||
        die "$image has no linux/$arch variant (docker buildx imagetools inspect $image)"
    echo "ok $image (linux/$arch)"
done
