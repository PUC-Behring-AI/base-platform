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

[0.1.0]: https://github.com/PUC-Behring-AI/base-platform/releases/tag/v0.1.0
