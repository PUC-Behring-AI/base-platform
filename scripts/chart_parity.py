#!/usr/bin/env python3
"""Compare a layer's compose file with the output of `helm template`.

    chart_parity.py --compose compose.yaml --rendered rendered.yaml --map parity.yaml

Per mapped service it compares env var names, container ports, secrets (a
password/key/token-named variable fed by `${X:?}` or `${X:-}` in compose must
be a `secretKeyRef` in the chart) and a pinned image digest. Exit 0 when they
match, 1 with one `service <s>: <what> compose=<x> chart=<y>` line per
mismatch, 2 when the inputs cannot be read or the map is malformed.
The map schema is documented in docs/ADAPTATION.md.
"""

from __future__ import annotations

import argparse
import re
import sys

import yaml

WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "Job"}
SECRET_NAME = re.compile(r"(PASSWORD|SECRET|TOKEN|KEY)", re.IGNORECASE)
SECRET_VALUE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:[?-]")
DIGEST = re.compile(r"@(sha256:[0-9a-f]+)")


class InputError(Exception):
    pass


def _load_all(path: str) -> list:
    try:
        with open(path) as f:
            return [d for d in yaml.safe_load_all(f) if d]
    except (OSError, yaml.YAMLError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc


def _load_one(path: str) -> dict:
    docs = _load_all(path)
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise InputError(f"{path}: expected one YAML mapping")
    return docs[0]


def _compose_env(service: dict) -> dict[str, str | None]:
    env = service.get("environment") or {}
    if isinstance(env, dict):
        return {k: None if v is None else str(v) for k, v in env.items()}
    out: dict[str, str | None] = {}
    for item in env:
        name, sep, value = str(item).partition("=")
        out[name] = value if sep else None
    return out


def _compose_ports(service: dict) -> set[int]:
    ports = {int(str(p).split("/")[0]) for p in service.get("expose") or []}
    for p in service.get("ports") or []:
        if isinstance(p, dict):
            ports.add(int(p["target"]))
        else:
            ports.add(int(str(p).split("/")[0].split(":")[-1]))
    return ports


def _chart_view(workload: dict) -> dict:
    containers = workload["spec"]["template"]["spec"].get("containers") or []
    env: dict[str, bool] = {}  # name -> fed by secretKeyRef
    ports: set[int] = set()
    images: list[str] = []
    for c in containers:
        for e in c.get("env") or []:
            ref = (e.get("valueFrom") or {}).get("secretKeyRef")
            env[e["name"]] = bool(ref)
        ports.update(int(p["containerPort"]) for p in c.get("ports") or [])
        images.append(c.get("image", ""))
    return {"env": env, "ports": ports, "images": images}


def _find_workload(rendered: list, name: str, kind: str | None) -> dict | None:
    for doc in rendered:
        if doc.get("kind") not in WORKLOADS or doc["metadata"]["name"] != name:
            continue
        if kind is None or doc["kind"] == kind:
            return doc
    return None


def _check_ignores(entries: list) -> set[tuple[str, str]]:
    ignored = set()
    for entry in entries:
        label = f"service {entry.get('service')} field {entry.get('field')}"
        if not entry.get("service") or not entry.get("field"):
            raise InputError(f"ignore entry ({label}): service and field are required")
        if not str(entry.get("reason") or "").strip():
            raise InputError(f"ignore entry ({label}): a reason is required")
        ignored.add((entry["service"], entry["field"]))
    return ignored


def compare(compose: dict, rendered: list, mapping: dict) -> list[str]:
    mapped = mapping.get("services") or {}
    ignored = _check_ignores(mapping.get("ignore") or [])
    lines: list[str] = []

    def report(svc: str, field: str, what: str, c: str, h: str) -> None:
        if (svc, field) not in ignored:
            lines.append(f"service {svc}: {what} compose={c} chart={h}")

    services = compose.get("services") or {}
    for svc, spec in services.items():
        if svc not in mapped and not spec.get("profiles"):
            report(svc, "workload", "workload", "present", "unmapped")
    for svc, entry in mapped.items():
        if svc not in services:
            report(svc, "workload", "workload", "absent", "present")
            continue
        workload = _find_workload(rendered, entry["workload"], entry.get("kind"))
        if workload is None:
            report(svc, "workload", "workload", "present", "absent")
            continue
        spec, chart = services[svc], _chart_view(workload)
        env = _compose_env(spec)
        for name, value in env.items():
            if name not in chart["env"]:
                report(svc, "env", f"env {name}", "present", "absent")
            elif SECRET_NAME.search(name) and SECRET_VALUE.match(value or "") \
                    and not chart["env"][name]:  # fmt: skip
                report(svc, "secrets", f"secret {name}", "secret", "plain")
        cports = _compose_ports(spec)
        if cports:
            for p in sorted(cports - chart["ports"]):
                report(svc, "ports", f"port {p}", "present", "absent")
            for p in sorted(chart["ports"] - cports):
                report(svc, "ports", f"port {p}", "absent", "present")
        pinned = DIGEST.search(str(spec.get("image", "")))
        if pinned and not any(pinned.group(1) in i for i in chart["images"]):
            got = ",".join(chart["images"]) or "none"
            report(svc, "image", "image digest", pinned.group(1), got)
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--compose", required=True)
    parser.add_argument("--rendered", required=True)
    parser.add_argument("--map", required=True)
    args = parser.parse_args(argv)
    try:
        lines = compare(_load_one(args.compose), _load_all(args.rendered), _load_one(args.map))
    except InputError as exc:
        print(f"chart_parity: {exc}", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
