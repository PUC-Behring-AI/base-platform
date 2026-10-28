#!/usr/bin/env bash
# =============================================================================
# scripts/k8s-test.sh — the system test of the base on the local kind cluster
# =============================================================================
#
# Usage, after scripts/k8s-up.sh <instance-dir>:
#   scripts/k8s-test.sh <instance-dir>
#   scripts/k8s-test.sh deploy/helmfile/reference-instance     the base alone
#
#   1. every Deployment and StatefulSet of the four layers is ready;
#   2. through the Gateway, as a browser would: an account is created with the
#      operator command (C5), it logs in and runs the flows
#      <instance-dir>/system-test.yaml lists, in order (scripts/k8s_system_test.py);
#      every answer must validate against c3_envelope.schema.json, and each
#      job must succeed;
#   3. when system-test.yaml asks for it, a pod in namespace agents searches
#      knowledge (C1) and the answer must validate, with enough passages;
#   4. a Job in namespace knowledge, labelled as the layer's own jobs, tries
#      https://example.org and must FAIL by timing out (no route out);
#   5. the same kind of Job reaches the inference gateway's liveliness check
#      and must succeed.
#
# Needs python3 with jsonschema and pyyaml (pyproject.toml) on this machine.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT=kind-base
LAYERS="interface knowledge agents inference"
# busybox 1.37, digest checked with `docker buildx imagetools inspect` on 2026-10-28.
PROBE_IMAGE=busybox@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e

die() { echo "k8s-test: FAIL: $*" >&2; exit 1; }
step() { echo "── $*"; }
kc() { kubectl --context "$CONTEXT" "$@"; }

[ $# -eq 1 ] || die "usage: scripts/k8s-test.sh <instance-dir>"
[ -d "$1" ] || die "no instance directory at $1"
INSTANCE="$(cd "$1" && pwd)"
for tool in kubectl docker python3 openssl; do
    command -v "$tool" >/dev/null || die "$tool is not installed"
done
python3 -c 'import jsonschema, yaml' 2>/dev/null || die "python3 has no jsonschema or pyyaml (pip install -e .)"
system_test() { python3 "$ROOT/scripts/k8s_system_test.py" "$@"; }
# system-test.yaml is read before anything is asked of the cluster.
plan="$(system_test check "$INSTANCE")" || die "$INSTANCE/system-test.yaml (above)"
echo "system-test.yaml: $plan"

# ── 1. Ready ────────────────────────────────────────────────────────────────

step "1. every Deployment and StatefulSet ready"
for ns in $LAYERS; do
    for workload in $(kc -n "$ns" get deployment,statefulset -o name); do
        kc -n "$ns" rollout status "$workload" --timeout=300s >/dev/null ||
            die "$ns/$workload is not ready"
        echo "ready $ns/$workload"
    done
done

# ── 2. The instance's flows through the Gateway ─────────────────────────────

step "2. login and the instance's flows through the Gateway"
proxy="$(docker ps -q --filter "label=io.x-k8s.cloud-provider-kind.gateway.name=base/edge/base")"
published=""
# `docker port` fails when the proxy has no host binding (Linux, where the
# Gateway's address itself is reachable): then the address is used.
[ -z "$proxy" ] || published="$({ docker port "$proxy" 80/tcp || true; } | sed -n '/^0\.0\.0\.0:/{s/.*://p;q;}')"
if [ -n "$published" ]; then
    url="http://127.0.0.1:$published"
else
    address="$(kc -n edge get gateway base -o jsonpath='{.status.addresses[0].value}')"
    [ -n "$address" ] || die "Gateway base has neither a localhost port nor an address"
    echo "the Gateway's proxy has no localhost port: using its address on the kind network"
    url="http://$address"
fi
echo "Gateway: $url"

image="$(kc -n interface get deployment bff -o jsonpath='{.spec.template.spec.containers[0].image}')"
origin="$(kc -n interface get deployment bff \
    -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="BFF_PUBLIC_ORIGIN")].value}')"
if [ -z "$image" ] || [ -z "$origin" ]; then
    die "cannot read the BFF's image and origin"
fi
principal="system-test-$(date +%s)@example.org"
password="$(openssl rand -hex 16)"

# The operator command, as ADAPTATION §10 runs it: a pod with the interface
# image and the one label the sidecar admits. The token stays in the Secret.
overrides="$(cat <<EOF
{"spec": {"containers": [{"name": "c5-operator", "image": "$image",
  "command": ["python", "-m", "app.c5_client", "create", "--principal", "$principal",
              "--name", "System test", "--role", "admin", "--password", "$password"],
  "env": [{"name": "C5_URL", "value": "http://identity-sidecar:8003"},
          {"name": "C5_OPERATOR_TOKEN",
           "valueFrom": {"secretKeyRef": {"name": "k8s-secrets", "key": "C5_OPERATOR_TOKEN"}}}]}]}}
EOF
)"
kc -n interface run c5-operator --rm -i --restart=Never --quiet --image="$image" \
    --labels=app.kubernetes.io/component=c5-operator --overrides="$overrides" >/dev/null ||
    die "the operator command could not create $principal"
