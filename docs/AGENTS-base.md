# AGENTS-base.md — rules common to every repository in the base

**Version: 1.1 · 2026-09-12**

This file is the shared half of each repository's `AGENTS.md`. Every repository
has its own `AGENTS.md` that **points here** and adds what is specific to it.

**The repository addendum wins** on conflict: whoever wrote it knows that
repository.

This file is versioned. A repository declares which version it follows on the
first line of its own `AGENTS.md`. That is what makes it possible to tell who is
behind — the one thing ten loose copies never allow.

**Provenance.** These sections were extracted from `idia-server/AGENTS.md`
(now `base-inference`), where they had accumulated over five phases of work.
They were translated from Portuguese and generalised away from that
repository's specific paths; each generalisation is marked. They were not
rewritten. They are calibrated axioms, and rewriting one in passing is how one
gets lost.

---

## Document Evolution Contract

### The architecture document is a living document

Every layer keeps an architecture document describing what it is and how it
works. It evolves with the code. These rules prevent it from drifting out of
sync.

> *Generalised: the source named `ARCHITECTURE.md` at a fixed path. Here it means
> whichever document a repository designates as its architecture reference.*

**SYNC-REQUIRED triggers** — any change to:

- Container definitions: base image, dependencies, entrypoint
- Service configuration: what runs, with what parameters
- Orchestration: services, ports, networks, volumes, hardware allocation
- Configuration rendering or templating logic
- Monitoring: scrape targets, alert rules
- Any file under `tests/` that introduces a new test category
- Port mappings, network topology, security perimeters
- Model loading or hardware placement strategy

**Minor update** — version bump, parameter adjustment, new environment variable:

- Edit only the affected section.
- No full document review.
- Update the footer with the date and the sections changed.

**Major update** — new layer, new deployment target, changed pattern:

- Full document review.
- Old sections marked `[DEPRECATED — see section X]`.
- Requires human approval before merge.

**Desync prevention:**

- If code and the architecture document disagree, the code is the truth — but
  the document must be updated in the same pull request.
- Every implementation task affecting the architecture declares
  `[UPDATES <arch doc> — section X]` in its plan.
- Never merge code without the corresponding architecture update.

**Version footer:**

```markdown
---
*Document version: 1.1 | Last updated: YYYY-MM-DD | Sections changed: [list]*
```

### AGENTS.md update rules

- Updated when a new phase is planned (new stacks, tools, workflows).
- Updated when component versions change materially.
- Updated when new constraints are discovered during development.
- Updated when the directory layout or the test suite changes significantly.
- The **Testing Strategy** section must reflect exactly the tests implemented
  in `tests/`.

---

## Anti-Drift Rule (AXIOM — NON-OVERRIDABLE)

Every implementation task that creates, modifies or removes an infrastructure
artefact (Dockerfile, config YAML, Compose file, entrypoint, deployment script,
CI/CD pipeline, integration or security test) MUST:

1. Declare in the plan: `[UPDATES <arch doc> — section X]`
2. Update the corresponding section in the architecture document, in the same
   commit
3. Update the architecture document's version footer
4. Add an entry to the Structural Change History

**Violation:** if an artefact is merged without the corresponding architecture
update, the commit is incomplete. The correction comes before any other work.

---

## Governance & Maintainability Axioms (AXIOM — NON-OVERRIDABLE)

These rules exist because traceability of decisions and ease of maintenance are
project priorities. A new team member, or an agent, must be able to understand
any part of the system from the documentation and the commits alone — without
interviewing the original author.

### 0. Decision Closure Rule — a plan only exists once its decisions are closed

No implementation plan is complete while design decisions remain open. The plan's
author must:

1. Identify every open question during analysis of the problem.
2. Document each question explicitly in the plan.
3. **Close each decision** before finishing the plan, using:
   - Established best practice, when the user has no preference.
   - The author's reasoned recommendation, when the user delegates.
   - Further investigation (skills, research, existing code) when needed —
     never unverified guesses.
