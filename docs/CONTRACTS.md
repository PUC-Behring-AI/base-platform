# The inter-layer contracts

Eight contracts. All of them live **here**, not in the layer that implements them.

## Why here

A contract that lives in the layer implementing it has a single owner, and that
owner can change it alone. The consumer finds out at the rebase. Living here,
changing a contract is a pull request in this repository, and `CODEOWNERS`
requires approval from **both** affected teams.

## The eight

| | From → To | Invariant |
|---|---|---|
| **C1** | `knowledge` → `agents` | Every response carries `classification` and `provenance`. **There is no read path without a classification.** |
| **C2** | `agents` → `inference` | OpenAI-compatible. The key is a function of the highest classification in the context. |
| **C3** | `interface` → `agents` | The only arrow leaving the interface. |
| **C4** | all → `platform` | Metrics. **No payload, ever.** One direction, no response. |
| **C5** | `platform` → `inference`, `interface` | Identity: issue a credential, create an account, grant model access. Nobody writes into another layer's storage. |
| **C6** | all → `knowledge` | Provenance. One record per request, carrying a classification, stored under the same policy as the data it describes. Read back through `agents` with at least one filter (`c6_query`). |
| **C7** | `knowledge` → `inference` | Embeddings only. **The credential reaches the embedding models and the embeddings route, and nothing else, and it is always `local-only`.** |
| **C8** | `agents` → `knowledge` | Domain records and uploaded sources. **The engine stamps the classification from the collection's declaration; the caller may only raise it.** Every write emits C6. |

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

"Where it came from" is two things: the **source** (the collection, such as a
set of documents) and the **locator** (where inside it, such as a document and
its pages). Both are required. A passage that names its collection but not its
place in it cannot be cited, and a consumer asked "where does it say that?"
has nothing to answer with.

### C2 — inference

OpenAI-compatible protocol, so that any client built on the OpenAI SDK works
unchanged.

What this contract adds to the protocol: **the credential is not free**. The
caller chooses between `local-only` and `external` based on the highest
classification present in the context. The inference layer does not validate that
choice — it serves what the key permits, and that is what makes the rule enforced
rather than agreed.

**Spend is counted per key, not per person.** On product calls, `agents` calls
`inference` with its own key, chosen by classification. The base enforces
budgets and rate limits per key, that is, per deployment: no product call is
limited per person. An instance that needs per-person limits passes the person
as the end user and gives each one a budget on the gateway; that mechanism was
measured on the pinned gateway in #69. It is safe only while no person holds a
key that reaches chat models, because any key may name any end user.

### C3 — the product API

The interface talks to `agents` and to nothing else. There is no "just for this
screen", "just for autocomplete", "just in development" exception. The exception
destroys the property the contract exists to provide.

When a screen needs something this contract does not carry, the fix is a change
to C3 — a pull request here — never a second arrow.

**The envelope** (`schemas/c3_envelope.schema.json`). The body of each call is
instance-defined, and each instance keeps its payload schemas in
`<prefix>-platform/schemas/`. What every call shares is fixed here:

- **`X-Request-Id`.** The interface's backend-for-frontend (ADR-013) generates
  it, one per call. Every layer propagates it unchanged, and it keys C6.
- **Identity.** `X-Account-Id` and `X-Account-Roles` (the `identity` definition)
  are asserted by the backend-for-frontend. `agents` trusts them because the
  backend-for-frontend is the only process that can reach it. They are never
  taken from the browser.
- **Every response carries a `classification`.** A screen must know what it is
  showing. An answer built from classified evidence carries that evidence's
  class, and nothing in the interface may lower it.
- **Every response carries an `outcome`: `answered` or `declined`.** A flow
  that cannot or should not answer, because the evidence does not support an
  answer for instance, declines. That is a result, not a failure: it must not
  look like an error on a screen or in an error rate. A declined response
  carries a machine-readable `declined_code` and keeps its `classification`.
  The body stays instance-defined, so the marker sits beside it, not inside it.
