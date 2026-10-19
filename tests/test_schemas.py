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
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry

from schemas.validate import build_registry, load_all_schemas, unchecked_formats, validator_for

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


def test_at_least_the_six_expected_schemas_exist(schemas: dict[str, Any]) -> None:
    expected = {
        "https://schemas.base.internal/envelope.schema.json",
        "https://schemas.base.internal/classification.schema.json",
        "https://schemas.base.internal/c1_evidence.schema.json",
        "https://schemas.base.internal/c5_identity.schema.json",
        "https://schemas.base.internal/c6_provenance.schema.json",
        "https://schemas.base.internal/c3_envelope.schema.json",
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
                    "locator": "page 3",
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


def test_c1_evidence_rejects_an_empty_locator(
    schemas: dict[str, Any], registry: Registry
) -> None:
    instance = _valid_c1_instance()
    instance["passages"][0]["provenance"]["locator"] = ""
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
            "create_account_request",
            {
                "principal_id": "user-42",
                "display_name": "Jane Researcher",
                "password": "correct-horse-battery",
                "role": "admin",
            },
        ),
        (
            "create_account_response",
            {
                "account_id": "acct-1",
                "principal_id": "user-42",
                "created_at": "2026-09-14T10:00:00Z",
                "password": "generated-or-echoed",
            },
        ),
        (
            "get_account_response",
            {
                "account_id": "acct-1",
                "principal_id": "user-42",
                "display_name": "Jane Researcher",
                "role": "user",
                "has_credential": True,
                "model_ids": ["local-mistral-7b"],
            },
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


def test_c5_issue_credential_accepts_an_embedding_credential(registry: Registry) -> None:
    """C7's credential is issued through C5, local-only, with purpose 'embed'."""
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/issue_credential_request"
    }
    instance = {
        "principal_id": "knowledge",
        "budget": 1.0,
        "rate_limit_rpm": 600,
        "allowed_key_policies": ["local-only"],
        "purpose": "embed",
    }
    Draft202012Validator(schema, registry=registry).validate(instance)


@pytest.mark.parametrize("policies", [["external"], ["local-only", "external"]])
def test_c5_issue_credential_refuses_an_embedding_credential_that_can_leave(
    registry: Registry, policies: list[str]
) -> None:
    """An embedding credential reaches every document and every query in the
    index, so it can never be one that reaches a third-party provider (C7)."""
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/issue_credential_request"
    }
    instance = {
        "principal_id": "knowledge",
        "budget": 1.0,
        "rate_limit_rpm": 600,
        "allowed_key_policies": policies,
        "purpose": "embed",
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema, registry=registry).validate(instance)


def test_c5_issue_credential_rejects_an_unknown_purpose(registry: Registry) -> None:
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/issue_credential_request"
    }
    instance = {
        "principal_id": "user-42",
        "budget": 2.0,
        "rate_limit_rpm": 60,
        "allowed_key_policies": ["local-only"],
        "purpose": "anything",
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


def test_c5_create_account_rejects_a_too_short_password(registry: Registry) -> None:
    """A password short enough to type by accident is not a smaller version
    of a real one -- see the minLength this shares with nothing else in the
    schema by coincidence."""
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/create_account_request"
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema, registry=registry).validate(
            {"principal_id": "user-42", "display_name": "Jane", "password": "short"}
        )


def test_c5_create_account_rejects_an_unknown_role(registry: Registry) -> None:
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/create_account_request"
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema, registry=registry).validate(
            {"principal_id": "user-42", "display_name": "Jane", "role": "superadmin"}
        )


def test_c5_get_account_rejects_missing_has_credential(registry: Registry) -> None:
    """has_credential is the one field this response exists to carry safely
    -- the alternative colleague.sh's original docker exec status check used
    was printing a prefix of the actual key, which this operation exists to
    stop doing."""
    schema = {
        "$ref": "https://schemas.base.internal/c5_identity.schema.json#/$defs/get_account_response"
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema, registry=registry).validate(
            {
                "account_id": "acct-1",
                "principal_id": "user-42",
                "display_name": "Jane",
                "role": "user",
                "model_ids": [],
            }
        )


# ── c3_envelope.schema.json — what every product call shares ─────────────

_RID = "3fae9c9e-0e34-4e0a-9f9d-6c9f6a0a2b11"
_CLASS = {"name": "client-confidential", "key_policy": "local-only"}


def _c3(def_name: str, registry: Registry) -> Draft202012Validator:
    schema = {"$ref": f"https://schemas.base.internal/c3_envelope.schema.json#/$defs/{def_name}"}
    return Draft202012Validator(schema, registry=registry)


