"""Tests for scripts/chart_parity.py, which compares a compose file with the
output of `helm template`. Fixtures are inline YAML: no helm, no Docker."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import chart_parity  # noqa: E402

COMPOSE = """
services:
  bff:
    image: ghcr.io/example/bff@sha256:aaaa
    expose: ["8080"]
    environment:
      AGENTS_BASE_URL: http://agents:8000
      ACCOUNTS_DB_BFF_PASSWORD: ${ACCOUNTS_DB_BFF_PASSWORD:?set it}
  tools:
    profiles: [debug]
    image: busybox
"""

RENDERED = """
apiVersion: apps/v1
kind: Deployment
metadata: {name: bff}
spec:
  template:
    spec:
      containers:
        - name: bff
          image: ghcr.io/example/bff@sha256:aaaa
          ports: [{containerPort: 8080}]
          env:
            - {name: AGENTS_BASE_URL, value: "http://agents:8000"}
            - name: ACCOUNTS_DB_BFF_PASSWORD
              valueFrom: {secretKeyRef: {name: s, key: k}}
"""

MAP = "services:\n  bff: {workload: bff}\n"


def _run(tmp_path, capsys, compose=COMPOSE, rendered=RENDERED, mapping=MAP):
    paths = {}
    for name, text in (("compose", compose), ("rendered", rendered), ("map", mapping)):
        paths[name] = tmp_path / f"{name}.yaml"
        paths[name].write_text(text)
    code = chart_parity.main(
        [
            "--compose", str(paths["compose"]),
            "--rendered", str(paths["rendered"]),
            "--map", str(paths["map"]),
        ]
    )  # fmt: skip
    return code, capsys.readouterr()


def test_match_exits_zero(tmp_path, capsys):
    code, out = _run(tmp_path, capsys)
    assert code == 0, out.out
    assert out.out == ""


def test_missing_env_name_reported(tmp_path, capsys):
    rendered = RENDERED.replace("AGENTS_BASE_URL", "OTHER_URL")
    code, out = _run(tmp_path, capsys, rendered=rendered)
    assert code == 1
    assert "service bff: env AGENTS_BASE_URL compose=present chart=absent" in out.out


def test_port_mismatch_reported(tmp_path, capsys):
    rendered = RENDERED.replace("containerPort: 8080", "containerPort: 80")
    code, out = _run(tmp_path, capsys, rendered=rendered)
    assert code == 1
    assert "service bff: port 8080 compose=present chart=absent" in out.out
    assert "service bff: port 80 compose=absent chart=present" in out.out


def test_secret_as_plain_env_reported(tmp_path, capsys):
    rendered = RENDERED.replace("valueFrom: {secretKeyRef: {name: s, key: k}}", "value: hunter2")
    code, out = _run(tmp_path, capsys, rendered=rendered)
    assert code == 1
    assert "service bff: secret ACCOUNTS_DB_BFF_PASSWORD compose=secret chart=plain" in out.out


def test_image_digest_mismatch_reported(tmp_path, capsys):
    rendered = RENDERED.replace("sha256:aaaa", "sha256:bbbb")
    code, out = _run(tmp_path, capsys, rendered=rendered)
    assert code == 1
    assert "service bff: image digest compose=sha256:aaaa chart=" in out.out


def test_ignore_without_reason_is_an_error(tmp_path, capsys):
    mapping = MAP + "ignore:\n  - {service: bff, field: ports}\n"
    code, out = _run(tmp_path, capsys, mapping=mapping)
    assert code == 2
    assert "service bff" in out.err and "field ports" in out.err and "reason" in out.err


def test_ignore_with_reason_silences_the_field(tmp_path, capsys):
    rendered = RENDERED.replace("containerPort: 8080", "containerPort: 80")
    mapping = MAP + "ignore:\n  - {service: bff, field: ports, reason: Gateway listener}\n"
    code, out = _run(tmp_path, capsys, rendered=rendered, mapping=mapping)
    assert code == 0, out.out


def test_unmapped_service_reported(tmp_path, capsys):
    compose = COMPOSE + "  worker:\n    image: busybox\n"
    code, out = _run(tmp_path, capsys, compose=compose)
    assert code == 1
    assert "service worker: workload compose=present chart=unmapped" in out.out


def test_profiled_service_is_skipped_unless_mapped(tmp_path, capsys):
    code, _ = _run(tmp_path, capsys)
    assert code == 0
    mapping = MAP + "  tools: {workload: tools}\n"
    code, out = _run(tmp_path, capsys, mapping=mapping)
    assert code == 1
    assert "service tools: workload compose=present chart=absent" in out.out


def test_missing_file_is_an_error(tmp_path, capsys):
    code = chart_parity.main(
        ["--compose", str(tmp_path / "no.yaml"), "--rendered", "x", "--map", "y"]
    )
    assert code == 2
    assert "no.yaml" in capsys.readouterr().err


def test_job_kind_selects_the_job(tmp_path, capsys):
    compose = "services:\n  mig:\n    image: busybox\n    environment: [DB_URL]\n"
    rendered = (
        "kind: Deployment\nmetadata: {name: mig}\nspec: {template: {spec: {containers: "
        "[{name: a, env: []}]}}}\n---\n"
        "kind: Job\nmetadata: {name: mig}\nspec: {template: {spec: {containers: "
        "[{name: a, env: [{name: DB_URL, value: x}]}]}}}\n"
    )
    mapping = "services:\n  mig: {workload: mig, kind: Job}\n"
    code, out = _run(tmp_path, capsys, compose=compose, rendered=rendered, mapping=mapping)
    assert code == 0, out.out


if __name__ == "__main__":
    pytest.main([__file__])
