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
in the base. **And no central registry exists** — an instance documents itself,
in its own `<prefix>-platform` README, which is private and sits with the
instance.

**Alternative discarded, twice.** First, a prefix table in the base, since an
opaque contract code needs decoding somewhere. Then, when that was removed, the
same table on the organisation's profile page.

**What each would have cost — and the second one was not hypothetical.** A base
holding a registry of who uses it has become a component of its largest
consumer; the concrete failure is that the next project inherits the first
one's vocabulary in every example and every default, and nobody notices,
because by then it reads as the way things are named here.

Moving the table to the organisation profile looked like the fix and was worse.
That page is **public**. It turned an internal architecture note into a product
announcement for a platform that is not one, and it published a client's
contract number and project description to anyone who visited. The page was
live for about two hours before it was taken down; the repository holding it
was deleted.

**Consequences.** Examples in base documentation use `<prefix>` and are less
vivid than a real one would be. Someone encountering an instance prefix opens
that instance's `platform` repository to decode it — and someone without access
to that repository does not get an answer, which is the correct outcome rather
than a gap.

**The generalisation, which is the expensive part of this record:** the
question "where should this list live?" kept producing answers, and the right
answer was that the list should not exist. A registry is a thing to maintain,
a thing to leak, and a thing that has to sit somewhere with a visibility of its
own. Self-documenting artefacts have none of those properties.

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

---

## ADR-009: Provenance is not observability, and they do not share a store

**Context.** Version 0.1.0 had one contract for "telemetry: traces and metrics",
landing in one place. Under that wording, a store recording model prompts and
completions sat beside a store recording request counts, and both were treated
as operational infrastructure.

That is a leak path, and it is invisible from every side. If a request carried
data classified as confidential, the trace store now holds that text — outside
the sensitivity taxonomy, outside the key policy, and readable by anyone with
operations access. Nothing in the architecture flags it, because the record was
filed as a metric.

It is also a loss in the other direction. An audit trail is a **product
requirement** in any deployment that must explain its outputs. Filing it as
operational telemetry gives it the retention of a metric — days, aggregated —
when what is needed is per-record and permanent.

**Decision.** Two contracts, split by one question: *does the record contain
payload?*

- **No** → metric. C4, to `platform`. Aggregated, disposable, readable by
  whoever operates the system.
- **Yes** → provenance. C6, to `knowledge`. Carries a classification assigned
  the same way C1 assigns one, stored under the same key policy as the data it
  describes, append-only, correlated across layers by a request identifier.

Emission stays with each layer in both cases. Only the destination is shared.

**Alternative discarded.** A sixth layer owning both, on the argument that the
provenance store is the one place containing everything and its access control
should belong to no single layer.

**What that would have cost.** It is the right shape eventually, and it is
premature now: a sixth layer before the fifth one works, which is exactly what
ADR-004's rule against early extension points warns about. The argument that
justifies it — the store's access control differs from every layer's — is
answered for now by the classification travelling with the record. When that
stops being enough, the contract is already the boundary, so moving the store
is a deployment change rather than a redesign.

**Consequences.** `knowledge` now has two write profiles that look nothing alike:
batch ingestion of source material, and a per-request append on the hot path.
That is a real operational tension and it is accepted knowingly. `platform`
gains infrastructure it runs but must never read payload from — its own
"does not own" line says so.

---

## ADR-010: Identity is a contract, because without one it becomes a raw SQL write

**Context.** Provisioning a person crosses two layers: a credential with a
budget in the serving layer, an account with model grants in the interface
layer. No contract covered it.

The first implementation did it anyway. It entered a container by fixed name
and ran `sqlite3` against the interface's private database, inserting and
deleting rows in its access-grant table directly. Six hundred lines of shell
doing surgery on a neighbour's storage — and no contract could be violated,
because none existed.

**Decision.** C5. The serving layer exposes issuing, inspecting and revoking a
credential; the interface layer exposes creating, inspecting and removing an
account and granting model access. `platform` orchestrates the two calls and
owns the rollback when the second fails after the first succeeded.

**No layer writes into another layer's storage.** Not through a database file,
not through a container name, not "just for provisioning".

**Alternative discarded.** Keep it as an operations script that reaches into
both, moved into `platform` so at least it lives where it crosses.

