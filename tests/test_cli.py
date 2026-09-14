"""Tests for ./base-platform, the thin cross-layer CLI.

Everything here runs the script as a subprocess with no Docker and no
sibling repositories checked out -- --dry-run and --help are the two paths
that make no external call, by design, so CI can verify them without the
infrastructure compose.base.yaml itself needs. See tests/test_compose_base.py
for the checks that do need Docker and the siblings.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).parent.parent.resolve()


def _run(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(repo_root / "base-platform"), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


class TestHelp:
    def test_help_exits_zero(self, repo_root: Path) -> None:
        result = _run(repo_root, "--help")
        assert result.returncode == 0

    def test_help_names_every_subcommand(self, repo_root: Path) -> None:
        result = _run(repo_root, "--help")
        for subcommand in ("up", "down", "status", "logs"):
            assert subcommand in result.stdout

    def test_no_args_prints_quick_start_without_failing(self, repo_root: Path) -> None:
        result = _run(repo_root)
        assert result.returncode == 0
        assert "base-platform" in result.stdout


class TestDryRun:
    def test_up_dry_run_prints_the_compose_command(self, repo_root: Path) -> None:
        result = _run(repo_root, "up", "--dry-run")
        assert result.returncode == 0
        assert "docker compose -f" in result.stdout
        assert "compose.base.yaml up -d" in result.stdout

    def test_up_dry_run_does_not_check_siblings(self, repo_root: Path) -> None:
        """Dry-run only echoes the command -- it must not fail just because
        this checkout has no sibling repositories next to it (true in CI)."""
        result = _run(repo_root, "up", "--dry-run")
        assert result.returncode == 0

    def test_up_rejects_an_unknown_flag(self, repo_root: Path) -> None:
        result = _run(repo_root, "up", "--not-a-real-flag")
        assert result.returncode != 0
        assert "--not-a-real-flag" in result.stderr


class TestUnknownCommand:
    def test_unknown_command_is_refused_and_named(self, repo_root: Path) -> None:
        result = _run(repo_root, "frobnicate")
        assert result.returncode != 0
        assert "frobnicate" in result.stderr
