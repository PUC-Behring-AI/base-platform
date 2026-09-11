"""Shared schema-loading helper.

Import this from a sibling repository rather than copying its logic — five
copies of a twenty-line loader is the AGENTS.md-duplication defect again, just
smaller. The convention matches scripts/gate.sh: base-platform is a sibling
directory on disk, overridable with BASE_PLATFORM_DIR.

    import os, sys
    from pathlib import Path
    base_platform = Path(os.environ.get("BASE_PLATFORM_DIR", Path(__file__).parent.parent / "base-platform"))
    sys.path.insert(0, str(base_platform))
    from schemas.validate import validator_for

base-platform's own tests/test_schemas.py imports this too, rather than
duplicating it locally — the first consumer does not get an exception from its
own rule.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMAS_DIR = Path(__file__).parent


def load_all_schemas(schemas_dir: Path = SCHEMAS_DIR) -> dict[str, dict[str, Any]]:
    """Every *.schema.json in schemas_dir, keyed by its own $id.

    Raises if a file has no $id — nothing could ever $ref it, which almost
    certainly means it was added without reading how the others are wired.
    """
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(schemas_dir.glob("*.schema.json")):
        with path.open(encoding="utf-8") as fh:
            schema = json.load(fh)
        if "$id" not in schema:
            raise ValueError(f"{path.name} has no $id — nothing can $ref it")
        schemas[schema["$id"]] = schema
    return schemas


def build_registry(schemas: dict[str, dict[str, Any]] | None = None) -> Registry:
    """A referencing.Registry with every schema's $id resolvable via $ref."""
    if schemas is None:
        schemas = load_all_schemas()
    resources = [Resource.from_contents(s) for s in schemas.values()]
    # Every resource here has a declared $id (load_all_schemas raises
    # otherwise), so .id() is never None in practice.
    pairs = [(r.id(), r) for r in resources]
    assert all(uri is not None for uri, _ in pairs)
    return Registry().with_resources(pairs)  # type: ignore[arg-type]


def validator_for(schema_id_or_ref: str, registry: Registry | None = None) -> Draft202012Validator:
    """A validator for a full schema ($id) or a $def within one (URI#/$defs/name).

    >>> validator_for("https://schemas.base.internal/c1_evidence.schema.json")
    >>> validator_for("https://schemas.base.internal/c5_identity.schema.json#/$defs/create_account_request")
    """
    registry = registry or build_registry()
    if "#" in schema_id_or_ref:
        return Draft202012Validator({"$ref": schema_id_or_ref}, registry=registry)
    schema = registry.contents(schema_id_or_ref)
    return Draft202012Validator(schema, registry=registry)
