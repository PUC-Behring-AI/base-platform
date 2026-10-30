"""Tests for scripts/publish-release.sh, which builds a release's charts and
engine images and attaches them to each engine repository's GitHub Release.

Each test builds the five base repositories under tmp_path, each a clone of a
bare origin with an annotated tag, and puts stub `docker`, `helm` and `gh` on
PATH: they record their arguments, docker writes a tar of the build context it
was given to the --output dest, helm packages the chart directory, and gh
answers from a per-repository file of attached assets. No real repository,
registry, image or release is touched.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.resolve() / "scripts" / "publish-release.sh"
ENGINES = {
    "base-knowledge": ("base-knowledge", "."),
    "base-inference": ("base-inference-stand-in", "stand-in"),
    "base-agents": ("base-agents", "."),
    "base-interface": ("base-interface", "."),
}
REPOS = ["base-platform", *ENGINES]
ORG = "test-org"
TAG = "v0.5.0"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

_DOCKER = r"""
case "$1 $2" in
  "buildx inspect") exit 0 ;;
  "buildx build") ;;
  *) exit 1 ;;
esac
dest=""; ctx=""
while [ $# -gt 0 ]; do
  case "$1" in
    --output) dest="${2##*dest=}"; shift ;;
    --builder|--platform|--label) shift ;;
    *) ctx="$1" ;;
  esac
  shift
done
echo "context $ctx" >> "$CALLS"
tar -cf "$dest" -C "$ctx" .
"""

_HELM = r"""
[ "$1" = package ] || exit 1
chart="$2"; out="$4"
name="$(sed -n 's/^name: *//p' "$chart/Chart.yaml")"
version="$(sed -n 's/^version: *//p' "$chart/Chart.yaml")"
mkdir -p "$out"
tar -cf "$out/$name-$version.tgz" -C "$chart" .
"""

_GH = r"""
if [ "$1" = api ]; then
  repo="$(echo "$2" | cut -d/ -f3)"
  if [ -f "$GH_STATE/$repo.assets" ]; then cat "$GH_STATE/$repo.assets"; exit 0; fi
  echo "gh: Not Found (HTTP 404)" >&2
  exit 1
fi
for a in "$@"; do
  case "$a" in *.md) cp "$a" "$GH_STATE/notes-seen.md" ;; esac
done
exit 0
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    ).stdout


def _make_repo(root: Path, name: str, files: dict[str, str]) -> Path:
    origin = root / "origins" / f"{name}.git"
    origin.mkdir(parents=True)
    _git(origin, "init", "-q", "--bare", "-b", "main")
    repo = root / name
    repo.mkdir()
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    _git(repo, "init", "-q", "-b", "main")
    # The configured origin names the organisation; insteadOf sends it to the
    # local bare repository.
    _git(repo, "remote", "add", "origin", f"https://github.com/{ORG}/{name}.git")
    _git(repo, "config", f"url.{root}/origins/.insteadOf", f"https://github.com/{ORG}/")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(repo, "tag", "-a", TAG, "-m", f"base {TAG}")
    _git(repo, "push", "-q", "origin", TAG)
    return repo


def _make_set(root: Path, *, version: str = "0.5.0", chart: dict[str, str] | None = None) -> None:
    _make_repo(
        root,
        "base-platform",
        {
            "VERSION": f"{version}\n",
            "CHANGELOG.md": (
                "# Changelog\n\n## [Unreleased]\n\n## [0.5.0] — 2026-10-20\n\n"
                "### Added\n\n- **A thing.**\n\n## [0.4.0] — 2026-10-01\n\n- older\n"
            ),
        },
    )
    for name, (_, context) in ENGINES.items():
        _make_repo(
            root,
            name,
            {
                "deploy/chart/Chart.yaml": (
                    f"apiVersion: v2\nname: {name}\nversion: {(chart or {}).get(name, '0.5.0')}\n"
                ),
                f"{context}/Dockerfile": "FROM scratch\n",
                f"{context}/app.txt": "tracked\n",
            },
        )


