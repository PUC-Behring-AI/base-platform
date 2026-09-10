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
