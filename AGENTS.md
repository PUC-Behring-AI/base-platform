# AGENTS.md — base-platform
# Follows AGENTS-base.md v1.5, at docs/AGENTS-base.md — this repository hosts
# that file, and still follows it like every other repository in the base.
# Base: v0.9.0

## Project

**Name:** base-platform
**Layer:** `platform`
**State:** contracts, gate, composition and the C1/C5/C6 schemas are real —
see `docs/CONTRACTS.md` §State. Executable fakes per layer are next.

## What must not enter this repository

- **Any product logic.** If a decision here is "what should the answer be"
  rather than "how do two layers agree", it belongs to a layer, not here.
- **The name of a client, a contract, a methodology or an instance.** See the
  README and ADR-006. This was violated twice already — once in the base's own
  docs, once by publishing a registry on the organisation's public profile —
  and both are the reason this line exists.
- **A service that belongs to a layer.** The metrics *backend* lives here
  under C4; a service that *emits* metrics does not — that stays in the layer
  that runs it.

## Contracts this repository owns the definition of

All six — C1 through C6 — are defined in `docs/CONTRACTS.md`, not implemented
here. This repository's job is narrower: keep that definition the single
source, and require both bound teams to approve a change to it.

## What this repository actually runs

- **The metrics backend** (`compose.yaml`): Prometheus and Grafana. It reads
  `observability/prometheus.yml` and provisions Grafana from
  `observability/grafana/`. It carries no scrape target of its own beyond
  itself — every other target arrives via `compose.base.yaml`, mounted from
  the layer that emits it.
- **The composition** (`compose.base.yaml`): which layers take part in a full
  deployment, and where each layer's observability fragment gets mounted. This
  file is the only one in the base allowed to name all five layers by
  directory path, because composing them *is* the platform layer's job.
- **The cross-layer CLI** (`./base-platform`): a thin wrapper around
  `docker compose -f compose.base.yaml` — `up`, `down`, `status`, `logs`.
  Deliberately does not replace any single layer's own CLI: `base-inference`
  keeps `./base-inference` for deploying, setting up and managing only that
  layer, because that stays a real, separate operation. This CLI is for
  operating all five together.
- **The shared gate** (`scripts/gate.sh`): see below.
- **The harmony check** (`scripts/harmony.sh`): runs every sibling
  repository's gate against the working trees on disk. It is the step
  AGENTS-base.md's Axiom 10 requires before any pull request, in any
  repository of the base or of an instance. From a base repository the
  siblings are the base layers alone; from an instance, its own repositories
  and the base. CI runs it too
  (`.github/workflows/harmony.yml`, reusable): each repository's settings
  name its siblings (`HARMONY_SIBLINGS`) and hold a read-only deploy key per
  private sibling (`HARMONY_KEY_<NAME>`), so no file names a repository.
- **The release script** (`scripts/release.sh`): the only way the base is
  tagged. It tags the five at `v<VERSION>` only when all five declare that
  version, sit on a clean `main`, and pass `harmony.sh` (`docs/ADAPTATION.md` §7).

## The shared gate

Every repository in the base needs a gate before it needs code — a repository
with zero lines of product logic still has documentation that can drift and a
base version that can go stale. `scripts/gate.sh` here is that minimum,
callable directly or through a five-line wrapper any consuming repository
installs (`docs/ADAPTATION.md` §"Install the gate").

It checks what is true regardless of how much code a repository has: the
living docs exist, the declared base version is known (not necessarily
current — see ADAPTATION.md on staying behind), every YAML file parses, and —
only if the repository has grown code — its tests and shell scripts pass. A
repository with no code yet passes on the first checks alone, and that is
correct: the gate does not invent a floor to look thorough.

`base-inference` keeps its own richer gate (real coverage floor, a bats suite,
a specific ruff file list) rather than switching to this one — it already had
working infrastructure before this one existed, and replacing it was not worth
the risk for this pass. The shared gate is the floor every *new* engine starts
on, not a replacement for one that already does more.

## This repository in the system

Every other repository reads this one; this one reads none of them at
runtime.

| Who reads it | What they read | Through |
|---|---|---|
| every engine and instance | the contract schemas | `schemas/validate.py`, put on `sys.path` by each repository's `schema_bridge.py` (`BASE_PLATFORM_DIR`) |
| every engine and instance | the shared gate | the `scripts/gate.sh` wrappers and each CI's sibling checkout |
| every engine and instance | `docs/AGENTS-base.md` | the first lines of each `AGENTS.md` |
| every instance | `docs/ADAPTATION.md`, `VERSION`, `CHANGELOG.md` | `<prefix>-platform/base-version.yaml` |
| `compose.base.yaml` | each engine's `compose.yaml` and observability fragment | sibling paths under `BASE_ROOT` |

An instance's repositories are sockets, and the code its teams develop
enters as modules in those teams' own repositories (`docs/ADR.md` ADR-014,
`docs/ADAPTATION.md` §4 *Sockets and modules*). This repository names neither.

So a change here is the change with the widest reach in the base. A schema
or gate change can turn every sibling red. Run `scripts/harmony.sh` before
every pull request.

## Changing a contract

1. Open a pull request here, editing `docs/CONTRACTS.md`.
2. `CODEOWNERS` requires approval from the teams the contract binds — the
   five teams exist, but review enforcement stays off while most of them
   have a single member (the org owner), which would deadlock every PR
   against its own author. See `CONTRIBUTING.md` for the current state per
   team.
3. The merge here is what authorises the layers to implement the change.
4. If the change is breaking (any contract shape change is, by
   `CHANGELOG.md`'s own rule), bump `VERSION`, write the changelog entry, and
   tag all five base repositories on the new version.
