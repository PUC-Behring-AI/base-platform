"""Tests for scripts/harmony.sh, the gate of the whole set of repositories.

Each test builds fake sibling repositories under tmp_path -- a git repo with
an AGENTS.md declaring "# Base:" and a scripts/gate.sh that passes, fails, or
records what it saw -- and points BASE_ROOT at them. No real sibling is
touched, so this runs in CI where only base-platform is checked out.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.resolve() / "scripts" / "harmony.sh"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **_GIT_ENV}
    )


def _make_repo(root: Path, name: str, *, gate: str | None = "exit 0", base: str = "v0.4.0") -> Path:
    repo = root / name
    (repo / "scripts").mkdir(parents=True)
    (repo / "AGENTS.md").write_text(f"# AGENTS.md — {name}\n# Base: {base}\n")
    if gate is not None:
        gate_file = repo / "scripts" / "gate.sh"
        gate_file.write_text(f"#!/usr/bin/env bash\n{gate}\n")
        gate_file.chmod(0o755)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _run(root: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BASE_")}
    env["BASE_ROOT"] = str(root)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd or root,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


class TestDiscovery:
    def test_runs_every_gate_and_passes(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        _make_repo(root, "base-knowledge")
        result = _run(root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "| base-platform | main | v0.4.0 | pass |" in result.stdout
        assert "| base-knowledge | main | v0.4.0 | pass |" in result.stdout

    def test_ignores_directories_without_a_base_line(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        (root / "unrelated").mkdir()
        (root / "unrelated" / "AGENTS.md").write_text("# not part of the base\n")
        result = _run(root)
        assert result.returncode == 0
        assert "unrelated" not in result.stdout

    def test_fails_when_nothing_is_found(self, root: Path) -> None:
        result = _run(root)
        assert result.returncode == 1
        assert "no repository of the base" in result.stderr


class TestFailures:
    def test_a_failing_sibling_fails_the_whole_run(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        _make_repo(root, "base-agents", gate="echo broken-by-sibling; exit 1")
        result = _run(root)
        assert result.returncode == 1
        assert "broken-by-sibling" in result.stdout
        assert "Harmony failed" in result.stdout

    def test_a_sibling_without_a_gate_fails(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        _make_repo(root, "x-like", gate=None)
        result = _run(root)
        assert result.returncode == 1
        assert "no scripts/gate.sh" in result.stdout


class TestWarnings:
    def test_a_sibling_off_its_default_branch_warns(self, root: Path) -> None:
        repo = _make_repo(root, "base-platform")
        _git(repo, "switch", "-q", "-c", "feature")
        result = _run(root)
        assert result.returncode == 0
        assert "off main (feature, 0 uncommitted)" in result.stdout

    def test_a_layer_named_repository_without_a_base_line_warns(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        bare = root / "x-platform"
        bare.mkdir()
        _git(bare, "init", "-q", "-b", "main")
        result = _run(root)
        assert result.returncode == 0
        assert "not checked" in result.stdout and "x-platform" in result.stdout

    def test_no_left_out_warning_when_a_worktree_of_it_was_checked(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        main = root / "x-platform"
        main.mkdir()
        _git(main, "init", "-q", "-b", "main")
        (main / "README.md").write_text("x\n")
        _git(main, "add", "-A")
        _git(main, "commit", "-q", "-m", "init")
        worktree = root / "x-platform-wt"
        _git(main, "worktree", "add", "-q", str(worktree), "-b", "wt")
        (worktree / "AGENTS.md").write_text("# Base: v0.4.0\n")
        (worktree / "scripts").mkdir()
        (worktree / "scripts" / "gate.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        (worktree / "scripts" / "gate.sh").chmod(0o755)
        result = _run(root, cwd=worktree)
        assert result.returncode == 0, result.stdout
        assert "| x-platform | wt |" in result.stdout
        assert "not checked" not in result.stdout

    def test_divergent_base_lines_warn(self, root: Path) -> None:
        _make_repo(root, "base-platform", base="v0.4.0")
        _make_repo(root, "base-knowledge", base="v0.2.0")
        result = _run(root)
        assert result.returncode == 0
        assert "different base versions" in result.stdout


class TestWhichWorkingTree:
    def test_the_main_checkout_wins_over_a_worktree(self, root: Path) -> None:
        main = _make_repo(root, "base-knowledge", gate="echo from-main")
        _git(main, "worktree", "add", "-q", str(root / "base-knowledge-wt"), "-b", "wt")
        result = _run(root)
        assert result.returncode == 0
        assert str(root / "base-knowledge-wt") not in result.stdout
        assert "| base-knowledge | main |" in result.stdout

    def test_running_from_a_worktree_uses_that_worktree(self, root: Path) -> None:
        main = _make_repo(root, "base-knowledge")
        worktree = root / "base-knowledge-wt"
        _git(main, "worktree", "add", "-q", str(worktree), "-b", "wt")
        result = _run(root, cwd=worktree)
        assert result.returncode == 0
        assert "| base-knowledge | wt |" in result.stdout

    def test_exports_each_chosen_path_to_every_gate(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        main = _make_repo(root, "base-knowledge")
        worktree = root / "base-knowledge-wt"
        _git(main, "worktree", "add", "-q", str(worktree), "-b", "wt")
        _make_repo(root, "base-agents", gate='echo "saw=$BASE_KNOWLEDGE_DIR"; exit 1')
        result = _run(root, str(worktree))
        assert f"saw={worktree}" in result.stdout

    def test_only_checks_exactly_the_paths_given(self, root: Path) -> None:
        platform = _make_repo(root, "base-platform")
        _make_repo(root, "x-platform", gate="echo red-outsider; exit 1")
        result = _run(root, "--only", str(platform), cwd=root / "x-platform")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "| base-platform | main |" in result.stdout
        assert "x-platform" not in result.stdout

    def test_only_without_a_path_is_refused(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        result = _run(root, "--only")
        assert result.returncode == 2
        assert "--only needs" in result.stderr

    def test_a_path_outside_the_base_is_refused(self, root: Path) -> None:
        _make_repo(root, "base-platform")
        (root / "elsewhere").mkdir()
        result = _run(root, str(root / "elsewhere"))
        assert result.returncode == 2
        assert "not a repository of the base" in result.stderr
