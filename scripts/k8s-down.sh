#!/usr/bin/env bash
# =============================================================================
# scripts/k8s-down.sh — take the base off the local kind cluster
# =============================================================================
#
# Usage:
#   scripts/k8s-down.sh            every Helm release on the cluster removed
#   scripts/k8s-down.sh --delete   the cluster, its registry and
#                                  cloud-provider-kind removed as well
#
# Without --delete the cluster, its namespaces, Secrets and volumes stay, so
# the next k8s-up.sh starts from what the databases hold. The releases are
# found with `helm list`, not the helmfile: removing needs no instance
# directory, and nothing is left behind that the helmfile no longer names.
# With --delete nothing of the harness stays on the machine but the images
# it built.

set -euo pipefail

CONTEXT=kind-base
# Where k8s-up.sh keeps cloud-provider-kind's log and pidfile.
STATE="${XDG_CACHE_HOME:-$HOME/.cache}/base-kind"

die() { echo "k8s-down: $*" >&2; exit 1; }

delete=0
case "${1:-}" in
    '') ;;
    --delete) delete=1 ;;
    *) die "usage: scripts/k8s-down.sh [--delete]" ;;
esac

if ! kind get clusters | grep -qx base; then
    echo "no kind cluster base"
elif [ "$delete" -eq 1 ]; then
    kind delete cluster --name base
else
    # --all: a release stuck pending-install or failed is removed too.
    helm --kube-context "$CONTEXT" list -A --all | awk 'NR > 1 {print $1, $2}' |
        while read -r release ns; do
            helm --kube-context "$CONTEXT" uninstall "$release" -n "$ns" --wait
        done
fi

if [ "$delete" -eq 1 ]; then
    if docker inspect kind-registry >/dev/null 2>&1; then
        docker rm -f kind-registry >/dev/null
        echo "removed the registry kind-registry"
    fi
    # The Gateway's proxies are containers cloud-provider-kind started.
    for proxy in $(docker ps -aq --filter label=io.x-k8s.cloud-provider-kind.cluster=base); do
        docker rm -f "$proxy" >/dev/null
        echo "removed the Gateway proxy $proxy"
    done
    # Only the instance k8s-up.sh started (its pidfile): one started by
    # hand, perhaps for another cluster, is left running.
    pidfile="$STATE/cloud-provider-kind.pid"
    if [ -f "$pidfile" ]; then
        pid="$(cat "$pidfile")"
        if ps -o command= -p "$pid" | grep -Eq '^([^ ]*/)?cloud-provider-kind( |$)'; then
            kill "$pid"
            echo "stopped cloud-provider-kind (pid $pid)"
        fi
        rm -f "$pidfile"
    fi
fi
