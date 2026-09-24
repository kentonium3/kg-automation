---
title: "Second Brain Graph Layer — Design"
doc_type: design
status: draft
owners: ["@kentonium3"]
last_updated: '2026-09-24'
audience: agents_and_humans
---

# Second Brain Graph Layer — Design Document

**Status:** Draft
**Author:** Kent Gale
**Location:** `docs/design/second-brain-graph-layer.md`
**Related Epic:** [#692](https://github.com/kentonium3/kg-automation/issues/692)

---

## Problem Statement

Felix's current second-brain approach processes flat Markdown on each query: full re-read → chunk → embed → retrieve. This produces no persistent graph of relationships, no temporal tracking of how priorities and commitments evolve, and no structural enforcement that planned work connects to stated purposes and outcomes. The result is a system that can retrieve content but cannot reason about it — particularly for priority trade-offs, conflict detection, and life-coaching against defined outcomes.

The goal of this layer is to give Felix (and a dedicated life-coach agent) the ability to:

- Traverse any task or project upward to the purpose it serves
- Detect scheduling conflicts and capacity overruns before they happen
- Track how goals, priorities, and decisions evolve over time
- Surface explicit trade-off questions: "You said you want A by [date]. E doesn't fit this week without displacing B. Postpone or trade off?"
- Record decisions durably so future reasoning can reference past choices

---

## Vocabulary & role in the program (#833)

This layer is not an enrichment bolted onto the task tracker. In the #833 program frame
it is the **cognitive substrate** — Felix's model of Kent's world — and the EA
intelligence (router, escalation, coaching, agentic action) is built *on top of it*.
Vikunja, calendar, email, and drive are **I/O adapters**: how the substrate senses and
acts. They are peripheral tracking surfaces, in principle interchangeable; the substrate
is not. The real power is the **reasoning functions over the temporal dimension** —
conflict prediction before it happens, trade-off surfacing, decision memory ("you've
deferred this 4× since March"). Task CRUD is plumbing.

### Named things

| Term | What it is | Metaphor |
|---|---|---|
| **Life Lattice** (short: **Lattice**) | The structured, vectorized, **temporal** graph — the P→O→P→T hierarchy + Commitments + Principles + ingested content, woven with Graphiti's bi-temporal edges. Structured to *predetermined patterns* (the ontology). Authoritative and canon-like. | **Canon** |
| **Second brain** | Kent's curated Obsidian vault — a categorized corpus of narrative knowledge. Structured, but general-purpose reference, not pattern-conformant. | **Data warehouse** / reference pool |
| **Episode** | One unit of raw, unstructured lived input — a capture, note, message, event, or decision — before it is woven into structure. Graphiti's native ingest primitive (`add_episode`). | **Data lake** |
| **Membrane** | The selective admit/promote gate an episode crosses to become structure (the EA-brief promotion gate: `propose → human-approve → structure grows`). | Cell membrane |

The name **Life Lattice** is deliberate: it binds the **why** (Purpose), the **what**
(Outcome→Project→Task), and the **when** (temporal edges) into one queryable whole — the
connection goal apps, task trackers, and calendars each hold only a third of.

### Open membrane-topology question

When an episode arrives already **lattice-shaped** (e.g. *"add these three tasks to this
project, due end of week"*), must it first be recorded in the second brain (warehouse)
before being woven into the Lattice (canon), or can it flow **directly** to the Lattice?
I.e. does the second brain and the Lattice share one membrane, or does each have its own?
This is a real ingest-topology decision for the vault-ingest work (#696) and is called out
in Open Questions below; it is **not** yet decided.

---

## Tool Selection

### Graphiti (by Zep AI)

Graphiti is the selected graph engine. It is an open-source, temporally-aware knowledge graph framework backed by Neo4j or FalkorDB.

**Why Graphiti over LightRAG:**

LightRAG is optimized for static or slowly-evolving document corpora — strong at answering "what does my knowledge base say about X" but architecturally unable to track fact validity over time. It merges time-specific facts under a single entity node without explicit temporal separation. It cannot natively answer "what were my active goals in March" or "which Outcome did I deprioritize and when."

Graphiti implements a **bi-temporal model**: every graph edge carries explicit validity intervals (`valid_from`, `valid_until`). When a fact changes, the old relationship is invalidated — not deleted. The full history is preserved and queryable at any point in time. This is not a nice-to-have for a life-management second brain; it is the core requirement.

> **Scope caveat (measured, 2026-09-15, #974):** the bi-temporal model versions
> **relationships only**. Node *attributes* (e.g. `Task.scheduled_date`) are overwritten
> in place with no history. History for state changes therefore comes from the episode
> log, not from attribute versioning — see the *state vs history representation rule*
> under §Edge attribute models & wiring.

Additional selection factors:

- Native Anthropic API support (alongside OpenAI, Gemini, Groq)
- Built-in MCP server — directly connectable to Claude and OpenClaw without a custom integration layer
- Custom entity types via Pydantic models — domain-specific ontology without schema migrations
- Hybrid retrieval: vector similarity + BM25 full-text + graph traversal in a single query
- Apache 2.0 license; Zep Cloud not required
- FalkorDB backend (default for MCP server) is lightweight enough for office2

### Inference seam (per function, never global)

"Native Anthropic API support" above is a capability of Graphiti, not a decision of this
design. The layer has **four distinct inference functions** — structured writes, extraction,
embedding/reranking, and reasoning — and #974 measured them at three different cost/quality
points in one run: structured adapter writes need **no model** ($0, exact); extraction ran
**locally** on office4 (Qwen3-Next-80B, llama.cpp Vulkan) at $0 marginal; #844's reasoning
ran on the **Anthropic API**. So provider, model, and location are a **per-function
configuration seam** (RFC #986), placed per ADR-0009 (large-context inference is office4,
best-effort, behind a fallback; office2 cannot host it). Nothing in this document hardcodes a
provider; where a section names one (#844/#974 postures), it records what was measured, not
what is required. Graphiti's own `LLMClient` / `EmbedderClient` / `CrossEncoderClient`
abstractions are the natural attachment points for that seam.

### Backend: FalkorDB

FalkorDB is preferred over Neo4j for this deployment:

- Significantly lighter resource footprint (Redis module vs. JVM process)
- Default backend for the Graphiti MCP server Docker Compose setup
- office2 (32GB RAM, GTX 1060) handles it comfortably alongside existing services
- Single `docker compose up` deployment

---

## Ontology Design

### Guiding Principles

1. **Fixed semantic tiers, arbitrary depth within Project and Task.** Semantic tier identity matters because the life-coach agent applies different reasoning at each level — a Purpose is definitional, a Task is schedulable, and conflating them breaks the reasoning model.

2. **Every node must connect upward to a Purpose.** No floating tasks. No projects without an Objective. This structural rule is the enforcement mechanism for explicit prioritization.
   *Standing-practice exception (2026-09-24, from #849 Arc F; ratified by Kent the same day).* A recurring Task that exists only to **enact a Principle** — a morning meditation, a journaling habit — is a *standing practice*, not work toward an Outcome: it has no finish line and no measure, and minting an Outcome for it would fabricate a target rate the coaching loop is supposed to *infer* from its trajectory. Such a Task anchors to its Principle through the static `EMBODIES` edge instead of to an Outcome, and reaches Purpose/Domain through that Principle's `SCOPED_TO` scope (or the global default). Nothing floats: the anchor is a Principle rather than a Purpose. Practices are discovered from the Principle side ("am I keeping my non-negotiables?"), and their health is the slope of their episode log, never a seeded threshold.

3. **Project and Task are self-similar.** Both support arbitrary nesting depth via `CONTAINS` edges. A Project can contain sub-Projects and Tasks. A Task can contain sub-Tasks. The boundary: Projects have scope and deliverables; Tasks have a single actor and a single action.

4. **Many-to-many is allowed upward.** A single Outcome can serve multiple Purposes. A single Objective can be advanced by multiple Projects. This reflects reality — work often serves more than one master — while keeping the hierarchy structurally enforced.

5. **Decisions are first-class nodes.** Every trade-off conversation that reaches a resolution is ingested as an episode, from which a **Decision entity** is extracted; the Decision carries durable `DECIDED` (and `GOVERNED_BY`) edges to the nodes it bears on, and the source episode remains linked to it via Graphiti's built-in `MENTIONS` edge. Future conflicts can be checked against past decisions.

6. **Principles are a first-class, cross-cutting constraint axis** (Kent, 2026-07-20). Where the Purpose→…→Task hierarchy *directs* decisions (what/why you pursue), **Principles *constrain*** them (how you decide — the values, standards, and non-negotiables the boss will or won't accept). A Principle is definitional-tier (slow-changing, like Purpose) and cross-cutting (not in the hierarchy, like Commitment). It is seeded explicitly and is the least-duplicable element in the system — the deepest moat. See [`executive-assistant-architecture.md`](executive-assistant-architecture.md) §6 for the EA framing that motivated adding this type.

---

### Tier Definitions

#### PURPOSE
The "why I exist / what I'm for" level. Immutable or near-immutable. Changes represent life events, not planning events. No due date. No status in the task sense.

A Purpose is **not** the purpose *of* a particular Outcome — it is the purpose *from which*
Outcomes are derived, and it sits above Outcome in the chain (Kent, 2026-09-16). A Purpose
statement can read like an ambitious Outcome statement; the tiers are told apart by shape,
not by tone:

| | date | measure of done | status | 
|---|---|---|---|
| **Purpose** | none | none | none |
| **Outcome** | required | required | tracked |
| **Domain** | never | never | none (it is a container) |

*Examples:* "I wish to be financially independent so that I have the freedom to do what I
want with my time and so I can financially support causes I believe in," "to be a great
father to my children," "Build wealth through AI-leveraged operations as a solo operator"

> **Why this matters operationally (#974):** on ambiguous episode text, LLM extraction typed
> 2 of 3 Purposes as Domains. Seeding and any adapter-rendered text must make the shape
> explicit — state a Purpose with no date and no measure — or the tier collapses on ingest.

#### DOMAIN
A persistent life area that groups Outcomes. Not time-bounded. Serves as a routing and grouping layer — prevents all Outcomes from hanging directly off Purpose nodes and gives the life-coach agent a natural partition for capacity reasoning.

**Domains carry no edge to Purpose — by design (2026-09-15, #974).** Domain is the
*where* axis; Purpose is the *why* axis; the why-chain is single-sourced through
Outcomes (`Outcome -SERVES-> Purpose`). A Domain's purpose-affinity is **derived** —
the Purposes served by the Outcomes that `BELONGS_TO` it — never asserted, because
Domains genuinely span Purposes and an asserted edge could disagree with the
Outcome-level truth. An empty or ambiguous derivation is a coaching signal, not a
modeling gap. Seed data and extraction wording must not assert Domain→Purpose
relations; the post-extraction validator rejects them as unregistered pairs.

**Kent's operating contexts are Domains (2026-09-18, from the #849 four-contexts note).** The
four parallel surfaces Kent works across — personal, Intentional, spec-kitty, PointerHealth —
each with its own calendar and mail system, are modelled as Domains on the *work* side: an
Outcome `BELONGS_TO` the context it lives in. The **account or system a message arrived
through** is *episode provenance* (the episode's `source_description`), not a node — the same
person can reach Kent through several of them, which is what the `Person.aliases` list
absorbs. `Capacity` with no `CONSTRAINS` edge is global, so it is the one resource all four
contexts contend for; a **cross-context collision** (#849 Arc A) is therefore a
Domain-partitioned read against a single Capacity, and needs no new entity type.

*Examples:* Intentional LLC, Physical Conditioning, Business Acquisition, Felix/Second Brain

#### OUTCOME
A concrete, time-bounded end state that serves one or more Purposes. Measurable: you either achieved it or didn't, by a specific date. The primary unit of life-level planning.

*Examples:* "Intentional LLC generating $X/month by Dec 2026," "Reach [physical benchmark] by Q3 2026"

#### OBJECTIVE
An intermediate result required to reach an Outcome. Still result-oriented, not activity-oriented. Time-bounded with a shorter horizon than the parent Outcome. An Objective can be advanced by multiple Projects simultaneously.

*Examples:* "Land first enterprise AI deployment client by Sep 2026," "Deploy Felix graph layer with vault ingested by end of July"

#### PROJECT
A coordinated body of work that delivers one or more Objectives. Has scope, not just a deadline. Projects are self-similar — a Project can contain sub-Projects of arbitrary depth. A Project can also contain Tasks directly. Projects can deliver multiple Objectives; Objectives can be served by multiple Projects.

*Examples:* "BD pipeline build," "FalkorDB + Graphiti infrastructure," "Obsidian vault ingest pipeline"

#### TASK
A discrete, schedulable unit of action. Has a single actor and a single action. Tasks are self-similar — a Task can contain sub-Tasks of arbitrary depth. A Task must connect upward to a Project or directly to an Objective (never floating). Tasks can be shared across multiple Projects. The one exception is a **standing practice** — a recurring Task whose only justification is a Principle — which anchors via `EMBODIES` instead (guiding principle 2, exception).

#### COMMITMENT
A hard temporal constraint. Not in the hierarchy — a cross-cutting node type that the life-coach agent treats as a fixed point when calculating capacity. Cannot be moved unilaterally (external commitments) or represents a hard internal deadline.

**Anchoring rule (2026-09-23, from #849 Arc C).** A Commitment is anchored by a **datetime**
*or* by a **trigger condition** ("once we're past the launch"), never neither. A trigger-gated
Commitment has no date, so it can never go *overdue* — it becomes *due* when its condition is
met, which is often only inferable indirectly. Where the condition names a node, a `GATED_ON`
edge points at it so the reasoning loop knows what to check; the trigger text is kept
regardless. **Intake policy:** when Kent defers a captured promise without a date, ask for a
trigger, not a date. Standing commitments (a weekly paid session) carry a `recurrence_rule`
rather than one datetime per instance.

*Examples:* "Contrarian cohort call Thursday 2pm," "Client delivery deadline"

#### PRINCIPLE
A cross-cutting **constraint** on decisions — a value, standard, or non-negotiable. Definitional tier: slow-changing and foundational like Purpose, but *not in the hierarchy* — it does not direct work, it governs *how* work and inbound decisions are judged. The reasoning agent (and the EA decision-router) checks a proposed action against applicable Principles before acting: a high-value action that violates a **hard** Principle is never auto-handled — it surfaces. Applies globally by default, or is scoped to specific Purposes/Domains via `SCOPED_TO`. Seeded explicitly by Kent alongside Purposes and Outcomes; not extracted from source material.

*Examples:* "Never commit secrets or bypass a governance gate for expediency," "Protect deep-work mornings — no meetings before noon," "Reversible internal actions are autonomous; irreversible/outbound actions require preview"

#### PERSON *(added 2026-09-18; ratified by Kent the same day on #849)*
A human Kent deals with — the **who** axis, beside why (Purpose), what (Outcome→Task), and
when (temporal edges). Cross-cutting like Commitment, Principle, and Capacity: **not a
hierarchy tier**, and exempt from guiding principle 2 (a Person has no upward edge to a
Purpose; that rule governs work nodes). Kent himself is **not** a node — the ego is implicit,
otherwise every edge would sprout a Kent endpoint. A Person is a **hub**: edges point *at* it
(`COMMITTED_TO`, `INVOLVES`); nothing is sourced from it, because people do not direct Kent's
work — Purposes do.

Why it exists: three of the six hard cases Kent scoped for #849 (dropped ball, cross-channel
identity, stakeholder pattern) are *relational* and inexpressible without a who; and
cross-episode entity resolution — the one graph mechanism neither #844 nor #974 exercised —
needs something to resolve *across*.

**Identity-resolution rule.** A Person carries an `aliases` list — every handle they appear
under (email address, Slack display name, calendar invitee spelling). Structured adapters
resolve handle → Person against that list **before writing** (deterministic, $0). The
extraction path relies on Graphiti's entity dedup plus the post-extraction near-duplicate
check, and a merge is committed **only on evidence**: production aliases are added by adapter
configuration or a Decision-grade confirmation, never by LLM name similarity alone. Kent's
ruling when cutting #849's Arc D (2026-09-23): a person's handles are unique to that person,
so resolution is a **deterministic precondition of the corpus**, not a reasoning problem to
test. `is_contact` marks the people whose mail must always surface (the router's $0 lookup).

**Privacy.** A Person node is PII by construction. Adding the *type* widens nothing: #849 uses
a fictional cast, and any real-person data is gated by the #696 privacy gate and the
physical-exclusion rule (§Rollout → Design spike, item 3). The local-extraction path (inside
the tailnet, $0) is the favourable one for such content. Do not read the type as permission.

**Organisations are not nodes (2026-09-24, #849 synthesis Q4).** An organisation appears in
exactly three existing places: `Person.organisation` (where a human works),
`Commitment.counterparty` (a string when the counterparty is an organisation; a `COMMITTED_TO`
edge when it is a human), and episode provenance (sender address or calendar organiser).
Grouping mail by vendor is a $0 string operation on the sender domain. An `Organisation` type
is deferred until a question must *traverse* one ("what have I committed to anyone at X?");
none in #849 does, and minting org nodes there would blur the `is_contact` test.

*Examples:* a client principal (email + calendar), a collaborator (Slack), a family member.

#### INTEREST *(added 2026-09-23; ratified by Kent 2026-09-24)*
A topic Kent currently wants information on — the "current interest" list he maintains by
voice, journal, or WhatsApp (#849 Arc E). Cross-cutting and scope-free, like Capacity. Not a
Principle (it constrains nothing) and not a Domain (it is a subject, not a life area). It is
**bi-temporal by nature**: every add or drop is an episode, so the list *as of a given week*
is recovered by anchored expansion under the state-vs-history rule, while `status` holds the
current value. Needed to seed the intake router's digest and "current interest" judgement
honestly; not a #849 build item.

*Examples:* "local LLM inference on consumer hardware", "5K training plans"

---

### Pydantic Entity Models

> **Reserved-field rule (graphiti-core):** custom entity types supply *type-specific
> attributes only*. Graphiti's `EntityNode` already owns `uuid`, `name`, `group_id`,
> `labels`, `created_at`, `name_embedding`, `summary`, and `attributes`; redeclaring any
> of these in a custom type fails `validate_entity_types` at `add_episode` time. The node's
> canonical name is `EntityNode.name` — the models below therefore declare no `name` field.
> `description` is deliberately kept as an authored, definitional attribute, distinct from
> the engine-generated rolling digest in `EntityNode.summary`.

```python
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class StatusEnum(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


class StrictnessEnum(str, Enum):
    HARD = "hard"   # never violate; a violating action always surfaces, never auto-handled
    SOFT = "soft"   # strong preference; weighed against the action's value


class Purpose(BaseModel):
    """Immutable life-level why. Changes are life events."""
    description: str
    core_values: list[str] = []


class Domain(BaseModel):
    """Persistent life area. Not time-bounded. Routing layer."""
    description: str


class Outcome(BaseModel):
    """Concrete, time-bounded end state. Measurable."""
    description: str
    target_date: Optional[str] = None       # ISO date
    success_criteria: str = ""
    status: StatusEnum = StatusEnum.ACTIVE
    priority_rank: Optional[int] = None     # relative rank among active Outcomes


class Objective(BaseModel):
    """Intermediate result required to reach an Outcome."""
    description: str
    target_date: Optional[str] = None
    success_criteria: str = ""
    status: StatusEnum = StatusEnum.ACTIVE
    effort_estimate_hours: Optional[float] = None


class Project(BaseModel):
    """Coordinated body of work. Self-similar — can contain sub-Projects."""
    description: str
    target_date: Optional[str] = None
    status: StatusEnum = StatusEnum.ACTIVE
    effort_estimate_hours: Optional[float] = None
    notes: str = ""


class Task(BaseModel):
    """Discrete, schedulable unit of action. Self-similar — can contain sub-Tasks."""
    description: str = ""
    due_date: Optional[str] = None
    scheduled_date: Optional[str] = None
    effort_estimate_hours: Optional[float] = None
    status: StatusEnum = StatusEnum.ACTIVE
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None   # RRULE string; aligns with Vikunja
    is_shared: bool = False                 # True if multiple Projects contain this Task
    tags: list[str] = []


class Commitment(BaseModel):
    """Hard temporal constraint. Fixed point for scheduling.
    Invariant: `datetime` or `trigger` is set — never neither (see Anchoring rule)."""
    description: str = ""
    datetime: Optional[str] = None          # ISO datetime; None for trigger-gated
    trigger: Optional[str] = None           # condition text, e.g. "once we're past the launch"
    recurrence_rule: Optional[str] = None   # RRULE for standing commitments
    duration_hours: Optional[float] = None
    is_external: bool = True                # False = hard internal deadline
    counterparty: Optional[str] = None      # derived from COMMITTED_TO when present


class Principle(BaseModel):
    """Cross-cutting definitional constraint — a value, standard, or non-negotiable.
    Governs *how* decisions are made, not *what* is pursued. Slow-changing."""
    description: str
    rationale: str = ""                      # why this matters to Kent
    strictness: StrictnessEnum = StrictnessEnum.HARD
    is_global: bool = True                   # False = scoped via SCOPED_TO edges


class Decision(BaseModel):
    """A resolved trade-off, extracted from its decision episode.
    First-class per guiding principle 5; the raw episode stays linked via MENTIONS."""
    rationale: str = ""
    decided_at: Optional[str] = None         # ISO datetime
    options_considered: list[str] = []


class Capacity(BaseModel):
    """Measured availability constraint — a fact, not a preference.
    The quantity the reasoning loop uses for step-6 arithmetic; the *value*
    protecting that time (if any) is a separate Principle for step-7 checks."""
    description: str = ""
    hours_per_week: Optional[float] = None


class RelationshipEnum(str, Enum):
    CLIENT = "client"
    COLLABORATOR = "collaborator"
    FAMILY = "family"
    PEER = "peer"
    VENDOR = "vendor"
    OTHER = "other"


class Person(BaseModel):
    """A human Kent deals with — the who axis (ratified 2026-09-18, #849).
    Cross-cutting hub, never a hierarchy tier; Kent is not a node. See §Tier
    Definitions → PERSON for the identity-resolution and privacy rules."""
    description: str = ""                    # who they are to Kent
    relationship: RelationshipEnum = RelationshipEnum.OTHER
    organisation: Optional[str] = None
    aliases: list[str] = []                  # every handle: email, Slack display, calendar spelling
    is_contact: bool = False                 # on Kent's contacts list — a $0 router lookup


class InterestStatusEnum(str, Enum):
    ACTIVE = "active"
    DROPPED = "dropped"


class Interest(BaseModel):
    """A topic Kent currently wants information on (ratified 2026-09-24).
    Cross-cutting, scope-free, found by typed-label lookup like Capacity. Adds and drops
    are episodes, so 'the interest list as of week N' comes from anchored expansion."""
    topic: str
    status: InterestStatusEnum = InterestStatusEnum.ACTIVE
```

---

### Edge Types

All edges carry `valid_from` / `valid_until` automatically via Graphiti's bi-temporal model.

> **Episode boundary (graphiti-core):** typed custom edges exist only between *entity*
> nodes (`edge_type_map` is keyed by entity-type pairs). Episodes are `EpisodicNode`s,
> whose only outbound link is the built-in untyped `MENTIONS` edge. Decision-bearing
> episodes therefore yield an extracted **Decision entity** (above), which carries the
> typed `DECIDED` / `GOVERNED_BY` edges; provenance back to the raw episode rides
> `MENTIONS`. Rows below name entity→entity edges only.

| Edge | From | To | Meaning |
|---|---|---|---|
| `SERVES` | Outcome | Purpose | This Outcome serves this Purpose |
| `BELONGS_TO` | Outcome | Domain | This Outcome lives in this Domain |
| `ADVANCES` | Objective | Outcome | This Objective advances this Outcome |
| `DELIVERS` | Project | Objective | This Project delivers this Objective |
| `CONTAINS` | Project | Project | Sub-project relationship (arbitrary depth) |
| `CONTAINS` | Project | Task | Task belongs to this Project |
| `CONTAINS` | Task | Task | Sub-task relationship (arbitrary depth) |
| `REQUIRES` | Objective | Task | Task required directly by Objective (no Project wrapper) |
| `SHARED_BY` | Task | Project | Task is shared across multiple Projects |
| `BLOCKS` | Commitment | Task/Project | Commitment blocks progress on this node |
| `GATES` | Commitment | Task/Project | Commitment is a prerequisite for this node |
| `CONFLICTS_WITH` | Task | Task | Agent-detected scheduling conflict |
| `TRADES_OFF` | Outcome | Outcome | Agent-detected tension between Outcomes |
| `DECIDED` | Decision | any | This Decision resolved the fate of this node (timestamp + rationale live on the Decision entity) |
| `SCOPED_TO` | Principle | Purpose/Domain | Principle applies only within this Purpose/Domain (absence = global) |
| `GOVERNED_BY` | Decision | Principle | The Decision was constrained by / cited this Principle |
| `VIOLATES` | Task/Project | Principle | Agent-detected tension between a proposed action and a Principle |
| `EMBODIES` | Task | Principle | This recurring Task **is the practice of** this Principle — a standing practice with no Outcome. The one sanctioned static Task→Principle attachment; says what the Task *is*, not which Principles govern it |
| `CONSTRAINS` | Capacity | Purpose/Domain | Capacity bounds work in this scope (absence = global) |
| `DUE_BY` | Task/Project/Outcome | Commitment | This node's hard deadline is this Commitment (source side is the work node, matching the upward-pointing convention) |
| `GATED_ON` | Commitment | Project/Objective/Outcome/Commitment | This trigger-gated Commitment becomes due when this node completes / occurs |
| `COMMITTED_TO` | Commitment | Person | The Person this Commitment was made to (its counterparty); attributed — see `CommittedTo` |
| `INVOLVES` | Task/Project | Person | This Person is a stakeholder in this node |

### Edge attribute models & wiring

Most edges carry **no custom attributes** — their meaning is the type itself, and
bi-temporal validity comes free from Graphiti. Four edges carry attributes:

```python
class ConflictsWith(BaseModel):
    """Agent-detected scheduling conflict."""
    basis: str = ""                          # what collides (e.g. "18h demanded vs 15h capacity")
    window_start: Optional[str] = None       # ISO date
    window_end: Optional[str] = None

class TradesOff(BaseModel):
    """Agent-detected tension between Outcomes."""
    basis: str = ""

class Decided(BaseModel):
    """Disposition this Decision applied to the target node."""
    disposition: str = ""                    # committed | postponed | displaced | abandoned

class Violates(BaseModel):
    """Detected Principle tension; severity comes from Principle.strictness, not here."""
    note: str = ""

class CommittedTo(BaseModel):
    """Where and how the commitment to this Person was made."""
    channel: str = ""                        # email | slack | calendar | in_person | other
    made_at: Optional[str] = None            # ISO datetime, if distinct from the episode's reference_time
```

Wiring intent (implementer verifies exact API shape against the pinned graphiti-core —
the doc states design intent, not engine mechanics):

- `entity_types`: all twelve models, keyed by their class names, passed to `add_episode`.
- `edge_type_map`: keyed by (source-type, target-type) name pairs per the table above.
  `CONTAINS` registers for (Project, Project), (Project, Task), and (Task, Task).
  `DECIDED` registers Decision → **{Purpose, Domain, Outcome, Objective, Project, Task,
  Commitment} — seven pairs, deliberately excluding Principle**: (Decision, Principle)
  must have exactly one candidate edge name (`GOVERNED_BY`) so extraction never has to
  choose, and amending a Principle is a Kent re-seed event, not a graph-recorded
  Decision. Enumerate pairs explicitly rather than relying on any generic-pair fallback
  until the fallback behavior is verified on the pinned version.
- **Principles never attach statically to Tasks/Projects for *applicability*.** Which
  Principles govern a node is computed at reasoning time (loop step 7) from global Principles
  plus `SCOPED_TO` edges along the traversed chain; `GOVERNED_BY`/`VIOLATES` record *events*,
  not standing attachments. The single exception is `EMBODIES` (Task → Principle), which is
  not an applicability claim but an identity one: the Task *is* that Principle's standing
  practice (guiding principle 2, exception). `EMBODIES` never substitutes for the step-7 check.
- **The `edge_type_map` is advisory, not enforced** (measured on graphiti-core 0.30.2,
  #974: unregistered-pair edges are stored as-is). Therefore any **extraction** path
  MUST run a **post-extraction validator** before results are trusted: reject or
  quarantine edges on unregistered (source-type, target-type, name) triples, and flag
  near-duplicate entity names across tiers (the dominant residual failure mode —
  identically-named objective/project/deadline nodes). Structured adapters writing
  typed nodes/edges directly do not need the validator; they are the preferred write
  path and cost no LLM calls.
- **Authority rule:** where a flag and an edge encode the same fact, the **edge is
  authoritative** and the flag is derived (`Task.is_shared` ⇐ existence of `SHARED_BY`
  edges; `Task.due_date` ⇐ its `DUE_BY` Commitment when one exists — attribute-only due
  dates remain valid for soft dates that never earned a Commitment;
  `Outcome.target_date` ⇐ its `DUE_BY` Commitment likewise; `Commitment.counterparty` ⇐ its
  `COMMITTED_TO` Person). Writers maintain
  the edge; the flag may lag or be dropped entirely.
- **Unmaterialised-commitment pattern** (with `Person`): a Commitment carrying a
  `COMMITTED_TO` edge but **no inbound `DUE_BY` / `GATES` / `BLOCKS`** from any Task or
  Project is a promise that never became work — the structural form of #849's "dropped
  ball". It is one Cypher pattern, distinct from the retrieval form (the promise never
  entered the Lattice at all and lives only in the episode log); #849 should test both.

### State vs history representation rule

**Node attributes hold current state only; history lives in the episode log.**
Graphiti's bi-temporal intervals version *edges*, not attributes — a rewritten
`scheduled_date` leaves no trace. So any state change whose history matters (reschedule,
defer, status change) is recorded by the writing adapter as **one episode per event**
(`reference_time` = when it happened, `MENTIONS` linking the affected node), plus a
`Decision` node with `DECIDED` edges when an actual decision was made. A state change
*without* a Decision is deliberately distinguishable from one *with* — the bare-event
pattern ("deferred 4× and never decided anything") is itself a coaching signal.
This is not a spike workaround: proof-ladder rung 2 is adapters writing events into the
Lattice, and §Integration already routes Vikunja task events in as episodes.

**Discovery contract for scope-free nodes:** a global `Capacity` (no `CONSTRAINS` edge) and
every `Interest` are intentionally not traversal-reachable; reasoning-loop step 6 (and the
router's interest check) find them by **typed-label lookup**, not by walking edges. Retrieval configurations that only search edges will miss
edgeless nodes (measured in #974) — consumers must include node search.

### Graph namespace (group_id)

Spike/prototype data uses a dedicated `group_id` (`spike_692`) so it can never mingle
with future real Lattice data.

**Naming rule: `group_id` uses `[A-Za-z0-9_]` only — underscores, never hyphens.**
Measured on graphiti-core 0.30.2 + FalkorDB 4.20.1 (2026-09-15, #974): a hyphenated
group_id silently disables BM25 edge full-text (the escaped query `@group_id:"x\-y"`
returns 0 keyword hits) while hybrid search still returns vector hits — keyword recall
disappears with **no error surfaced**. Two further operational facts from the same
retest: on FalkorDB each group_id is its own graph, and **unscoped `search()` does not
span groups** — consumers must always pass `group_ids` explicitly. Group-scoped search
itself works; #844's "had to run unscoped" is superseded by this measurement.

The production single-group vs multi-group strategy remains open, but is now a design
choice rather than an engine limitation.

---

## Life-Coach Agent Reasoning Model

The life-coach agent operates on this graph to perform trade-off reasoning. Its core loop when a new Task or Project is proposed:

1. Ingest proposed node as an episode; extract entity and upward relationships
2. Traverse upward to Outcome and Purpose; identify which life area this serves
3. Retrieve all Tasks and Projects scheduled for the relevant time window
4. Traverse each competing node upward to its Outcome; compare `priority_rank` and `target_date` urgency
5. Retrieve active Commitments for the time window (fixed points) — expanding `recurrence_rule` instances, and including trigger-gated Commitments whose `GATED_ON` target has completed or whose condition is inferably met
6. Calculate available effort: window capacity (from applicable `Capacity` nodes — global plus those `CONSTRAINS`-scoped to the traversed Purpose/Domain) minus Commitments minus existing scheduled work
7. **Check applicable Principles** (global + those `SCOPED_TO` the traversed Purpose/Domain): does the proposed action violate any? A **hard** violation is never auto-handled — it surfaces regardless of priority; a **soft** violation is weighed against the action's value. Record the check via `GOVERNED_BY` (and `VIOLATES` when detected).
8. Determine fit: does the proposed node fit without displacing higher-priority work?
9. If no fit: identify the lowest-priority scheduled item whose Outcome ranks below the proposed node's Outcome
10. Surface the conflict: "You have [A] by [date], which needs [B]. This week also has [C] and [D] at [hours]. [E] would require displacing [F] (serving Outcome [X], priority [N]). Postpone E or trade off F?"
11. Ingest the decision as an episode → a `Decision` entity is extracted carrying `DECIDED` edges (and `GOVERNED_BY` edges to any Principles that bore on it) with timestamp and rationale; the episode stays linked via `MENTIONS`

Past decisions are retrievable: "You've deferred E four times since March. Either commit to it or explicitly abandon it."

---

## Integration Points

### Vikunja
Vikunja remains the operational task scheduler. Graphiti becomes the *meaning layer* above it — tracking why tasks exist and how they connect to outcomes. Integration path: Vikunja task events (create, complete, defer, status change) trigger Graphiti episode ingestion, keeping the graph current without manual maintenance. RRULE recurrence strings align directly between the Task entity model and Vikunja's repeat support.

### OpenClaw
OpenClaw agents query the Graphiti MCP server rather than reading Markdown files. Graph traversal queries replace full vault re-reads. The life-coach agent is a reasoning wrapper over graph traversal — not a RAG pipeline.

### Obsidian Second Brain
Initial ingest: walk the vault, treat each note as an episode, extract entities and relationships via LLM. The graph builds bottom-up from existing content and is then enriched with explicit Purpose/Outcome/Objective nodes defined by Kent.

### Felix MCP Connectivity
The Graphiti MCP server exposes `query_graph` and `get_graph_schema` tools. These are directly connectable to Claude (via MCP config) and to OpenClaw agents via the agent registry. No custom integration layer required.

---

## Infrastructure

### Deployment Target
office2 (Ubuntu 24.04 LTS, 32GB RAM, Tailscale IP 100.92.197.90)

### Services
- FalkorDB — graph database (Docker, default Graphiti backend)
- Graphiti MCP server — graph API and MCP endpoint (Docker)
- Ingest pipeline — Python script, run on demand or triggered by Vikunja events

### Binding
Consistent with Felix security posture: bind to Tailscale IP only, not 0.0.0.0. Add to `service-inventory.json` on deployment.

### Backup
Graph data directory included in restic backup scope. This is a gap risk until off-site backup is resolved.

---

## Rollout & validation

We are building the cognitive core of the system **live on production, with no staging
environment.** The strategy that makes that safe is that the Lattice is **additive and
side-car isolated** by construction: it ships as separate services (FalkorDB + Graphiti
MCP, Tailscale-bound), nothing in the existing inbox/habits/calendar/escalation pipelines
imports it, consumption is via opt-in MCP tools, and sync is one-way (adapters → Lattice).
**The Lattice service *is* the staging analog** — a parallel observer that can be built,
seeded, and queried with zero production blast radius until a consumer is explicitly wired.

### Where the risk actually is

Standing up the DB, defining the ontology (#694), seeding (#695), ingesting (#696), and
querying (#697) are isolated and reversible — near-zero prod risk. Risk concentrates in two
places, and both stay gated for a long time:

1. **Write-back** — the Lattice writing *into* Vikunja or the vault. Start and stay
   **one-way** (adapters canonical) until a specific write path is proven.
2. **Decision-influence** — Lattice output silently changing what Felix *does* (escalation
   order, router importance, auto-surfacing). A wrong or stale Lattice then produces wrong
   behavior. Every influence path is opt-in, reversible, and human-gated until earned.

Governing rule: **the Lattice stays advisory and derived; the adapters stay source of truth
for their own domain; promote one proof point at a time.** This is shadow-mode /
strangler-fig adoption — the mature pattern for iterating safely on production.

### Design spike (do first, throwaway, zero prod contact)

> **STATUS (2026-09-15): the spike RAN as #844** (mission
> `life-lattice-viability-spike-01KY37JY`, closed 2026-07-22, live on office2, torn down).
> Outcomes per item — full detail in
> [`kitty-specs/life-lattice-viability-spike-01KY37JY/findings.md`](../../kitty-specs/life-lattice-viability-spike-01KY37JY/findings.md):
>
> 1. **office2 fit — PASS** (+~112 MB host idle, no contention).
> 2. **Temporal-reasoning payoff — split verdict.** The *reasoning* is GO (Kent, blinded:
>    "clearly valuable"). The *graph substrate* is NO-GO/inconclusive at small static
>    scale: the default-config graph arm lost 0/4 blinded comparisons to a flat-context
>    baseline. Caveats bound this (untuned retrieval, Q4 under-seeded, **typed
>    `entity_types` untested** — findings "Threats to validity"). **Build direction DECIDED
>    2026-09-16 (Kent): pursue the graph, with adapters as the writers** — see the
>    Build-direction decision below. The remaining open question is not affordability but
>    whether graph-mediated retrieval earns its complexity at scale, which is **#849**
>    (dynamic/scale regime, tuned retrieval + typed entities vs a vector-RAG baseline),
>    gated on Kent's scenario stories.
> 3. **Privacy/extraction — posture set for spike-grade work:** Claude extraction
>    (Anthropic API; episode text crosses the Tailscale boundary), local FastEmbed
>    embedder + local reranker (no OpenAI; Anthropic has no embeddings API). Real-vault
>    ingest remains hard-gated per #696.
> 4. **Ontology fit — significant friction in default config:** with no custom
>    `entity_types`, Graphiti flattened everything to generic `Entity` nodes and the
>    upward hierarchy survived only as fragile extracted edges. Typed-entity
>    configuration was the open half — **closed by #974** (typed-entity spike,
>    office4, closed 2026-09-15): the corrected ontology loads and direct typed
>    writes work at $0; anchored episode expansion recovers full defer history;
>    node+edge hybrid retrieval recovers edgeless facts that edge-only search
>    misses; typed Capacity beats bare text. LLM extraction is input-sensitive —
>    labels went 18/30 → 29/30 and edges 3/22 → 19/22 only with tier-definition
>    instructions plus templated wording (local Qwen3-Next-80B; free prose
>    unproven, #849 tests it) — and `edge_type_map` is not enforced, so extraction
>    requires the post-extraction validator (§Edge attribute models & wiring).
>    Full findings + reusable harness: kentonium3/kg-automation#974.
>
> The item list below is retained as the original spike definition (historical record).

Time-boxed investigation to kill the four make-or-break unknowns *before* committing to the
full #693→#698 build:

1. **office2 fit** — does Graphiti + FalkorDB run acceptably alongside the existing stack?
   (de-risks #693)
2. **Temporal-reasoning payoff (the make-or-break)** — hand-seed a small
   Purpose → Outcome → Project → Task chain and test the target questions: upward traversal
   ("why this task?") and conflict/trade-off detection. If the temporal reasoning does not
   pay off, nothing built above it matters — so prove this **first**.
   - **Content is manufactured but realistic.** No real lattice content exists yet (the
     ontology is newly formalized), and none is needed to prove the reasoning. Fabricate a
     chain *shaped like Kent's actual life* and **deliberately construct** the stress
     scenarios (a real week-conflict, a trade-off, a "deferred 4× since March" pattern)
     rather than hoping real data contains them. Real data substitutes in as the structure
     firms up — and the later shadow-mode proof rungs (ladder 2–3) genuinely require it.
   - This **decouples reasoning validation from the privacy gate (spike item 3)**: synthetic
     content isn't sensitive, so this test runs without waiting on the extraction decision.
3. **Privacy / extraction posture (hard gate)** — vault ingest uses an LLM to extract
   entities from sensitive life-planning content; the Lattice will hold it. Which LLM, and
   does anything cross the Tailscale boundary? Must be resolved before any vault ingest. The
   truly-private content is handled by **physical exclusion** — it lives only on devices
   Felix cannot reach, so it is never present on office2 to ingest; the #696 gate is therefore
   a **verification that the excluded content is not present** in the episodes crossing the
   membrane, not an in-repo rule that enforces the exclusion. May force the local-LLM question
   early.
4. **Ontology fit** — does hand-seeding reveal friction in the tier model? (empirical answer
   to the #367 hierarchy-research question, on a slice rather than by exhaustive survey).

### Build-direction decision (Kent, 2026-09-16)

**Pursue the graph, with adapters as the writers.** Kent's steer on where cycles go: *"If
we're going to spend cycles I'd rather spend them figuring out if the end goal is going to
work."* So plumbing is minimised and validation of the end goal is prioritised.

What the decision rests on (#974, measured, $0):
- Structured adapters write typed nodes and edges **directly, with no LLM** — verified by a
  tripwire client recording zero LLM calls. Exact structure, no extraction risk, no cost.
- Deadlines are **adapter-written `Commitment` nodes with `DUE_BY`**; extraction never
  produced one, collapsing every deadline into its deliverable.
- LLM extraction is confined to genuinely unstructured content, and runs **locally at $0**
  on office4 for templated, one-relation-per-sentence text (29/30 labels, 19/22 edges, 5/6
  strict chains on a local 80B-A3B model). **Free prose remains unproven** (ambiguous
  wording: 18/30, 3/22, 0/6).
- The cost objection that shelved this epic applies only to the extraction half, and even
  that half now has a local, no-cost path.

What this decision does **not** settle: whether graph-mediated retrieval beats the best
non-graph baseline at scale. #974 measured mechanisms on 34–36 nodes, where a retrieval
budget of 50 returns the whole graph. **#849 is the gate** and it is the priority spend.

**Cost shape is a scored axis, and today's number is a lower bound (Kent, 2026-09-18).** The
flat baseline's per-query cost scales with the corpus; the graph's scales with the answer, because
it pays once to structure and assembles a small context per question. #849 therefore scores
input-tokens-per-correct-answer alongside correctness. Because the corpus only grows once the
Outcome→commitment→action chain is in use, a cost gap measured now **understates** the eventual
gap, and a "graph does not pay off yet" reading would be regime-bound the way #844's was — the
findings must say so before the run, not after. Inference cost as the practical capacity limit is
the motivating context of RFC #986 (per-function provider/model seam) and ADR-0009 (office4
large-context inference); this design leaves that seam open and hardcodes no provider.

### Proof-feature ladder (each rung: parallel on prod, additive, reversible, one proof point)

> **Status (2026-09-17):** the ladder below is the **plan-of-record**. The contingency
> recorded here on 2026-09-15 (build direction undecided after #844) was resolved by the
> Build-direction decision above (Kent, 2026-09-16: pursue the graph, adapters as the
> writers). What remains gated on **#849** is not *whether* to climb the ladder but whether
> graph-mediated retrieval earns its complexity at scale — which bears on rung 3's
> reasoning arm, not on rungs 1–2. The #693→#698 sequencing and the membrane-topology
> question are still open scheduling/ingest decisions, not build-direction ones.

1. **Read-only, hand-seeded, queried only by Kent** via MCP in Claude Desktop — zero Felix
   involvement. *Proof: can it answer "why this task?"*
2. **One-way adapter → Lattice shadow sync** (Vikunja/calendar events) — Lattice auto-mirrors
   reality. *Proof: it stays consistent without manual upkeep.*
3. **Life-coach reasoning in advisory shadow mode** — on a new task it produces a trade-off
   analysis that is **logged / sent to Kent as FYI, never acted on**. *Proof: does its
   conflict detection match Kent's judgment? Measure hit-rate over weeks.* **This rung is the
   real target; rungs 1–2 are scaffolding to reach it.**
4. **Promote proven advisories to human-gated surfacing** — Kent gets the trade-off question
   and decides.
5. **Only much later** — the router (#820) consults the Lattice for the "importance" axis,
   under #820's own promotion-gate discipline.

**End state:** substrate reasons, router dispatches, adapters execute.
**Path:** substrate reasons in shadow, Kent executes — until it earns the wheel.

### Named risks to hold

- **Privacy / exposure** (LLM extraction of sensitive episodes) — hard gate; spike item 3.
  The `Person` type makes PII a first-class node; real-person data stays behind
  the same gate (§Tier Definitions → PERSON).
- **Lattice becoming a silent load-bearing dependency** — mitigated by advisory/derived +
  adapters canonical.
- **Backup gap** — graph-data backup is unresolved (see Infrastructure → Backup); resolve
  before real data accrues.
- **Ontology churn** — mitigated by Graphiti's migration-free custom types + early
  slice validation, so getting the tiers slightly wrong at first is cheap to correct.
- **Analysis paralysis on the hierarchy survey (#367)** — time-box; validate on a real slice.

---

## Open Questions

1. **Initial ontology seeding:** Does Kent define Purpose/Principle/Outcome/Domain nodes manually as a structured exercise before vault ingest, or does the first ingest attempt to extract them from existing notes? Recommendation: manual seeding first — these are definitional and too important to leave to LLM extraction from potentially inconsistent source material. **Principles especially** are authored by Kent, never extracted.

2. **Vikunja sync direction:** ~~One-way (Vikunja → Graphiti) or bidirectional?~~ **Decided
   (2026-09-16, with the build direction): one-way, adapters → Lattice.** Adapters are the
   writers of typed nodes/edges and remain canonical for their own domain; write-back stays
   gated per §Rollout → *Where the risk actually is* until a specific write path is proven.

3. **Privacy boundary:** Graphiti graph content will include sensitive life-planning data. Confirm vault content privacy posture before connecting any cloud-hosted LLM for extraction. This may accelerate the local LLM evaluation currently deferred pending observability data.

4. **Life-coach agent identity:** Implement as a named OpenClaw agent with its own system prompt and graph access, or as a mode of an existing agent? Recommend named agent — distinct persona and reasoning constraints matter for this use case.

---

## Out of Scope

- Architecture doc — Claude Code / spec-kitty concern; lives in `docs/design/architecture/`
- Docker Compose configuration — implementation artifact, produced during Epic execution
- Ingest pipeline code — implementation artifact, produced during Epic execution
- Vikunja webhook integration — follow-on work after core graph layer is proven
