# schemas/

The executable half of `docs/CONTRACTS.md`. Prose says what a contract
guarantees; these files make the guarantee checkable by machine.

Not every contract has a schema here, and that is deliberate rather than
incomplete:

| Contract | Schema here? | Why |
|---|---|---|
| C1 | `c1_evidence.schema.json` | the base defines the evidence shape |
| C2 | no | OpenAI-compatible — the shape is [already defined externally](https://platform.openai.com/docs/api-reference/chat), and C2's own addition is a policy (which credential), not a payload field |
| C3 | `c3_envelope.schema.json` | the envelope only, in `$defs` (`identity`, `response`, `job_accepted`, `job_status`, `error`); each call's body is instance-specific and lives in `<prefix>-platform/schemas/` |
| C4 | no | Prometheus exposition format, not JSON; its invariant ("no payload") is checked by each layer's own tests, not by a base-level schema |
| C5 | `c5_identity.schema.json` | `$defs` per operation (`issue_credential_request` carries C7's `purpose: "embed"`): `issue_credential_request`/`response`, `revoke_credential_request`, `create_account_request`/`response`, `get_account_response` (the interface half holds accounts and roles only, since 0.7.0) |
| C6 | `c6_provenance.schema.json` | composes `envelope.schema.json` + `classification.schema.json` via `allOf` |
| C6 (read) | `c6_query.schema.json` | `$defs`: `query` (at least one filter, bounded limit) and `response` (C6 records, each under its own class) |
| C7 | no | OpenAI-compatible `/v1/embeddings`; C7's own addition is a credential scope, carried by C5's `issue_credential_request.purpose` |
| C8 | `c8_record.schema.json` | `$defs` per operation: `write_request`/`write_response`, `record`, `read_response`, `delete_request`, `source_upload`/`source_upload_response`; the record body is instance-specific |

`envelope.schema.json` and `classification.schema.json` are shared fragments,
`$ref`'d by the others rather than duplicated into each.

## Validating against them

```python
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

schemas = {}
for path in Path("schemas").glob("*.schema.json"):
    schema = json.load(path.open())
    schemas[schema["$id"]] = schema

registry = Registry().with_resources(
    (Resource.from_contents(s).id(), Resource.from_contents(s)) for s in schemas.values()
)
validator = Draft202012Validator(schemas["https://schemas.base.internal/c1_evidence.schema.json"], registry=registry)
validator.validate(your_payload)
```

`tests/test_schemas.py` in this repository is the reference implementation of
this pattern, and the thing to copy rather than reinvent — it also carries the
tests proving `allOf` composition works, which is not obvious the first time
you write a schema that extends another.

## The trap already caught once

`envelope.schema.json` has no `additionalProperties: false`. That is
deliberate: `c6_provenance.schema.json` composes it via `allOf` and adds
fields of its own, and a subschema with `additionalProperties: false` rejects
exactly the fields the composing schema is trying to add — each `allOf`
branch is validated against the *whole* instance independently. If you are
about to add `additionalProperties: false` to a fragment meant for reuse,
check whether anything `$ref`s it with `allOf` first.
