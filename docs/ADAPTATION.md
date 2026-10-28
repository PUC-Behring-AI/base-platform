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
    # Beside the main checkout, not beside HERE: from a worktree
    # (.claude/worktrees/<name>), HERE/.. is the worktrees directory.
    MAIN="$(dirname "$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir)")"
    BASE_PLATFORM_DIR="${BASE_PLATFORM_DIR:-$MAIN/../base-platform}"
    if [ ! -x "$BASE_PLATFORM_DIR/scripts/gate.sh" ]; then
        echo "base-platform not found at $BASE_PLATFORM_DIR — clone it as a sibling, or set BASE_PLATFORM_DIR" >&2
        exit 1
    fi
    exec "$BASE_PLATFORM_DIR/scripts/gate.sh" "$HERE"

Make it executable: `chmod +x scripts/gate.sh`.

**`.github/workflows/gate.yml`** — checks out this repository and
`base-platform` as siblings, `base-platform` at the tag the instance pins
(§7), then runs `./scripts/gate.sh`, on every pull request. Every layer but
`<prefix>-platform` also checks out `<prefix>-platform`, where the pin lives;
it is private, so that checkout takes a read-only deploy key, held in the
secret the harmony workflow already uses, `HARMONY_KEY_<PREFIX>_PLATFORM`:

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
              ref: v<base>
              path: base-platform
          - uses: actions/checkout@v4   # not in <prefix>-platform itself
            with:
              repository: PUC-Behring-AI/<prefix>-platform
              ssh-key: ${{ secrets.HARMONY_KEY_<PREFIX>_PLATFORM }}
              path: <prefix>-platform
          - uses: actions/setup-python@v5
            with:
              python-version: "3.11"
          - run: pip install pytest pyyaml jsonschema ruff
          - uses: actions/setup-node@v4   # only in a repository with package.json
            with:
              node-version-file: <this-repo-name>/.nvmrc
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
is declared — in an instance, declared and pinned alike (§7). That is not a
weak gate — it is the whole floor a documentation-only repository has to
clear, and inventing more would mean checking something that does not exist
yet.

One more file, so the issue rule is not copied either.
**`.github/workflows/issue-hygiene.yml`** — calls `base-platform`'s, which
comments on a new issue opened without the `### Vizinhas` heading. It is
reusable, like `harmony.yml`. An instance calls it at the tag it pins (§7),
from the first version after 0.5.0 on; a `base-*` repository calls it at
`@main`:

    name: issue hygiene
    on:
      issues:
        types: [opened]
    permissions:
      issues: write
    jobs:
      check-vizinhas:
        uses: PUC-Behring-AI/base-platform/.github/workflows/issue-hygiene.yml@v<base>

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
| `knowledge` | `ontology/` (RDF/OWL), `connectors/` (sources), `collections/` (domain records written over C8, each with a class), `taxonomy.yaml` |
| `inference` | `models.yaml` (served models and where each runs); `tiers.yaml` is pending — nothing reads it yet, and base-inference#106 defines it |
| `agents` | `flows/`, `prompts/`, `tools/` (MCP declarations) |
| `interface` | `src/instance/` (code): theme, and the routes and navigation entries it maps from module packages. Built into an image `FROM base-interface:<tag>` (ADR-013, ADR-014) |
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
  group. `inference` takes configuration only today, because code inside the
  gateway could bypass the very policy it enforces; accepting modules there is
  open, and needs its own record (ADR-014).
- `interface` takes code by a different socket, because a browser bundle is
  not an installed package (ADR-013, ADR-014):
  - the instance's `src/instance/` is compiled into the engine's frontend
    shell at image build. It composes the screens of one or more module
    packages: it maps each module's routes and navigation entries into
    `defineInstance`, owns the theme, and supplies the calls a module makes
    over C3. The screens themselves live in the modules;
  - route components are lazy imports only. The build validates the instance
    by loading `src/instance/index.ts` in Node before bundling, so a static
    import of a module package from that file fails the build;
  - a module package declares React, React DOM and React Router as peers, and
    the instance's build deduplicates them, so the page holds one copy of each;
  - an instance export that is missing or invalid fails the build;
  - the only process with a route out is the engine's backend-for-frontend,
    on a network that reaches only `agents`.
  `base-interface`'s `specs/interface-socket.md` gives the exact build.
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

