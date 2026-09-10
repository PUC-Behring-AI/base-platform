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

**The prefix is decoded in the instance's own `<prefix>-platform` README, and
nowhere else.** Not here, and not in a central list.

A contract code is opaque by design, so something has to decode it — but the
answer is not a registry. The base cannot hold one: a base holding a list of
who uses it has become a component of its largest consumer. And a central list
elsewhere has to live somewhere, which is how the first attempt ended up
publishing a client's contract number on the organisation's public page.

An instance that documents itself needs no registry. Whoever can see
`<prefix>-knowledge` can open `<prefix>-platform` and read what the prefix
means. Whoever cannot see it has no need to know.

## 2. Create the five repositories

`<prefix>-platform`, `-knowledge`, `-inference`, `-agents`, `-interface`.
Private, unless explicitly decided otherwise.

Create each one with an initial commit, so that the first content change can go
through a pull request:

    gh repo create PUC-Behring-AI/<repo> --private --add-readme \
      --description "<one line>"

Without `--add-readme` the repository has no branch at all, and GitHub then
refuses `gh pr create` with `Base ref must be a branch`. The throwaway README it
creates is replaced by the first pull request.

Apply the organisation properties to each one:

    gh api --method PATCH repos/PUC-Behring-AI/<repo>/properties/values --input - <<JSON
    {"properties":[{"property_name":"layer","value":"<layer>"},{"property_name":"role","value":"instance"}]}
    JSON

## 3. Fill in the extension points

This is the **declarative** half of adaptation. The other half is domain code,
and section 4 covers it.

| Layer | The instance declares |
|---|---|
| `knowledge` | `ontology/` (RDF/OWL), `connectors/` (sources), `taxonomy.yaml` |
| `inference` | `models.yaml` (served models and key policy per class) |
| `agents` | `flows/`, `prompts/`, `tools/` (MCP declarations) |
| `interface` | `forms/`, `views/` |
| `platform` | `schemas/` (C1–C4 payloads), `versions.yaml` |

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

## 4. Write the code that is only yours

Computation, validation, methodology rules. This lives in the instance repository
and should not be squeezed into YAML.

**When you need something the engine cannot express**, the rule is: open an
extension point in the engine only when **two** instances ask for the same thing,
or when what you need is confidential and therefore cannot live in the engine.
Until then, write it in your own repository.

An engine generalised from a single case stiffens what was hard and abstracts
what was easy.

## 5. Pin the base version

**The base has one version, and the five repositories are tagged together on
it.** `base-platform/VERSION` holds it; `base-platform/CHANGELOG.md` says what
changed between one and the next.

An instance records the version it runs on, in
`<prefix>-platform/base-version.yaml`:

    base: 0.1.0

One number, not five. A single version means the combination has been released
together, so "was this set tested against itself?" has an answer. Per-layer
pinning would be more precise and would lose exactly that.

The cost is real and worth knowing: a fix in one engine bumps the version of all
five. That is deliberate — the alternative is five numbers nobody reconciles.

## 6. Upgrading

The base does not push. An instance pulls, and this is what pulling looks like:

1. Read `CHANGELOG.md` from the base tag above yours.
2. **Any entry marked `BREAKING` is a contract change.** It obliges the
   instance to act before pinning the new version; nothing else does.
3. Bump `base-version.yaml`, run the instance's gate, ship it through a pull
   request like any other change.

Staying behind is allowed and is sometimes correct. What is not allowed is not
knowing: the pinned version is in a file, in git, so "which instances are behind
0.2.0?" is a question a grep answers.

## 7. Board the train

The release train departs weekly with whatever is ready. The instance boards it
like any other.
