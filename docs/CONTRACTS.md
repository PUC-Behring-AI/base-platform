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
| `platform` → `interface` | Create, inspect and remove an account; grant or revoke access to a model; link an issued credential to an account; register a model in the visibility catalog; configure the upstream gateway once at deploy time |

**No layer writes into another layer's storage.** Not through a database file,
not through a container name, not "just for provisioning". A layer that cannot
be provisioned through its own API is a layer whose API is incomplete — that is
a defect in the layer, not a licence to go around it.

`platform` orchestrates the two calls and owns the rollback when the second
fails after the first succeeded.

**BREAKING, 0.3.0.** The three operations added to `interface` close a gap
`0.2.0` left open: a consuming layer's own account-creation script could call
`create_account` and `grant_access` and still have three real reasons left to
reach into the interface's storage directly — linking an issued credential to
that account, registering the account's models in the visibility catalog, and
the one-time upstream configuration a fresh deployment needs before any of it
is reachable. Each is now its own operation, for the same reason the first two
were: a layer that cannot be provisioned through its own API is a layer whose
API is incomplete.

- **Linking a credential** is not the same operation as issuing one. The
  credential is minted by `inference` (`issue_credential`); this operation
  hands the resulting secret to `interface` so it can call the gateway on the
  account's behalf. Two operations, two layers, one still-external secret.
- **The model catalog entry is global and idempotent**, not per-account — a
  deployment registers a model once, when it becomes available, not once per
  person provisioned onto it. A caller that repeats it per account is not
  violating the contract; it is just calling it far more often than the data
  changes.
- **Configuring the upstream gateway is a deploy-time bootstrap**, not
  provisioning. A deployment that skips it has no model dropdown and every
  account it provisions is otherwise complete — the two failure modes do not
  look alike, and conflating them into one operation would hide which one
  happened.

**BREAKING, 0.4.0.** `create_account` grows two optional request fields and
one conditional response field, found trying to make an actual consumer
switch to the three 0.3.0 operations: a login credential and a role, neither
of which the account operation could carry before. `platform → interface`
also grows a fourth operation, **inspect an account**, closing the gap
between what C5's own prose already promised ("create, inspect and remove")
and what only ever shipped (create and remove).

- **A password is optional on the way in, conditional on the way out.** If the
  caller supplies one, it is set; if not, and the account is being created for
  the first time, the interface generates one — and must return it, because
  nothing else in this contract issues a login credential, and a generated
  secret nobody receives is not a smaller version of provisioning, it is a
  broken one. An update to an existing account that supplies no password
  touches nothing and returns none.
- **A role is optional and create-time only.** Applied when the account is
  created; ignored on an update to one that already exists, the same way the
  password is.
- **Inspecting an account never returns the credential itself, only
  `has_credential`.** The operation this replaces — reading Open WebUI's
  `api_key` table directly — printed a prefix of the real secret. A status
  check does not need the secret to answer "is one linked", and carrying it
  anyway would make this operation a second way to read what
  `link_credential` already wrote once.

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

**C1, C5 and C6 are executable.** Their payload shapes live in `schemas/` as
JSON Schema, with `tests/test_schemas.py` proving each one accepts what it
should and rejects what it should — including the invariant that matters
most, that a classification's `key_policy` can only ever be `local-only` or
`external`.

C2 has no schema here because its shape is OpenAI-compatible — defined
externally, not by this repository. C3 has none because its shape is
instance-specific by design. C4 has none because it is a metrics exposition
format, not JSON, and its invariant (no payload) is enforced by each layer's
own tests rather than by a base-level schema.

This file remains the normative *description* of what each contract
guarantees. `schemas/` is normative for the three payload *shapes* it covers;
where the two would ever disagree, fix the disagreement, because a schema
whose text and validator tell different stories loses whichever one nobody
reads.

Executable fakes — a running service per layer that speaks its side of these
schemas — are the next slice, tracked per layer.
