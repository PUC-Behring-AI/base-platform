#!/usr/bin/env bash
# =============================================================================
# scripts/k8s-registry.sh — the kind cluster's image registry, localhost:5001
# =============================================================================
#
# Usage:
#   scripts/k8s-registry.sh
#
# Starts registry kind-registry on localhost:5001 when it is not running, and
# changes nothing when it is. k8s-up.sh calls it before it creates the
# cluster; an instance whose build scripts push straight to a registry calls
# it first, builds with `--push localhost:5001`, then runs k8s-up.sh, whose
# images step finds the images there (ADAPTATION §10). k8s-up.sh connects the
# registry to the cluster's network once the cluster exists;
# k8s-down.sh --delete removes it.

set -euo pipefail

REGISTRY=kind-registry
REGISTRY_PORT=5001
# registry:3, digest checked with `docker buildx imagetools inspect` on 2026-10-28.
REGISTRY_IMAGE=registry@sha256:d4032d4cc323c1731c707931ecada07a53076eac38e3b61ae57533f170f2c6c3

die() { echo "k8s-registry: $*" >&2; exit 1; }

[ $# -eq 0 ] || die "usage: scripts/k8s-registry.sh"
command -v docker >/dev/null || die "docker is not installed"

if [ "$(docker inspect -f '{{.State.Running}}' "$REGISTRY" 2>/dev/null || true)" != true ]; then
    docker rm -f "$REGISTRY" >/dev/null 2>&1 || true
    docker run -d --restart=always -p "127.0.0.1:$REGISTRY_PORT:5000" --network bridge \
        --name "$REGISTRY" "$REGISTRY_IMAGE" >/dev/null
fi
echo "registry $REGISTRY on localhost:$REGISTRY_PORT"
