# The five-layer architecture

## Vocabulary

Three words with fixed meaning. Confusing them produces a design error — it
already did once.

- **base** — the set of reusable engines.
- **instance** — one deployed platform, with its own prefix.
- **domain** — the field of application. It names no repository.

## The layers

| Layer | Owns | Does **not** own |
|---|---|---|
| `knowledge` | Ingestion, relational, vector, RDF graph, object store, assignment of the sensitivity classification at the source, **the provenance store** | No notion of business flow. Never calls a model. Holds no operational metric. |
| `inference` | Ray Serve, vLLM, KubeRay, LiteLLM, virtual keys, budgets, elasticity, enforcement of the routing policy | Knows nothing about the domain. Never reads the knowledge base. |
| `agents` | Flows, orchestration, MCP, guardrails, the routing decision, explainability | Persists no knowledge. Manages no GPU. Renders nothing. Does not *store* the audit trail — it emits to it. |
| `interface` | Session, layout, forms, visualisation, audit view | Does not talk to `knowledge` or `inference`. Exactly one arrow leaves here. |
| `platform` | Contracts, gate, cross-layer tests, release train, **the metrics backend**, the operator CLI | Not one line of product logic. Never stores a payload. |

The `interface` restriction is what makes leak auditing tractable. With one
arrow, "where could confidential data get out?" has a finite answer.

## Base and instance

    BASE (reusable)                  INSTANCE <prefix> (private)
    ┌───────────────────────────┐    ┌──────────────────────────────────┐
    │ base-platform  contracts  │◄───│ <prefix>-platform   schemas      │
    │ base-knowledge engines    │◄───│ <prefix>-knowledge  ontology     │
    │ base-inference serving    │◄───│ <prefix>-inference  models       │
    │ base-agents    runtime    │◄───│ <prefix>-agents     flows, logic │
    │ base-interface shell      │◄───│ <prefix>-interface  forms        │
    └───────────────────────────┘    └──────────────────────────────────┘
       serves every instance              serves only this one

**The boundary is reuse, not code versus configuration.** An instance repository
carries domain *code*, not only declarations. A domain with a scoring model, a
validation rule or a calculation of its own gets software, not YAML — and
trying to express that calculation as configuration is a recognised way to
waste a quarter.

One question separates the columns: *does it serve more than one instance?* If
it does, it is an engine. If it does not, it belongs to the instance — whether
it is an ontology file or two thousand lines of Python.

**Binding rule:** an engine gains an extension point only when two instances ask
for the same thing, or when the first asks for something confidential that
therefore cannot live in the engine. Until then, the instance writes code in its
own repository.

An engine generalised from a single case stiffens what was hard and abstracts
what was easy.

## The routing rule: decided in one place, enforced in another

`agents` decides; `inference` enforces. Both, not one.

    Person (VPN) ──► interface ──C3──► agents ──C2──► inference ──► GPT/Claude
                                          │                ▲        (only with an
                                          C1               │        external key)
                                          ▼                │
                                      knowledge ───────────┘
                              (classification originates here)

The gateway issues two families of virtual key: `local-only`, which reaches only
locally served models, and `external`, which reaches GPT/Claude/Gemini. The
agent layer picks the key from the highest classification present in the
context. The inference layer **does not trust that choice** — it serves what the
key permits.

Without the second half, the guarantee rests on an `if` being correct in code
that four teams edit. With it, it rests on a gateway policy, testable on its own.

## Release

A single versioned train: `base-platform` declares the version of each layer, and
a merge there is the release. Cadence is **weekly**. The train departs on the
scheduled day with whatever is ready; whoever missed it takes the next one.
**The train never waits.**

The cost of that choice, stated so nobody rediscovers it: the slowest layer sets
the pace for all four. The fixed cadence is what stops that becoming an
indefinite wait.

## Two kinds of record, and why they do not share a home

The criterion is one question: **does the record contain payload?**

| | Metrics (C4) | Provenance (C6) |
|---|---|---|
| Answers | is it up, how fast, how much | what produced this, on what evidence, under which key |
| Contains | counters, latencies, histograms | passages, prompts, completions, decisions |
| Lands in | `platform` | `knowledge`, under a classification |
| Retention | days, aggregated, disposable | contractual, per record, append-only |
| Readable by | whoever operates the platform | whoever may read the data it describes |

A trace store that records prompts is not observability. It holds the same text
the request carried, so if that text was confidential, the store is now a
confidential-data store — sitting outside the taxonomy, outside the key policy,
and readable by anyone with operations access.

**Emission is always the layer's own.** What is centralised is where records
land, never who produces them.

## External engine dependencies, verified

Two libraries were assumed as engine dependencies before anyone read their
API. Verified 2026-09-12.

- **`kif`** (`base-knowledge`, IBM Research, Apache-2.0, `kif-lib` 0.13.0 on
  PyPI) is real and matches its own description: a retrieval layer over
  arbitrary RDF graphs (RDFLib, Jena, QLever, RDFox backends; mappings for
  Wikidata, DBpedia, FactGrid, PubChem, UniProt), not a Wikidata-only client.
  It serves the graph half of C1. It does **not** carry provenance as a
  first-class field of its own — what provenance exists is inherited from
  whatever the underlying source already carries (Wikidata's statements have
  qualifiers and references; an arbitrary RDF source may not). `base-knowledge`
  cannot assume C1's provenance requirement is satisfied by `kif` alone; it
  has to be checked against the actual source the layer indexes.
- **`quail`** (`base-agents`) **does not exist** under the assumed description
  ("AI toolkit for questionnaire analysis"). Two public projects share the
  name — `ContextLab/quail` (free-recall memory experiment analysis, unrelated
  domain) and `text-machine-lab/quail` (a reading-comprehension QA dataset, not
  a library) — neither does what the dependency was assumed to do. The
  questionnaire-analysis engine `base-agents` needs for its first domain has no
  chosen library yet. This is not a gap to fill by picking one silently; it is
  an open decision.

## Why it is this way

`docs/ADR.md` carries the decisions and the alternatives discarded, written
without reference to any project.

**This document names no client, no contract and no instance**, and neither does
any other file in this repository. The rule and its cost are in the README.
