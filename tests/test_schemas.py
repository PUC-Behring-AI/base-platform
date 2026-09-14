"""Tests proving the base's JSON Schemas are valid and compose correctly.

These are the executable half of the contracts in docs/CONTRACTS.md. A schema
that does not validate what it claims to is worse than no schema: it looks
like enforcement and enforces nothing -- the exact failure mode ADR-009
documents for the pre-split C4 contract, now happening one layer up if these
tests are not the ones actually run.
"""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry

from schemas.validate import build_registry, load_all_schemas

# Imported, not reimplemented: this repository is schemas/validate.py's own
# first consumer, and duplicating its loader here to test it would be the
# same defect the module's own docstring warns sibling repositories against.


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, Any]]:
    return load_all_schemas()


@pytest.fixture(scope="module")
def registry(schemas: dict[str, dict[str, Any]]) -> Registry:
    return build_registry(schemas)


def _validator(schema: dict[str, Any], registry: Registry) -> Draft202012Validator:
    return Draft202012Validator(schema, registry=registry)


# ── Every schema file is well-formed ─────────────────────────────────────


def test_at_least_the_five_expected_schemas_exist(schemas: dict[str, Any]) -> None:
    expected = {
        "https://schemas.base.internal/envelope.schema.json",
        "https://schemas.base.internal/classification.schema.json",
        "https://schemas.base.internal/c1_evidence.schema.json",
        "https://schemas.base.internal/c5_identity.schema.json",
        "https://schemas.base.internal/c6_provenance.schema.json",
    }
    missing = expected - schemas.keys()
    assert not missing, f"schema(s) missing from schemas/: {missing}"


def test_every_schema_is_valid_draft_2020_12(schemas: dict[str, Any]) -> None:
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)  # raises SchemaError if invalid


# ── envelope.schema.json ─────────────────────────────────────────────────


def test_envelope_accepts_a_minimal_valid_instance(
    schemas: dict[str, Any], registry: Registry
) -> None:
    instance = {
        "request_id": "3fae9c9e-0e34-4e0a-9f9d-6c9f6a0a2b11",
        "emitted_at": "2026-09-11T10:00:00Z",
        "emitted_by": "agents",
    }
    envelope_schema = schemas["https://schemas.base.internal/envelope.schema.json"]
    _validator(envelope_schema, registry).validate(instance)


def test_envelope_rejects_an_unknown_layer_name(
    schemas: dict[str, Any], registry: Registry
) -> None:
    instance = {
        "request_id": "3fae9c9e-0e34-4e0a-9f9d-6c9f6a0a2b11",
        "emitted_at": "2026-09-11T10:00:00Z",
        "emitted_by": "not-a-real-layer",
    }
    envelope_schema = schemas["https://schemas.base.internal/envelope.schema.json"]
    with pytest.raises(Exception):
        _validator(envelope_schema, registry).validate(instance)


# ── classification.schema.json — the security-relevant invariant ────────


def test_classification_accepts_the_two_allowed_key_policies(
    schemas: dict[str, Any], registry: Registry
) -> None:
    validator = _validator(
        schemas["https://schemas.base.internal/classification.schema.json"], registry
    )
    for policy in ("local-only", "external"):
        validator.validate({"name": "anything", "key_policy": policy})


def test_classification_rejects_a_third_key_policy(
    schemas: dict[str, Any], registry: Registry
) -> None:
    """This is the test that matters most in this file.

    C2's whole guarantee is that a request can only ever run under one of two
    key families. A schema that quietly accepted a third value would not
    break anything visibly -- it would just stop being the thing that makes
    the guarantee enforceable.
    """
    validator = _validator(
        schemas["https://schemas.base.internal/classification.schema.json"], registry
    )
    with pytest.raises(Exception):
        validator.validate({"name": "anything", "key_policy": "trust-me"})


# ── c1_evidence.schema.json ──────────────────────────────────────────────


def _valid_c1_instance() -> dict[str, Any]:
    return {
        "request_id": "3fae9c9e-0e34-4e0a-9f9d-6c9f6a0a2b11",
        "passages": [
            {
                "content": "the sky is blue",
                "classification": {"name": "public", "key_policy": "external"},
                "provenance": {
                    "source": "doc://example/1",
                    "retrieved_at": "2026-09-11T10:00:00Z",
                },
            }
        ],
    }


def test_c1_evidence_accepts_a_valid_instance(
    schemas: dict[str, Any], registry: Registry
) -> None:
    _validator(schemas["https://schemas.base.internal/c1_evidence.schema.json"], registry).validate(
        _valid_c1_instance()
    )


