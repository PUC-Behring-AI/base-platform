"""The instance's part of scripts/k8s-test.sh: what <instance-dir>/system-test.yaml
asks of the cluster through the Gateway (ADAPTATION §10).

    python3 scripts/k8s_system_test.py check <instance-dir>
    python3 scripts/k8s_system_test.py flows <instance-dir> <url> <origin> <principal> <password>
    python3 scripts/k8s_system_test.py search-url <instance-dir>
    python3 scripts/k8s_system_test.py search-check <instance-dir> < answer.json

system-test.yaml:

    schemas: [../schemas/c3]      # optional: directories of JSON Schemas loaded
                                  # beside the base's, relative to the instance
    steps:                        # at least one, run in order, one session
      - flow: echo                # POST /api/v1/flows/<flow>
        input: {query: x}         # the request body, or input_file: <path>
                                  # (JSON or YAML, relative to the instance)
        status: 202               # 200: a C3 response; 202: a C3 job, polled
                                  # to its end, which must succeed
        body_schema: <$id>        # optional: validates the response's body
        outcome: answered         # optional: the response's outcome
        timeout: 120              # optional, 202 only: seconds to wait for the job
        save: {name: body.id}     # optional: ${name} in a later step's input
    knowledge_search:             # optional: a C1 search from namespace agents
      query: some words
      limit: 3
      min_passages: 1

Every answer validates against the base's C3 envelope; a key this file does
not know is refused, so a typo never turns a check off.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
C3 = "https://schemas.base.internal/c3_envelope.schema.json#/$defs/"
C1 = "https://schemas.base.internal/c1_evidence.schema.json"
KNOWLEDGE = "http://knowledge.knowledge.svc:8001/v1/evidence"
TOP = {"schemas", "steps", "knowledge_search"}
STEP = {"flow", "input", "input_file", "status", "body_schema", "outcome", "save", "timeout"}
SEARCH = {"query", "limit", "min_passages"}
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
JOB_SECONDS = 120


class ConfigError(Exception):
    pass


def _unknown(where: str, got: dict, known: set[str]) -> None:
    extra = sorted(set(got) - known)
    if extra:
        raise ConfigError(f"{where}: unknown key(s) {extra} (known: {sorted(known)})")


def load(instance: Path) -> dict[str, Any]:
    """system-test.yaml, checked, with input_file read and paths resolved."""
    path = instance / "system-test.yaml"
    if not path.is_file():
        raise ConfigError(f"no {path}")
    doc = yaml.safe_load(path.read_text())
    if not isinstance(doc, dict):
        raise ConfigError(f"{path}: not a mapping")
    _unknown(str(path), doc, TOP)

    entries = doc.get("schemas") or []
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
        raise ConfigError(f"{path}: schemas is a list of directories")
    schemas = []
    for entry in entries:
        directory = (instance / entry).resolve()
        if not directory.is_dir():
            raise ConfigError(f"{path}: schemas: no directory {directory}")
        schemas.append(directory)

    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ConfigError(f"{path}: steps: at least one step is required")
    checked = []
    for n, step in enumerate(steps, 1):
        where = f"{path}: step {n}"
        if not isinstance(step, dict):
            raise ConfigError(f"{where}: not a mapping")
        _unknown(where, step, STEP)
        if not isinstance(step.get("flow"), str) or not step["flow"]:
            raise ConfigError(f"{where}: flow is required")
        if step.get("status") not in (200, 202):
            raise ConfigError(f"{where}: status must be 200 (a response) or 202 (a job)")
        for key in ("body_schema", "outcome"):
            if key in step and (not isinstance(step[key], str) or not step[key]):
                raise ConfigError(f"{where}: {key} must be a string")
        timeout = step.get("timeout", JOB_SECONDS)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            raise ConfigError(f"{where}: timeout must be a whole number of seconds")
        if ("input" in step) == ("input_file" in step):
            raise ConfigError(f"{where}: exactly one of input, input_file")
        if "input_file" in step:
            source = instance / step["input_file"]
            if not source.is_file():
                raise ConfigError(f"{where}: no input file {source}")
            body = yaml.safe_load(source.read_text())
        else:
            body = step["input"]
        if not isinstance(body, dict):
            raise ConfigError(f"{where}: the input is not a mapping")
        save = step.get("save") or {}
        if not isinstance(save, dict) or not all(isinstance(v, str) for v in save.values()):
            raise ConfigError(f"{where}: save maps a name to a dotted path")
        checked.append({**step, "input": body, "save": save, "timeout": timeout})

    search = doc.get("knowledge_search")
    if search is not None:
        where = f"{path}: knowledge_search"
        if not isinstance(search, dict):
            raise ConfigError(f"{where}: not a mapping")
        _unknown(where, search, SEARCH)
        if not isinstance(search.get("query"), str) or not search["query"]:
            raise ConfigError(f"{where}: query is required")
        for key, default in (("limit", 3), ("min_passages", 1)):
            value = search.setdefault(key, default)
            if not isinstance(value, int) or value < 0:
                raise ConfigError(f"{where}: {key} must be a whole number")
    return {"schemas": schemas, "steps": checked, "knowledge_search": search}


def substitute(value: Any, saved: dict[str, Any]) -> Any:
    """`${name}` in every string of value, from what earlier steps saved. A
    string that is exactly one `${name}` takes the saved value's type."""
    if isinstance(value, dict):
        return {k: substitute(v, saved) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, saved) for v in value]
    if not isinstance(value, str):
        return value
    for name in VAR.findall(value):
        if name not in saved:
            raise ConfigError(f"${{{name}}} is not saved by an earlier step")
    whole = VAR.fullmatch(value)
    if whole:
        return saved[whole.group(1)]
    return VAR.sub(lambda m: str(saved[m.group(1)]), value)


