# How an instance is born

An instance is a platform deployed on top of the base. This document is what
someone follows to create the second one.

## 1. Pick the prefix

The code of the contract funding the project, lowercase, no spaces. `g122` comes
from REDACTED-INSTANCE.

Do not use the methodology name (it mixes what is the client's with what is ours)
nor the client name (it collides if they commission two platforms).

**Add the line to the prefix map in this repository's `README.md`, in the first
table.** Without it, the prefix is a riddle to whoever arrives later.

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

## 5. Board the train

`base-platform` declares the version of each layer. The instance boards the weekly
cadence like any other.