def test_c1_evidence_rejects_a_passage_with_no_classification(
    schemas: dict[str, Any], registry: Registry
) -> None:
    """The invariant CONTRACTS.md states in words: there is no read path
    without a classification. This is that sentence, executable."""
    instance = _valid_c1_instance()
    del instance["passages"][0]["classification"]
    with pytest.raises(Exception):
        _validator(
            schemas["https://schemas.base.internal/c1_evidence.schema.json"], registry
        ).validate(instance)


def test_c1_evidence_rejects_a_passage_with_no_provenance(
    schemas: dict[str, Any], registry: Registry
) -> None:
    instance = _valid_c1_instance()
    del instance["passages"][0]["provenance"]
    with pytest.raises(Exception):
        _validator(
            schemas["https://schemas.base.internal/c1_evidence.schema.json"], registry
        ).validate(instance)


# ── c6_provenance.schema.json — proves the allOf composition works ──────


def _valid_c6_instance() -> dict[str, Any]:
    return {
        "request_id": "3fae9c9e-0e34-4e0a-9f9d-6c9f6a0a2b11",
        "emitted_at": "2026-09-11T10:00:05Z",
        "emitted_by": "agents",
        "classification": {"name": "client-confidential", "key_policy": "local-only"},
        "payload": {"model_addressed": "local-mistral-7b", "evidence_ids": ["doc://example/1"]},
    }


def test_c6_provenance_accepts_a_valid_instance(
    schemas: dict[str, Any], registry: Registry
) -> None:
    """If this fails, the allOf composition with envelope.schema.json is
    broken -- most likely because envelope grew additionalProperties:false
    again. See the note in envelope.schema.json for why that trap exists."""
    _validator(
        schemas["https://schemas.base.internal/c6_provenance.schema.json"], registry
    ).validate(_valid_c6_instance())


def test_c6_provenance_rejects_missing_classification(
    schemas: dict[str, Any], registry: Registry
) -> None:
    """ADR-009 exists because a provenance record without a classification is
    exactly how a trace store quietly becomes an unclassified data store."""
    instance = _valid_c6_instance()
    del instance["classification"]
    with pytest.raises(Exception):
        _validator(
            schemas["https://schemas.base.internal/c6_provenance.schema.json"], registry
        ).validate(instance)


def test_c6_provenance_rejects_missing_payload(
    schemas: dict[str, Any], registry: Registry
) -> None:
    instance = _valid_c6_instance()
    del instance["payload"]
    with pytest.raises(Exception):
        _validator(
            schemas["https://schemas.base.internal/c6_provenance.schema.json"], registry
        ).validate(instance)


# ── c5_identity.schema.json — $defs, resolved individually ──────────────


@pytest.mark.parametrize(
    ("def_name", "valid_instance"),
    [
        (
            "issue_credential_request",
            {
                "principal_id": "user-42",
                "budget": 2.0,
                "rate_limit_rpm": 60,
                "allowed_key_policies": ["local-only"],
            },
        ),
        (
            "create_account_request",
            {"principal_id": "user-42", "display_name": "Jane Researcher"},
        ),
        (
            "grant_access_request",
            {"principal_id": "user-42", "model_id": "local-mistral-7b"},
        ),
        (
            "link_credential_request",
            {"principal_id": "user-42", "virtual_key": "sk-abc123"},
        ),
        (
            "ensure_model_catalog_entry_request",
            {"model_id": "local-mistral-7b", "display_name": "Mistral 7B (local)"},
        ),
        (
            "configure_upstream_request",
            {"api_base_url": "http://litellm:4000/v1", "discovery_key": "sk-discovery"},
        ),
    ],
)
def test_c5_definition_accepts_its_valid_instance(
    def_name: str,
    valid_instance: dict[str, Any],
    registry: Registry,
) -> None:
    schema = {"$ref": f"https://schemas.base.internal/c5_identity.schema.json#/$defs/{def_name}"}
    Draft202012Validator(schema, registry=registry).validate(valid_instance)


def test_c5_issue_credential_rejects_an_unknown_key_policy(registry: Registry) -> None:
    """A principal cannot be issued a credential scoped to a policy that does
    not exist -- same invariant as classification, checked at the point
    where a credential is actually minted."""
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/issue_credential_request"
    }
    instance = {
        "principal_id": "user-42",
        "budget": 2.0,
        "rate_limit_rpm": 60,
        "allowed_key_policies": ["anything-goes"],
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema, registry=registry).validate(instance)


def test_c5_link_credential_rejects_missing_virtual_key(registry: Registry) -> None:
    """The whole point of this operation is carrying the secret across the
    boundary -- an instance missing it is not a smaller version of the
    request, it is a different, useless one."""
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/link_credential_request"
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema, registry=registry).validate({"principal_id": "user-42"})


def test_c5_configure_upstream_rejects_missing_discovery_key(registry: Registry) -> None:
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/configure_upstream_request"
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema, registry=registry).validate(
            {"api_base_url": "http://litellm:4000/v1"}
        )