### Sockets and modules

An instance's repositories are **sockets**: each one receives its layer's
**modules** and plugs them into the engine (ADR-014). The code a team develops
— a methodology library, a set of screens, a flow — is a module, in that
team's own repository. The socket keeps what is the instance's alone and no
team's product: configuration, brand and theme, the list of modules it plugs,
the adapter that maps each module onto the contracts, the image, and the tests
of the plugged whole.

| Layer | How a module plugs in |
|---|---|
| `knowledge`, `agents` | a Python package installed in the instance image, discovered through `base_<layer>.modules`, loaded when the manifest lists it (above) |
| `interface` | a UI package whose routes `src/instance/` maps, lazily, into the shell (above) |
| `inference` | none today: configuration only; accepting modules here is open and needs its own record (ADR-014) |
| `platform` | none |

A module:

- **runs standalone** for its team, with no base, no login and no instance
  repository beside it. Plugged mode is a second mode the socket turns on;
- **never names the instance**, its client, its contract or its
  infrastructure. What is the client's — brand, logo, product name — stays in
  the socket. A module keeps its own list of forbidden terms and checks
  itself against it; the base's leak denylist is the wrong list, because it
  holds domain words a module may need;
- **depends on no base package.** Its types, errors and port are its own; the
  socket's adapter maps them onto the contracts;
- **is consumed at its team's `main`**, not by tag. The socket records the
  commit in each image (a build argument written into an image label) and
  tests against `main` on a schedule, opening an issue in the socket when
  `main` breaks it. A private module is read in CI with a read-only deploy key
  held in a secret of the socket's own, as in §3;
- **changes by pull request in its own repository**, which its team reviews
  and merges. A module repository is not a member of the base or of an
  instance: no `# Base:` line, no harmony run, its own tests.

