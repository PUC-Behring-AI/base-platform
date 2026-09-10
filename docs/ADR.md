# ADR — Architecture Decision Records

Why the base is shaped the way it is. Each record states the decision, the
alternative discarded, and what that alternative would have cost.

**These records name no client, no contract and no instance.** The decisions
below were first driven by a real engagement, and the full reasoning — with the
contract clauses that motivated it — lives with that instance, not here. What
survives in this repository is the part that generalises. Where a decision only
made sense for one project, it is not in this file, and it is not in the base.

Format: Context · Decision · Alternative discarded · Consequences.

---

## ADR-001: Five layers, and the fourth one is the point

**Context.** The obvious decomposition of an AI platform has three parts: where
data lives, where models run, and what the user sees. Every version of this
architecture started there.

That decomposition has a hole. Something has to decide **which model a given
request may reach** — and when some of the data is more sensitive than the rest,
that decision is a security control, not a routing detail. It belongs to none of
the three: the interface would be choosing on behalf of data it cannot classify;
the serving layer would need to know how sensitive a payload is, which is the
knowledge layer's information; the knowledge layer does not call models at all.

**Decision.** A fourth layer, `agents`, sitting between interface and the other
two. It owns orchestration, guardrails, the routing decision and the audit
trail. A fifth, `platform`, owns the contracts between all of them.

**Alternative discarded.** Distribute it — let each layer expose its own agents.

**What that would have cost.** The routing decision would exist in three
repositories. Three places to get right, three places to change together, and
no single test that covers the rule, because no layer tests its neighbour's
boundary. The first divergence would be silent.

**Consequences.** Five repositories per deployment rather than three. One more
network hop. In exchange, the question "who decides which model sees this?" has
exactly one answer, and it is testable in one place.

---

## ADR-002: The routing rule is decided in one layer and enforced in another

**Context.** Some data must never reach a third-party model provider. A rule
like that, implemented once, is an `if` statement in code that several teams
edit — and it fails silently, because the failure looks like a successful
request.

**Decision.** Split it. `agents` **decides**, choosing between credentials
scoped to different model sets. `inference` **enforces**, serving only what the
presented credential permits, and never validating the caller's reasoning.

The enforcement mechanism is the gateway's existing per-model key policy: two
families of virtual key, one reaching only locally served models, one reaching
external providers.

**Alternative discarded.** Enforce it once, in the layer that decides.

**What that would have cost.** The guarantee would rest on application code
being correct. With the split, a defect in the deciding layer cannot leak: the
credential carrying that request has no permission to leave the network.

**Consequences.** Two places implement one rule, which normally is a smell. It
is justified here because the second place is a policy rather than a branch, and
because it can be tested with no application running at all. The instance
declares which sensitivity classes exist and which key policy each one gets; it
does not get to declare whether the policy is enforced.

---

## ADR-003: The interface has exactly one outbound arrow

**Context.** Auditing "where could sensitive data reach someone who should not
see it?" is only tractable if the set of paths out of the user-facing layer is
small and known.

**Decision.** The interface talks to `agents` and to nothing else. No exception
for a single screen, for autocomplete, or for development.

**Alternative discarded.** Allow the interface to read directly from the
knowledge layer for cases where going through `agents` is disproportionate.

**What that would have cost.** The exception is always reasonable at the moment
it is requested — one field, one screen, one sprint. It is the *count* of arrows
that carries the audit argument, and a count of two is not meaningfully better
than a count of five.

**Consequences.** When a screen needs data the contract does not carry, the fix
is a contract change with two approvals, not two lines of code. This is
inconvenient by design, and it is the most likely rule in this repository to be
broken for a good local reason.

---

## ADR-004: Base and instance are repository pairs, consumed by version

**Context.** The five engines are reusable. What runs on them — ontologies,
flows, forms, scoring rules — is not. Those two things change at different rates
and are often owned by different parties.

**Decision.** Each layer is two repositories: the engine in the base, the
instance content in `<prefix>-<layer>`. The instance depends on the engine by
version and never forks it.

**Alternative discarded.** Template repositories — "Use this template", one copy
per instance, each free to diverge.

