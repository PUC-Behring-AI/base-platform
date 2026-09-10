# base-platform

What binds the five layers together: the contracts, the gate and the release
train.

This repository holds **no product logic**. If it acquires any, that logic has
become a layer and must move out.

**Version:** see [`VERSION`](VERSION). What changed between versions is in
[`CHANGELOG.md`](CHANGELOG.md).

## This repository knows of no project

Deliberately, and it is the hardest rule here to keep. The base names no client,
no contract, no methodology and no instance — not in a table, not in an example,
not even in the rule that forbids it.

The moment the base carries a registry of who uses it, it stops being a base: it
becomes a component of its largest consumer, and every project after that
inherits the first one's vocabulary.

**Where instances are listed:** the organisation profile, which belongs to the
organisation and not to the base. Registering a new prefix is step 1 of
[`docs/ADAPTATION.md`](docs/ADAPTATION.md).

## The five layers

| Repository | Layer | Owns |
|---|---|---|
| `base-platform` | `platform` | Contracts, gate, release train, the metrics backend, the composition |
| `base-knowledge` | `knowledge` | Relational, vector, RDF graph, object store, sensitivity classification |
| `base-inference` | `inference` | Serving models: elasticity, virtual keys, routing enforcement |
| `base-agents` | `agents` | Agent runtime, MCP, guardrails, the routing decision, audit trail |
| `base-interface` | `interface` | Session, layout, forms, visualisation |

An **instance** is a deployed platform assembled on these five. It gets its own
prefix and its own five repositories, named `<prefix>-<layer>`.

## Running it

```bash
docker compose -f compose.base.yaml up -d   # all five layers
docker compose up -d                        # the metrics backend alone
```

Each layer owns the services it runs, in its own repository, in its own
`compose.yaml`. This repository's fragment holds the metrics backend and
nothing else; `compose.base.yaml` says which layers take part and assumes the
five repositories are siblings on disk.

A service defined in the composition file instead of in its layer is a service
two teams edit.

## Where to start

| You want to | Read |
|---|---|
| Understand the whole architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Know what your layer owes its neighbour | [`docs/CONTRACTS.md`](docs/CONTRACTS.md) |
| Create a new instance, or upgrade one | [`docs/ADAPTATION.md`](docs/ADAPTATION.md) |
| Work as an agent in any of these repos | [`docs/AGENTS-base.md`](docs/AGENTS-base.md) |
| Know why the architecture is what it is | [`docs/ADR.md`](docs/ADR.md) |

## State

Documentation only. Executable contracts, fakes and the shared gate do not exist
yet.
