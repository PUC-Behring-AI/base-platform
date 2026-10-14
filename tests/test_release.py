"""Tests for scripts/release.sh, the only way the base is tagged.

Each test builds the five base repositories under tmp_path, each a git repo
with a bare origin, an AGENTS.md declaring "# Base:" and a scripts/gate.sh,
and points BASE_ROOT at them. No real repository or remote is touched.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.resolve() / "scripts" / "release.sh"
REPOS = ["base-platform", "base-knowledge", "base-inference", "base-agents", "base-interface"]

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    ).stdout


def _make_repo(root: Path, name: str, *, base: str, gate: str = "exit 0") -> Path:
    origin = root / "origins" / f"{name}.git"
    origin.mkdir(parents=True)
    _git(origin, "init", "-q", "--bare", "-b", "main")
    repo = root / name
    (repo / "scripts").mkdir(parents=True)
    (repo / "AGENTS.md").write_text(f"# AGENTS.md — {name}\n# Base: {base}\n")
    gate_file = repo / "scripts" / "gate.sh"
    gate_file.write_text(f"#!/usr/bin/env bash\n{gate}\n")
    gate_file.chmod(0o755)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _make_set(root: Path, *, version: str = "0.5.0", dated: bool = True, **bases: str) -> None:
    for name in REPOS:
        _make_repo(root, name, base=bases.get(name.replace("-", "_"), f"v{version}"))
    platform = root / "base-platform"
    (platform / "VERSION").write_text(f"{version}\n")
    date = "2026-10-20" if dated else "unreleased"
    (platform / "CHANGELOG.md").write_text(f"# Changelog\n\n## [{version}] — {date}\n")
    _git(platform, "add", "-A")
    _git(platform, "commit", "-q", "-m", "version")
    _git(platform, "push", "-q", "origin", "main")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BASE_")}
    env["BASE_ROOT"] = str(root)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        env={**env, **_GIT_ENV},
    )


def _origin_tags(root: Path, name: str) -> str:
    return _git(root / "origins" / f"{name}.git", "tag", "-l")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


class TestReady:
    def test_without_tag_it_checks_and_tags_nothing(self, root: Path) -> None:
        _make_set(root)
        result = _run(root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Ready" in result.stdout
        assert all(_origin_tags(root, name) == "" for name in REPOS)

    def test_with_tag_it_tags_and_pushes_the_five(self, root: Path) -> None:
        _make_set(root)
        result = _run(root, "--tag")
        assert result.returncode == 0, result.stdout + result.stderr
        for name in REPOS:
            assert _origin_tags(root, name).split() == ["v0.5.0"]
            head = _git(root / name, "rev-parse", "HEAD").strip()
            tagged = _git(root / name, "rev-parse", "v0.5.0^{commit}").strip()
            assert tagged == head


class TestRefusals:
    def test_a_layer_behind_the_version_refuses(self, root: Path) -> None:
        _make_set(root, base_knowledge="v0.4.0")
        result = _run(root, "--tag")
        assert result.returncode == 1
        assert "base-knowledge: declares 'v0.4.0', not v0.5.0" in result.stderr
        assert all(_origin_tags(root, name) == "" for name in REPOS)

    def test_an_undated_changelog_refuses(self, root: Path) -> None:
        _make_set(root, dated=False)
        result = _run(root)
        assert result.returncode == 1
        assert "has no date" in result.stderr

    def test_an_existing_tag_refuses(self, root: Path) -> None:
        _make_set(root)
        _git(root / "base-agents", "tag", "v0.5.0")
        _git(root / "base-agents", "push", "-q", "origin", "v0.5.0")
        _git(root / "base-agents", "tag", "-d", "v0.5.0")
        result = _run(root)
        assert result.returncode == 1
        assert "base-agents: v0.5.0 already exists on origin" in result.stderr

    def test_uncommitted_changes_refuse(self, root: Path) -> None:
        _make_set(root)
        (root / "base-inference" / "stray.txt").write_text("x\n")
        result = _run(root)
        assert result.returncode == 1
        assert "base-inference: uncommitted changes" in result.stderr

    def test_a_commit_not_on_origin_refuses(self, root: Path) -> None:
        _make_set(root)
        (root / "base-interface" / "local.txt").write_text("x\n")
        _git(root / "base-interface", "add", "-A")
        _git(root / "base-interface", "commit", "-q", "-m", "local")
        result = _run(root)
        assert result.returncode == 1
        assert "base-interface: HEAD is not origin/main" in result.stderr

    def test_a_missing_repository_refuses(self, root: Path) -> None:
        _make_set(root)
        subprocess.run(["rm", "-rf", str(root / "base-agents")], check=True)
        result = _run(root)
        assert result.returncode == 1
        assert "base-agents: no main checkout" in result.stderr

    def test_a_red_gate_refuses(self, root: Path) -> None:
        _make_set(root)
        gate = root / "base-knowledge" / "scripts" / "gate.sh"
        gate.write_text("#!/usr/bin/env bash\nexit 1\n")
        _git(root / "base-knowledge", "commit", "-q", "-am", "red")
        _git(root / "base-knowledge", "push", "-q", "origin", "main")
        result = _run(root, "--tag")
        assert result.returncode == 1
        assert "harmony.sh failed" in result.stderr
        assert all(_origin_tags(root, name) == "" for name in REPOS)

    def test_an_unknown_argument_is_refused(self, root: Path) -> None:
        _make_set(root)
        assert _run(root, "--force").returncode == 2
