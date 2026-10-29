#!/usr/bin/env bash
# Turns the Gateway API on in an EKS Auto Mode cluster, with AWS managing the
# Gateway API CRDs, and waits for the update to finish. Called once per
# cluster by main.tf (terraform_data.gateway_api), because the aws provider
# has no argument for it yet.
#
# Idempotent: a cluster that already has it is left alone, and an update
# already in progress (EKS refuses a second one) is waited for first.
#
# Uses the ambient AWS credentials (environment, AWS_PROFILE, SSO cache),
# not the Terraform aws provider's profile or assume_role.
#
# Usage: enable-gateway-api.sh <cluster-name> <region>
# Needs aws-cli 2.38.6 or newer: older ones refuse `gatewayApi`.
set -euo pipefail

[ "$#" -eq 2 ] || { echo "usage: $0 <cluster-name> <region>" >&2; exit 2; }
cluster="$1"
region="$2"

# Waits up to twenty minutes for one update, polled every ten seconds.
wait_update() {
    local id="$1" status tries=120
    while [ "$tries" -gt 0 ]; do
        status="$(aws eks describe-update --region "$region" --name "$cluster" \
            --update-id "$id" --query update.status --output text)"
        case "$status" in
            Successful)
                echo "update $id: Successful"
                return 0
                ;;
            Failed|Cancelled)
                aws eks describe-update --region "$region" --name "$cluster" \
                    --update-id "$id" --query update.errors >&2
                echo "update $id: $status" >&2
                return 1
                ;;
        esac
        tries=$((tries - 1))
        sleep 10
    done
    echo "update $id: still not finished after twenty minutes" >&2
    return 1
}

for id in $(aws eks list-updates --region "$region" --name "$cluster" \
        --query updateIds --output text); do
    status="$(aws eks describe-update --region "$region" --name "$cluster" \
        --update-id "$id" --query update.status --output text)"
    if [ "$status" = "InProgress" ]; then
        echo "update $id is in progress on $cluster; waiting for it first"
        wait_update "$id"
    fi
done

managed="$(aws eks describe-cluster --region "$region" --name "$cluster" \
    --query cluster.kubernetesNetworkConfig.elasticLoadBalancing.gatewayApi.crds.managed \
    --output text)"
if [ "$managed" = "True" ]; then
    echo "$cluster: the Gateway API is already on, with AWS-managed CRDs"
    exit 0
fi

update_id="$(aws eks update-cluster-config --region "$region" --name "$cluster" \
    --kubernetes-network-config '{"elasticLoadBalancing":{"enabled":true,"gatewayApi":{"crds":{"managed":true}}}}' \
    --query update.id --output text)"
echo "update $update_id: enabling the Gateway API on $cluster"
wait_update "$update_id"
