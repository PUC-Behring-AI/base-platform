"""Tests for the schemas and postgres charts under deploy/charts/.

Each test renders a chart with `helm template` and asserts on the YAML. No
cluster is needed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parent.parent.resolve()
CHARTS = ROOT / "deploy" / "charts"
DIGEST = "sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873"

needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _helm(chart: str, *sets: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "t", str(CHARTS / chart)]
    for s in sets:
        cmd += ["--set", s]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _render(chart: str, *sets: str) -> list[dict[str, Any]]:
    result = _helm(chart, *sets)
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def _kind(docs: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    (doc,) = [d for d in docs if d["kind"] == kind]
    return doc


PG = ("auth.existingSecret=pg-secret", "auth.username=app", "auth.database=appdb")


@needs_helm
def test_schemas_configmap_has_every_schema() -> None:
    cm = _kind(_render("schemas"), "ConfigMap")
    assert cm["metadata"]["name"] == "base-platform-schemas"
    expected = sorted(p.name for p in (ROOT / "schemas").glob("*.json"))
    assert expected
    assert sorted(cm["data"]) == expected


def test_schema_copy_in_sync() -> None:
    source = {p.name: p.read_bytes() for p in (ROOT / "schemas").glob("*.json")}
    copy = {p.name: p.read_bytes() for p in (CHARTS / "schemas" / "files").glob("*.json")}
    assert copy == source, "run scripts/sync-chart-schemas.sh"


@needs_helm
def test_postgres_requires_existing_secret() -> None:
    result = _helm("postgres", "auth.username=app", "auth.database=appdb")
    assert result.returncode != 0
    assert "/auth/existingSecret" in result.stderr  # helm prints the schema path


@needs_helm
def test_postgres_policy_allows_only_listed() -> None:
    peer = {"podSelector": {"matchLabels": {"role": "client"}}}
    docs = _render("postgres", *PG, "allowFrom[0].podSelector.matchLabels.role=client")
    policy = _kind(docs, "NetworkPolicy")
    assert policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    ports = [{"port": 5432, "protocol": "TCP"}]
    assert policy["spec"]["ingress"] == [{"from": [peer], "ports": ports}]
    egress = policy["spec"]["egress"]
    assert [p["port"] for rule in egress for p in rule["ports"]] == [53, 53]


@needs_helm
def test_postgres_empty_allow_list_denies_ingress() -> None:
    policy = _kind(_render("postgres", *PG), "NetworkPolicy")
    assert "ingress" not in policy["spec"]


@needs_helm
def test_postgres_workload_wiring() -> None:
    docs = _render("postgres", *PG)
    sts = _kind(docs, "StatefulSet")
    svc = _kind(docs, "Service")
    pod = sts["spec"]["template"]["spec"]
    (container,) = pod["containers"]
    assert container["image"] == f"postgres@{DIGEST}"
    assert "envFrom" not in container
    env = {e["name"]: e for e in container["env"]}
    assert env["POSTGRES_USER"]["value"] == "app"
    assert env["POSTGRES_DB"]["value"] == "appdb"
    assert env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"] == {
        "name": "pg-secret",
        "key": "password",
    }
    assert container["ports"][0]["containerPort"] == 5432
    assert svc["spec"]["ports"][0]["port"] == 5432
    assert svc["spec"]["ports"][0]["targetPort"] == 5432
    assert svc["metadata"]["name"] == sts["spec"]["serviceName"] == "t"
    assert "pg_isready" in container["readinessProbe"]["exec"]["command"]
    (claim,) = sts["spec"]["volumeClaimTemplates"]
    assert claim["spec"]["storageClassName"] == "base-rwo"
    assert claim["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert claim["spec"]["resources"]["requests"]["storage"] == "1Gi"
    assert container["volumeMounts"][0]["mountPath"] == "/var/lib/postgresql/data"


@needs_helm
def test_postgres_image_and_mount_overridable() -> None:
    docs = _render(
        "postgres",
        *PG,
        "image.repository=example.invalid/pg",
        "image.tag=18-alpine",
        "image.digest=",
        "storage.mountPath=/var/lib/postgresql",
        "auth.passwordKey=pw",
    )
    container = _kind(docs, "StatefulSet")["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "example.invalid/pg:18-alpine"
    assert container["volumeMounts"][0]["mountPath"] == "/var/lib/postgresql"
    env = {e["name"]: e for e in container["env"]}
    assert env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"]["key"] == "pw"


@needs_helm
def test_postgres_helm_test_hook() -> None:
    pod = _kind(_render("postgres", *PG), "Pod")
    assert pod["metadata"]["annotations"]["helm.sh/hook"] == "test"


@needs_helm
def test_postgres_name_is_exactly_the_release_name() -> None:
    for release in ("interface-accounts-db", "my-postgres"):
        cmd = ["helm", "template", release, str(CHARTS / "postgres")]
        for value in PG:
            cmd += ["--set", value]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        assert _kind(docs, "Service")["metadata"]["name"] == release
        assert _kind(docs, "StatefulSet")["metadata"]["name"] == release
        assert _kind(docs, "NetworkPolicy")["metadata"]["name"] == release
        assert _kind(docs, "Pod")["metadata"]["name"] == f"{release}-test"


@needs_helm
def test_postgres_pgdata_under_the_volume() -> None:
    for mount in ("/var/lib/postgresql/data", "/var/lib/postgresql"):
        docs = _render("postgres", *PG, f"storage.mountPath={mount}")
        container = _kind(docs, "StatefulSet")["spec"]["template"]["spec"]["containers"][0]
        env = {e["name"]: e for e in container["env"]}
        assert env["PGDATA"]["value"] == f"{mount}/pgdata"
        assert container["volumeMounts"][0]["mountPath"] == mount


@needs_helm
def test_postgres_empty_image_tag_rejected() -> None:
    result = _helm("postgres", *PG, "image.tag=", "image.digest=")
    assert result.returncode != 0
    assert "/image/tag" in result.stderr