- **A typed error.** It carries a machine-readable `code` and a `message` for a
  person. The message never contains classified content, because errors reach
  logs.
- **Two call modes.**
  - **Synchronous:** the `response` definition.
  - **Job:** starting returns `job_accepted`. Polling returns `job_status`,
    which carries ordered steps, so a screen can show each step as it really
    completes, and either a `result` (a `response`) or an `error`, never both.
    The job keeps the request id of the call that started it, and every step
    emits C6 under it.

  Streaming is not part of C3 until a screen needs it.

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
| `platform` → `interface` | Create, inspect and remove an account, with its role. Nothing else: since ADR-013 the interface calls no model, so it holds no model credential and no model catalog |

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

**BREAKING, 0.7.0.** The interface half shrinks to accounts and roles. Five
operations existed only because the interface's earlier chat UI called the
model gateway directly: grant and revoke access to a model, link a
credential, register a model in the catalog, and configure the upstream
gateway. Under ADR-013 the interface reaches only `agents`, so:

- **A model credential no longer enters the interface.** That is the point of
  the change, not a side effect. `link_credential` wrote a secret into a layer
  that has no use for it.
- **Inspecting an account** returns the account and its role, without
  `has_credential` or `model_ids`.
- **Which models a person may use** is the scope of the credential that
  `inference` issues (`platform → inference`). The interface no longer keeps a
  second copy of it.

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

**Reading it back** (`schemas/c6_query.schema.json`). An audit view needs
"show me everything that produced this output", and the interface may reach
only `agents`. So the read goes interface → `agents` (C3) → `knowledge`:

- **A query names at least one filter**: the request it is about, a record
  (collection plus id), or a time window, with a bounded `limit`. A query with
  no filter would make the provenance store the widest read path in the system.
- **Every record comes back under its own classification.** A record about
  confidential evidence is confidential to read.
- **Who may read which class is the instance's rule, by role.** Classification
  says where data may go, not who may see it. An agents instance declares
  which roles read which classes. `agents` passes the interface no record of a
  class the caller's roles do not grant. **With no rule declared, every read is
  refused**: nobody reads by default. The rule is role × class only. Access per
  assessment or per team would be a separate contract change.
- **The interface sends the query as C3's `provenance_query`**: filter, limit
  and cursor. `agents` adds the reader's request id and forwards a `c6_query`.
  The answer is a C3 `response` whose body holds `records` (and
  `next_cursor`), classified as the strictest class among them, or
  `local-only` when there are none.
- **The read is itself recorded**, under the reader's own request id.
- **A human decision is a C6 record.** Accepting, overriding or dismissing a
  model proposal, or approving a document, is emitted by `agents` on the
  interface's behalf, with the decision in `payload`. It carries payload, so it
  is provenance, not a metric. The interface sends it as C3's `decision`
  (`about_request_id`, `decision`, `target`, an optional `detail`). **The
  screen never chooses its class.** `agents` classifies it as the strictest
  class among the C6 records of the request decided on, and refuses a decision
  about a request with no record.

### C7 — embeddings

`knowledge` turns every passage it indexes, and every query it searches with,
into a vector. The model that does it is served by `inference`, like every
other model, so that one layer owns the GPUs, the serving stack and the
enforcement of who reaches what. ADR-012 records why `knowledge`, which calls no
model, may call this one.

It is not C2. C2's credential is chosen per request, from the highest
classification in the context. `knowledge`'s embedding credential is constant:
documents of every class pass through it, so it must be acceptable for the most
sensitive one. What C7 fixes:

