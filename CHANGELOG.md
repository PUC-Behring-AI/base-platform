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

### Added

- **Terraform modules for a managed EKS Auto Mode cluster** (#86): `deploy/terraform/persistent` and `deploy/terraform/cluster`, each called by an instance from a root of its own (separate state). Nothing here installs an application: helmfile does, on EKS as on kind. `docs/ADAPTATION.md` §10 gains *The managed cluster*; `deploy/terraform/README.md` has the interface, the provider block and the pinned versions.
  - `persistent` (never destroyed): ECR repositories with a lifecycle policy, a versioned private backups bucket, monthly and daily account-wide budgets. Variables `name`, `region`, `tags`, `ecr_repositories`, `budget_monthly_usd`, `budget_daily_usd`, `budget_emails`; outputs `ecr_repository_urls`, `backups_bucket`.
  - `cluster` (the stack teardown destroys): EKS Auto Mode on public subnets without NAT (the default VPC unless named), StorageClass `base-rwo` on `ebs.csi.eks.amazonaws.com`, NetworkPolicy enforcement on, GatewayClass `base-alb` with an internet-facing ALB by default, an arm64 node pool and an optional amd64 GPU pool, and a Pod Identity role for External Secrets Operator limited to `secretsmanager:GetSecretValue` under `secrets_prefix`. Variables `name`, `region`, `tags`, `kubernetes_version`, `vpc_id`, `subnet_ids`, `gpu_node_pool`, `eso_namespace`, `secrets_prefix` and optional tuning ones; outputs `cluster_name`, `cluster_endpoint`, `cluster_certificate_authority_data`, `oidc_issuer`, `storage_class`, `gateway_class`, `eso_role_arn`.
  - The root configures the `aws` and `alekc/kubectl` providers (kubectl with `lazy_load = true`), and the applying machine needs aws-cli 2.38.6 or newer: the aws provider cannot yet turn the Gateway API on, so a script does it once per cluster.
  - Not verified: no `apply` has run. Unchecked on a live cluster: nodes of NodeClass `base` joining, Auto Mode's EBS driver honouring the volume tags, the `gateway.k8s.aws` CRDs being installed and a GatewayClass-level `parametersRef` being honoured, and whether External Secrets Operator needs more than `GetSecretValue`.
  - Not `BREAKING`: nothing an instance already uses changes.
- **The gate workflow's Terraform step**: Terraform 1.17.1 pinned by sha256, then `terraform fmt -check`, `init -backend=false`, `validate` and `test` for each module; `tests/test_terraform.py` runs the same checks and refuses an account id, a region outside a variable default or an instance name in the modules.
- **The reusable `system-kind` workflow** (#84): `.github/workflows/system-kind.yml`, called with `uses: …/system-kind.yml@vX.Y.Z` and inputs `base_ref` (required), `instance_path`, `instance_repository`, secret `instance_env`. It checks out the five base repositories at `base_ref` with harmony's deploy keys, installs the kind toolchain pinned by sha256, runs `scripts/k8s-up.sh` and `scripts/k8s-test.sh` on the instance directory, and on failure uploads the cluster's state as artifact `cluster-state`. On base-platform's own pull requests it runs when `deploy/`, `scripts/k8s-*` or the workflow changes. First green run on 2026-10-29: 5 min 16 s on a 2 vCPU `ubuntu-latest` runner (`docs/ADAPTATION.md` §10).

## [0.9.0] — 2026-10-29

### Added

- **A Helm chart per layer** (base-knowledge#48, base-inference#128, base-agents#41, base-interface#52): each engine ships `deploy/chart`, so the base runs on a Kubernetes cluster as well as under compose.
- **Chart conventions and a parity checker** (`docs/ADAPTATION.md`, #82). The conventions say how a layer's chart is written; the checker compares a chart's rendered workloads with the layer's compose fragment and fails on a difference that is not declared.
- **`deploy/charts/schemas` and `deploy/charts/postgres`**: the contract schemas as a chart, and a small Postgres the layers use as their stores.
- **A local kind harness and a system test** (#83): `scripts/k8s-up.sh`, `k8s-test.sh` and `k8s-down.sh` bring the whole base up on a local kind cluster, test it end to end and remove it.
- **The gate's chart step**: `scripts/gate.sh` lints, renders and validates (kubeconform) every `deploy/chart` or `deploy/charts/<name>`, and stops parsing chart templates as YAML. CI installs the pinned `helm` and `kubeconform`.
- **An instance's own releases on the kind harness** (#91): an optional `<instance-dir>/releases.yaml` adds releases of base charts on the helmfile's allow-list (`postgres`), each installed after its namespace's `schemas` and before the layers it names in `neededBy`, so one cold `scripts/k8s-up.sh` brings the instance up. A chart off the list, an unknown key, a bad name or `needs`, or a missing values file is refused before the cluster is touched. The reference instance declares `knowledge-store` as the example.
- **`scripts/k8s-registry.sh`** (#92): starts the kind registry `localhost:5001` idempotently; `k8s-up.sh` runs it before the cluster, and an instance may run it first and build with `--push localhost:5001`.
- **An instance's system test** (#93): `<instance-dir>/system-test.yaml` lists the flows `scripts/k8s-test.sh` runs through the Gateway (input, expected status, body schema, outcome, saved values, job timeout) and an optional C1 knowledge search; `scripts/k8s_system_test.py` reads and runs it. The reference instance keeps `echo`.

### Changed

- **base-interface's edge template reads its settings from the environment** (base-interface#52). `edge/default.conf.template` took Docker's DNS and `bff:8080` as literals; it now uses `${BFF_UPSTREAM}` and the name servers the nginx image exports as `NGINX_LOCAL_RESOLVERS`, and the composition sets `BFF_UPSTREAM=bff:8080` and `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`, which render the same configuration as before.
  - Not `BREAKING`: no contract in `docs/CONTRACTS.md` changes, and an instance that uses the engine's edge unchanged needs nothing.
  - An instance that overrides the edge template, or replaces the edge service's environment, must set both variables, or nginx starts with an empty upstream.

- **An instance is a set of sockets; team code enters as modules** (`docs/ADR.md` ADR-014). An instance's `<prefix>-<layer>` repositories plug modules into the engines; a team's product — screens, flows, methodology code — lives in that team's own repository, runs standalone, never names the instance, and is consumed at its `main` with the commit recorded in the image. ADR-014 amends ADR-013's "the instance supplies `src/instance/`": the interface instance composes screens from module packages and holds none of its own.
  - `docs/ADAPTATION.md` §4 gains *Sockets and modules*, and its interface bullet says how a UI module is composed (lazy routes, one React); §5 sends domain code to modules.
  - `AGENTS-base.md` 1.5 adds *Base, sockets and modules*: which kind of repository an agent is in, and what each may contain.
  - Not `BREAKING`: no contract and no engine changes. An instance whose interface already holds its screens in `src/instance/` keeps building; ADR-014 says where those screens belong.

- **`BREAKING`: `scripts/k8s-test.sh` takes `<instance-dir>`, which must hold a `system-test.yaml`** (#93). An instance that ran it with no argument adds the file (the reference instance's is the minimal example) and passes its directory.
- The reference instance's `.env.required` gains `KNOWLEDGE_STORE_PASSWORD` (namespace `knowledge`), for `knowledge-store`: an existing `deploy/helmfile/reference-instance/.env` needs the line. Not `BREAKING`: it concerns only running the base alone, not an instance.

## [0.8.0] — 2026-10-21

### Changed

- **`BREAKING` — C5's interface half shrinks to accounts and roles** (`docs/CONTRACTS.md` §C5, `schemas/c5_identity.schema.json`).
  - Removed: `grant_access`, `revoke_access`, `link_credential`, `ensure_model_catalog_entry` and `configure_upstream`, plus `has_credential` and `model_ids` from `get_account_response`.
  - The interface calls no model since ADR-013, and model access is the scope of the credential `inference` issues.

  **What each layer must do:**
  - `interface` drops those operations with its chat UI (base-interface#32, #33);
  - `platform`'s provisioning (`colleague create` in base-inference) stops calling them.

- **`BREAKING` for people provisioned with `colleague create`: the chat UI is gone** (base-interface#33). base-interface removed Open WebUI, which called the model gateway directly, and the composition drops its wiring (`compose.wiring.interface.yaml`). The interface is a React shell behind a backend-for-frontend, and its accounts live in its own store; Open WebUI's accounts are not migrated. A person's gateway key keeps working from any OpenAI-compatible client. `colleague create` mints the key only (base-inference#124).

  **What an instance must do:** create interface accounts through base-interface's C5 operator command (`scripts/account.sh`), starting with an admin.

- **`BREAKING` — C2 states who is limited: the key, not the person** (`docs/CONTRACTS.md` §C2, #69). Once product calls go interface → agents → inference, agents calls with its own key, so budgets and rate limits apply per key, that is, per deployment. Per-person limits on product calls are not a base guarantee. An instance that needs them passes the person as the gateway's end user, with a budget per person, measured in #69. This is safe only while no person holds a key that reaches chat models.

  **What an instance must do:** nothing, unless it relied on per-person budgets for product use. Keys issued to people through `colleague create` keep their tiers.

- **`BREAKING` — C3's `response` gains a required `outcome`** (`docs/CONTRACTS.md` §C3, `schemas/c3_envelope.schema.json`). It is `answered` or `declined`; a declined response also carries a machine-readable `declined_code`. A flow that declines returns a result, not an error, and a screen tells the two apart without reading the instance-defined body. A job's `result` is a `response`, so it carries the field too.

  **What each layer must do:**
  - `agents` sets `outcome` on every response and job result (base-agents#9, its flows socket);
  - `interface` reads it, and shows a decline as a decline, not as a failure;
  - an instance: nothing in its body schemas, which stay inside `body`.

### Added

- **`BREAKING` — C3 carries human decisions and C6 reads in engine-defined bodies** (`docs/CONTRACTS.md` §C6, `schemas/c3_envelope.schema.json`: `decision`, `provenance_query`).
  - A decision is `{about_request_id, decision: accept | override | dismiss | approve, target, detail?}`. `agents` classifies its C6 record as the strictest class among the records of the request decided on; the screen never picks it.
  - A C6 read is `{filter, limit, cursor?}`. The reader-access rule is the instance's, declared by role in its agents instance. With no rule, every read is refused.

  **What each layer must do:**
  - `agents` serves both routes (base-agents#26);
  - `interface` sends these bodies;
  - an instance declares its reader-access rule in its agents instance, or no one reads provenance.

- The composed base's metrics backend joins `interface-metrics`, the internal network base-interface's backend-for-frontend replicas are scraped on (base-interface#19). `tests/test_compose_base.py` checks that `interface-agents` and `interface-metrics` are declared identically in every fragment, as it already does for `base-internal`.

### Fixed

- harmony's CI sets up Node when a sibling declares it in `.nvmrc`. The gate's Node step requires the installed major to equal `.nvmrc`'s. Without this step, the first sibling with a `package.json` (base-interface#18) would fail every repository's harmony on the runner's preinstalled Node. Siblings declaring different majors fail the run by name.
- harmony's CI installs `psycopg` and `psycopg-pool`, the client of base-interface's account store (base-interface#32). Its tests start a throwaway Postgres in Docker.

## [0.7.0] — 2026-10-19

### Added

- **The gate checks Node / TypeScript** when a repository has a `package.json` (ADR-013 gave the interface a TypeScript codebase). The rules:
  - `package-lock.json` and `.nvmrc` are required, and the Node major must match;
  - then `npm ci`, plus `tsc --noEmit`, `eslint` and `vitest run`, each only when its configuration is present;
  - a tool configured but not installed fails instead of skipping.

  ADAPTATION §3's workflow example adds `actions/setup-node`.

- **`BREAKING` — C3 gains an envelope** (`docs/CONTRACTS.md` §C3, `schemas/c3_envelope.schema.json`). The envelope covers:
  - `X-Request-Id`, generated by the interface's backend-for-frontend;
  - the caller's identity (`X-Account-Id`, `X-Account-Roles`), asserted by the backend-for-frontend;
  - a required `classification` on every response, and a typed error;
  - two call modes: synchronous, and job (`job_accepted`, then `job_status` with ordered steps and a result or an error).

  Bodies stay instance-defined. **What each layer must do:**
  - `agents` implements the envelope and a job runner (base-agents#11);
  - `interface` calls only through it (base-interface#19);
  - an instance writes its payload schemas in `<prefix>-platform/schemas/`.

- **`BREAKING` — C8, domain records, `agents` → `knowledge`** (`docs/CONTRACTS.md` §C8, `schemas/c8_record.schema.json`). It covers writes and reads of the records a person builds, and uploads of sources for ingestion:
  - collections declared by the instance in `knowledge`, each with a class;
  - the engine stamps the classification, and the caller may only raise it;
  - optimistic concurrency by revision;
  - every write emits C6.

  **What each layer must do:**
  - `knowledge` implements C8 and lets an instance declare collections;
  - `agents` writes through it, never around it;
  - an instance declares its collections.

- **`BREAKING` — C6 gains a read path** (`docs/CONTRACTS.md` §C6, `schemas/c6_query.schema.json`). An audit view reads provenance through `agents`:
  - a query needs at least one filter (request, record or time window) and a bounded limit;
  - each record keeps its own class, and the read is itself recorded;
  - a human decision (accept, override, dismiss, approve) is a C6 record that `agents` emits for the interface.

  Who may read which class is still undefined in the base; each instance states its rule. **What each layer must do:**
  - `knowledge` serves the query;
  - `agents` exposes it over C3 and emits decisions.

### Changed

- **BREAKING** — C1: every passage's `provenance` carries a required,
  non-empty `locator`, where in its source the passage is (a document and its
  pages, a record key), in an instance-defined format. Before, a passage named
  its source alone and could not be cited (#53). base-knowledge writes it from
  each module's `Hit.locator`, now required, and locates a static passage as
  `<source>#<index>` (base-knowledge#34). An instance acts before pinning:
  every knowledge module returns a locator with each hit.
- **ADR-013: the interface carries instance code.**
  - The engine becomes a React shell plus a backend-for-frontend.
  - An instance's `src/instance/` (routes, navigation, theme) is built into an image `FROM base-interface:<tag>`.
  - The backend-for-frontend is the layer's one arrow, on a network that reaches only `agents`.
  - ADR-011's "`interface` takes configuration only" narrows to `inference`. ADAPTATION §4 and ARCHITECTURE follow.
  - **What an instance must do:** nothing yet. `forms/` and `views/` were never read by any engine. The engine side is tracked in base-interface#15.

### Fixed

- The gate and harmony find the sibling repositories beside the main
  checkout, also when run from a worktree (`.claude/worktrees/<name>`). Before,
  the gate looked for `<prefix>-platform/base-version.yaml` inside the
  worktrees directory and failed, harmony run from a base-platform worktree
  silently dropped every sibling, and `tests/test_compose_base.py` skipped
  (#15). The gate now exports `BASE_<NAME>_DIR` for every base sibling it
  finds, unless one is already set, so a test suite run through it sees the
  same siblings.
- harmony checks the working tree given on the command line, not the one the
  current directory is in, when both belong to the same repository (#31).
- The gate wrapper in `docs/ADAPTATION.md` §3 finds `base-platform` beside the
  main checkout. Each repository's copy changes in its own pull request.

## [0.6.0] — 2026-10-16

### Note on the five repositories' history

All five base repositories had their history rewritten on 2026-10-16, and
`base-platform` was deleted and recreated a second time. The 2026-09-14 purge
had replaced a client's, a contract's and a methodology's names but left an
instance prefix and a description of its domain in three commits, and one
commit message carried a pasted service configuration with credentials. The
private repositories carried the same names in their bootstrap commits and
specs, and test fixtures carried one domain's vocabulary.

What it means for anyone holding the base:

- `v0.1.0`, `v0.2.0` and `v0.5.0` point at rewritten commits. Their trees are
  the same except for the removed text. A clone made before 2026-10-16 must be
  deleted and cloned again; pushing from it would bring the old history back.
- In `base-platform`, issue and pull-request numbers are kept: open issues were
  recreated at their numbers, closed ones with their text, and every pull
  request as a closed issue whose branch and diff are gone.
- The credentials belonged to the precursor's deployment. The base reads none
  of them; any deployment of the base sets its own.


### Added

- `scripts/leak-check.sh` (#34), run by the shared gate in every `base-*`
  repository: fails when a tracked path or file, a pull request's commit
  message or its body contains a term of a denylist read from the
  `BASE_DENYLIST` secret or a local `BASE_DENYLIST_FILE` — never written in
  this repository. A hit names the place and the term's number, never the
  term. With no list given the check warns that it is not active. Skipped in
  an instance, which names itself.
- The gate workflow scans each pull request's diff and commit messages with
  gitleaks (#39), from a release binary pinned by version and sha256, and
  fails the run on a finding. Findings are printed redacted.
- **Instances: the shared gate checks the pin** (#38, `ADAPTATION.md` §7). In
  every `<prefix>-*` repository it reads `<prefix>-platform/base-version.yaml`
  and fails when the file is missing, when the `# Base:` line, a workflow's
  `@ref` on a `base-*` repository, a `base-*` checkout `ref:`, a `base_ref:`
  or a Dockerfile's base image tag disagrees with it, or when its tag does
  not exist. An instance acts before its next pull request on a base that
  carries this: write `base-version.yaml`, pin every reference to the tag,
  and check `<prefix>-platform` out in the other layers' gate workflow (§3).
  Not breaking for `base-*` repositories, where the step is skipped.
- `.github/workflows/harmony.yml` takes `inputs.base_ref` (default `main`):
  a caller pinning `vX.Y.Z` gets `base-platform` and every `base-*` sibling
  at that tag, instead of at `main` whatever `@ref` it called. The §3 gate
  template checks `base-platform` out at the pinned tag too.

### Changed

- `.github/workflows/issue-hygiene.yml` (#41) is reusable (`workflow_call`).
  `ADAPTATION.md` §3 gives the caller, so a repository calls the one rule
  instead of carrying a copy that keeps the old rule when this one changes.
- `AGENTS-base.md` 1.4, **Axiom 10** (#37): the invariant splits in two. The
  base layers' `main` branches work together at all times; an instance works
  with the base at the version it pins, and checks that in its own CI. 1.3
  bound the base's `main` to every instance's `main`, which contradicted
  pinning (`ADAPTATION.md` §7, §9) and would have had the base check out, and
  name, its consumers.
- `scripts/harmony.sh` follows: from a base repository it checks the base
  layers alone; from an instance, that instance's own `<prefix>-*`
  repositories and the base. Another instance cloned alongside is no longer
  checked, or named, by either.

### Fixed

- `ADAPTATION.md` §4 (#40): `base-agents` is listed with its socket issue
  (base-agents#9) next to the other layers that will take code, and
  `tiers.yaml` is marked pending — nothing reads it yet; base-inference#106
  defines it.
- `tests/test_harmony.py`: a fixture repository was named after a real
  instance prefix; it is `x-like` now (#34). A test name is as public as a
  document.
- `scripts/release.sh` (#36): harmony runs on the five base layers only,
  through the new `harmony.sh --only <path>...`. A repository cloned next to
  the base, an instance included, no longer decides whether the base can be
  tagged (ADR-004: the base does not push, an instance pulls).

## [0.5.0] — 2026-10-15

The first version tagged after 0.2.0 — 0.3.0 and 0.4.0 never were. Tagged
when all five layers fulfilled it (`docs/ADAPTATION.md` §7): `base-knowledge`
with its C7 client (base-knowledge#16), `base-inference` with its embedding
model kind (base-inference#108).

C7 opens the first arrow out of `knowledge`, to an embedding model, and the
instance socket convention (ADR-011) lands with it.

### Added

- **`BREAKING` — C7, embeddings, `knowledge` → `inference`** (`docs/CONTRACTS.md`, ADR-012):
  - OpenAI-compatible `/v1/embeddings` only;
  - an always `local-only` credential, confined to the embedding models and to the embeddings route;
  - one embedding model per index, vectors stored under their passage's classification, and every call recorded in C6.

  ADR-001 and `ARCHITECTURE.md` narrow to "never calls a generative model". **What each layer must do:**
  - `inference` serves an embedding model kind, and mints the confined credential;
  - `knowledge` builds the client and hands it to modules;
  - an instance declares its embedding model.
- **`BREAKING` — C5 `issue_credential_request` gains `purpose`** (`chat` | `embed`, default `chat`). An `embed` credential must have `allowed_key_policies: ["local-only"]`; the schema refuses anything else.
- `AGENTS-base.md` 1.3, **Axiom 10, One System Rule**: the base and instance
  repositories are one system. Every repository's `main` works with every
  sibling's `main`, and `scripts/harmony.sh` runs before every pull request.
- `scripts/harmony.sh`: runs every sibling repository's gate against the working
  trees on disk. Run from a worktree, it checks the siblings against that
  worktree, and it exports `BASE_<NAME>_DIR` so the cross-layer tests do the
  same.
- `ADAPTATION.md` §7: what a `# Base:` line claims (the layer does everything
  the version asks of it), and when a version is tagged. `scripts/release.sh`
  is the only way to tag: it checks the five agree, are on a clean `main`, and
  pass `harmony.sh`. The shared gate now fails on a `# Base:` newer than
  `VERSION`. §9 no longer promises a weekly train that never ran.
- `.github/workflows/harmony.yml` (#25): harmony.sh in CI, reusable by every
  repository. Each repository's settings name its siblings and hold a
  read-only deploy key per private sibling; no file names a repository.
- `ADAPTATION.md` §4: where an engine reads its instance (`BASE_INSTANCE_DIR`,
  mounted read-only; unset means empty, invalid means refuse to start), how
  instance code enters an engine (entry-point group `base_<layer>.modules`,
  listed in the manifest), the stamp, the egress rule, and how an instance
  image is built. ADR-011 records why the code socket opens now.

### Fixed

- `schemas/validate.py` (#21): `validator_for` checks `format`, so a
  `request_id` that is not a uuid is refused instead of reaching the C6 store.
  It refuses to build where a format the schemas use has no checker: every
  layer that validates installs `jsonschema[format-nongpl]`.
- `compose.base.yaml` (#30): Compose v2 refused the file ("conflicts with
  imported resource"). Each override is now merged inside its include entry.
- `docs/CONTRACTS.md`: the C6 section had lost its heading and read as part of C5.
- `ADAPTATION.md` §4: the `taxonomy.yaml` example spelled `key-policy`; the
  schema field is `key_policy`. `models.yaml` no longer claims a "key policy
  per class" — `inference` never sees a class.

## [0.4.0] — 2026-09-14 — never tagged

Found trying to make a real consumer (`base-inference/scripts/colleague.sh`)
actually switch to the three operations `0.3.0` added: `create_account`
could not carry a login credential or a role, and no operation could inspect
an account at all, despite C5's own prose promising it since before there
was a schema.

### Added

- **`BREAKING` — `create_account_request` gains optional `password` and
  `role`; `create_account_response` gains a conditional `password`.** A
  caller that supplies no password gets one generated and returned on first
  creation — the only moment it is ever knowable, since nothing else in this
  contract issues a login credential. An update to an existing account that
  supplies neither field touches neither. `role` only ever applies at
  creation. See `docs/CONTRACTS.md` §C5.
- **`BREAKING` — `platform → interface` gains a fourth operation: inspect an
  account.** `get_account_response` carries `display_name`, `role`,
  `model_ids`, and `has_credential` — never the credential itself, only
  whether one is linked. This replaces reading Open WebUI's `api_key` table
  directly, which is what printed a prefix of the real secret before this
  operation existed to answer the same question safely.

## [0.3.0] — 2026-09-14 — never tagged

Redistributing the parts of the original monolithic server into the layers they
belong to (issue #14, recreated as #2 — see the repository history note
below), and making the contracts executable instead of prose (issue #7,
recreated as #3). Both grow one slice at a time. It was meant to be the first
tag since 0.2.0; no tag was made, for this version or the next.

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
  from every ref with `git filter-repo` on 2026-09-14 (incompletely — see
  the note under [0.6.0]); `v0.1.0` and `v0.2.0`
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

[0.5.0]: https://github.com/PUC-Behring-AI/base-platform/releases/tag/v0.5.0
[0.2.0]: https://github.com/PUC-Behring-AI/base-platform/releases/tag/v0.2.0
[0.1.0]: https://github.com/PUC-Behring-AI/base-platform/releases/tag/v0.1.0
