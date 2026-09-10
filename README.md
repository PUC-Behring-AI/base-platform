# base-platform

What binds the five layers together: the contracts, the gate and the release
train.

This repository holds **no product logic**. If it acquires any, that logic has
become a layer and must move out.

## Prefixes — read this first

| Prefix | What it is |
|---|---|
| `base-` | The reusable base. Engines that serve more than one instance. |
| `g122-` | Instance **REDACTED-INSTANCE / REDACTED-CONTRACT** — AI-assisted exploratory geological risk assessment platform, built on the REDACTED-METHOD methodology. Private: it carries the client's methodology and sensitivity taxonomy. |

## The eleven repositories

| Repository | Layer | Team | Role |
|---|---|---|---|
| `base-platform` | `platform` | — | Contracts, gate, release |
| `base-knowledge` | `knowledge` | Team 1 | Data and knowledge engine |
| `base-inference` | `inference` | Team 2 | Inference engine |
| `base-agents` | `agents` | Team 3 | Agent engine |
| `base-interface` | `interface` | Team 4 | Interface engine |
| `g122-platform` | `platform` | — | Instance schemas |
| `g122-knowledge` | `knowledge` | Team 1 | Ontology, connectors, taxonomy |
| `g122-inference` | `inference` | Team 2 | Served models and key policy |
| `g122-agents` | `agents` | Team 3 | REDACTED-METHOD flows, LoK and PoS computation |
| `g122-interface` | `interface` | Team 4 | Forms and visualisations |
| `.github` | — | — | Organisation profile (the only public one) |

## Where to start

| You want to | Read |
|---|---|
| Understand the whole architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Know what your layer owes its neighbour | [`docs/CONTRACTS.md`](docs/CONTRACTS.md) |
| Create a new instance | [`docs/ADAPTATION.md`](docs/ADAPTATION.md) |
| Work as an agent in any of these repos | [`docs/AGENTS-base.md`](docs/AGENTS-base.md) |
| Know why any of this exists | [`specs/`](specs/) — in Portuguese, the decision record |

## State

Documentation only. Executable contracts, fakes and the shared gate do not exist
yet — they are stages E1 and E2 of the spec.