There is no package registry for modules either. The image build takes the
module from a sibling checkout of its repository, passed as a Docker build
context:

    docker build --build-context <module>=../<module> \
                 --build-arg <MODULE>_SHA=$(git -C ../<module> rev-parse HEAD) .

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
`base-interface`, and the socket issue in `base-agents` (base-agents#9), all
citing the convention written here.

## 5. Write the code that is only yours

Computation, validation, methodology rules. This should not be squeezed into
YAML. It lives in a **module**, in the repository of the team that develops it,
and the instance's socket plugs it in (§4, *Sockets and modules*). What stays
in the instance repository is the code that binds modules to the base: the
adapters, the brand, the composition.

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

    base: 0.5.0

One number, not five. A single version means the combination has been released
together, so "was this set tested against itself?" has an answer. Per-layer
pinning would be more precise and would lose exactly that.

The cost is real and worth knowing: a fix in one engine bumps the version of all
five. That is deliberate — the alternative is five numbers nobody reconciles.

**The gate checks the pin.** In every `<prefix>-*` repository the shared gate
reads `base-version.yaml` — in the repository itself for `<prefix>-platform`,
in the sibling `<prefix>-platform` for the other four — and fails when:

- the file cannot be found, naming the path it looked at;
- the repository's `# Base:` line names another version;
- the tag `v<base>` does not exist in `base-platform`;
- any other place that states the version disagrees: a workflow's
  `uses: …/base-*/…@ref`, a checkout `ref:` of a `base-*` repository, a
  `base_ref:` passed to the harmony workflow, or a Dockerfile's
  `ARG BASE_TAG=` or `FROM base-*:tag`.

So the version is stated once in fact and the rest are checked against it. A
pin that names an untagged version, or a workflow that still runs the base at
`main`, fails the pull request instead of passing as if it were tested.

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

## 10. Kubernetes

Compose stays the development loop. Each layer also ships a Helm chart, so the
same five layers can run on a cluster. The chart is hand-written, not generated
from compose: compose has no notion of a hook, a policy or a storage class, and
a converter would hide those choices. A parity check keeps the two in step
instead.

### Layout, per layer

    deploy/chart/
      Chart.yaml              # version == the repository's release tag
      values.yaml
      values.schema.json      # required secret names, image overrides
      templates/
      templates/tests/        # helm test hooks
      ci/kind-values.yaml     # values for the local kind cluster
      parity.yaml             # compose-to-chart map, see below
    tests/test_chart.py       # renders with `helm template`, asserts on the output

The tests are pytest suites that render the chart and assert on the YAML. No
other chart-test framework is used: one runner, one language, and the same
assertions can call the parity checker. The gate (§3) adds its own chart step
(`helm template`, `kubeconform`, `helm lint --strict`). A repository with a
chart installs pinned helm and kubeconform in its gate workflow, as
base-platform's `gate.yml` does; an unpinned tool changes the verdict without a
change in the repository.

### Rules every chart follows

1. **Every secret reaches a chart only as an `existingSecret` name.**
   `values.schema.json` makes it required, and no default secret value exists
   anywhere. A default password is a password in every cluster that forgot to
   override it, and a chart that renders without the secret fails late and far
   from the cause.
2. **Every image is overridable by `image.repository`, `image.tag` and
   `image.digest`.** A socket image is built `FROM` the base image (§4) and must
   replace it without editing the chart.
3. **Network policy is namespaced `networking.k8s.io/v1` `NetworkPolicy`
   only:** default deny, DNS allowed, each edge explicit, mirroring each compose
   network. The network that has no route out (`base-internal`) gets no egress
   beyond its members and DNS. Cluster-wide policy kinds differ between kind and
   managed clusters, so a base chart cannot depend on them.
4. **A Service port equals its container port.** The AWS VPC CNI's network
   policy enforcement matches on the container port, so a remapped port is
   silently not enforced.
5. **Storage is a StorageClass by name from a value, default `base-rwo`,
   `ReadWriteOnce`.** The kind harness creates `base-rwo` on local-path with
   `WaitForFirstConsumer`, so the chart never names a provider.
6. **One-shot jobs (migrations, loads) are Helm `pre-install,pre-upgrade` hook
   Jobs** with `helm.sh/hook-delete-policy: before-hook-creation`, ordered by
   hook weight the way compose orders them with
   `depends_on: condition: service_completed_successfully`. Without the delete
   policy a second upgrade fails on the Job that already exists.
7. **No Bitnami chart or image.** Bitnami froze its catalogue on 2025-08-28;
   what a chart pulls from there no longer receives fixes.
8. **No cloud identity, ingress host, cloud ARN or account in a base chart.**
   The base cannot know where it runs. Managed-cluster identity (EKS Pod
   Identity) lives outside the chart, in the instance.

9. **Every variable is declared explicitly in `env`; `envFrom` is not
   allowed.** Secrets use `valueFrom.secretKeyRef`. The parity check can only
   compare names it can see, and `envFrom` hides them behind a Secret or
   ConfigMap it never reads.

### The parity check

`scripts/chart_parity.py` compares a layer's compose file with the rendered
chart. A layer's `tests/test_chart.py` calls it after `helm template`:

    python3 scripts/chart_parity.py --compose compose.yaml \
        --rendered rendered.yaml --map deploy/chart/parity.yaml

It exits 0 when they match, 1 with one line per mismatch
(`service <s>: <what> compose=<x> chart=<y>`), and 2 when an input cannot be
read or `parity.yaml` is malformed. Per service it compares env var names (not
values), container ports (`expose`/`ports` target against `containerPort`),
secrets (a password-, key-, secret- or token-named variable fed by `${X:?}` or
`${X:-}` in compose must be a `secretKeyRef` in the chart) and, when compose
pins an image digest, that the chart's image carries the same digest. A compose
service with `profiles:` is skipped unless `parity.yaml` lists it. Only a
workload's `containers` are compared, not its `initContainers`. Env is checked
from compose to chart (the chart may carry more), ports in both directions
when compose declares any; a container using `envFrom` is reported.

    services:            # compose service -> chart workload
      bff: {workload: bff}
      accounts-migrate: {workload: accounts-migrate, kind: Job}
    ignore:              # intentional differences; a reason is required
      - {service: edge, field: ports, reason: "published port becomes a Gateway listener"}

`kind` (Deployment, StatefulSet, DaemonSet or Job) is optional and only needed
when two workloads share a name. `field` is one of `workload`, `env`, `ports`,
`secrets`, `image`. An `ignore` entry without a reason is an error (exit 2): an
unexplained difference is the drift the check exists to catch.