def _stubs(tmp_path: Path) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    state = tmp_path / "gh-state"
    state.mkdir()
    for tool, body in {"docker": _DOCKER, "helm": _HELM, "gh": _GH}.items():
        (bin_dir / tool).write_text(f'#!/bin/bash\necho "{tool} $*" >> "$CALLS"\n{body}\n')
        (bin_dir / tool).chmod(0o755)
    return bin_dir, calls, state


@pytest.fixture
def env(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    bin_dir, calls, state = _stubs(tmp_path)
    return root, bin_dir, calls, state


def _run(env, *args: str) -> subprocess.CompletedProcess:
    root, bin_dir, calls, state = env
    environ = {k: v for k, v in os.environ.items() if not k.startswith("BASE_")}
    environ.update(_GIT_ENV)
    environ.update(
        {
            "BASE_ROOT": str(root),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "XDG_CACHE_HOME": str(root.parent / "cache"),
            "CALLS": str(calls),
            "GH_STATE": str(state),
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        env=environ,
    )


def _out(env) -> Path:
    return env[0].parent / "cache" / "base-publish" / TAG


def _calls(env, tool: str) -> list[str]:
    calls = env[2]
    if not calls.exists():
        return []
    return [line for line in calls.read_text().splitlines() if line.startswith(f"{tool} ")]


def _sums(directory: Path) -> dict[str, str]:
    rows = [line.split("  ") for line in (directory / "SHA256SUMS").read_text().splitlines()]
    return {file: digest for digest, file in rows}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _attach_all(env, *, differ: str | None = None) -> None:
    """Make every release hold exactly what was built, `differ` with another
    digest."""
    state = env[3]
    for name in ENGINES:
        directory = _out(env) / name
        lines = []
        for file in [*_sums(directory), "SHA256SUMS"]:
            digest = "0" * 64 if file == differ else _sha(directory / file)
            lines.append(f"{file} sha256:{digest}")
        (state / f"{name}.assets").write_text("\n".join(lines) + "\n")


class TestRefusals:
    def test_a_missing_tag_refuses(self, env) -> None:
        _make_set(env[0])
        _git(env[0] / "base-agents", "tag", "-d", TAG)
        result = _run(env, TAG)
        assert result.returncode == 1
        assert f"base-agents: no tag {TAG}" in result.stderr
        assert _calls(env, "docker") == []

    def test_a_lightweight_tag_refuses(self, env) -> None:
        _make_set(env[0])
        repo = env[0] / "base-knowledge"
        _git(repo, "tag", "-d", TAG)
        _git(repo, "tag", TAG)
        _git(repo, "push", "-q", "-f", "origin", TAG)
        result = _run(env, TAG)
        assert result.returncode == 1
        assert f"base-knowledge: {TAG} is a lightweight tag" in result.stderr

    def test_a_tag_that_differs_from_origin_refuses(self, env) -> None:
        _make_set(env[0])
        repo = env[0] / "base-interface"
        (repo / "late.txt").write_text("x\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "late")
        _git(repo, "tag", "-f", "-a", TAG, "-m", "moved")
        result = _run(env, TAG)
        assert result.returncode == 1
        assert f"base-interface: local {TAG} is" in result.stderr
        assert "origin's is" in result.stderr

    def test_a_version_mismatch_refuses(self, env) -> None:
        _make_set(env[0], version="0.4.0")
        result = _run(env, TAG)
        assert result.returncode == 1
        assert f"base-platform: VERSION at {TAG} is '0.4.0', not 0.5.0" in result.stderr

    def test_a_chart_version_mismatch_refuses(self, env) -> None:
        _make_set(env[0], chart={"base-inference": "0.4.0"})
        result = _run(env, TAG)
        assert result.returncode == 1
        assert (
            f"base-inference: deploy/chart/Chart.yaml at {TAG} is version '0.4.0', not 0.5.0"
            in result.stderr
        )

    def test_an_unknown_argument_is_refused(self, env) -> None:
        _make_set(env[0])
        assert _run(env, TAG, "--force").returncode == 2


class TestBuild:
    def test_builds_from_the_tag_not_the_working_tree(self, env) -> None:
        _make_set(env[0])
        repo = env[0] / "base-knowledge"
        (repo / "stray.txt").write_text("untracked\n")
        (repo / "app.txt").write_text("edited, not committed\n")
        result = _run(env, TAG, "--platforms", "linux/arm64")
        assert result.returncode == 0, result.stdout + result.stderr
        contexts = [c.split(" ", 1)[1] for c in _calls(env, "context")]
        assert contexts and not any(c.startswith(str(env[0])) for c in contexts)
        image = _out(env) / "base-knowledge" / f"base-knowledge-{TAG}-linux-arm64.tar.gz"
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(image.read_bytes()))) as tar:
            names = tar.getnames()
            assert "./app.txt" in names
            assert "./stray.txt" not in names
            assert tar.extractfile("./app.txt").read() == b"tracked\n"

    def test_each_image_is_built_per_platform_with_its_labels(self, env) -> None:
        _make_set(env[0])
        result = _run(env, TAG)
        assert result.returncode == 0, result.stdout + result.stderr
        builds = [c for c in _calls(env, "docker") if c.startswith("docker buildx build")]
        assert len(builds) == 8
        commit = _git(env[0] / "base-inference", "rev-parse", f"{TAG}^{{commit}}").strip()
        stand_in = [b for b in builds if f"name=base-inference-stand-in:{TAG}" in b]
        assert len(stand_in) == 2
        for b in stand_in:
            assert "--builder base-multiarch" in b
            assert f"--label org.opencontainers.image.version={TAG}" in b
            assert f"--label org.opencontainers.image.revision={commit}" in b
            assert b.endswith("/base-inference/stand-in")
        assert {b.split("--platform ")[1].split()[0] for b in builds} == {
            "linux/arm64",
            "linux/amd64",
        }

    def test_sums_manifest_and_lock(self, env) -> None:
        _make_set(env[0])
        result = _run(env, TAG)
        assert result.returncode == 0, result.stdout + result.stderr
        out = _out(env)
        lock = (out / "lock.sha256").read_text().splitlines()
        assert lock[0] == f"# base {TAG}"
        assert all(line in result.stdout.splitlines() for line in lock)
        locked = {line.split("  ")[1]: line.split("  ")[0] for line in lock[1:]}
        for name, (image, _) in ENGINES.items():
            directory = out / name
            files = [
                f"{name}-0.5.0.tgz",
                f"{image}-{TAG}-linux-arm64.tar.gz",
                f"{image}-{TAG}-linux-amd64.tar.gz",
                "manifest.json",
            ]
            sums = _sums(directory)
            assert list(sums) == files
            for file in [*files, "SHA256SUMS"]:
                assert locked[f"{name}/{file}"] == _sha(directory / file)
            for file in files:
                assert sums[file] == _sha(directory / file)
            manifest = json.loads((directory / "manifest.json").read_text())
            commit = _git(env[0] / name, "rev-parse", f"{TAG}^{{commit}}").strip()
            assert manifest["repo"] == name
            assert manifest["tag"] == TAG
            assert manifest["commit"] == commit
            assert manifest["chart"] == {
                "file": f"{name}-0.5.0.tgz",
                "name": name,
                "version": "0.5.0",
                "sha256": sums[f"{name}-0.5.0.tgz"],
            }
            assert manifest["images"] == [
                {
                    "ref": f"{image}:{TAG}",
                    "platform": f"linux/{arch}",
                    "file": f"{image}-{TAG}-linux-{arch}.tar.gz",
                    "sha256": sums[f"{image}-{TAG}-linux-{arch}.tar.gz"],
                }
                for arch in ("arm64", "amd64")
            ]
        assert not (out / "base-platform").exists()
        assert not any(k.startswith("base-platform/") for k in locked)

    def test_a_rerun_reuses_what_still_matches_and_rebuilds_the_rest(self, env) -> None:
        _make_set(env[0])
        assert _run(env, TAG, "--platforms", "linux/arm64").returncode == 0
        env[2].unlink()
        tampered = _out(env) / "base-agents" / f"base-agents-{TAG}-linux-arm64.tar.gz"
        tampered.write_bytes(b"not the image")
        result = _run(env, TAG)
        assert result.returncode == 0, result.stdout + result.stderr
        builds = [c for c in _calls(env, "docker") if c.startswith("docker buildx build")]
        rebuilt = sorted(
            b.split("name=")[1].split(",")[0] + " " + b.split("--platform ")[1].split()[0]
            for b in builds
        )
        assert rebuilt == sorted(
            [f"base-agents:{TAG} linux/arm64"]
            + [f"{image}:{TAG} linux/amd64" for image, _ in ENGINES.values()]
        )
        assert _calls(env, "helm") == []


class TestUpload:
    def test_a_dry_run_uploads_nothing(self, env) -> None:
        _make_set(env[0])
        result = _run(env, TAG, "--platforms", "linux/arm64")
        assert result.returncode == 0, result.stdout + result.stderr
        assert _calls(env, "gh") == []
        assert "Dry run: nothing uploaded" in result.stdout
        assert f"{ORG}/base-knowledge release {TAG}:" in result.stdout
        assert "base-platform: no assets." in result.stdout

    def test_upload_creates_the_release_and_attaches_every_asset(self, env) -> None:
        _make_set(env[0])
        result = _run(env, TAG, "--upload")
        assert result.returncode == 0, result.stdout + result.stderr
        gh = _calls(env, "gh")
        creates = [c for c in gh if c.startswith("gh release create")]
        uploads = [c for c in gh if c.startswith("gh release upload")]
        assert len(creates) == 4 and len(uploads) == 4
        for name in ENGINES:
            assert any(f"-R {ORG}/{name} " in c and "--verify-tag" in c
                       and f'--title base {TAG}' in c for c in creates)
            upload = next(u for u in uploads if f"-R {ORG}/{name} " in u)
            assert "--clobber" not in upload
            attached = sorted(Path(p).name for p in upload.split()[6:])
            assert attached == sorted([*_sums(_out(env) / name), "SHA256SUMS"])
        assert not any("base-platform" in c for c in creates + uploads)
        notes = (env[3] / "notes-seen.md").read_text()
        assert "**A thing.**" in notes and "older" not in notes

    def test_an_identical_asset_is_skipped(self, env) -> None:
        _make_set(env[0])
        assert _run(env, TAG).returncode == 0
        _attach_all(env)
        result = _run(env, TAG, "--upload")
        assert result.returncode == 0, result.stdout + result.stderr
        gh = _calls(env, "gh")
        assert not any(c.startswith(("gh release create", "gh release upload")) for c in gh)
        assert "manifest.json already attached, same digest" in result.stdout

    def test_a_differing_asset_refuses_without_replace(self, env) -> None:
        _make_set(env[0])
        assert _run(env, TAG).returncode == 0
        _attach_all(env, differ="manifest.json")
        result = _run(env, TAG, "--upload")
        assert result.returncode == 1
        assert "base-knowledge: manifest.json is attached with sha256:000" in result.stderr
        gh = _calls(env, "gh")
        assert not any(c.startswith(("gh release create", "gh release upload")) for c in gh)

    def test_a_differing_asset_is_replaced_with_replace(self, env) -> None:
        _make_set(env[0])
        assert _run(env, TAG).returncode == 0
        _attach_all(env, differ="manifest.json")
        result = _run(env, TAG, "--upload", "--replace")
        assert result.returncode == 0, result.stdout + result.stderr
        uploads = [c for c in _calls(env, "gh") if c.startswith("gh release upload")]
        assert len(uploads) == 4
        for upload in uploads:
            assert "--clobber" in upload
            assert upload.split()[-1].endswith("/manifest.json")