**What that would have cost.** Relocating the violation is not fixing it. The
script would still depend on a container name, a file path and a table schema
that the interface layer is free to change without telling anyone — and the day
it changes, provisioning breaks with a stack trace pointing at the wrong
repository.

**Consequences.** A layer that cannot be provisioned through its own API is
now, by this contract, a layer with an incomplete API — a defect in that layer
rather than a licence to go around it. Where the interface is a third-party
product without such an API, the interface layer either wraps it or replaces
it, and that cost is visible instead of hidden in a shell script.

---

## ADR-011: Instance code enters an engine through one socket, under the confidentiality clause

**Context.** ADR-005 says an instance carries code, not only configuration.
Most of that code runs in the instance's own repository. Some of it cannot: a
connector that ingests the instance's sources, or a search over tables only the
instance defines, has to run inside the knowledge engine, behind C1. Today the
only way in is a pull request to the engine — which puts the instance's domain,
and often its client's methodology, into the base.

ADR-004 forbids opening an extension point before two instances ask for it,
**unless what the first one needs cannot live in the base for confidentiality
reasons.**

**Decision.** One code socket per layer that needs it, opened under that second
clause: an installed Python package, discovered through the entry-point group
`base_<layer>.modules`, loaded only when the instance manifest lists it.
`knowledge` first; `agents` through the same group when its flows need it.
`inference` and `interface` take configuration only. (ADR-013 narrows this: `interface` takes instance code through a build-time directory. `inference` stays configuration-only.)

What the socket guarantees is in `ADAPTATION.md` §4: the engine, not the
module, sets every classification, and a container running instance code
reaches only internal services.

**Alternative discarded.** A module as a separate service behind an internal
API, one container per module.

**What that would have cost.** The classification would then be applied on the
far side of a network hop, by whichever process answered — the guarantee would
move from "the engine's code path" to "every module's deployment". And every
module would be one more image to build, pin and publish, on a plan that has
nowhere to publish them yet.

**Consequences.** An instance image exists for every layer that accepts
modules: the base image plus the instance's installed packages. A module runs
with the engine's privileges, so its egress, not its good behaviour, is what
keeps it from calling a model around C2. And the first instance no longer pays
the "open an extension point first" price for code — it pays it once, here.

---

## ADR-012: The knowledge layer may call an embedding model, over C7 only

**Context.** ADR-001 placed the routing decision in `agents` partly because
"the knowledge layer does not call models at all". A real evidence store breaks
that sentence. It needs a vector for every passage it indexes and for every
query it searches with, and the model that produces them has to run somewhere.

**Decision.** `knowledge` calls exactly one kind of model, an embedding model,
served by `inference`, through one contract, C7. The credential is issued
through C5 with `purpose: "embed"`. It is always `local-only`, and it is
confined to the embedding models and to the embeddings route. ADR-001's
sentence narrows to "the knowledge layer calls no generative model". Its
argument is unchanged: `knowledge` still makes no routing decision, because an
embedding call routes nothing — its credential is fixed, not chosen per
request.

**Alternative discarded.** Embed in-process, inside the knowledge container,
with a model bundled into the image.

**What that would have cost.** A second serving stack, inside the one layer
built to hold no models: its own GPU or CPU sizing, its own model pinning, its
own weights download. And it would sit in a container that runs instance code
(ADR-011), so the network rule keeping that code from reaching a provider
would have to allow a model runtime next to it. Every instance would also pick
its embedding model in a different place from every other model it serves.

**Consequences.** `knowledge` gains one outbound arrow, to `inference`, and
`inference` gains a second kind of caller. Both are on the contract, and both
are narrower than C2: one route, one key family, one model kind. An index's
vectors belong to one model, so changing the embedding model is a re-embedding
job, not a configuration flip.


---

## ADR-013: The interface carries instance code: a frontend shell, and a backend-for-frontend as its one arrow

**Context.** ADR-011 said `interface` takes configuration only. The engine
would render an instance's `forms/*.schema.json`, and `views/` would order
them. The first instance's screens are not forms:

- a long model pass that the person follows step by step;
- a list ranked by a model, which the person can reorder;
- a clickable chart and a knowledge chart per category;
- a per-question screen where the person answers, accepts or dismisses a model
  proposal, and attaches evidence;
- a report built from live state.

None of these is a JSON Schema form. All of them are the instance's
confidential methodology made visible, so under ADR-004 they cannot live in
the engine either.