4. Record the decision and its rationale in the plan or the documentation.

**Violation:** a plan presented with unapproved open questions does not
authorise implementation. Implementation stops until every decision is closed.

### 1. Architecture Feedback Loop — every implementation discovery feeds back

Implementation inevitably reveals details the original architecture did not
anticipate. When it does:

1. The discovery is recorded.
2. The architecture document is updated to reflect the corrected understanding.
3. Implementation continues on the updated architecture — never on the stale
   version.

**Cycle:** `Architecture → Implementation → Discovery → Architecture update →
Implementation continues`

**This applies to:** parameters that turn out different from expected; workflows
requiring undocumented extra steps; dependencies or versions that prove
incompatible; any difference between real and specified behaviour.

**Record:** every turn of the cycle must be traceable through a commit or an
entry in the architecture document's Structural Change History.

### 2. Traceability Axiom — every commit must make sense to a newcomer six months later

A commit is not only "what changed" — it is **why it changed**, which decision
was taken, and which alternative was discarded.

| Criterion | Required? | Good | Bad |
|---|---|---|---|
| **Why** does this change exist? | Yes | "pre-render workflow, because the config has `${VAR}` placeholders since phase 2" | "update config" |
| **Which decision** was taken? | Yes | "use image `x:2.56.0-py311-gpu` — it bundles the engine at 0.22.0" | "update image" |
| **Which alternative** was discarded? | Yes | "installing the engine separately was discarded: it breaks the framework's version pinning" | "fix deps" |
| **What** changed (the diff)? | Yes, implicit in git | — | — |

**In practice:** the commit message must answer, in plain language, "why",
"which decision" and "which alternative".

**Derived documentation:** when an implementation decision changes the
architecture, the architecture document is updated in the same commit, and the
Structural Change History entry references that commit.

### 3. Maintainability Over Novelty — prefer the known over the new

When several technical approaches solve the same problem:

1. Prefer the best documented, best tested, most familiar approach.
2. Experimental or cutting-edge approaches require an explicit justification of
   why the established approach does not serve.
3. "Because it is newer / faster / better" is not sufficient justification
   without measurable evidence for the specific use case.
4. If a new approach is chosen, document explicitly what is expected to be
   gained and what the fallback plan is.

**Exception:** when the active problem cannot be solved by established
approaches — in which case, document why.

---

## Code Quality Axioms (AXIOM — NON-OVERRIDABLE)

These rules exist because an audit found recurring failure patterns: missing
input validation, undeclared dependencies, I/O without diagnostics, and
insufficient test coverage of error cases. They apply to all code, in every
phase.

### 4. Input Validation Rule — every environment variable with a constrained type is validated

Every environment variable with a numeric type (int, float) or a range must be
validated before use. The validation must:

- Reject values that cannot be converted to the expected type.
- Reject values outside the documented range.
- Emit a clear message with the value received and the range expected.
- Exit non-zero on validation failure, at the entrypoint.

### 5. Dependency Declaration Rule — every import has an entry in the manifest

No dependency may be imported without being declared in the project manifest,
with explicit version bounds (`>=` for the minimum, `<` for the maximum).

**Forbidden:** relying on transitive dependencies. If the code imports a
library, that library is declared — even when a framework already brings it.

### 6. Error Handling Rule — every I/O operation has an explicit diagnostic

Every file, network or subprocess operation is wrapped with error handling whose
messages:

- Identify the specific file or resource that failed.
- Explain the probable cause (permission, encoding, not found).
- Suggest a corrective action for the operator.

**Exception:** pure functions in tests, which perform no I/O.

### 7. Test Coverage Rule — error paths are tested

For every function with input validation, the error cases are tested alongside
the happy paths. Minimum coverage includes:

- Values outside the expected range.
- Values of the wrong type.
- Special characters that could subvert the output format.
- Missing or inaccessible files.

### 8. Secret Hygiene Rule — environment variables with real values are never logged

