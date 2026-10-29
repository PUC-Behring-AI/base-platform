#!/usr/bin/env bash
# Turns the Gateway API on in an EKS Auto Mode cluster, with AWS managing the
# Gateway API CRDs, and waits for the update to finish. Called once per
# cluster by main.tf (terraform_data.gateway_api), because the aws provider
# has no argument for it yet.
#
# Usage: enable-gateway-api.sh <cluster-name> <region>
# Needs aws-cli 2.38.6 or newer: older ones refuse `gatewayApi`.
set -euo pipefail

[ "$#" -eq 2 ] || { echo "usage: $0 <cluster-name> <region>" >&2; exit 2; }
cluster="$1"
region="$2"

update_id="$(aws eks update-cluster-config --region "$region" --name "$cluster" \
    --kubernetes-network-config '{"elasticLoadBalancing":{"enabled":true,"gatewayApi":{"crds":{"managed":true}}}}' \
    --query update.id --output text)"
echo "update $update_id: enabling the Gateway API on $cluster"

# Twenty minutes, polled every ten seconds.
tries=120
while [ "$tries" -gt 0 ]; do
    status="$(aws eks describe-update --region "$region" --name "$cluster" \
        --update-id "$update_id" --query update.status --output text)"
    case "$status" in
        Successful)
            echo "update $update_id: Successful"
            exit 0
            ;;
        Failed|Cancelled)
            aws eks describe-update --region "$region" --name "$cluster" \
                --update-id "$update_id" --query update.errors >&2
            echo "update $update_id: $status" >&2
            exit 1
            ;;
    esac
    tries=$((tries - 1))
    sleep 10
done
echo "update $update_id: still not finished after twenty minutes" >&2
exit 1