**Decision.** The interface engine is two parts, and the instance adds code to
the first.

- **A frontend shell (React)**: session handling, layout and navigation, a C3
  client that stamps the request identifier, and theme tokens. The instance
  supplies `src/instance/`, which holds its routes, navigation entries and
  theme. A multi-stage build `FROM base-interface:<pinned tag>` joins the shell
  and the instance code. The gate's existing pin check covers that `FROM` line
  (§7 of ADAPTATION.md), and no package registry is needed. (ADR-014
  amends this: `src/instance/` is a socket that composes screens from module
  packages, and holds none of its own.)
- **A backend-for-frontend (BFF)**: the engine's existing Python service, grown.
  It serves the built assets, owns login and the session, generates the request
  identifier (C6), and forwards product calls to `agents` over C3. It is the
  only process in the layer with a route out. It sits on a network whose only
  other member is `agents`. The browser reaches its own origin and nothing
  else.

Components that look generic start in the instance and move to the engine only
when a second instance asks for them (ADR-004). Examples are a proposal card
with accept and dismiss, a citation list, and an audit view.

ADR-011's sentence narrows to "`inference` takes configuration only". The
entry-point socket stays Python-only. The interface socket is a build-time
directory, not an entry point, because a browser bundle is not an installed
package.

**Alternative discarded.** Keep the interface configuration-only. Either the
screens are squeezed into schema-driven forms, or they are built as a separate
frontend outside the layer.

**What that would have cost.** Forms would lose most of the screens. Charts,
ranking and the evidence workflow have no schema form. A frontend outside the
layer is worse. It would be a second application that the one-arrow rule
(ADR-003) does not see, and the first thing it would need is a direct read from
`knowledge`, "just for this screen".

**Consequences.** ADR-003 is enforced by the network instead of by review: the
BFF is the one arrow, and its network reaches only `agents`. The engine gains a
TypeScript codebase, and the gate must check it. An interface instance gets an
image of its own, built the way ADAPTATION §4 builds a layer with modules. The
engine's earlier chat UI, which called the model gateway directly, has no place
in this shape and leaves the layer. C5's interface half then holds no model
credential.

---

## ADR-014: An instance is a set of sockets; team code enters as modules

**Context.** ADR-004 and ADR-005 say an instance repository carries the
instance's code, and ADR-013 says the interface instance supplies
`src/instance/`, which holds its screens. Read literally, every screen, flow and
rule an instance needs is written inside its `<prefix>-<layer>` repositories.
That breaks as soon as more than one team builds for an instance:

- a team that develops a methodology library, or a set of screens, has to work
  inside the instance's repositories and run the instance's infrastructure to
  see its own work;
- a second product for the same layer, a conversational screen next to a form
  workflow say, has nowhere to go but into the first one's code;
- a team's code written there names the instance, its client and its
  infrastructure, so it can never run, or be reviewed, without them.

One layer already works the other way: a team develops a library in its own
repository, runs it alone, and the instance's knowledge repository only plugs
it into the engine through `base_knowledge.modules` (ADR-011). That is the
shape this record generalises.

**Decision.** Three levels, each in its own repositories.

- **Base** (`base-*`): the engines, reusable by any instance, consumed by tag.
  The base never knows an instance exists (ADR-006).
- **Sockets**: an instance's `<prefix>-<layer>` repositories. A socket receives
  its layer's modules and plugs them into the engine. It holds what is the
  instance's alone and no team's product: the configuration (ADAPTATION §4),
  the brand and theme, the list of modules it plugs, the adapter that maps each
  module onto the base's contracts, the image, and the tests that the plugged
  whole works. ADR-011 calls an engine's entry point for code its socket; the
  instance repository is the other half of that joint.
- **Modules**: what a team develops, in that team's own repository, plugged
  into a socket. A module:
  - runs standalone for its team, with no base, no login and no instance
    repository beside it; plugged mode is a second mode the socket turns on;
  - never names the instance, its client, its contract or its infrastructure;
    what is the client's (brand, logo, product name) stays in the socket;
  - depends on no base package: its types, errors and port are its own, in its
    own terms, and the socket maps them onto the contracts;
  - is consumed at its team's `main`, not by tag. The socket records the
    commit in each image it builds, and tests against `main` on a schedule,
    opening an issue in the socket when `main` breaks it;
  - changes only by pull request in the module's repository, reviewed and
    merged by its team.

