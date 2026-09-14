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

## 4. Fill in the extension points

This is the **declarative** half of adaptation. The other half is domain code,
and section 5 covers it.

| Layer | The instance declares |
|---|---|
| `knowledge` | `ontology/` (RDF/OWL), `connectors/` (sources), `taxonomy.yaml` |
| `inference` | `models.yaml` (served models and key policy per class) |
| `agents` | `flows/`, `prompts/`, `tools/` (MCP declarations) |
| `interface` | `forms/`, `views/` |
| `platform` | `schemas/` (C1–C6 payloads), `base-version.yaml` |

**`taxonomy.yaml` is the most important file on that list.** It is where the
routing rule becomes a parameter: each sensitivity class declares the key policy
that applies to it.

    classes:
      - name: public
        key-policy: external
      - name: client-confidential
        key-policy: local-only

The inference engine enforces the policy. The instance decides which classes
exist and what each one permits — it does not decide *whether* the policy is
enforced.

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
knowingly — not the gate's to force.

## 9. Board the train

The release train departs weekly with whatever is ready. The instance boards it
like any other.
