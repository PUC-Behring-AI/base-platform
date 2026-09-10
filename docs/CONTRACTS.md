# The inter-layer contracts

Four contracts. All of them live **here**, not in the layer that implements them.

## Why here

A contract that lives in the layer implementing it has a single owner, and that
owner can change it alone. The consumer finds out at the rebase. Living here,
changing a contract is a pull request in this repository, and `CODEOWNERS`
requires approval from **both** affected teams.

## The four

| | From → To | Invariant |
|---|---|---|
| **C1** | `knowledge` → `agents` | Every response carries `classification` and `provenance`. **There is no read path without a classification.** |
| **C2** | `agents` → `inference` | OpenAI-compatible. The key is a function of the highest classification in the context. |
| **C3** | `interface` → `agents` | The only arrow leaving the interface. |
| **C4** | all → `knowledge` | Telemetry: traces and metrics. One direction, no response. |

### C1 — evidence retrieval

The consumer (`agents`) needs to know, for every retrieved passage, **where it
came from** and **how sensitive it is**. Both travel with the content, in the
same response, always — not as an optional field and not in a separate call.

An optional field here is equivalent to an absent one: a consumer that forgets to
read it produces an unclassified path, and nothing fails.

### C2 — inference

OpenAI-compatible protocol, so that any client built on the OpenAI SDK works
unchanged.

What this contract adds to the protocol: **the credential is not free**. The
caller chooses between `local-only` and `external` based on the highest
classification present in the context. The inference layer does not validate that
choice — it serves what the key permits, and that is what makes the rule enforced
rather than agreed.

### C3 — the product API

The interface talks to `agents` and to nothing else. There is no "just for this
screen", "just for autocomplete", "just in development" exception. The exception
destroys the property the contract exists to provide.

When a screen needs something this contract does not carry, the fix is a change
to C3 — a pull request here — never a second arrow.

### C4 — telemetry

Traces and metrics flow to the backends hosted in `knowledge`. One direction: no
layer reads another's telemetry at runtime.

## How to change a contract

1. Open a pull request **in this repository**, changing `docs/CONTRACTS.md` and,
   once it exists, the corresponding schema.
2. `CODEOWNERS` requires approval from the two teams the contract binds.
3. The merge here is what authorises the layers to change.

Changing the implementation before the contract inverts the order and turns the
contract into documentation of what already happened.

## State

**Prose and tables only.** Versioned schemas and executable fakes are stage E1 of
the spec and do not exist yet. Until they do, this file is the only source, and
it is normative.
