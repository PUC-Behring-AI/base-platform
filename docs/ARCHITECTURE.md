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
| `knowledge` | Ingestion, relational, vector, RDF graph, object store, assignment of the sensitivity classification at the source, observability backends | No notion of business flow. Never calls a model. |
| `inference` | Ray Serve, vLLM, KubeRay, LiteLLM, virtual keys, budgets, elasticity, enforcement of the routing policy | Knows nothing about the domain. Never reads the knowledge base. |
| `agents` | Flows, orchestration, MCP, guardrails, the routing decision, audit trail, explainability | Persists no knowledge. Manages no GPU. Renders nothing. |
| `interface` | Session, layout, forms, visualisation, audit view | Does not talk to `knowledge` or `inference`. Exactly one arrow leaves here. |
| `platform` | Contracts, gate, cross-layer tests, release train | Not one line of product logic. |

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

## Why it is this way

`docs/ADR.md` carries the decisions and the alternatives discarded, written
without reference to any project.

**This document names no client, no contract and no instance**, and neither does
any other file in this repository. The rule and its cost are in the README.
