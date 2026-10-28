"""Tests for the kind harness: scripts/k8s-{up,down,test,images,registry}.sh,
scripts/k8s_system_test.py and the helmfile they drive.

No cluster is needed. The refusal tests put stub tools on PATH that record
any call and fail, so a refusal is proven to happen before the harness
touches a cluster. test_helmfile_renders needs helm, helmfile and kubeconform
and the layer checkouts beside this one (BASE_ROOT, as compose.base.yaml);
it is skipped, saying which, when they are absent; the tests of an instance's
own releases need helmfile alone.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS = ["k8s-up.sh", "k8s-down.sh", "k8s-test.sh", "k8s-images.sh", "k8s-registry.sh"]
REFERENCE = ROOT / "deploy" / "helmfile" / "reference-instance"
HELMFILE = ROOT / "deploy" / "helmfile" / "helmfile.yaml.gotmpl"
LAYERS = ["interface", "knowledge", "agents", "inference"]
TOOLS = ["kind", "kubectl", "helm", "helmfile", "docker", "cloud-provider-kind"]

sys.path.insert(0, str(ROOT / "scripts"))
import k8s_system_test  # noqa: E402


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
                     "name: knowledge", "name: agents", "name: litellm",
                     "name: knowledge-store"):
        assert workload in rendered.stdout, workload


# ── The registry before the cluster (base-platform#92) ──────────────────────


def test_registry_is_started_when_absent(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path, {"docker": "exit 0"})
    result = _run("k8s-registry.sh", path=bin_dir)
    assert result.returncode == 0, result.stderr
    assert "docker run -d --restart=always -p 127.0.0.1:5001:5000" in calls.read_text()


def test_registry_left_alone_when_running(tmp_path):
    bin_dir, calls = _stub_tools(
        tmp_path, {"docker": 'case "$1" in inspect) echo true;; *) exit 1;; esac'}
    )
    result = _run("k8s-registry.sh", path=bin_dir)
    assert result.returncode == 0, result.stderr
    assert "docker run" not in calls.read_text()
    assert "docker rm" not in calls.read_text()


def _fake_base_root(tmp_path: Path) -> Path:
    base_root = tmp_path / "base-root"
    for layer in LAYERS:
        chart = base_root / f"base-{layer}" / "deploy" / "chart"
        chart.mkdir(parents=True)
        (chart / "Chart.yaml").write_text(f"name: base-{layer}\n")
    return base_root


def test_up_starts_registry_before_cluster(tmp_path):
    # The cluster cannot be created here (kind fails): the registry must
    # already be running by then, so an instance can push before the images.
    bin_dir, calls = _stub_tools(
        tmp_path,
        {"helmfile": "exit 0", "docker": 'case "$1" in inspect) echo false;; *) exit 0;; esac'},
    )
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=two\n")
    result = _run(
        "k8s-up.sh", str(inst), path=bin_dir, extra={"BASE_ROOT": str(_fake_base_root(tmp_path))}
    )
    assert result.returncode != 0
    log = calls.read_text().splitlines()
    run = next(i for i, c in enumerate(log) if c.startswith("docker run"))
    cluster = next(i for i, c in enumerate(log) if c.startswith("kind "))
    assert run < cluster, log
    # The releases were read before either.
    assert log[0].startswith("helmfile ") and " list" in log[0], log


def test_up_refuses_releases_the_helmfile_refuses(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path, {"helmfile": "echo 'bad chart' >&2; exit 1"})
    inst = _instance(tmp_path, "FIRST_KEY=one\nSECOND_KEY=two\n")
    result = _run(
        "k8s-up.sh", str(inst), path=bin_dir, extra={"BASE_ROOT": str(_fake_base_root(tmp_path))}
    )
    assert result.returncode != 0
    assert "the helmfile does not render" in result.stderr
    assert [c.split()[0] for c in calls.read_text().splitlines()] == ["helmfile"]


# ── An instance's own releases (base-platform#91) ───────────────────────────

needs_helmfile = pytest.mark.skipif(
    shutil.which("helmfile") is None, reason="helmfile not installed"
)


def _helmfile(instance: Path, command: str = "build"):
    env = dict(os.environ)
    env.update(
        BASE_ROOT=str(_base_root()),
        K8S_INSTANCE_DIR=str(instance),
        KIND_NETWORK_CIDR="172.18.0.0/16",
    )
    return subprocess.run(
        ["helmfile", "-f", str(HELMFILE), "-e", "kind", command],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _releases(rendered: str) -> dict[str, dict]:
    for part in rendered.split("\n---\n"):
        doc = yaml.safe_load(part)
        if isinstance(doc, dict) and doc.get("releases"):
            return {f"{r['namespace']}/{r['name']}": r for r in doc["releases"]}
    raise AssertionError(rendered)


@needs_helmfile
def test_reference_instance_release_is_installed_before_its_layer():
    result = _helmfile(REFERENCE)
    assert result.returncode == 0, result.stderr
    releases = _releases(result.stdout)
    store = releases["knowledge/knowledge-store"]
    assert store["chart"] == "../charts/postgres"
    assert store["needs"] == ["knowledge/schemas"]
    assert store["values"] == [str(REFERENCE / "values/common/knowledge-store.yaml")]
    assert "knowledge/knowledge-store" in releases["knowledge/knowledge"]["needs"]
    # No other layer waits for it.
    for layer in ("interface", "agents", "inference"):
        assert "knowledge/knowledge-store" not in releases[f"{layer}/{layer}"]["needs"]


def _with_releases(tmp_path: Path, releases: object) -> Path:
    inst = tmp_path / "instance"
    shutil.copytree(REFERENCE, inst)
    (inst / "releases.yaml").write_text(yaml.safe_dump(releases))
    return inst


@needs_helmfile
def test_instance_without_releases_file_has_the_base_alone(tmp_path):
    inst = tmp_path / "instance"
    shutil.copytree(REFERENCE, inst)
    (inst / "releases.yaml").unlink()
    result = _helmfile(inst)
    assert result.returncode == 0, result.stderr
    releases = _releases(result.stdout)
    assert "knowledge/knowledge-store" not in releases
    assert releases["knowledge/knowledge"]["needs"] == ["knowledge/schemas", "inference/inference"]


@needs_helmfile
def test_release_needs_and_several_layers(tmp_path):
    inst = _with_releases(tmp_path, {"releases": [
        {"name": "store", "namespace": "agents", "chart": "postgres",
         "values": ["values/common/knowledge-store.yaml"],
         "needs": ["inference/inference-db"], "neededBy": ["agents", "interface"]},
    ]})
    result = _helmfile(inst)
    assert result.returncode == 0, result.stderr
    releases = _releases(result.stdout)
    assert releases["agents/store"]["needs"] == ["agents/schemas", "inference/inference-db"]
    assert "agents/store" in releases["agents/agents"]["needs"]
    assert "agents/store" in releases["interface/interface"]["needs"]


@pytest.mark.parametrize(
    ("release", "message"),
    [
        ({"chart": "redis"},
         'chart "redis" is not one of the base charts an instance may use: postgres'),
        ({"chart": "../charts/postgres"}, "is not one of the base charts"),
        ({"namespace": "default"}, 'namespace "default" is not one of'),
        ({"neededBy": ["edge"]}, 'neededBy "edge" is not a layer'),
        ({"name": "inference-db"}, "the base already has a release by that name"),
        ({"values": ["values/common/nowhere.yaml"]}, "no values file"),
        ({"wait": False}, 'unknown key "wait"'),
    ],
)
@needs_helmfile
def test_release_refused(tmp_path, release, message):
    entry = {"name": "store", "namespace": "knowledge", "chart": "postgres",
             "values": ["values/common/knowledge-store.yaml"]}
    entry.update(release)
    result = _helmfile(_with_releases(tmp_path, {"releases": [entry]}), "list")
    assert result.returncode != 0
    assert message in result.stderr, result.stderr


@needs_helmfile
def test_releases_file_with_unknown_top_key_refused(tmp_path):
    result = _helmfile(_with_releases(tmp_path, {"release": []}), "list")
    assert result.returncode != 0
    assert 'unknown key "release" (only: releases)' in result.stderr, result.stderr


# ── The instance's system test (base-platform#93) ───────────────────────────


def _system_test(tmp_path: Path, doc: object) -> Path:
    inst = tmp_path / "instance"
    inst.mkdir(exist_ok=True)
    (inst / "system-test.yaml").write_text(yaml.safe_dump(doc))
    return inst


def test_reference_system_test_runs_echo():
    config = k8s_system_test.load(REFERENCE)
    assert [(s["flow"], s["status"]) for s in config["steps"]] == [("echo", 202)]


def test_test_requires_the_instance_dir(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path)
    result = _run("k8s-test.sh", path=bin_dir)
    assert result.returncode != 0
    assert "usage: scripts/k8s-test.sh <instance-dir>" in result.stderr
    assert not calls.exists()


def test_test_refuses_a_bad_system_test_before_the_cluster(tmp_path):
    bin_dir, calls = _stub_tools(tmp_path)
    for tool in ("python3", "openssl"):
        (bin_dir / tool).symlink_to(shutil.which(tool) or f"/usr/bin/{tool}")
    inst = _system_test(tmp_path, {"steps": [{"flow": "echo", "status": 201, "input": {}}]})
    result = _run("k8s-test.sh", str(inst), path=bin_dir)
    assert result.returncode != 0
    assert "status must be 200" in result.stderr
    assert not calls.exists(), calls.read_text()


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({}, "at least one step"),
        ({"steps": []}, "at least one step"),
        ({"steps": [{"status": 202, "input": {}}]}, "flow is required"),
        ({"steps": [{"flow": "f", "input": {}}]}, "status must be 200"),
        ({"steps": [{"flow": "f", "status": 200}]}, "exactly one of input, input_file"),
        ({"steps": [{"flow": "f", "status": 200, "input": {}, "input_file": "x"}]},
         "exactly one of input, input_file"),
        ({"steps": [{"flow": "f", "status": 200, "input_file": "nowhere.json"}]}, "no input file"),
        ({"steps": [{"flow": "f", "status": 200, "input": {}, "expect": 1}]}, "unknown key(s)"),
        ({"step": []}, "unknown key(s) ['step']"),
        ({"schemas": ["nowhere"], "steps": [{"flow": "f", "status": 200, "input": {}}]},
         "no directory"),
        ({"steps": [{"flow": "f", "status": 200, "input": {}}], "knowledge_search": {}},
         "query is required"),
        ({"steps": [{"flow": "f", "status": 200, "input": {}}],
          "knowledge_search": {"query": "q", "min_passages": -1}}, "whole number"),
    ],
)
def test_system_test_refused(tmp_path, doc, message):
    with pytest.raises(k8s_system_test.ConfigError) as err:
        k8s_system_test.load(_system_test(tmp_path, doc))
    assert message in str(err.value)


def test_input_file_and_search_url(tmp_path):
    inst = _system_test(tmp_path, {
        "steps": [{"flow": "f", "status": 200, "input_file": "in.json"}],
        "knowledge_search": {"query": "seal & cap", "limit": 2},
    })
    (inst / "in.json").write_text('{"a": 1}')
    config = k8s_system_test.load(inst)
    assert config["steps"][0]["input"] == {"a": 1}
    assert k8s_system_test.search_url(config) == (
        "http://knowledge.knowledge.svc:8001/v1/evidence?query=seal+%26+cap&limit=2"
    )
    assert config["knowledge_search"]["min_passages"] == 1


def test_substitute():
    saved = {"id": 7, "name": "n"}
    got = k8s_system_test.substitute({"a": "${id}", "b": ["x-${name}-${id}"], "c": 1}, saved)
    assert got == {"a": 7, "b": ["x-n-7"], "c": 1}
    with pytest.raises(k8s_system_test.ConfigError, match="not saved"):
        k8s_system_test.substitute({"a": "${other}"}, saved)


def _response(body):
    return {"request_id": str(uuid.uuid4()), "outcome": "answered", "body": body,
            "classification": {"name": "public", "key_policy": "local-only"}}


class _Gateway(http.server.BaseHTTPRequestHandler):
    """The interface as the flows see it: login, a flow answered at once
    (create), a flow answered by a job (start), the job."""

    seen: list = []

    def log_message(self, *args):
        pass

    def _send(self, status, payload=None, headers=None):
        raw = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, body, self.headers.get("Cookie")))
        if self.path == "/auth/login":
            self._send(204, headers={"Set-Cookie": "s=abc; Secure; HttpOnly"})
        elif self.path == "/api/v1/flows/create":
            self._send(200, _response({"id": "a-1"}))
        elif self.path == "/api/v1/flows/start":
            self._send(202, {"request_id": str(uuid.uuid4()), "job_id": "j-1"})
        else:
            self._send(404, {})

    def do_GET(self):
        self._send(200, {"request_id": str(uuid.uuid4()), "job_id": "j-1", "state": "succeeded",
                         "steps": [], "result": _response({"done": True})})


@pytest.fixture
def gateway():
    _Gateway.seen = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_flows_chain_saved_values(tmp_path, gateway):
    inst = _system_test(tmp_path, {"steps": [
        {"flow": "create", "status": 200, "input": {"title": "t"}, "outcome": "answered",
         "save": {"note": "body.id"}},
        {"flow": "start", "status": 202, "input": {"note_id": "${note}"}},
    ]})
    k8s_system_test.flows(k8s_system_test.load(inst), gateway, "http://o", "p", "pw")
    assert _Gateway.seen[1:] == [
        ("/api/v1/flows/create", {"title": "t"}, "s=abc"),
        ("/api/v1/flows/start", {"note_id": "a-1"}, "s=abc"),
    ]


def test_flows_refuse_an_unexpected_status(tmp_path, gateway):
    inst = _system_test(tmp_path, {"steps": [{"flow": "create", "status": 202, "input": {}}]})
    with pytest.raises(SystemExit, match="HTTP 200, expected 202"):
        k8s_system_test.flows(k8s_system_test.load(inst), gateway, "http://o", "p", "pw")


def test_flows_check_the_body_schema(tmp_path, gateway):
    schemas = tmp_path / "own-schemas"
    schemas.mkdir()
    (schemas / "thing.schema.json").write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://schemas.example.internal/thing.schema.json",
        "type": "object", "required": ["missing"],
    }))
    inst = _system_test(tmp_path, {"schemas": [str(schemas)], "steps": [
        {"flow": "create", "status": 200, "input": {},
         "body_schema": "https://schemas.example.internal/thing.schema.json"},
    ]})
    with pytest.raises(Exception, match="'missing' is a required property"):
        k8s_system_test.flows(k8s_system_test.load(inst), gateway, "http://o", "p", "pw")


def test_search_check_counts_passages(tmp_path):
    inst = _system_test(tmp_path, {"steps": [{"flow": "f", "status": 200, "input": {}}],
                                   "knowledge_search": {"query": "q", "min_passages": 1}})
    config = k8s_system_test.load(inst)
    empty = json.dumps({"request_id": str(uuid.uuid4()), "passages": []})
    with pytest.raises(SystemExit, match="0 passage"):
        k8s_system_test.search_check(config, empty)
