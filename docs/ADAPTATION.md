# How an instance is born

An instance is a platform deployed on top of the base. This document is what
someone follows to create the second one.

## 1. Pick the prefix

The code of the contract or grant funding the project, lowercase, no spaces.

Two names to avoid, for reasons that only separate later:

- **The methodology name.** It usually belongs to the client and predates the
  project; carrying it in a repository of ours mixes what is theirs with what is
  ours. It also fails the day the same methodology is applied for a second
  client.
- **The client name.** It collides the day that client commissions a second
  platform.

**There is no central registry to add the prefix to.** An earlier version of
this document said to register it in the organisation profile; that page is
public, and doing so once already leaked a client's contract number. An
instance documents itself — see step 6.

## 2. Create the five repositories

`<prefix>-platform`, `-knowledge`, `-inference`, `-agents`, `-interface`.
Private, unless explicitly decided otherwise.

Apply the organisation properties to each one:

    gh api --method PATCH repos/PUC-Behring-AI/<repo>/properties/values --input - <<JSON
    {"properties":[{"property_name":"layer","value":"<layer>"},{"property_name":"role","value":"instance"}]}
    JSON

## 3. Install the gate

Every repository gets a gate before it gets code, and the gate has to run
somewhere nobody has to configure by hand — a `PreToolUse` hook watching one
machine is not a gate a second contributor's clone can satisfy. Three files,
all boilerplate:

**`scripts/gate.sh`** — a five-line wrapper delegating to the one in
`base-platform`, which is checked out as a sibling directory (the same
assumption `compose.base.yaml` makes):

    #!/usr/bin/env bash
    # scripts/gate.sh — thin wrapper. The real gate lives in base-platform and
    # is shared across every repository in the base; duplicating its logic
    # here is the serve_config.yaml defect multiplied by however many repos
    # copy it. See base-platform/scripts/gate.sh for what it checks.
    set -euo pipefail
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    BASE_PLATFORM_DIR="${BASE_PLATFORM_DIR:-$HERE/../base-platform}"
    if [ ! -x "$BASE_PLATFORM_DIR/scripts/gate.sh" ]; then
        echo "base-platform not found at $BASE_PLATFORM_DIR — clone it as a sibling, or set BASE_PLATFORM_DIR" >&2
        exit 1
    fi
    exec "$BASE_PLATFORM_DIR/scripts/gate.sh" "$HERE"

Make it executable: `chmod +x scripts/gate.sh`.

**`.github/workflows/gate.yml`** — checks out this repository and
`base-platform` as siblings, then runs `./scripts/gate.sh`, on every pull
request:

    name: gate
    on: [pull_request]
    permissions:
      contents: read
    jobs:
      gate:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
            with:
              path: <this-repo-name>
          - uses: actions/checkout@v4
            with:
              repository: PUC-Behring-AI/base-platform
              path: base-platform
          - uses: actions/setup-python@v5
            with:
              python-version: "3.11"
          - run: pip install pytest pyyaml jsonschema ruff
          - run: ./scripts/gate.sh
            working-directory: <this-repo-name>

  (`base-platform`'s own workflow skips the sibling checkout — it is already
  itself.) The runner executes the script; nothing about "the gate ran" is
  taken on anyone's word.

**`CONTRIBUTING.md`** — a short file pointing at
`base-platform/CONTRIBUTING.md` for the procedure shared by every repository
(issue and pull request conventions, the `### Vizinhas` heading, cross-repo
`blocked_by`), plus whatever is only this repository's own.

Run the gate once before the first commit. On a repository with no code yet,
it checks two things and passes: the living docs exist, and the base version
is declared. That is not a weak gate — it is the whole floor a
documentation-only repository has to clear, and inventing more would mean
checking something that does not exist yet.

### Plan limits — what the gate cannot do here, and why

`docs/AGENTS-base.md` says the CI "is a required check, **wherever branch
protection is available to require one**", and points at this section for
where it is not. This is that section; until 2026-09-14 it did not exist, so
the caveat forwarded the reader to an explanation nobody had written — which
reads exactly like "this is handled elsewhere" and is the failure mode this
base documents better than any other.