def dig(payload: Any, dotted: str) -> Any:
    for key in dotted.split("."):
        if not isinstance(payload, dict) or key not in payload:
            raise ConfigError(f"no {dotted} in {json.dumps(payload)[:300]}")
        payload = payload[key]
    return payload


def _registry(extra: list[Path]):
    sys.path.insert(0, str(ROOT))
    from schemas import validate

    schemas = validate.load_all_schemas(ROOT / "schemas")
    for directory in extra:
        schemas.update(validate.load_all_schemas(directory))
    registry = validate.build_registry(schemas)
    return lambda ref, payload: validate.validator_for(ref, registry).validate(payload)


def flows(config: dict[str, Any], url: str, origin: str, principal: str, password: str) -> None:
    check = _registry(config["schemas"])

    def call(method, path, body=None, cookie=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url + path, data=data, method=method)
        req.add_header("Origin", origin)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    status, headers, raw = call(
        "POST", "/auth/login", {"principal_id": principal, "password": password}
    )
    if status != 204:
        sys.exit(f"login: HTTP {status}: {raw[:300]!r}")
    # The session cookie is Secure; sent back by hand, since this is plain HTTP.
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    print("logged in")

    saved: dict[str, Any] = {}
    for step in config["steps"]:
        name = step["flow"]
        status, _, raw = call(
            "POST", f"/api/v1/flows/{name}", substitute(step["input"], saved), cookie
        )
        if status != step["status"]:
            sys.exit(f"flow {name}: HTTP {status}, expected {step['status']}: {raw[:300]!r}")
        if status == 200:
            answer = json.loads(raw)
            check(C3 + "response", answer)
            print(f"flow {name}: HTTP 200, valid C3 response")
        else:
            accepted = json.loads(raw)
            check(C3 + "job_accepted", accepted)
            job = accepted["job_id"]
            print(f"flow {name}: HTTP 202, valid C3 job_accepted, job {job}")
            deadline = time.monotonic() + step["timeout"]
            while True:
                status, _, raw = call("GET", f"/api/v1/jobs/{job}", cookie=cookie)
                if status != 200:
                    sys.exit(f"job {job}: HTTP {status}: {raw[:300]!r}")
                state = json.loads(raw)["state"]
                if state in ("succeeded", "failed"):
                    break
                if time.monotonic() > deadline:
                    sys.exit(f"job {job} still {state} after {step['timeout']} s")
                time.sleep(1)
            final = json.loads(raw)
            check(C3 + "job_status", final)
            if final["state"] != "succeeded":
                sys.exit(f"job {job} ended {final['state']}: {json.dumps(final)[:500]}")
            answer = final["result"]
            check(C3 + "response", answer)
            print(f"job {job} succeeded; its result is a valid C3 response")
        if "outcome" in step and answer.get("outcome") != step["outcome"]:
            sys.exit(f"flow {name}: outcome {answer.get('outcome')!r}, expected "
                     f"{step['outcome']!r}: {json.dumps(answer)[:500]}")
        if "body_schema" in step:
            check(step["body_schema"], answer["body"])
            print(f"    body valid against {step['body_schema']}")
        print(f"    body: {json.dumps(answer.get('body'))[:200]}")
        for var, dotted in step["save"].items():
            saved[var] = dig(answer, dotted)


def search_url(config: dict[str, Any]) -> str:
    search = config["knowledge_search"]
    if search is None:
        return ""
    query = urllib.parse.urlencode({"query": search["query"], "limit": search["limit"]})
    return f"{KNOWLEDGE}?{query}"


def search_check(config: dict[str, Any], raw: str) -> None:
    answer = json.loads(raw)
    _registry(config["schemas"])(C1, answer)
    want = config["knowledge_search"]["min_passages"]
    if len(answer["passages"]) < want:
        sys.exit(f"the C1 search returned {len(answer['passages'])} passage(s), "
                 f"expected at least {want}")
    for p in answer["passages"]:
        print("    passage:", json.dumps(p)[:160])


def main(argv: list[str]) -> int:
    usage = __doc__.split("\n\n")[1]
    if len(argv) < 2:
        sys.exit(f"usage:\n{usage}")
    command, instance = argv[0], Path(argv[1])
    try:
        config = load(instance)
        if command == "check" and len(argv) == 2:
            print(f"{len(config['steps'])} step(s): "
                  + ", ".join(s["flow"] for s in config["steps"])
                  + ("; a knowledge search" if config["knowledge_search"] else ""))
        elif command == "flows" and len(argv) == 6:
            flows(config, *argv[2:])
        elif command == "search-url" and len(argv) == 2:
            print(search_url(config))
        elif command == "search-check" and len(argv) == 2:
            search_check(config, sys.stdin.read())
        else:
            sys.exit(f"usage:\n{usage}")
    except ConfigError as exc:
        sys.exit(f"system-test.yaml: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