**What that would have cost.** Divergence would be permanent and unmeasurable.
On the first security fix in an engine, every instance created before it would
be behind, and nothing would say which ones — a copy does not record where it
came from.

**Consequences.** Twice the repositories. And a real cost paid by the *first*
instance: whenever it needs something an engine cannot express, the path is
"open an extension point, version it, then use it", not "write it here". That
is the price of the base, and it is charged entirely to the project with a
deadline.

The rule that contains it: **an engine gains an extension point only when two
instances ask for the same thing, or when the first asks for something that
cannot live in the base for confidentiality reasons.** Until then the instance
writes its own code. An engine generalised from a single case stiffens what was
hard and abstracts what was easy.

---

## ADR-005: The boundary is reuse, not code versus configuration

**Context.** "Engine plus configuration" is the natural way to read ADR-004, and
it is wrong in a way that costs weeks: it suggests an instance is a set of YAML
files.

**Decision.** The test is one question — *does it serve more than one instance?*
If yes, it belongs to the engine. If no, it belongs to the instance, whether it
is an ontology file or two thousand lines of code.

**Alternative discarded.** Define the instance as purely declarative, and push
everything executable into engines.

**What that would have cost.** Every domain with a calculation of its own —
scoring, validation, methodology rules — would either be squeezed into a
configuration language that cannot express it, or would force a
domain-specific extension point into an engine that must stay agnostic. Both
outcomes are worse than letting the instance hold code.

**Consequences.** Instance repositories carry real software, with their own
tests. The declarative extension points listed in `ADAPTATION.md` are the
*declarative half* of adaptation, not the whole of it.

---

## ADR-006: The base names no project

**Context.** The first version of every document in this repository named the
instance that motivated it — in the prefix table, in the diagrams, in the
examples, and in the very rule that forbade doing so.

**Decision.** No client, contract, methodology or instance name appears anywhere
in the base. The registry that decodes an instance prefix lives in the
organisation profile, which belongs to the organisation rather than to the base.

**Alternative discarded.** Keep a prefix table in the base, since an opaque
contract code needs decoding somewhere.

**What that would have cost.** A base holding a registry of who uses it has
become a component of its largest consumer. The concrete failure is not the
table itself: it is that the next project inherits the first one's vocabulary
in every example, every diagram and every default — and nobody notices, because
by then it reads as the way things are named here.

**Consequences.** Examples in base documentation use `<prefix>` and are
therefore less vivid than a real one would be. Someone encountering an instance
prefix in the wild must look it up in the organisation profile rather than here.

---

## ADR-007: One version for the whole base

**Context.** An instance needs to say which base it runs on, and needs to learn
when a newer one exists.

**Decision.** The base has a single version in `base-platform/VERSION`. All five
repositories are tagged together on it. An instance pins that one number.

**Alternative discarded.** A semantic version per layer, with the instance
pinning five.

**What that would have cost.** Five numbers nobody reconciles, and the loss of
the only question that matters at deploy time: *was this combination released
together?* Per-layer versions are more precise about what changed and silent
about whether the set was ever tested as a set.

**Consequences.** A fix in one engine bumps the version of all five, and an
instance that wants only that fix takes the rest with it. Accepted: the release
train is weekly and the set is small.

---

## ADR-008: Grouping through organisation custom properties

**Context.** GitHub has no folders or subgroups for repositories. Ten
repositories belonging to one architecture look, in the repository list, exactly
like ten unrelated ones.

**Decision.** Two organisation-level custom properties, `layer` and `role`,
applied to every repository in the architecture. They make the list filterable:
one query for the base, one for a layer across instances.

**Alternative discarded.** Topics, or a separate organisation.

**What that would have cost.** Topics are free-text and anyone can edit them,
so they drift and cannot be trusted as a filter. A separate organisation gives
real isolation, but splits members and settings across two places before there
is any reason to — and it remains available later, at the cost of moving
repositories rather than redesigning anything.

**Consequences.** A repository created without its properties is invisible to
every filter, and nothing warns about it. Setting them is a step in
`ADAPTATION.md`, and until the shared gate exists, nothing enforces it.
