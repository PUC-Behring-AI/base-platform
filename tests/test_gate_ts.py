"""Tests for the Node / TypeScript step of scripts/gate.sh.

Each test builds a fake base-* repository under tmp_path, so the pin step is
skipped and only the new step decides the outcome. Nothing here reaches the
network: the package.json files declare no dependencies, so npm ci installs
nothing, and a tool that would need a download (tsc) is expected to fail
loudly instead.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()
GATE = ROOT / "scripts" / "gate.sh"
VERSION = (ROOT / "VERSION").read_text().strip()

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npm") is None,
    reason="node/npm not installed",
)

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _node_major() -> str:
    out = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
    return out.stdout.strip().lstrip("v").split(".")[0]


def _repo(
    root: Path, *, package: bool = True, lockfile: bool = True, nvmrc: str | None = ""
) -> Path:
    repo = root / "base-fake"
    repo.mkdir()
    (repo / "README.md").write_text("# base-fake\n")
    (repo / "AGENTS.md").write_text(f"# AGENTS.md — base-fake\n# Base: v{VERSION}\n")
    if package:
        (repo / "package.json").write_text(
            json.dumps({"name": "base-fake", "version": "0.0.0", "private": True})
        )
    if lockfile:
        (repo / "package-lock.json").write_text(
            json.dumps(
                {
                    "name": "base-fake",
                    "version": "0.0.0",
                    "lockfileVersion": 3,
                    "requires": True,
                    "packages": {"": {"name": "base-fake", "version": "0.0.0"}},
                }
            )
        )
    if nvmrc is not None:
        (repo / ".nvmrc").write_text((nvmrc or _node_major()) + "\n")
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env={**os.environ, **_GIT_ENV}
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/acme/base-fake.git"],
        cwd=repo,
        check=True,
    )
    return repo


def _gate(repo: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BASE_")}
    return subprocess.run(
        ["bash", str(GATE), str(repo)], capture_output=True, text=True, timeout=120, env=env
    )


def test_a_repository_without_package_json_skips_the_step(tmp_path: Path) -> None:
    result = _gate(_repo(tmp_path, package=False, lockfile=False, nvmrc=None))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sem package.json" in result.stdout


def test_package_json_without_a_lockfile_fails(tmp_path: Path) -> None:
    result = _gate(_repo(tmp_path, lockfile=False))
    assert result.returncode != 0
    assert "package-lock.json" in result.stdout + result.stderr


def test_package_json_without_nvmrc_fails(tmp_path: Path) -> None:
    result = _gate(_repo(tmp_path, nvmrc=None))
    assert result.returncode != 0
    assert ".nvmrc" in result.stdout + result.stderr


def test_a_node_major_other_than_nvmrc_fails(tmp_path: Path) -> None:
    other = str(int(_node_major()) + 1)
    result = _gate(_repo(tmp_path, nvmrc=other))
    assert result.returncode != 0
    assert f".nvmrc pede {other}" in result.stdout + result.stderr


def test_tsconfig_without_typescript_installed_fails_loudly(tmp_path: Path) -> None:
    """A type check that cannot run is a failure, not a skip."""
    repo = _repo(tmp_path)
    (repo / "tsconfig.json").write_text("{}\n")
    result = _gate(repo)
    assert result.returncode != 0
    assert "tsc" in result.stdout + result.stderr


def test_a_project_with_nothing_to_check_passes_and_says_what_it_skipped(tmp_path: Path) -> None:
    result = _gate(_repo(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "dependências instaladas do lockfile" in result.stdout
    assert "sem tsconfig.json" in result.stdout
    assert "vitest não está nas dependências" in result.stdout
