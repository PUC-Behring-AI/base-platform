"""Tests for scripts/leak-check.sh, the denylist check of the shared gate.

Each test builds a throwaway git repository under tmp_path and a denylist of
neutral terms. The point the output assertions guard: a hit is reported by
place and term number, never by the term -- this repository's logs are public.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.resolve() / "scripts" / "leak-check.sh"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

TERMS = "\nzorblax\n  acme  \n"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    ).stdout.strip()


def _commit(repo: Path, files: dict[str, str], message: str = "init") -> None:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _run(repo: Path, **env: str) -> subprocess.CompletedProcess:
    clean = {
        k: v
        for k, v in os.environ.items()
        if k not in ("BASE_DENYLIST", "BASE_DENYLIST_FILE", "LEAK_CHECK_RANGE", "PR_BODY")
    }
    return subprocess.run(
        ["bash", str(SCRIPT), str(repo)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**clean, **env},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "base-thing"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _commit(path, {"README.md": "a neutral readme\n"})
    return path


def _assert_no_term(result: subprocess.CompletedProcess) -> None:
    out = (result.stdout + result.stderr).lower()
    assert "zorblax" not in out
    assert "acme" not in out


class TestHits:
    def test_a_term_in_a_file_fails_without_printing_it(self, repo: Path) -> None:
        _commit(repo, {"docs/notes.md": "line one\nbuilt for ZORBLAX here\n"})
        result = _run(repo, BASE_DENYLIST=TERMS)
        assert result.returncode == 1
        assert "docs/notes.md:2: termo #1" in result.stderr
        _assert_no_term(result)

    def test_a_term_in_a_path_is_reported_by_position(self, repo: Path) -> None:
        _commit(repo, {"acme-knowledge/x.md": "acme inside too\n"})
        result = _run(repo, BASE_DENYLIST=TERMS)
        assert result.returncode == 1
        assert "de git ls-files: termo #2" in result.stderr
        assert "(caminho com termo):1: termo #2" in result.stderr
        _assert_no_term(result)

    def test_a_term_in_a_commit_message_in_the_range_fails(self, repo: Path) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        _commit(repo, {"a.md": "clean\n"}, message="feat: thing\n\nfor acme")
        result = _run(repo, BASE_DENYLIST=TERMS, LEAK_CHECK_RANGE=f"{base}..HEAD")
        assert result.returncode == 1
        assert "linha 3: termo #2" in result.stderr
        _assert_no_term(result)

    def test_a_term_in_the_pr_body_fails(self, repo: Path) -> None:
        result = _run(repo, BASE_DENYLIST=TERMS, PR_BODY="summary\n\nAcme asked for it")
        assert result.returncode == 1
        assert "corpo do PR, linha 3: termo #2" in result.stderr
        _assert_no_term(result)

    def test_the_list_can_come_from_a_file(self, repo: Path, tmp_path: Path) -> None:
        _commit(repo, {"a.md": "zorblax\n"})
        listing = tmp_path / "denylist"
        listing.write_text(TERMS)
        result = _run(repo, BASE_DENYLIST_FILE=str(listing))
        assert result.returncode == 1
        assert "a.md:1: termo #1" in result.stderr


class TestPasses:
    def test_no_hit_passes(self, repo: Path) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        _commit(repo, {"a.md": "zorblaxian acmeish words\n"}, message="docs: neutral")
        result = _run(
            repo, BASE_DENYLIST=TERMS, LEAK_CHECK_RANGE=f"{base}..HEAD", PR_BODY="neutral"
        )
        assert result.returncode == 0, result.stderr
        assert "[ok]" in result.stdout
        _assert_no_term(result)


class TestNotActive:
    def test_no_list_warns_that_nothing_was_checked(self, repo: Path) -> None:
        _commit(repo, {"a.md": "zorblax\n"})
        result = _run(repo)
        assert result.returncode == 0
        assert "NÃO está ativa" in result.stdout

    def test_in_ci_the_warning_is_an_annotation(self, repo: Path) -> None:
        result = _run(repo, GITHUB_ACTIONS="true")
        assert "::warning::leak check is NOT active" in result.stdout

    def test_a_missing_list_file_fails(self, repo: Path, tmp_path: Path) -> None:
        result = _run(repo, BASE_DENYLIST_FILE=str(tmp_path / "nope"))
        assert result.returncode == 1

    def test_an_empty_list_fails(self, repo: Path) -> None:
        result = _run(repo, BASE_DENYLIST="\n  \n")
        assert result.returncode == 1
        assert "vazia" in result.stderr
