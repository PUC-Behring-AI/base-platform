#!/usr/bin/env bash
# =============================================================================
# scripts/k8s-test.sh — the system test of the base on the local kind cluster
# =============================================================================
#
# Usage, after scripts/k8s-up.sh:
#   scripts/k8s-test.sh
#
#   1. every Deployment and StatefulSet of the four layers is ready;
#   2. through the Gateway, as a browser would: an account is created with the
#      operator command (C5), it logs in, starts the flow `echo` (C3, a job
#      the reference instance's agents image serves), and polls the job until
#      it ends; every answer must validate against c3_envelope.schema.json and
#      the job must succeed;
#   3. a Job in namespace knowledge, labelled as the layer's own jobs, tries
#      https://example.org and must FAIL by timing out (no route out);
#   4. the same kind of Job reaches the inference gateway's liveliness check
#      and must succeed.
#
# Needs python3 with jsonschema (pyproject.toml) on this machine.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT=kind-base
LAYERS="interface knowledge agents inference"
# busybox 1.37, digest checked with `docker buildx imagetools inspect` on 2026-10-28.
PROBE_IMAGE=busybox@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e

die() { echo "k8s-test: FAIL: $*" >&2; exit 1; }
step() { echo "── $*"; }
kc() { kubectl --context "$CONTEXT" "$@"; }

[ $# -eq 0 ] || die "usage: scripts/k8s-test.sh"
for tool in kubectl docker python3 openssl; do
    command -v "$tool" >/dev/null || die "$tool is not installed"
done
python3 -c 'import jsonschema' 2>/dev/null || die "python3 has no jsonschema (pip install -e .)"

# ── 1. Ready ────────────────────────────────────────────────────────────────

step "1. every Deployment and StatefulSet ready"
for ns in $LAYERS; do
    for workload in $(kc -n "$ns" get deployment,statefulset -o name); do
        kc -n "$ns" rollout status "$workload" --timeout=300s >/dev/null ||
            die "$ns/$workload is not ready"
        echo "ready $ns/$workload"
    done
done

# ── 2. A job through the Gateway ────────────────────────────────────────────

step "2. login and a C3 job through the Gateway"
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
[ -n "$image" ] && [ -n "$origin" ] || die "cannot read the BFF's image and origin"
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

PYTHONPATH="$ROOT" python3 - "$url" "$origin" "$principal" "$password" <<'PY' || die "the C3 job"
import json
import sys
import time
import urllib.error
import urllib.request

from schemas.validate import validator_for

url, origin, principal, password = sys.argv[1:]
C3 = "https://schemas.base.internal/c3_envelope.schema.json#/$defs/"


def call(method, path, body=None, cookie=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url + path, data=data, method=method)
    req.add_header("Origin", origin)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def valid(name, status, raw):
    payload = json.loads(raw)
    validator_for(C3 + name).validate(payload)
    print(f"HTTP {status}, valid C3 {name}")
    return payload


status, headers, raw = call("POST", "/auth/login", {"principal_id": principal, "password": password})
if status != 204:
    sys.exit(f"login: HTTP {status}: {raw[:300]!r}")
# The session cookie is Secure; sent back by hand, since this is plain HTTP.
cookie = headers["Set-Cookie"].split(";", 1)[0]
print("logged in")

status, _, raw = call("POST", "/api/v1/flows/echo", {"query": "system test"}, cookie)
if status != 202:
    sys.exit(f"flow echo: HTTP {status}: {raw[:300]!r}")
job = valid("job_accepted", status, raw)["job_id"]

deadline = time.monotonic() + 120
while True:
    status, _, raw = call("GET", f"/api/v1/jobs/{job}", cookie=cookie)
    if status != 200:
        sys.exit(f"job {job}: HTTP {status}: {raw[:300]!r}")
    state = json.loads(raw)["state"]
    if state in ("succeeded", "failed") or time.monotonic() > deadline:
        break
    time.sleep(1)
answer = valid("job_status", status, raw)
if answer["state"] != "succeeded":
    sys.exit(f"job {job} ended {answer['state']}: {json.dumps(answer)[:500]}")
validator_for(C3 + "response").validate(answer["result"])
print(f"job {job} succeeded; its result is a valid C3 response: "
      f"{json.dumps(answer['result']['body'])[:200]}")
PY

# ── 3 and 4. What a knowledge pod can reach ─────────────────────────────────

# A Job labelled as the knowledge layer's own jobs, so the layer's policies
# apply to it exactly as to a migration or a load.
probe() {
    local name="$1" target="$2"
    kc -n knowledge delete job "$name" --ignore-not-found >/dev/null
    kc -n knowledge apply -f - >/dev/null <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: $name
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      labels:
        app.kubernetes.io/name: base-knowledge
        app.kubernetes.io/instance: knowledge
        app.kubernetes.io/component: job
    spec:
      restartPolicy: Never
      containers:
        - name: probe
          image: $PROBE_IMAGE
          # kindnet's policy engine lets a new pod's packets through until
          # it has learnt the pod's address (measured: a request at start
          # reached example.org, the same request 5 s later timed out), so
          # the probe waits before it asks. Tracked in base-platform#90.
          command: [sh, -c, "sleep 10 && exec wget -T 5 -O /dev/null $target"]
EOF
    local outcome=""
    for _ in $(seq 90); do
        outcome="$(kc -n knowledge get job "$name" \
            -o jsonpath='{.status.conditions[?(@.status=="True")].type}')"
        case "$outcome" in *Complete*|*Failed*) break ;; esac
        sleep 1
    done
    kc -n knowledge logs "job/$name" 2>&1 | sed 's/^/    /'
    case "$outcome" in
        *Complete*) probe_result=succeeded ;;
        *Failed*) probe_result=failed ;;
        *) die "Job knowledge/$name did not finish in 90 s" ;;
    esac
}

step "3. a knowledge pod cannot reach the internet"
probe egress-world https://example.org
[ "$probe_result" = failed ] || die "a knowledge pod reached https://example.org"
kc -n knowledge logs job/egress-world 2>&1 | grep -q "timed out" ||
    die "the request to example.org failed, but not by timing out (see above)"
echo "refused: no route out of knowledge"

step "4. a knowledge pod reaches the inference gateway"
probe egress-inference http://litellm.inference.svc:4000/health/liveliness
[ "$probe_result" = succeeded ] || die "a knowledge pod cannot reach litellm.inference.svc:4000"
echo "reached litellm.inference.svc:4000/health/liveliness"

echo "k8s-test: all four checks passed"