- **OpenAI-compatible `/v1/embeddings`, and nothing else.** The credential is
  issued through C5 with `purpose: "embed"`. Inference confines it in two ways.
  It reaches only the deployment's embedding models, through a dedicated access
  group, so a chat model refuses it. And it may call only the embeddings route,
  so an embedding model refuses a chat completion with it. Both halves are
  needed: measured on LiteLLM v1.85.0, a key confined by model alone could
  still ask an embedding model for a chat completion.
- **Always `local-only`.** The C5 schema refuses an embedding credential with
  any other key policy, and an embedding model declared as external refuses to
  start in `inference`.
- **One embedding model per index.** Vectors from two models are not
  comparable. Changing the model means re-embedding the index, never mixing
  vectors from both.
- **A vector is stored under its passage's classification.** A vector can leak
  what its text said, so it is that text's data, under that text's class.
- **Every call carries `X-Request-Id`.** A query-time call reuses the C1
  request's id. An ingest job gets one id, generated by `knowledge` for that
  job. Either way, `knowledge` records the call in C6 (`emitted_by:
  knowledge`), under the classification of what was embedded.
- **Instance code never holds the credential.** The knowledge engine builds the
  client and hands a module an embedding function, never the key or the URL
  (ADR-011's stamp, applied to this arrow).

### C8 — domain records

The product builds things: an assessment, its answers, the evidence a person
attaches, the sources they upload. These records are not evidence retrieved
under C1, and they are not provenance under C6. Until C8 there was no contract
for them. The interface stores no domain data, and `agents` is not a store, so
the first instance would have written them wherever was closest: the browser,
the interface's database, or a client from `agents` straight into the store.
Each of those paths carries classified data with no classification and no
provenance.

What C8 fixes (`schemas/c8_record.schema.json`):

- **Collections are declared by the instance in `knowledge`, next to its
  connectors.** Each collection carries a class, the same way a source does. A
  write to an undeclared collection is refused.
- **The engine stamps; the caller never classifies.** This is ADR-011's rule,
  applied to writes. A write may carry `requested_class` to make a record *more*
  sensitive than its collection, never less, and the engine refuses a lower
  one. Reads return the class with every record, as C1 does: **no read path
  without a classification.**
- **Optimistic concurrency.** A replace or a delete names the
  `expected_revision`, and a stale one is refused. Two people editing the same
  record must not silently overwrite each other.
- **Uploading a source** sends the file with `source_upload` metadata. It is
  ingested under its collection's class like any connector, and afterwards it
  is evidence, found through C1.
- **Every write and every upload emits C6** under the request id it carries.
  The event log of a record is C6, not a field of the record.

The bodies are instance-defined. Only the envelope is fixed here.

## How to change a contract

1. Open a pull request **in this repository**, changing `docs/CONTRACTS.md` and,
   once it exists, the corresponding schema.
2. `CODEOWNERS` requires approval from the two teams the contract binds.
3. The merge here is what authorises the layers to change.

Changing the implementation before the contract inverts the order and turns the
contract into documentation of what already happened.

## State

**C1, C3 (its envelope), C5, C6 (write and read) and C8 are executable.** Their payload shapes live in `schemas/` as
JSON Schema, with `tests/test_schemas.py` proving each one accepts what it
should and rejects what it should — including the invariant that matters
most, that a classification's `key_policy` can only ever be `local-only` or
`external`.

C2 and C7 have no schema here because their shapes are OpenAI-compatible —
defined externally, not by this repository. C7's own addition is in C5: the
`purpose` an embedding credential is issued with. C3's schema covers the
envelope only; the body of each call is instance-specific by design. C4 has
none because it is a metrics exposition format, not JSON, and its invariant
(no payload) is enforced by each layer's own tests rather than by a base-level
schema.

This file remains the normative *description* of what each contract
guarantees. `schemas/` is normative for the payload *shapes* it covers;
where the two would ever disagree, fix the disagreement, because a schema
whose text and validator tell different stories loses whichever one nobody
reads.

Executable fakes — a running service per layer that speaks its side of these
schemas — are the next slice, tracked per layer.
