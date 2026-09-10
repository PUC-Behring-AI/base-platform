# The inter-layer contracts

Six contracts. All of them live **here**, not in the layer that implements them.

## Why here

A contract that lives in the layer implementing it has a single owner, and that
owner can change it alone. The consumer finds out at the rebase. Living here,
changing a contract is a pull request in this repository, and `CODEOWNERS`
requires approval from **both** affected teams.

## The six

| | From → To | Invariant |
|---|---|---|
| **C1** | `knowledge` → `agents` | Every response carries `classification` and `provenance`. **There is no read path without a classification.** |
| **C2** | `agents` → `inference` | OpenAI-compatible. The key is a function of the highest classification in the context. |
| **C3** | `interface` → `agents` | The only arrow leaving the interface. |
| **C4** | all → `platform` | Metrics. **No payload, ever.** One direction, no response. |
| **C5** | `platform` → `inference`, `interface` | Identity: issue a credential, create an account, grant model access. Nobody writes into another layer's storage. |
| **C6** | all → `knowledge` | Provenance. One record per request, carrying a classification, stored under the same policy as the data it describes. |

### The criterion that separates C4 from C6

**Does the record contain payload?**

- **No** — a counter, a latency, a histogram. That is a *metric*: C4, to `platform`,
  operational, aggregated, disposable.
- **Yes** — a retrieved passage, a prompt, a completion, a decision. That is
  *provenance*: C6, to `knowledge`, **classified data**, permanent, retained on
  the terms the deployment's contract sets.

The two were one contract in version 0.1.0, and the conflation created a leak
path. See ADR-009.

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

### C4 — metrics

Counters, latencies, histograms. They flow to the backend hosted in `platform`,
because operational instrumentation serves whoever runs the five layers and is
not knowledge about any domain.

**No payload.** Not a prompt, not a completion, not a retrieved passage, not a
user identifier that resolves to a person. A metric that carries payload has
become provenance, and provenance is C6 — stored under a classification, not in
an operations backend readable by anyone on call.

Emission is always the layer's own. What is shared is where records land, never
who emits them.

### C5 — identity

Provisioning a person crosses two layers: a credential in `inference`, an
account and its model grants in `interface`. This contract exists because
without it the crossing happens anyway — the first implementation reached into
the interface's private database with `docker exec` and raw SQL, and no
contract could be violated because none existed.

| Direction | The layer must expose |
|---|---|
| `platform` → `inference` | Issue, inspect and revoke a credential, with its budget and rate limits |
| `platform` → `interface` | Create, inspect and remove an account, and grant or revoke access to a model |

**No layer writes into another layer's storage.** Not through a database file,
not through a container name, not "just for provisioning". A layer that cannot
be provisioned through its own API is a layer whose API is incomplete — that is
a defect in the layer, not a licence to go around it.

`platform` orchestrates the two calls and owns the rollback when the second
fails after the first succeeded.

### C6 — provenance

One record per request, emitted by every layer that touched it, correlated by a
request identifier that the interface generates and every layer propagates
unchanged.

The record carries what the audit trail needs and nothing more: which evidence
was retrieved, which model was addressed, **which key policy the request ran
under**, and what was produced.

Three properties this contract requires, and each has a reason:

- **It carries a classification**, assigned the same way C1 assigns one. A
  provenance record about confidential evidence *is* confidential. It is stored
  under the same taxonomy and the same key policy as the data it describes —
  otherwise the audit trail becomes the widest read path in the system.
- **It is append-only.** An audit trail that can be edited answers no question
  worth asking.
- **It is reconstructable across layers.** "Show me everything that produced
  this output" must be answerable from the store alone. That is why the records
  land in one place rather than five, and why the correlation identifier is a
  contract obligation rather than a convention.

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