@pytest.mark.parametrize(
    ("def_name", "valid_instance"),
    [
        ("identity", {"account_id": "acct-1", "roles": ["user"]}),
        ("response", {"request_id": _RID, "classification": _CLASS, "body": {}}),
        ("job_accepted", {"request_id": _RID, "job_id": "job-1"}),
        (
            "job_status",
            {
                "request_id": _RID,
                "job_id": "job-1",
                "state": "running",
                "steps": [
                    {"name": "read sources", "state": "done"},
                    {"name": "draft", "state": "running"},
                ],
            },
        ),
        (
            "job_status",
            {
                "request_id": _RID,
                "job_id": "job-1",
                "state": "succeeded",
                "steps": [{"name": "draft", "state": "done"}],
                "result": {"request_id": _RID, "classification": _CLASS, "body": {"drafted": 3}},
            },
        ),
        (
            "job_status",
            {
                "request_id": _RID,
                "job_id": "job-1",
                "state": "failed",
                "steps": [{"name": "draft", "state": "failed"}],
                "error": {
                    "request_id": _RID,
                    "code": "model_unavailable",
                    "message": "no local model",
                },
            },
        ),
        ("error", {"request_id": _RID, "code": "not_found", "message": "no such record"}),
    ],
)
def test_c3_definition_accepts_its_valid_instance(
    def_name: str, valid_instance: dict[str, Any], registry: Registry
) -> None:
    _c3(def_name, registry).validate(valid_instance)


def test_c3_response_rejects_a_missing_classification(registry: Registry) -> None:
    """A screen must know what it is showing; C1 closes the same gap on reads."""
    with pytest.raises(ValidationError):
        _c3("response", registry).validate({"request_id": _RID, "body": {}})


def test_c3_response_rejects_a_missing_request_id(registry: Registry) -> None:
    with pytest.raises(ValidationError):
        _c3("response", registry).validate({"classification": _CLASS, "body": {}})


def test_c3_job_status_rejects_an_unknown_state(registry: Registry) -> None:
    with pytest.raises(ValidationError):
        _c3("job_status", registry).validate(
            {"request_id": _RID, "job_id": "job-1", "state": "streaming", "steps": []}
        )


def test_c3_job_status_rejects_success_without_a_result(registry: Registry) -> None:
    with pytest.raises(ValidationError):
        _c3("job_status", registry).validate(
            {"request_id": _RID, "job_id": "job-1", "state": "succeeded", "steps": []}
        )


def test_c3_job_status_rejects_a_result_while_running(registry: Registry) -> None:
    with pytest.raises(ValidationError):
        _c3("job_status", registry).validate(
            {
                "request_id": _RID,
                "job_id": "job-1",
                "state": "running",
                "steps": [],
                "result": {"request_id": _RID, "classification": _CLASS, "body": {}},
            }
        )


def test_c3_identity_rejects_an_empty_account(registry: Registry) -> None:
    with pytest.raises(ValidationError):
        _c3("identity", registry).validate({"account_id": "", "roles": []})


def test_c3_error_rejects_a_code_that_is_not_machine_readable(registry: Registry) -> None:
    with pytest.raises(ValidationError):
        _c3("error", registry).validate({"request_id": _RID, "code": "Not Found!", "message": "x"})


# ── validator_for checks "format", or refuses to build ──────────────────

_C6_ID = "https://schemas.base.internal/c6_provenance.schema.json"


def test_validator_for_rejects_a_request_id_that_is_not_a_uuid() -> None:
    """base-platform#21: "format" was an annotation, so X-Request-Id: trace-1
    reached the C6 store, whose audit trail is keyed on it."""
    instance = {**_valid_c6_instance(), "request_id": "trace-1"}
    with pytest.raises(ValidationError, match="uuid"):
        validator_for(_C6_ID).validate(instance)


def test_validator_for_rejects_a_timestamp_that_is_not_a_date_time() -> None:
    instance = {**_valid_c6_instance(), "emitted_at": "yesterday"}
    with pytest.raises(ValidationError, match="date-time"):
        validator_for(_C6_ID).validate(instance)


def test_validator_for_accepts_a_valid_instance() -> None:
    validator_for(_C6_ID).validate(_valid_c6_instance())


def test_every_format_the_schemas_use_has_a_checker_here(schemas: dict[str, Any]) -> None:
    """Without jsonschema's format-nongpl extra, date-time and uri have no
    checker and pass anything. build_registry refuses that; this proves the
    environment running the tests is not the one that would."""
    assert unchecked_formats(schemas) == set()


def test_build_registry_refuses_a_format_nothing_checks(
    schemas: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    checkers = dict(Draft202012Validator.FORMAT_CHECKER.checkers)
    del checkers["date-time"]
    monkeypatch.setattr(Draft202012Validator.FORMAT_CHECKER, "checkers", checkers)
    with pytest.raises(RuntimeError, match="date-time"):
        build_registry(schemas)
