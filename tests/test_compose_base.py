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


# The files that make up compose.base.yaml, read as written: compose v5
# merges two different definitions of one network without a word, so the
# merged config cannot show a divergence (base-knowledge#23).
_FRAGMENTS = (
    "base-knowledge/compose.yaml",
    "base-inference/docker-compose.yml",
    "base-agents/compose.yaml",
    "base-interface/compose.yaml",
    "base-platform/compose.yaml",
    "base-platform/compose.wiring.observability.yaml",
)


@pytest.fixture
def fragments(repo_root: Path) -> dict[str, dict]:
    base_root = _base_root(repo_root)
    if not _siblings_present(base_root):
        pytest.skip(f"sibling repositories not checked out in {base_root}")
    loaded = {}
    for relative in _FRAGMENTS:
        if relative.startswith("base-platform/"):
            path = repo_root / Path(relative).name
        else:
            path = base_root / relative
        loaded[relative] = yaml.safe_load(path.read_text()) or {}
    return loaded


class TestBaseInternalNetwork:
    """The network knowledge lives on, with no route out (base-knowledge#23)."""

    def test_every_declaration_is_the_same(self, fragments: dict[str, dict]) -> None:
        declared = {
            name: (fragment.get("networks") or {})["base-internal"]
            for name, fragment in fragments.items()
            if "base-internal" in (fragment.get("networks") or {})
        }
        assert declared, "no fragment declares base-internal"
        assert all(d == {"internal": True} for d in declared.values()), declared

    @pytest.mark.parametrize("service", ["agents", "litellm", "prometheus"])
    def test_whoever_reaches_knowledge_joins_it(self, composed: dict, service: str) -> None:
        assert "base-internal" in composed["services"][service]["networks"]

    def test_it_has_no_route_out(self, composed: dict) -> None:
        assert composed["networks"]["base-internal"]["internal"] is True


class TestInterfaceNetworks:
    """The interface BFF's networks (base-interface specs/interface-socket.md
    §3.7, §3.11). Each declared identically wherever it appears, for the same
    reason as base-internal."""

    @pytest.mark.parametrize("network", ["interface-agents", "interface-metrics"])
    def test_every_declaration_is_the_same(
        self, fragments: dict[str, dict], network: str
    ) -> None:
        declared = {
            name: (fragment.get("networks") or {})[network]
            for name, fragment in fragments.items()
            if network in (fragment.get("networks") or {})
        }
        assert declared, f"no fragment declares {network}"
        assert all(d == {"internal": True} for d in declared.values()), declared

    def test_agents_joins_interface_agents(self, composed: dict) -> None:
        assert "interface-agents" in composed["services"]["agents"]["networks"]

    def test_the_metrics_backend_joins_interface_metrics(self, composed: dict) -> None:
        assert "interface-metrics" in composed["services"]["prometheus"]["networks"]
