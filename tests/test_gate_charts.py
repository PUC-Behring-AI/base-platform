"""Tests for the Helm chart steps of scripts/gate.sh.

Each test builds a fake base-* repository under tmp_path, so the pin step is
skipped and only the YAML and chart steps decide the outcome. helm and
kubeconform run without a cluster, but kubeconform fetches the Kubernetes
schemas over the network (cached afterwards), so the first run needs network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()
GATE = ROOT / "scripts" / "gate.sh"
VERSION = (ROOT / "VERSION").read_text().strip()

needs_helm = pytest.mark.skipif(
    shutil.which("helm") is None or shutil.which("kubeconform") is None,
    reason="helm/kubeconform not installed",
)

_GOOD_TEMPLATE = """\
{{- if .Values.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Values.name }}
spec:
  selector:
    matchLabels:
      app: {{ .Values.name }}
  template:
    metadata:
      labels:
        app: {{ .Values.name }}
    spec:
      containers:
        - name: app
          image: example.invalid/app:1.0.0
{{- end }}
"""


def _repo(root: Path, *, template: str | None = _GOOD_TEMPLATE, values: str | None = None) -> Path:
    repo = root / "base-fake"
    repo.mkdir()
    (repo / "README.md").write_text("# base-fake\n")
    (repo / "AGENTS.md").write_text(f"# AGENTS.md — base-fake\n# Base: v{VERSION}\n")
    if template is not None:
        chart = repo / "deploy" / "chart"
        (chart / "templates").mkdir(parents=True)
        (chart / "Chart.yaml").write_text(
            "apiVersion: v2\nname: fake\nversion: 0.1.0\nappVersion: 1.0.0\n"
        )
        (chart / "values.yaml").write_text(
            values if values is not None else "enabled: true\nname: fake\n"
        )
        (chart / "templates" / "deploy.yaml").write_text(template)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/acme/base-fake.git"],
        cwd=repo,
        check=True,
    )
    return repo


def _gate(repo: Path, *, path: str | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BASE_")}
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        ["bash", str(GATE), str(repo)], capture_output=True, text=True, timeout=120, env=env
    )


@needs_helm
def test_templates_are_not_parsed_as_yaml(tmp_path: Path) -> None:
    result = _gate(_repo(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "arquivo(s) YAML válidos" in result.stdout


@needs_helm
def test_a_valid_chart_passes_the_chart_step(tmp_path: Path) -> None:
    result = _gate(_repo(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "charts Helm" in result.stdout
    assert "kubeconform" in result.stdout


@needs_helm
def test_broken_chart_fails(tmp_path: Path) -> None:
    template = _GOOD_TEMPLATE.replace(
        ".Values.name }}\nspec", '.Values.must | required "x" }}\nspec'
    )
    result = _gate(_repo(tmp_path, template=template))
    assert result.returncode != 0
    assert "helm template" in result.stdout + result.stderr


@needs_helm
def test_invalid_manifest_fails_kubeconform(tmp_path: Path) -> None:
    template = _GOOD_TEMPLATE.replace(
        "  selector:\n    matchLabels:\n      app: {{ .Values.name }}\n", ""
    )
    result = _gate(_repo(tmp_path, template=template))
    assert result.returncode != 0
    assert "kubeconform" in result.stdout + result.stderr


def test_no_chart_skips(tmp_path: Path) -> None:
    result = _gate(_repo(tmp_path, template=None))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[pulado]" in result.stdout
    assert "nenhum chart" in result.stdout


def test_missing_helm_fails_when_chart_exists(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in (
        "bash",
        "python3",
        "git",
        "find",
        "sort",
        "grep",
        "sed",
        "tr",
        "cat",
        "basename",
        "dirname",
        "tput",
        "node",
    ):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    result = _gate(_repo(tmp_path), path=str(bin_dir))
    assert result.returncode != 0
    assert "brew install helm" in result.stdout + result.stderr
