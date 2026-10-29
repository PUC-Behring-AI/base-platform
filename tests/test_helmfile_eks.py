"""Tests for the helmfile's `eks` environment (ADAPTATION §10, "The managed
cluster").

The reference instance is copied with values/eks/ made from its kind values,
since it carries no EKS values of its own. `helmfile build` needs helmfile
alone; the render (`helmfile template`) needs helm and the layer checkouts
beside this one too (BASE_ROOT), and is skipped, saying which, without them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent.resolve()
REFERENCE = ROOT / "deploy" / "helmfile" / "reference-instance"
HELMFILE = ROOT / "deploy" / "helmfile" / "helmfile.yaml.gotmpl"
LAYERS = ["interface", "knowledge", "agents", "inference"]

# CI installs no helmfile, so these are skipped there: base-platform#97.
needs_helmfile = pytest.mark.skipif(
    shutil.which("helmfile") is None, reason="helmfile not installed (CI: base-platform#97)"
)


def _base_root() -> Path:
    return Path(os.environ.get("BASE_ROOT", ROOT.parent)).resolve()


def _eks_instance(tmp_path: Path) -> Path:
    inst = tmp_path / "instance"
    shutil.copytree(REFERENCE, inst)
    shutil.copytree(inst / "values" / "kind", inst / "values" / "eks")
    return inst


def _helmfile(instance: Path, command: str, *args: str, env: str = "eks"):
    environ = dict(os.environ)
    environ.update(BASE_ROOT=str(_base_root()), K8S_INSTANCE_DIR=str(instance))
    # No KIND_NETWORK_CIDR: the eks environment must not need it.
    environ.pop("KIND_NETWORK_CIDR", None)
    return subprocess.run(
        ["helmfile", "-f", str(HELMFILE), "-e", env, *args, command],
        capture_output=True,
        text=True,
        env=environ,
        check=False,
    )


def _releases(rendered: str) -> dict[str, dict]:
    for part in rendered.split("\n---\n"):
        doc = yaml.safe_load(part)
        if isinstance(doc, dict) and doc.get("releases"):
            return {f"{r['namespace']}/{r['name']}": r for r in doc["releases"]}
    raise AssertionError(rendered)


def _kind_releases(instance: Path) -> dict[str, dict]:
    environ = dict(os.environ)
    environ.update(
        BASE_ROOT=str(_base_root()),
        K8S_INSTANCE_DIR=str(instance),
        KIND_NETWORK_CIDR="172.18.0.0/16",
    )
    result = subprocess.run(
        ["helmfile", "-f", str(HELMFILE), "-e", "kind", "build"],
        capture_output=True,
        text=True,
        env=environ,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return _releases(result.stdout)


@needs_helmfile
def test_eks_has_the_kind_releases_and_needs_plus_the_gateway(tmp_path):
    inst = _eks_instance(tmp_path)
    result = _helmfile(inst, "build")
    assert result.returncode == 0, result.stderr
    eks = _releases(result.stdout)
    kind = _kind_releases(inst)
    assert set(eks) == set(kind) | {"edge/gateway"}
    for name, release in kind.items():
        needs = release.get("needs", [])
        if name == "interface/interface":
            needs = [*needs, "edge/gateway"]
        assert eks[name].get("needs", []) == needs, name
    assert eks["edge/gateway"]["chart"] == "../charts/gateway"


@needs_helmfile
def test_eks_values_come_from_values_eks(tmp_path):
    inst = _eks_instance(tmp_path)
    result = _helmfile(inst, "build")
    assert result.returncode == 0, result.stderr
    releases = _releases(result.stdout)
    for layer in LAYERS:
        values = releases[f"{layer}/{layer}"]["values"]
        files = [v for v in values if isinstance(v, str)]
        assert files == [
            str(inst / "values" / "common" / f"{layer}.yaml"),
            str(inst / "values" / "eks" / f"{layer}.yaml"),
        ], layer


@needs_helmfile
def test_eks_takes_the_generated_overlay_last_when_present(tmp_path):
    inst = _eks_instance(tmp_path)
    generated = inst / "eks" / ".generated"
    generated.mkdir(parents=True)
    (generated / "interface.yaml").write_text("image: {digest: sha256:" + "0" * 64 + "}\n")
    result = _helmfile(inst, "build")
    assert result.returncode == 0, result.stderr
    releases = _releases(result.stdout)
    assert releases["interface/interface"]["values"][-1] == str(generated / "interface.yaml")
    # A release without an overlay keeps its two files.
    assert not any(".generated" in str(v) for v in releases["knowledge/knowledge"]["values"])


@needs_helmfile
def test_eks_interface_has_no_kind_ipblock(tmp_path):
    result = _helmfile(_eks_instance(tmp_path), "build")
    assert result.returncode == 0, result.stderr
    inline = _releases(result.stdout)["interface/interface"]["values"][0]
    assert "edge" not in inline
    assert inline["gateway"]["parentRef"] == {
        "name": "base",
        "namespace": "edge",
        "sectionName": "http",
    }


@needs_helmfile
@pytest.mark.parametrize(
    ("args", "expected"),
    [((), "base-alb"), (("--state-values-set", "gatewayClass=other"), "other")],
)
def test_eks_gateway_class_from_the_environment(tmp_path, args, expected):
    result = _helmfile(_eks_instance(tmp_path), "build", *args)
    assert result.returncode == 0, result.stderr
    gateway = _releases(result.stdout)["edge/gateway"]
    assert gateway["values"] == [{"className": expected}]


@needs_helmfile
def test_kind_has_no_gateway_release(tmp_path):
    assert "edge/gateway" not in _kind_releases(_eks_instance(tmp_path))


@needs_helmfile
@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_eks_renders_without_kind_only_objects(tmp_path):
    base_root = _base_root()
    missing = [f"base-{x}" for x in LAYERS if not (base_root / f"base-{x}/deploy/chart").is_dir()]
    if missing:
        pytest.skip(f"no chart beside this checkout (BASE_ROOT={base_root}): {missing}")
    inst = _eks_instance(tmp_path)
    generated = inst / "eks" / ".generated"
    generated.mkdir(parents=True)
    digest = "sha256:" + "a" * 64
    (generated / "knowledge.yaml").write_text(f"image: {{digest: {digest}}}\n")
    result = _helmfile(inst, "template", "--skip-deps")
    assert result.returncode == 0, result.stderr
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    (gateway,) = [d for d in docs if d["kind"] == "Gateway"]
    assert (gateway["metadata"]["name"], gateway["metadata"]["namespace"]) == ("base", "edge")
    assert gateway["spec"]["gatewayClassName"] == "base-alb"
    assert not [d for d in docs if d["kind"] == "StorageClass"]
    assert "cloud-provider-kind" not in result.stdout
    assert "rancher.io/local-path" not in result.stdout
    assert "172.18.0.0/16" not in result.stdout
    # The overlay reached the knowledge image.
    assert f"@{digest}" in result.stdout
