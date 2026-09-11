# schemas/

The executable half of `docs/CONTRACTS.md`. Prose says what a contract
guarantees; these files make the guarantee checkable by machine.

Not every contract has a schema here, and that is deliberate rather than
incomplete:

| Contract | Schema here? | Why |
|---|---|---|
| C1 | `c1_evidence.schema.json` | the base defines the evidence shape |
| C2 | no | OpenAI-compatible — the shape is [already defined externally](https://platform.openai.com/docs/api-reference/chat), and C2's own addition is a policy (which credential), not a payload field |
| C3 | no | intentionally instance-specific — "one arrow leaves the interface" is an architectural invariant, not a payload shape the base can fix |
| C4 | no | Prometheus exposition format, not JSON; its invariant ("no payload") is checked by each layer's own tests, not by a base-level schema |
| C5 | `c5_identity.schema.json` | `$defs` per operation: `issue_credential_request`/`response`, `revoke_credential_request`, `create_account_request`/`response`, `grant_access_request`, `revoke_access_request` |
| C6 | `c6_provenance.schema.json` | composes `envelope.schema.json` + `classification.schema.json` via `allOf` |

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