No environment variable holding a real value is printed to stdout or stderr,
except under an explicitly enabled `--debug` or `--dry-run` mode. Non-sensitive
identifiers (model names, IDs) may be logged. Passwords, tokens and API keys
are never logged — not even obfuscated.

### 9. Severity Calibration Rule — existing mitigations are weighed before assigning severity

When classifying the severity of a vulnerability:

1. Map the real attack surface — who can exploit it, through which vector?
2. Identify existing mitigations (firewall, local binding, internal network).
3. Assign severity **after** weighing mitigations, not before.

**Guide:**

- **Critical:** remote exploitation without authentication, no mitigations.
- **High:** remote exploitation with partial mitigations.
- **Medium:** exploitation requiring prior access (internal network, SSH,
  physical).
- **Low:** defensive improvement with no immediate risk.

---

## Container Image Policy

- Every image is pinned to an **immutable tag**. `:latest` is forbidden, and so
  is any tag that can be reassigned.
- Where the registry supports it, pin the SHA256 digest alongside the semantic
  version tag. A tag can be moved without the version string changing; a digest
  cannot.
- Do not install a separately-versioned copy of a dependency a framework already
  bundles. Overriding the bundled version breaks the combination the framework
  was tested against.

> *Generalised: the source listed four specific images with their pins. Those
> belong in the layer that runs them, not here.*

---

## Env Var Convention

- Secrets live in `.env`, which is never committed.
- `.env.example` is the documented template, and it is committed.
- Every environment variable is `UPPER_SNAKE_CASE`.
- Required variables are listed in the repository's own `AGENTS.md`, with their
  types and ranges.
- Optional variables document their defaults in the same place.
- A required secret uses the `${VAR:?message}` form wherever the tooling
  supports it, so that its absence refuses to start rather than starting with
  an empty value.

---

## Testing Strategy

The categories below are shared. Which of them a repository actually implements,
and what each of its test files covers, belongs in that repository's own
`AGENTS.md`.

### Test categories

| Marker | Category | What it validates | Needs infrastructure? |
|---|---|---|---|
| `docs` | Documentation | Required files exist, living documents have their sections, version footers | No |
| `config` | Configuration schema | YAML structure of every configuration file the repository owns | No — a YAML parser only |
| `integration` | Integration | Rendering and templating, environment substitution, error paths, cross-file consistency | Unit portion: no. Full suite: yes |
| `security` | Security | Port isolation, image pinning, trust boundaries, service binding | YAML checks: no. Network checks: yes |
| `deploy` | Dry-run and CLI | Command-line surface and dry-run rendering, with nothing started | No |
| (none) | In-process unit | Modules called as functions rather than subprocesses: every error path, every validation branch | No |

### Skipping policy

Tests depending on files from a future phase call `skip()` with an explanatory
message — they never fail over the absence of something not yet built. This is
what lets the suite run clean from the first phase onward.

### Adding new tests

1. Create `tests/test_<area>.py`.
2. Use the appropriate marker.
3. Use the shared fixtures from `conftest.py`.
4. If the test depends on a future-phase file, skip when the file is absent.
5. Register a new marker in the project manifest if it is a new category.
6. Update the Testing Strategy section in the repository's own `AGENTS.md`.
7. If the file is kept lint-clean, add it to the linter's list in the gate —
   outside that list, the linter never sees it.
8. New code is born with a test. Prefer an in-process call to a subprocess: it
   is faster, it reaches the error paths, and a subprocess given a clean
   environment is not measured at all, because that erases the variable that
   instruments the child.
9. **Shell behaviour is tested with a shell test runner, not with a subprocess
   call from another language.** If the new path talks to a service, add an
   endpoint to the fake rather than stubbing the client binary — a script may
   reach that service through more than one client, and a stub of one of them
   sees none of the others.
10. **A test that pins defective behaviour says that it is defective.** In the
    body: what is wrong, and the issue tracking it. Without that it is
    indistinguishable from a test endorsing the defect, and the fix looks like
    a regression.