echo "account $principal created through C5"

system_test flows "$INSTANCE" "$url" "$origin" "$principal" "$password" ||
    die "the flows of $INSTANCE/system-test.yaml (above)"

# ── 3, 4 and 5. What a pod can reach ────────────────────────────────────────

# probe <namespace> <name> <labels: a JSON object> <shell command>: runs a
# Job, leaves its log in $probe_log and how it ended in $probe_result.
probe() {
    local ns="$1" name="$2" labels="$3" command="$4"
    kc -n "$ns" delete job "$name" --ignore-not-found >/dev/null
    kc -n "$ns" apply -f - >/dev/null <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: $name
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      labels: $labels
    spec:
      restartPolicy: Never
      containers:
        - name: probe
          image: $PROBE_IMAGE
          # kindnet's policy engine lets a new pod's packets through until
          # it has learnt the pod's address (measured: a request at start
          # reached example.org, the same request 5 s later timed out), so
          # the probe waits before it asks. Tracked in base-platform#90.
          command: [sh, -c, "sleep 10 && $command"]
EOF
    local outcome=""
    for _ in $(seq 90); do
        outcome="$(kc -n "$ns" get job "$name" \
            -o jsonpath='{.status.conditions[?(@.status=="True")].type}')"
        case "$outcome" in *Complete*|*Failed*) break ;; esac
        sleep 1
    done
    probe_log="$(kc -n "$ns" logs "job/$name" 2>&1)"
    case "$outcome" in
        *Complete*) probe_result=succeeded ;;
        *Failed*) probe_result=failed ;;
        *) die "Job $ns/$name did not finish in 90 s" ;;
    esac
}
# A Job labelled as the knowledge layer's own jobs, so the layer's policies
# apply to it exactly as to a migration or a load.
KNOWLEDGE_JOB='{"app.kubernetes.io/name": "base-knowledge", "app.kubernetes.io/instance": "knowledge", "app.kubernetes.io/component": "job"}'

search="$(system_test search-url "$INSTANCE")"
if [ -n "$search" ]; then
    step "3. knowledge answers a C1 search from namespace agents"
    request_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
    probe agents c1-search '{"app.kubernetes.io/component": "system-test"}' \
        "wget -q -T 60 -O - --header 'X-Request-Id: $request_id' '$search'"
    [ "$probe_result" = succeeded ] || die "the C1 search failed: $probe_log"
    printf '%s' "$probe_log" | system_test search-check "$INSTANCE" ||
        die "the C1 search's answer (above)"
    echo "knowledge answered with a valid C1 response"
else
    step "3. no knowledge search (system-test.yaml asks for none)"
fi

step "4. a knowledge pod cannot reach the internet"
probe knowledge egress-world "$KNOWLEDGE_JOB" "exec wget -T 5 -O /dev/null https://example.org"
printf '%s\n' "$probe_log" | sed 's/^/    /'
[ "$probe_result" = failed ] || die "a knowledge pod reached https://example.org"
case "$probe_log" in
    *"timed out"*) ;;
    *) die "the request to example.org failed, but not by timing out (see above)" ;;
esac
echo "refused: no route out of knowledge"

step "5. a knowledge pod reaches the inference gateway"
probe knowledge egress-inference "$KNOWLEDGE_JOB" \
    "exec wget -T 5 -O /dev/null http://litellm.inference.svc:4000/health/liveliness"
[ "$probe_result" = succeeded ] || die "a knowledge pod cannot reach litellm.inference.svc:4000: $probe_log"
echo "reached litellm.inference.svc:4000/health/liveliness"

echo "k8s-test: all five checks passed"
