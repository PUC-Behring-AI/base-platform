"""Tests for the kind harness: scripts/k8s-{up,down,test,images}.sh and the
helmfile they drive.

No cluster is needed. The refusal tests put stub tools on PATH that record
any call and fail, so a refusal is proven to happen before the harness
touches a cluster. test_helmfile_renders needs helm, helmfile and kubeconform
and the layer checkouts beside this one (BASE_ROOT, as compose.base.yaml);
it is skipped, saying which, when they are absent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS = ["k8s-up.sh", "k8s-down.sh", "k8s-test.sh", "k8s-images.sh"]
REFERENCE = ROOT / "deploy" / "helmfile" / "reference-instance"
HELMFILE = ROOT / "deploy" / "helmfile" / "helmfile.yaml.gotmpl"
LAYERS = ["interface", "knowledge", "agents", "inference"]
TOOLS = ["kind", "kubectl", "helm", "helmfile", "docker", "cloud-provider-kind"]


def _stub_tools(tmp_path: Path, scripts: dict[str, str] | None = None) -> tuple[Path, Path]:
    """A PATH directory where every harness tool records its call and fails,
    unless `scripts` gives it a body."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    for tool in TOOLS:
        body = (scripts or {}).get(tool, "exit 1")
        (bin_dir / tool).write_text(
            f'#!/bin/bash\necho "{tool} $*" >> "{calls}"\n{body}\n'
        )
        (bin_dir / tool).chmod(0o755)
    return bin_dir, calls


def _instance(tmp_path: Path, env: str) -> Path:
    inst = tmp_path / "instance"
    (inst / "values" / "common").mkdir(parents=True)
    (inst / "values" / "kind").mkdir(parents=True)
    (inst / ".env.required").write_text(
        "# variable namespace...\nFIRST_KEY interface\nSECOND_KEY interface inference\n"
    )
    (inst / ".env").write_text(env)
    return inst


def _run(script: str, *args: str, path: Path, extra: dict[str, str] | None = None):
    env = {"PATH": f"{path}:/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
    env.update(extra or {})
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / script), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_up_refuses_missing_required_variable(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path)
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=\n")
    result = _run("k8s-up.sh", str(inst), path=bin_dir)
    assert result.returncode != 0
    assert "SECOND_KEY" in result.stderr
    assert not calls.exists(), calls.read_text()


def test_up_refuses_required_variable_absent_from_env(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path)
    inst = _instance(tmp_path, "FIRST_KEY=one\n")
    result = _run("k8s-up.sh", str(inst), path=bin_dir)
    assert result.returncode != 0
    assert "SECOND_KEY" in result.stderr
    assert not calls.exists(), calls.read_text()


def test_up_reads_a_last_line_without_newline(tmp_path):
    # The last line of .env.required has no newline: it is still required.
    bin_dir, calls = _stub_tools(tmp_path)
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=two\n")
    (inst / ".env.required").write_text("FIRST_KEY interface\nTHIRD_KEY inference")
    result = _run("k8s-up.sh", str(inst), path=bin_dir)
    assert result.returncode != 0
    assert "THIRD_KEY" in result.stderr
    assert not calls.exists(), calls.read_text()


def test_up_refuses_a_variable_without_namespace(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path)
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=two\n")
    (inst / ".env.required").write_text("# comment\nFIRST_KEY interface\nSECOND_KEY\n")
    result = _run("k8s-up.sh", str(inst), path=bin_dir)
    assert result.returncode != 0
    assert ".env.required line 3: SECOND_KEY names no namespace" in result.stderr
    assert not calls.exists(), calls.read_text()


def test_up_refuses_an_unknown_namespace(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path)
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=two\n")
    (inst / ".env.required").write_text("FIRST_KEY interface\nSECOND_KEY inference nowhere\n")
    result = _run("k8s-up.sh", str(inst), path=bin_dir)
    assert result.returncode != 0
    assert ".env.required line 2: SECOND_KEY: no namespace nowhere" in result.stderr
    assert not calls.exists(), calls.read_text()


def test_missing_chart_is_named(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path)
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=two\n")
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run("k8s-up.sh", str(inst), path=bin_dir, extra={"BASE_ROOT": str(empty)})
    assert result.returncode != 0
    assert f"layer knowledge: no chart at {empty}/base-knowledge/deploy/chart" in result.stderr
    assert not calls.exists(), calls.read_text()


def test_images_refuses_wrong_architecture(tmp_path):
    # The node is arm64; the image just built is amd64: refused before any
    # push, naming the image, never run emulated.
    bin_dir, calls = _stub_tools(
        tmp_path,
        {
            "kubectl": 'case "$*" in *architecture*) echo arm64;; *) exit 1;; esac',
            "docker": 'case "$1" in build) exit 0;; image) echo amd64;; *) exit 1;; esac',
        },
    )
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=two\n")
    (inst / "images.txt").write_text(f"localhost:5001/example:local {tmp_path}\n")
    result = _run("k8s-images.sh", str(inst), path=bin_dir)
    assert result.returncode != 0
    assert "localhost:5001/example:local is linux/amd64, the node is linux/arm64" in result.stderr
    assert "docker push" not in calls.read_text()


def test_scripts_are_bash32_clean():
    for name in SCRIPTS:
        text = (ROOT / "scripts" / name).read_text()
        for word in ("mapfile", "readarray", "declare -A", "local -n", "${!"):
            assert word not in text, f"{name} uses {word!r}, which bash 3.2 lacks"


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_scripts_pass_shellcheck():
    paths = [str(ROOT / "scripts" / n) for n in SCRIPTS]
    result = subprocess.run(["shellcheck", *paths], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout


def _base_root() -> Path:
    return Path(os.environ.get("BASE_ROOT", ROOT.parent)).resolve()


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("helm", "helmfile", "kubeconform")),
    reason="helm, helmfile or kubeconform not installed",
)
def test_helmfile_renders(tmp_path):
    base_root = _base_root()
    missing = [f"base-{x}" for x in LAYERS if not (base_root / f"base-{x}/deploy/chart").is_dir()]
    if missing:
        pytest.skip(f"no chart beside this checkout (BASE_ROOT={base_root}): {missing}")
    env = dict(os.environ)
    env.update(
        BASE_ROOT=str(base_root),
        K8S_INSTANCE_DIR=str(REFERENCE),
        KIND_NETWORK_CIDR="172.18.0.0/16",
    )
    rendered = subprocess.run(
        ["helmfile", "-f", str(HELMFILE), "-e", "kind", "template", "--skip-deps"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert rendered.returncode == 0, rendered.stderr
    out = tmp_path / "rendered.yaml"
    out.write_text(rendered.stdout)
    checked = subprocess.run(
        [
            "kubeconform",
            "-strict",
            "-ignore-missing-schemas",
            "-kubernetes-version",
            "1.36.0",
            "-summary",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    # One workload of each release: a release left out of the helmfile is a
    # layer missing from the cluster.
    for workload in ("name: interface-accounts-db", "name: inference-db", "name: bff",
                     "name: knowledge", "name: agents", "name: litellm"):
        assert workload in rendered.stdout, workload