---

## The local gate

Every repository that has a gate command carries `.claude/portao` holding that
command's path. A `PreToolUse` hook reads that file and refuses `gh pr create`
without a recent gate run. **With no file, the pull request passes ungated and
nothing says so** — which is the one absence invisible from both sides.

The gate belongs to the repository, not to the machine, so it is committed.

Two properties the gate must have:

- **It records its own marker**, or it blocks the pull request it just approved.
- **A missing tool fails the step, it does not skip it** — at least for the
  coverage floor. Skipping a floor is approving a pull request having measured
  nothing, and printing green over it.

`.claude/issue-vizinhas` holds the heading that every new issue body must carry.
An issue that never asks who it collides with is indistinguishable from one that
asked and found nothing, and only one of the two is honest.

## Cross-Repository Issue Tracing

An instance need that traces to a base defect is declared `blocked_by`, from
the instance issue to the base issue — never the reverse, and never as a
sub-issue.

**Direction is the whole rule.** `gh issue edit <instance-issue> --add-blocked-by
<https://github.com/PUC-Behring-AI/base-*/issues/N>` links the two. Verified
2026-09-12 against this organization: both directions round-trip correctly
through the REST API (`issue_dependencies_summary` counts the dependency,
`blockedBy`/`blocking` return the full cross-repo issue with its own
`repository_url`) — but GitHub's own documentation only shows same-repo
examples for this endpoint, and a community report describes a related bug
in a different reproduction path. Treat this as working today, not as a
documented guarantee. The fallback if it ever stops is a plain
`owner/repo#N` mention, which *is* documented and creates the same
cross-reference either way, just without the dependency count.

**Never a sub-issue for this.** A sub-issue is "part of the parent's
completion" — the wrong direction for an instance's issue against a base
engine, whose own completion must never depend on any one instance's need.
`--parent` decomposes a base epic into its own slices, same repository —
cross-repo sub-issues work too (also verified), but that is not what this is
for.

**Chained dependency is how "and so on" works.** `<prefix>-agents#N`
`blocked_by` `base-agents#M` `blocked_by` `base-platform#K`, one hop per
repository boundary actually crossed. Nothing new to build: it is the same
`blocked_by` edge, once per hop, and reading any issue in the chain shows
both what blocks it and what it blocks.

**The one thing this exposes across the boundary:** a base issue's own
sidebar will show `blocking: <prefix>-*#N` — metadata, visible only on that
issue's own page, never in a file the engine's code or docs carry. That is a
materially weaker exposure than a client name inside a document or a schema
(ADR-006), and is accepted here as the cost of the dependency count being
real rather than prose.

**A known tooling gap, not yet fixed.** The maintainer's `desbloqueadas.sh`
and `vizinhanca.sh` (outside this repository) print a blocker as `#N`
without naming its repository — ambiguous the moment a blocker crosses a
repository boundary, since `#14` read while working in an instance repo
could be misread as that repo's own issue. Fix by qualifying the number with
`repository_url` whenever it does not match the repository being read.

---

## Git Conventions

- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, …), in English.
- Never commit without an explicit request.
- **Ship through a pull request, never by pushing to the default branch** —
  including when you *can* bypass the gate. Being able to is not a reason to.
- Rebase. No merge commits, no squash: a merge commit breaks `git log --oneline`
  as a record, and a squash destroys the messages carrying the *why*.
- `--force-with-lease`, never `--force`.
- If the default branch breaks, revert first and fix afterwards.
- Run the local gate before opening the pull request, not after. A pull request
  opened without it turns CI into a discovery tool instead of a confirmation.
- **If a hook, guard or permission check refuses a command, stop and report it.**
  The escape hatch it names is for the human, not for the session. This is
  written here because it was violated on 2026-09-10, during the creation of
  these very repositories: two sessions hit a guard, used its escape hatch, and
  their repositories had to be deleted and rebuilt.
