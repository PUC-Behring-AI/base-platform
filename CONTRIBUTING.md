# Contributing

This is the shared procedure for every repository in the base — `base-platform`,
`base-knowledge`, `base-inference`, `base-agents`, `base-interface`, and any
`<prefix>-*` instance built on them. Each of the other four repositories
carries its own short `CONTRIBUTING.md` for what is only theirs, pointing back
here for the rest.

Nothing in this file depends on anything installed on a particular machine.
The gate is `scripts/gate.sh`, committed in the repository; it runs locally
and it runs again in CI, on the runner, so "the gate passed" is something
anyone can verify on the pull request itself rather than something the author
asserts.

## Opening an issue

The tracker is the project's memory. A conversation that produced a finding
and left it there loses it the moment the context window does.

Every issue is born self-sufficient. Whoever picks it up in a month will not
have had the conversation that produced it, so the body carries:

- **`file:line`** and the concrete scene — what someone using this repository
  runs into, not an abstract description of the code.
- **Why it matters.**
- **A checklist** for the fix, if it has more than one step.

`.github/ISSUE_TEMPLATE/issue.md` has the shape. Filling in `file:line` and the
scene is what makes an issue different from a `TODO` left in code — a comment
has no owner, no date, and appears in no list; an issue does.

### The `### Vizinhas` section

Every issue body ends with a `### Vizinhas` heading naming the issues it
collides with — in this repository or another one in the base. **"nenhuma" is
a valid answer.** What is not acceptable is silence: an issue that never asks
the question reads identically to one that asked and found nothing, and only
one of the two is honest.

Prefer the link GitHub carries natively over a bare mention in prose:

- `--parent NN` for a slice of an epic, in the same repository.
- `blocked_by` for an ordering dependency, same repository or across
  repositories — see below.

Both survive a body rewrite and show up in the issue sidebar; a mention in
prose does not.

### Cross-repository dependencies

An instance's need that traces to a defect in a base repository is declared
`blocked_by`, from the instance issue to the base issue — **never the
reverse, and never as a sub-issue.** A sub-issue means "part of the parent's
completion", which is the wrong direction here: a base engine's own
completion must never depend on any single instance's need.

    gh issue edit <instance-issue> --add-blocked-by \
      https://github.com/PUC-Behring-AI/base-*/issues/N

Chained dependency is how a need that crosses more than one boundary is
expressed: `<prefix>-agents#N` `blocked_by` `base-agents#M` `blocked_by`
`base-platform#K` — one hop per repository boundary actually crossed, each
one the same edge.

Writing the dependency only in prose ("Depends on #106") is invisible to
every tool that reads the graph — it does not reach the sidebar and does not
count toward `issue_dependencies_summary`. Declare it in the field.

## Opening a pull request

1. **Run `./scripts/gate.sh` before opening the PR, not after.** The CI runs
   the same script; opening a PR without running it locally first turns CI
   into a discovery tool instead of a confirmation, and costs a round trip.
2. Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, …), in English,
   explaining **why** the change exists and which alternative was discarded —
   not only what changed, which the diff already shows.
3. `Closes #NN` in the PR body whenever the work has an issue.
4. If the change touches a contract (`docs/CONTRACTS.md`, in `base-platform`
   only), it needs approval from every team the contract binds
   (`CODEOWNERS`), and it bumps `VERSION` plus a `CHANGELOG.md` entry marked
   `BREAKING`.
5. If the change touches the architecture, `docs/ARCHITECTURE.md` (or the
   repository's own architecture reference) is updated in the same PR — see
   `docs/AGENTS-base.md` §"Document Evolution Contract".

### Merging

- **Rebase. No merge commits, no squash.** A merge commit breaks
  `git log --oneline` as a record; a squash destroys the messages that carry
  the *why*.
- `--force-with-lease`, never `--force`, on your own branch.
- If the default branch breaks, revert first and fix afterwards — fixing
  forward on a red default branch leaves the project with no known-good
  version for as long as the fix takes.
- If the gate refuses locally, or the CI fails, the fix is to make the check
  pass — not to route around it.

### A known gap in what this procedure can enforce today

GitHub's branch protection and rulesets require a paid plan on a private
repository (verified 2026-09-14: `base-knowledge`, `base-agents`,
`base-interface` all return HTTP 403 on both endpoints; only `base-inference`,
public, accepts them). Until the organisation is on a plan that lifts that
limit, or a repository is public:

- **The CI runs and reports on every pull request, but is not a required
  check** on the four private repositories — it can be merged around. It is
  not silent, though: a red check on the PR page is a fact anyone reviewing
  can see, which is already stronger than the hook it replaces, whose failure
  was invisible to everyone but the machine it ran on.
- **`CODEOWNERS`, in `base-platform`, is inert for the same reason** — GitHub
  also forbids a PR author from approving their own PR, and every one of the
  five layer teams has exactly one member today (the organisation owner), so
  requiring review would deadlock every PR. Turn on required review once a
  team has a second member who is not also the one opening the PR.
- **`allow_auto_merge` and `delete_branch_on_merge` are both `false`, and
  `allow_merge_commit`/`allow_squash_merge` are both `true`**, on all five
  repositories — the opposite of the rebase-only rule above. Nothing in this
  repository can change that; it is a setting on each GitHub repository,
  changed under **Settings → General → Pull Requests**, and it is the
  organisation owner's call to make, not a session's.

Nothing above is worked around with local configuration. If it needs fixing,
it gets fixed at the account level, by whoever owns the organisation, and this
file is where that person finds out what to change and why.