How a module plugs in, per layer:

| Layer | Plug |
|---|---|
| `knowledge`, `agents` | an installed Python package, discovered through `base_<layer>.modules` (ADR-011). The engine stamps every classification; a module never classifies |
| `interface` | UI packages composed by the instance's `src/instance/`: the socket maps each module's routes and navigation into `defineInstance`, through lazy imports only; one copy of React, by deduplication; the theme stays the socket's; the socket supplies the calls the module makes over C3 |
| `inference` | none today: configuration only, because code inside the gateway could bypass the policy it enforces. Accepting modules in this layer is open, and needs its own record that keeps the policy out of a module's reach |
| `platform` | none: the socket is the instance's decision record, its contract payloads and its base pin |

This amends ADR-013's "the instance supplies `src/instance/`, which holds its
routes, navigation entries and theme". The instance still supplies
`src/instance/`, but as a socket: it composes screens that come from module
packages and holds no screens of its own. It also narrows ADR-005's
"instance repositories carry real software": the software a team develops is a
module; what stays in the socket is the code that binds modules to the base.

**Alternative discarded.** Keep every team's code in the instance's
repositories, one directory per team, as ADR-013 read literally.

**What that would have cost.** Each team would need the instance's
infrastructure, credentials and base checkouts to run its own work, so the
people who know the domain would be the slowest to change it. A second product
in a layer would share a codebase with the first. And the code would name the
instance throughout, so the day a team wanted to reuse its work for another
client, the first client's vocabulary would come with it — the failure ADR-006
exists to prevent, one level down.

**Consequences.**

- An instance has two kinds of dependency, with two rules: the base by tag
  (`<prefix>-platform/base-version.yaml`), each module at `main` with the
  commit recorded. A module's `main` can break a socket between two of the
  socket's own changes; the scheduled test is what finds it.
- A module repository is not a member of the base or of an instance. It has no
  `# Base:` line and no harmony run. It keeps its own tests, and its own check
  that no instance term appears in it.
- A socket that plugs a private module reads it in CI with a read-only key of
  its own, as harmony reads private siblings (ADAPTATION §3).
- No engine change was needed: `base_<layer>.modules` and `defineInstance`
  already accept code from another package. `ADAPTATION.md` §4 says how.

---

## ADR-015: A knowledge module may mount its own routes, outside C1, until C8

**Context.** C1 is the one way evidence leaves the knowledge layer, and every
passage it returns carries a classification stamped by the engine (ADR-012,
ADR-014). A module sometimes has to offer the agents layer something that is not
a passage: a computation, a lookup, an operation over its own data. There is no
contract for that yet.

**Decision.** A knowledge module may define an optional `routes()` method that
returns an ASGI application. The engine mounts it at `/v1/modules/<name>` after
the instance loads. The engine requires a uuid `X-Request-Id` on every call
under that prefix, with the same refusal as C1, and carries it into the C7
context so the module's embedding calls are attributed to the request. A module
without `routes()` is unchanged.

These routes are **outside C1's classification stamp**: the engine does not
classify what they return, and the module answers for it. They are reachable
only inside the deployment, by the network rules that already exist and that
this decision does not change: from the agents layer and the knowledge
namespace's own pods (Kubernetes), or from any service on the shared internal
network (compose). The mechanism is **transitional**: it is replaced by a
contract, C8 (base-knowledge#40), and a module's routes move onto it then.

**Alternative discarded.** Stamp every response of a module's routes. The engine
cannot: it does not know the shape of what a module returns, and a stamp it
invented would claim a classification nobody decided.

**What that would have cost.** Either a stamp that looks like a guarantee and is
not, or a module forced to disguise its output as passages. The first is a
security claim without a check behind it; the second pushes the module into
contortions that hide what it does.

**Consequences.**

- The prefix is a new surface on the knowledge layer. Its reach is whatever the
  deployment's network rules admit to the knowledge service; narrowing it to the
  agents layer alone would be a network-policy change, not an engine feature.
- Whatever a module returns here is outside the confidentiality guarantee C1
  gives. An instance that plugs such a module accepts that until C8 lands.
- Not `BREAKING`: no contract changes, and a module that does not use it is
  untouched.
