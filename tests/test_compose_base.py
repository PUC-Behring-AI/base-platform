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


def _base_root(repo_root: Path) -> Path:
    """BASE_ROOT, else the directory beside base-platform's main checkout --
    from a worktree, repo_root.parent is the worktrees directory (#15)."""
    if os.environ.get("BASE_ROOT"):
        return Path(os.environ["BASE_ROOT"]).resolve()
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(common).parent.parent


def _siblings_present(base_root: Path) -> bool:
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
    base_root = _base_root(repo_root)
    if not _siblings_present(base_root):
        pytest.skip(f"sibling repositories not checked out in {base_root}")
    result = subprocess.run(
        ["docker", "compose", "-f", str(repo_root / "compose.base.yaml"), "config"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "BASE_ROOT": str(base_root),
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
