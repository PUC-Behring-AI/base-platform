"""Tests for compose.base.yaml, the one file that composes all five layers.

Skipped if `docker` is not on PATH, or if the sibling repositories are not
checked out where compose.base.yaml expects them (see its own header
comment on layout) -- these are integration checks against real files on
disk, not something a schema test can substitute for.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


def _siblings_present(repo_root: Path) -> bool:
    base_root = repo_root.parent
    return all(
        (base_root / name / "compose.yaml").exists()
        or (base_root / name / "docker-compose.yml").exists()
        for name in ("base-knowledge", "base-inference", "base-agents", "base-interface")
    )


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def composed(repo_root: Path) -> dict:
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    if not _siblings_present(repo_root):
        pytest.skip("sibling repositories not checked out next to base-platform")
    result = subprocess.run(
        ["docker", "compose", "-f", str(repo_root / "compose.base.yaml"), "config"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "GRAFANA_ADMIN_PASSWORD": "x",
            "POSTGRES_PASSWORD": "x",
            "UI_PASSWORD": "x",
            "LITELLM_MASTER_KEY": "x",
        },
    )
    assert result.returncode == 0, result.stderr
    return yaml.safe_load(result.stdout)


class TestOpenWebUIWaitsOnLiteLLM:
    """base-interface/compose.yaml cannot declare this dependency itself --
    litellm is not defined there. This is the merge that puts it back."""

    def test_depends_on_litellm_healthy(self, composed: dict) -> None:
        depends = composed["services"]["open-webui"]["depends_on"]
        assert depends["litellm"]["condition"] == "service_healthy"