**Measured on 2026-09-14.** The organisation is on GitHub's **free** plan
(`gh api orgs/PUC-Behring-AI --jq .plan.name`). On that plan, branch
protection is unavailable for **private** repositories:

    $ gh api repos/PUC-Behring-AI/base-inference/branches/main/protection
    {"message":"Upgrade to GitHub Pro or make this repository public
     to enable this feature.","status":"403"}

The API will not even report the setting, let alone accept one. And every
instance repository is private by step 2 above, as are four of the five base
repositories — `base-platform` is the exception, and it now requires its
`gate` check, because that is the one place where the norm can be met for
nothing.

**So in a private repository the workflow runs, reports on the pull request,
and does not block a merge.** Two consequences follow, and neither is
optional:

- **Wait for the check before merging.** `gh pr merge --auto` does *not*
  wait where no check is required: there is nothing to wait for, so it
  merges immediately. The command has two opposite meanings depending on a
  setting nobody reads, and the dangerous one is the silent one. This was
  found the way such things are found — a pull request went to `main` before
  its gate had started.
- **Say so in the repository's own `CONTRIBUTING.md`.** A gate described as
  blocking, that reports, is worse than one honestly described as advisory:
  people calibrate on the description.

**The escape hatches, and what each costs.** Making a repository public
restores protection and is not available to an instance — step 2's privacy
is a client confidentiality decision, not a preference. Paying for GitHub
Team restores it everywhere and is a budget decision that belongs to whoever
holds the budget, recorded here rather than assumed either way. Neither is a
precondition for anything: the gate runs, reports, and the discipline above
covers the rest.

## 4. Fill in the extension points

This is the **declarative** half of adaptation. The other half is domain code,
and section 5 covers it.

| Layer | The instance declares |
|---|---|
| `knowledge` | `ontology/` (RDF/OWL), `connectors/` (sources), `taxonomy.yaml` |
| `inference` | `models.yaml` (served models and where each runs), `tiers.yaml` |
| `agents` | `flows/`, `prompts/`, `tools/` (MCP declarations) |
| `interface` | `forms/`, `views/` |
| `platform` | `schemas/` (C1–C6 payloads), `base-version.yaml` |

**`taxonomy.yaml` is the most important file on that list.** It is where the
routing rule becomes a parameter: each sensitivity class declares the key policy
that applies to it.

    classes:
      - name: public
        key_policy: external
      - name: client-confidential
        key_policy: local-only

The field is `key_policy`, as `schemas/classification.schema.json` spells it.
An earlier version of this example wrote `key-policy`, which that schema
rejects.

The inference engine enforces the policy. The instance decides which classes
exist and what each one permits — it does not decide *whether* the policy is
enforced.

**Classes live in this one file, and only `knowledge` reads it.** `inference`
never sees a classification: it knows the two key families that
`classification.schema.json` fixes, and nothing else. So `models.yaml` does not
map classes to anything. It declares where each model runs — served locally,
or by an external provider — and the engine derives what each family reaches:
a `local-only` key reaches local models, an `external` key reaches all of them.
The instance cannot declare an external model local; the engine refuses to
start if it tries. A second class→policy map in another layer would be a second
vocabulary for one decision, and the first divergence would be silent.

### Where the engine reads them

Each engine reads its instance from one directory, named by the
`BASE_INSTANCE_DIR` environment variable and mounted **read-only** by that
layer's own `compose.yaml`.

- **Unset** — the engine starts with an empty instance, logs a loud warning,
  and serves nothing it would have needed the instance for. This is what lets a
  base repository run its own tests and its own development stack with no
  instance at all. It is safe because nothing is served: an empty evidence
  set already routes to `local-only`.
- **Set, but a required file is missing or does not validate** — the engine
  refuses to start. A misdeclared instance is a defect to see at boot, not a
  degraded mode to discover in production.

There is no built-in default. A default model or a default taxonomy inside an
engine is the first instance's vocabulary leaking into every later one.

### When an engine accepts code

Configuration is not the whole of an instance (§5, ADR-005). Where instance
code has to run **inside** an engine, it enters one way only: an installed
Python package, discovered through the entry-point group
`base_<layer>.modules`.

- Only `knowledge` accepts modules today, and `agents` will, through the same
  group. `inference` and `interface` take configuration only: `inference`
  because code inside the gateway could bypass the very policy it enforces;
  `interface` because its forms and views are declarations, and stay so until
  two instances need code there (§5).
- A module loads only when the instance manifest lists it under `modules:`.
  Listed but not installed — refuse to start. Installed but not listed —
  ignored, and logged.

**The engine stamps; the module never classifies.** Everything a module returns
that crosses a contract passes through engine code first, and that code is the
only thing that sets `classification`. A module returns content and the
source it came from; the class comes from the source's declaration, the policy
from `taxonomy.yaml`. A module may ask for a *more* sensitive class, never a
less sensitive one. Otherwise "classification at the source" would move into
instance code, where no base test can see it.

**A container that runs instance code reaches only internal services.** In
process, a module could call a model provider directly and walk around C2. The
network is what stops that, not a code review.

### Building the instance image

A configuration-only layer needs no image of its own: the instance directory is
mounted into the base image. A layer with modules needs one, because an entry
point exists only for a package that is installed:

    FROM base-knowledge:<pinned tag>       # built locally, see below
    RUN pip install <instance package>==<version>

The base image is built from the sibling checkout of the base repository at
the tag the instance pins (`build.additional_contexts` in Compose). **There is
no image registry yet.** Two reasons: the private package storage on the
organisation's current plan is far smaller than a serving image of several
gigabytes (the quota is GitHub's published figure for the plan, not measured
here), and the release tags an image would be named after stop short of
`VERSION` (see §7). When production moves to the
Kubernetes target, a registry comes with it.

The engines do not implement this yet. Each layer's issue tracks its own half:
the extension-point issue in `base-knowledge`, `base-inference` and
`base-interface`, all citing the convention written here.

## 5. Write the code that is only yours

Computation, validation, methodology rules. This lives in the instance repository
and should not be squeezed into YAML.

**When you need something the engine cannot express**, the rule is: open an
extension point in the engine only when **two** instances ask for the same thing,
or when what you need is confidential and therefore cannot live in the engine.
Until then, write it in your own repository.

An engine generalised from a single case stiffens what was hard and abstracts
what was easy.

## 6. Document yourself — there is no one else who will

Write a README in `<prefix>-platform` that says what the prefix means, which
client or grant funds the instance, and what each of the other four
`<prefix>-*` repositories is for. Keep it private with the rest of the
instance.

Nothing decodes the prefix for you. Whoever can see `<prefix>-knowledge` can
open `<prefix>-platform` and read what it means; whoever cannot see it has no
need to.

## 7. Pin the base version

**The base has one version, and the five repositories are tagged together on
it.** `base-platform/VERSION` holds it; `base-platform/CHANGELOG.md` says what
changed between one and the next.

An instance records the version it runs on, in
`<prefix>-platform/base-version.yaml`:

    base: 0.2.0

One number, not five. A single version means the combination has been released
together, so "was this set tested against itself?" has an answer. Per-layer
pinning would be more precise and would lose exactly that.

The cost is real and worth knowing: a fix in one engine bumps the version of all
five. That is deliberate — the alternative is five numbers nobody reconciles.

**What a repository's `# Base: vX.Y.Z` line claims.** That the repository
does everything version X.Y.Z asks of its layer — not only that it was read
against X.Y.Z's contracts. A layer the new version asks nothing of declares it
as soon as someone has checked that; a layer it asks something of declares it
when the work is merged. Until then the line stays on the version the layer
does fulfil, and `AGENTS.md` names, next to it, the issue that holds it back.

**When a version is tagged.** When every one of the five declares `VERSION`,
`CHANGELOG.md` gives the version a date, and `scripts/release.sh` finds the
five on a clean `main` that `scripts/harmony.sh` passes. The script is the
only way a tag is made: it refuses otherwise, and with `--tag` it tags the
five at the commits it checked and pushes the tags. So a tag means the
combination fulfils the version and was tested against itself — which is what
an instance pinning it needs. Until the tag exists, the version is
unreleased, however far `VERSION` has moved.

0.3.0 and 0.4.0 were never tagged. The first tag after 0.2.0 is 0.5.0.

## 8. Upgrading

The base does not push. An instance pulls, and this is what pulling looks like:

1. Read `CHANGELOG.md` from the base tag above yours.
2. **Any entry marked `BREAKING` is a contract change.** It obliges the
   instance to act before pinning the new version; nothing else does.
3. Bump `base-version.yaml`, run the instance's gate, ship it through a pull
   request like any other change.

Staying behind is allowed and is sometimes correct. What is not allowed is not
knowing: the pinned version is in a file, in git, so "which instances are behind
0.2.0?" is a question a grep answers.

The shared gate's version check works the same way for the base repositories
themselves: it warns when an `AGENTS.md` declares an old version, and never
fails a pull request over it. Whether to update is the repository's call, made
knowingly — not the gate's to force. It fails only on a version newer than
`VERSION`: that declares a base that does not exist yet.

## 9. Board the train

There is no fixed release schedule. A version departs when the five fulfil it
(§7), and between 0.2.0 and 0.5.0 that took five weeks and three version
numbers. An instance boards a version by pinning its tag, never a `main`.
