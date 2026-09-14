# Changelog

The base has **one version**, and all five repositories — `base-platform`,
`base-knowledge`, `base-inference`, `base-agents`, `base-interface` — are tagged
together on it. An instance pins that one number in
`<prefix>-platform/base-version.yaml`.

`BREAKING` marks an entry that obliges an instance to act before pinning the new
version. **A change to any contract in `docs/CONTRACTS.md` is breaking by
definition**, because the layer on the other side is already relying on it.
Nothing else is breaking by default, and calling something breaking when it is
not teaches people to skim the marker.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [semver](https://semver.org/). While the major is `0`, the
minor carries breaking changes.

---

## [Unreleased]

## [0.3.0] — 2026-09-14

Redistributing the parts of the original monolithic server into the layers they
belong to (issue #14, recreated as #2 — see the repository history note
below), and making the contracts executable instead of prose (issue #7,
recreated as #3). Both grow one slice at a time; this is the first tag since
0.2.0.

### Note on this repository's history

`base-platform` was deleted and recreated on 2026-09-14: `git filter-repo`
cleaned a client/contract leak from `refs/heads/*` and `refs/tags/*`, but
seven already-merged pull requests still exposed it through
`refs/pull/N/head`, which no force-push touches. Recreating was the only way
to make the repository public without repeating the leak a third time. The
six issues open at the time were recreated (one open, five closed); PR
history before this point is gone. Everything in `[0.2.0]` and `[0.1.0]`
below describes what those PRs did — the entries are accurate, only their
own PR links no longer resolve.

### Added

- **`BREAKING` — C5 gains three operations on the `interface` side**: link an
  issued credential to an account, register a model in the visibility
  catalog, and configure the upstream gateway once at deploy time. `0.2.0`
  closed the gap between "a contract exists" and "the contract has a
  schema" for account creation and model grants; it left open the three
  remaining reasons a consuming layer's provisioning script still had to
  reach into `interface`'s storage directly. See `docs/CONTRACTS.md` §C5 for
  the full reasoning behind each of the three.
- **The gate now runs in CI, on every pull request, in all five repositories**
  (`.github/workflows/gate.yml`), instead of depending on a `PreToolUse` hook
  installed on one machine. `.github/ISSUE_TEMPLATE/issue.md` carries the
  `### Vizinhas` heading, and `.github/workflows/issue-hygiene.yml` flags a new
  issue missing it — the closest equivalent to a pre-creation check the issue
  API allows. `.github/pull_request_template.md` carries the merge checklist.
  `CONTRIBUTING.md`, here, is now the one place the issue and merge procedure
  is written down; the other four repositories carry a short version pointing
  back to it. `docs/ADAPTATION.md` §3 and `docs/AGENTS-base.md` §"The local
  gate" describe the new mechanism instead of the hook. `AGENTS-base.md` moves
  to **v1.2**.
- **`./base-platform`**, a thin CLI wrapping `docker compose -f
  compose.base.yaml` — `up`, `down`, `status`, `logs`. Does not replace any
  single layer's own CLI; `base-inference` keeps `./base-inference` for its
  own deploy/setup/service lifecycle. Closes the CLI half of issue #2's
  allocation table, which the original redistribution issue could not have
  gotten right without first reading what `./base-inference` actually does
  (it is entirely specific to that layer — moving it here would have broken
  it, not relocated it).
- **The gate now runs in CI, on every pull request, in all five repositories**
  (`.github/workflows/gate.yml`), instead of depending on a `PreToolUse` hook
  installed on one machine. `.github/ISSUE_TEMPLATE/issue.md` carries the
  `### Vizinhas` heading, and `.github/workflows/issue-hygiene.yml` flags a new
  issue missing it — the closest equivalent to a pre-creation check the issue
  API allows. `.github/pull_request_template.md` carries the merge checklist.
  `CONTRIBUTING.md`, here, is now the one place the issue and merge procedure
  is written down; the other four repositories carry a short version pointing
  back to it. `docs/ADAPTATION.md` §3 and `docs/AGENTS-base.md` §"The local
  gate" describe the new mechanism instead of the hook. `AGENTS-base.md` moves
  to **v1.2**.
- **`compose.base.yaml` composes all four available engines.**
  `base-knowledge`, `base-inference`, `base-agents` and `base-interface`'s
  identity sidecar all take part now, each mounting `schemas/` from here and
  publishing its own scrape target into the metrics backend. Verified with
  `docker compose config`, not assumed: every mount in the composed output
  resolves to a path that actually exists on disk.
- **Three fakes exist**, one per previously-documentation-only engine —
  tracked here because they are what makes the schemas above load-bearing
  rather than aspirational:
  - `base-knowledge`: C1 evidence retrieval and C6 provenance storage.
  - `base-agents`: the C2 routing decision (most-restrictive-wins across the
    evidence used), C3, and the richest C6 record of the three.
  - `base-interface`: a C5 identity sidecar replacing `docker exec` against
    Open WebUI's database with a mounted-volume connection and a real test
    suite — `base-inference`'s issue #37.

  All three verified beyond their own test suites: built as Docker images,
  run on a shared network, and exercised with real cross-container HTTP
  calls — a confidential-content question routes `local-only` end to end,
  from a real `base-agents` container asking a real `base-knowledge`
  container, with the resulting provenance record retrievable afterward.
- **`schemas/` — C1, C5 and C6 are now JSON Schema, not just prose.**
  `envelope.schema.json` and `classification.schema.json` are shared
  fragments; `c1_evidence.schema.json` and `c6_provenance.schema.json`
  compose them via `allOf`; `c5_identity.schema.json` holds one `$def` per
  operation. `tests/test_schemas.py` proves each schema accepts a valid
  instance and rejects the specific way it should fail — including that
  `classification.key_policy` accepts exactly `local-only` and `external`
  and nothing else, which is the actual security invariant C2 depends on.

  C2, C3 and C4 have no schema here on purpose: C2 is OpenAI-compatible and
  defined externally, C3 is instance-specific by design, and C4 is a metrics
  exposition format whose "no payload" invariant belongs in each layer's own
  tests. See `schemas/README.md`.
- **This repository's own `pyproject.toml` and `tests/`** — dogfooding the
  shared gate's Python-test path for the first time since it was written.
- **The metrics backend lives here now** — `compose.yaml` runs Prometheus and
  Grafana, and `observability/` holds their configuration. Nothing about any
  particular layer: each layer drops its own scrape file into `scrape.d/` and
  ships its own dashboards. The layer that emits a metric declares where to
  find it.
- **`compose.base.yaml`** composes the layers, each of which owns the services
  it runs in its own repository. A service defined in the composition instead
  of in its layer is a service two teams edit.

  It is also where each layer's scrape file and dashboards get mounted into the
  backend, because it is the only file that knows the other layers exist. The
  first version declared an empty named volume for `scrape.d/` and mounted
  nothing into it: the mechanism looked finished and Prometheus would have
  scraped only itself. Verified now with `docker compose config`, which is the
  check that would have caught it.
- **The shared gate**, `scripts/gate.sh` here plus a five-line wrapper any
  consuming repository installs (`docs/ADAPTATION.md` §3). Closes issue #8.
  It checks what is true of a repository regardless of how much code it has:
  the living docs exist, the declared base version is known, every YAML file
  parses — and, once a repository grows code, that its tests and shell
  scripts pass. A repository with zero lines of code passes on the docs and
  version checks alone, which is correct: the gate does not invent a floor to
  look thorough.
- **The version check reads `AGENTS.md` for a `# Base: vX.Y.Z` line** and
  compares it to this repository's own `VERSION`. Missing the line fails the
  gate — nothing else in the base makes "which version was this written
  against?" answerable, and issue #9 was exactly that gap. An old version
  warns rather than fails, because staying behind is the repository's decision
  to make, per `docs/ADAPTATION.md` §8 — the gate's job is to make that
  decision visible, not to make it.
- **This repository's own `AGENTS.md`.** Every other repository in the base
  pointed to `docs/AGENTS-base.md` and added its own rules; this one hosted
  that file and never wrote the pointer.

### Removed

- **`.claude/portao`, `.claude/issue-vizinhas`, and the `git-guard --stamp`
  call inside `scripts/gate.sh`**, in all five repositories — configuration
  specific to one person's machine, versioned inside a shared repository. A
  clone without that hook installed got a portão that printed "passou" and
  stamped nothing; see `.github/workflows/gate.yml` above for the replacement.
- **This repository's own git history carried the same leak the item below
  already describes, a second time, inside `base-platform` itself rather
  than on the organisation's profile page.** Two spec files
  (`specs/2026-09-10-arquitetura-base-cinco-camadas-design.md`,
  `specs/2026-09-10-plano-documentacao-base.md`) and six historical revisions
  of `README.md` and `docs/ADAPTATION.md` — all already superseded by commit
  `4a3bb54` — named the client, the contract number, and the confidential
  methodology, and remained reachable from `origin/main` regardless. Purged
  from every ref with `git filter-repo` on 2026-09-14; `v0.1.0` and `v0.2.0`
  were retagged onto the rewritten history. This repository was private for
  the entire time the leak was reachable; it is made public only after this
  purge, precisely so that making it public does not repeat the incident a
  third time.
- **The central instance registry, and the page that held it.** Version 0.2.0
  moved the list of instance prefixes out of the base and onto the
  organisation's profile page. That page is public: it turned an internal
  architecture note into a product announcement, and it published a client's
  contract number. The page was live for roughly two hours; the repository
  holding it has been deleted.

  There is no registry now. An instance documents itself in its own
  `<prefix>-platform` README. See ADR-006, which records both discarded
  answers and the reason the question kept producing bad ones.

### Fixed

- **`git-guard`'s G6 check was never actually validating this repository.**
  Its trigger, `.claude/portao`, did not exist here — a consequence of the
  missing `AGENTS.md` above — so `gh pr create --repo base-platform` was
  gated by whichever directory happened to be the shell's current one, not by
  this repository's own state. Every merge up to this point passed a check
  that was reading the wrong repository. Fixed together with the two items
  above, since the bug is only visible once they exist to reveal it.
- **`base-inference` keeps its own gate**, deliberately not migrated to the
  shared one. It already had a real coverage floor, a bats suite and a
  specific lint file list before the shared gate existed, and none of that was
  worth risking for this pass. The shared gate is the floor a *new* engine
  starts on, not a mandatory replacement for one that already does more.

### Notes

- `prometheus.yml` here carries no scrape target beyond Prometheus itself, and
  a comment saying why: no payload reaches this backend. A record with payload
  is provenance, it is classified, and it goes to `knowledge` under C6.
- Grafana refuses to start without `GRAFANA_ADMIN_PASSWORD`, rather than
  falling back to `admin:admin`.
- The gate script avoids `mapfile`/`readarray`: macOS ships bash 3.2 by
  default (GPLv2 licensing), which lacks both. Measured by running the gate
  for the first time on this machine — it failed on line one of the part that
  used them.

## [0.2.0] — 2026-09-10

Two new contracts and one rewritten. Everything here is `BREAKING`, because
every entry changes a contract and the layer on the other side already relies
on it.

### Changed

- **`BREAKING` — C4 is metrics only, and it lands in `platform`.** It used to
  say "telemetry: traces and metrics", landing in `knowledge`. That wording put
  a store recording prompts and completions beside one recording request
  counts, and treated both as operations infrastructure. **No payload may reach
  C4** — not a prompt, not a passage, not an identifier resolving to a person.
  See ADR-009.

### Added

- **`BREAKING` — C6, provenance.** One record per request, emitted by every
  layer that touched it, correlated by an identifier the interface generates
  and every layer propagates unchanged. It lands in `knowledge`, carries a
  classification assigned the way C1 assigns one, and is stored under the same
  key policy as the data it describes. Append-only. This is what makes an audit
  trail reconstructable across five layers, and it is a product requirement
  wherever a deployment must explain its outputs.
- **`BREAKING` — C5, identity.** The serving layer exposes issuing, inspecting
  and revoking a credential; the interface layer exposes creating an account
  and granting model access; `platform` orchestrates and owns the rollback.
  **No layer writes into another layer's storage** — the rule exists because
  the first implementation did exactly that, with `docker exec` and raw SQL
  against the interface's private database. See ADR-010.
- **ADR-009** — provenance is not observability, and the criterion that
  separates them: does the record contain payload?
- **ADR-010** — identity is a contract, because without one it becomes a raw
  SQL write.

### What an instance must do before pinning 0.2.0

1. Nothing sends payload to the metrics backend.
2. Every layer emits a provenance record and propagates the request identifier
   unchanged.
3. Provisioning goes through each layer's API. If a layer has no such API, that
   is a defect in the layer.

## [0.1.0] — 2026-09-10

The base exists as documentation. No executable artefact ships in this version:
an instance pinning `0.1.0` is declaring which set of contracts and rules it was
built against, not which code it runs.

### Added

- **Five layers with stated boundaries** — `docs/ARCHITECTURE.md`. Each layer's
  table says what it owns *and what it does not*, and the second half is the
  load-bearing one: it is what stops a layer growing into its neighbour.
- **Four inter-layer contracts** — `docs/CONTRACTS.md`. C1 evidence retrieval,
  C2 inference, C3 the product API, C4 telemetry. Prose and tables; versioned
  schemas do not exist yet.
- **The routing rule, split across two layers** — decided in `agents`, enforced
  in `inference` through the gateway's per-model key policy. A defect in the
  deciding layer cannot leak, because the credential carrying the request has
  no permission to leave.
- **The adaptation process** — `docs/ADAPTATION.md`. How an instance is born,
  what it declares, what it writes as code, and how it pins and upgrades.
- **`AGENTS-base.md` v1.0** — the axioms common to every base repository,
  versioned separately so a repository can declare which version it follows.
- **`CODEOWNERS`**, shipped commented out: the teams do not exist yet, and a
  rule pointing at a non-existent team blocks every pull request without saying
  why.
- **This changelog and `VERSION`.**

### Notes

- The base names no client, no contract, no methodology and no instance. That
  rule is stated in the README along with what it costs, and it was violated in
  the first draft of every document here — the corrections are the reason
  `0.1.0` is tagged today rather than yesterday.
- Five known gaps are tracked as issues in this repository: contracts are prose
  rather than schema, nine repositories have no gate, `AGENTS-base.md` has no
  version check, `CODEOWNERS` is inert, and two candidate library dependencies
  were assumed rather than verified.

[0.2.0]: https://github.com/PUC-Behring-AI/base-platform/releases/tag/v0.2.0
[0.1.0]: https://github.com/PUC-Behring-AI/base-platform/releases/tag/v0.1.0
