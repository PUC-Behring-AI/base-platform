"""Tests for the pin step of scripts/gate.sh, run in an instance repository.

Each test builds a fake instance under tmp_path -- x-platform with its
base-version.yaml, sometimes an x-knowledge beside it -- and a local git
repository standing in for base-platform's remote, tagged or not. The real
gate runs against them; BASE_PLATFORM_REMOTE points it at the stand-in, so
nothing here touches the network.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()
GATE = ROOT / "scripts" / "gate.sh"
VERSION = (ROOT / "VERSION").read_text().strip()
TAG = f"v{VERSION}"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

WORKFLOW = f"""\
name: ci
on: [pull_request]
jobs:
  harmony:
    uses: acme/base-platform/.github/workflows/harmony.yml@{TAG}
    with:
      base_ref: {TAG}
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          repository: acme/base-platform
          ref: {TAG}
"""

DOCKERFILE = f"""\
ARG BASE_TAG={TAG}
FROM base-knowledge:${{BASE_TAG}} AS build
FROM ghcr.io/acme/base-agents:{TAG}
FROM python:3.13-slim
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **_GIT_ENV}
    )


def _remote(root: Path, *, tagged: bool) -> Path:
    remote = root / "remote"
    remote.mkdir()
    _git(remote, "init", "-q", "-b", "main")
    _git(remote, "commit", "-q", "--allow-empty", "-m", "init")
    if tagged:
        _git(remote, "tag", TAG)
    return remote


def _repo(
    root: Path,
    name: str,
    *,
    base: str = TAG,
    pin: str | None = None,
    workflow: str = WORKFLOW,
    dockerfile: str = DOCKERFILE,
) -> Path:
    repo = root / name
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "README.md").write_text(f"# {name}\n")
    (repo / "AGENTS.md").write_text(f"# AGENTS.md — {name}\n# Base: {base}\n")
    (repo / ".github" / "workflows" / "ci.yml").write_text(workflow)
    (repo / "Dockerfile").write_text(dockerfile)
    if pin is not None:
        (repo / "base-version.yaml").write_text(f"base: {pin}\n")
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _gate(repo: Path, remote: Path, *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BASE_")}
    env["BASE_PLATFORM_REMOTE"] = str(remote)
    return subprocess.run(
        ["bash", str(GATE), str(repo)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


class TestAgreeing:
    def test_a_platform_whose_pins_agree_passes(self, root: Path) -> None:
        repo = _repo(root, "x-platform", pin=VERSION)
        result = _gate(repo, _remote(root, tagged=True))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "5 referência(s) à base" in result.stdout
        assert f"[ok] {TAG} — AGENTS.md" in result.stdout

    def test_another_layer_reads_the_pin_of_its_platform(self, root: Path) -> None:
        _repo(root, "x-platform", pin=VERSION)
        repo = _repo(root, "x-knowledge")
        result = _gate(repo, _remote(root, tagged=True))
        assert result.returncode == 0, result.stdout + result.stderr
        assert str(root / "x-platform" / "base-version.yaml") in result.stdout

    def test_a_base_repository_is_skipped(self, root: Path) -> None:
        repo = _repo(root, "base-thing", workflow="name: ci\non: [push]\njobs: {}\n")
        result = _gate(repo, _remote(root, tagged=False))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "o pino é de cada instância" in result.stdout


class TestDisagreeing:
    def test_a_base_line_that_differs_from_the_pin_fails(self, root: Path) -> None:
        repo = _repo(root, "x-platform", base="v0.0.1", pin=VERSION)
        result = _gate(repo, _remote(root, tagged=True))
        assert result.returncode == 1
        assert "AGENTS.md declara v0.0.1" in result.stderr

    def test_a_workflow_at_main_fails(self, root: Path) -> None:
        workflow = WORKFLOW.replace(f"harmony.yml@{TAG}", "harmony.yml@main")
        repo = _repo(root, "x-platform", pin=VERSION, workflow=workflow)
        result = _gate(repo, _remote(root, tagged=True))
        assert result.returncode == 1
        assert "harmony.yml@main" in result.stderr

    def test_a_base_checkout_without_ref_fails(self, root: Path) -> None:
        workflow = WORKFLOW.replace(f"          ref: {TAG}\n", "")
        repo = _repo(root, "x-platform", pin=VERSION, workflow=workflow)
        result = _gate(repo, _remote(root, tagged=True))
        assert result.returncode == 1
        assert "checkout de acme/base-platform com ref None" in result.stderr

    def test_a_dockerfile_tag_that_differs_fails(self, root: Path) -> None:
        dockerfile = DOCKERFILE.replace(f"base-agents:{TAG}", "base-agents:latest")
        repo = _repo(root, "x-platform", pin=VERSION, dockerfile=dockerfile)
        result = _gate(repo, _remote(root, tagged=True))
        assert result.returncode == 1
        assert "Dockerfile:3: tag latest" in result.stderr

    def test_a_tag_that_does_not_exist_fails(self, root: Path) -> None:
        repo = _repo(root, "x-platform", pin=VERSION)
        result = _gate(repo, _remote(root, tagged=False))
        assert result.returncode == 1
        assert f"a tag {TAG} não existe" in result.stderr

    def test_a_missing_base_version_file_fails_naming_it(self, root: Path) -> None:
        repo = _repo(root, "x-knowledge")
        result = _gate(repo, _remote(root, tagged=True))
        assert result.returncode == 1
        assert str(root / "x-platform" / "base-version.yaml") in result.stderr


class TestFromAWorktree:
    """base-platform#15: from <repo>/.claude/worktrees/<x>, the siblings sit
    beside the main checkout, not beside the worktree."""

    @staticmethod
    def _worktree(repo: Path) -> Path:
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "init")
        worktree = repo / ".claude" / "worktrees" / "wt"
        _git(repo, "worktree", "add", "-q", str(worktree), "-b", "wt")
        return worktree

    def test_the_pin_is_read_beside_the_main_checkout(self, root: Path) -> None:
        _repo(root, "x-platform", pin=VERSION)
        worktree = self._worktree(_repo(root, "x-knowledge"))
        result = _gate(worktree, _remote(root, tagged=True))
        assert result.returncode == 0, result.stdout + result.stderr
        assert str(root.resolve() / "x-platform" / "base-version.yaml") in result.stdout

    def test_the_test_suite_sees_the_base_siblings_of_the_main_checkout(self, root: Path) -> None:
        _repo(root, "x-platform", pin=VERSION)
        (root / "base-knowledge").mkdir()
        repo = _repo(root, "x-knowledge")
        (repo / "pyproject.toml").write_text("")
        (repo / "tests").mkdir()
        expected = str(root.resolve() / "base-knowledge")
        (repo / "tests" / "test_env.py").write_text(
            "import os\n\n\ndef test_env():\n"
            f"    assert os.environ.get('BASE_KNOWLEDGE_DIR') == {expected!r}\n"
        )
        worktree = self._worktree(repo)
        result = _gate(worktree, _remote(root, tagged=True), cwd=worktree)
        assert result.returncode == 0, result.stdout + result.stderr
