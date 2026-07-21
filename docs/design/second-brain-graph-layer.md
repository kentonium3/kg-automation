---
title: "Second Brain Graph Layer — Design"
doc_type: design
status: draft
owners: ["@kentonium3"]
last_updated: '2026-07-20'
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

Additional selection factors:

- Native Anthropic API support (alongside OpenAI, Gemini, Groq)
- Built-in MCP server — directly connectable to Claude and OpenClaw without a custom integration layer
- Custom entity types via Pydantic models — domain-specific ontology without schema migrations
- Hybrid retrieval: vector similarity + BM25 full-text + graph traversal in a single query
- Apache 2.0 license; Zep Cloud not required
- FalkorDB backend (default for MCP server) is lightweight enough for office2

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

3. **Project and Task are self-similar.** Both support arbitrary nesting depth via `CONTAINS` edges. A Project can contain sub-Projects and Tasks. A Task can contain sub-Tasks. The boundary: Projects have scope and deliverables; Tasks have a single actor and a single action.

4. **Many-to-many is allowed upward.** A single Outcome can serve multiple Purposes. A single Objective can be advanced by multiple Projects. This reflects reality — work often serves more than one master — while keeping the hierarchy structurally enforced.

5. **Decisions are first-class nodes.** Every trade-off conversation that reaches a resolution is ingested as an episode and creates a durable `DECIDED` relationship. Future conflicts can be checked against past decisions.

6. **Principles are a first-class, cross-cutting constraint axis** (Kent, 2026-07-20). Where the Purpose→…→Task hierarchy *directs* decisions (what/why you pursue), **Principles *constrain*** them (how you decide — the values, standards, and non-negotiables the boss will or won't accept). A Principle is definitional-tier (slow-changing, like Purpose) and cross-cutting (not in the hierarchy, like Commitment). It is seeded explicitly and is the least-duplicable element in the system — the deepest moat. See [`executive-assistant-architecture.md`](executive-assistant-architecture.md) §6 for the EA framing that motivated adding this type.

---

### Tier Definitions

#### PURPOSE
The "why I exist / what I'm for" level. Immutable or near-immutable. Changes represent life events, not planning events. No due date. No status in the task sense.

*Examples:* "Build wealth through AI-leveraged operations as a solo operator," "Radical personal transformation and growth"

#### DOMAIN
A persistent life area that groups Outcomes. Not time-bounded. Serves as a routing and grouping layer — prevents all Outcomes from hanging directly off Purpose nodes and gives the life-coach agent a natural partition for capacity reasoning.

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
A discrete, schedulable unit of action. Has a single actor and a single action. Tasks are self-similar — a Task can contain sub-Tasks of arbitrary depth. A Task must connect upward to a Project or directly to an Objective (never floating). Tasks can be shared across multiple Projects.

#### COMMITMENT
A hard temporal constraint. Not in the hierarchy — a cross-cutting node type that the life-coach agent treats as a fixed point when calculating capacity. Cannot be moved unilaterally (external commitments) or represents a hard internal deadline.

*Examples:* "Contrarian cohort call Thursday 2pm," "Client delivery deadline"

#### PRINCIPLE
A cross-cutting **constraint** on decisions — a value, standard, or non-negotiable. Definitional tier: slow-changing and foundational like Purpose, but *not in the hierarchy* — it does not direct work, it governs *how* work and inbound decisions are judged. The reasoning agent (and the EA decision-router) checks a proposed action against applicable Principles before acting: a high-value action that violates a **hard** Principle is never auto-handled — it surfaces. Applies globally by default, or is scoped to specific Purposes/Domains via `SCOPED_TO`. Seeded explicitly by Kent alongside Purposes and Outcomes; not extracted from source material.

*Examples:* "Never commit secrets or bypass a governance gate for expediency," "Protect deep-work mornings — no meetings before noon," "Reversible internal actions are autonomous; irreversible/outbound actions require preview"

---

### Pydantic Entity Models

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
    name: str
    description: str
    core_values: list[str] = []


class Domain(BaseModel):
    """Persistent life area. Not time-bounded. Routing layer."""
    name: str
    description: str


class Outcome(BaseModel):
    """Concrete, time-bounded end state. Measurable."""
    name: str
    description: str
    target_date: Optional[str] = None       # ISO date
    success_criteria: str = ""
    status: StatusEnum = StatusEnum.ACTIVE
    priority_rank: Optional[int] = None     # relative rank among active Outcomes


class Objective(BaseModel):
    """Intermediate result required to reach an Outcome."""
    name: str
    description: str
    target_date: Optional[str] = None
    success_criteria: str = ""
    status: StatusEnum = StatusEnum.ACTIVE
    effort_estimate_hours: Optional[float] = None


class Project(BaseModel):
    """Coordinated body of work. Self-similar — can contain sub-Projects."""
    name: str
    description: str
    target_date: Optional[str] = None
    status: StatusEnum = StatusEnum.ACTIVE
    effort_estimate_hours: Optional[float] = None
    notes: str = ""


class Task(BaseModel):
    """Discrete, schedulable unit of action. Self-similar — can contain sub-Tasks."""
    name: str
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
    """Hard temporal constraint. Fixed point for scheduling."""
    name: str
    description: str = ""
    datetime: str                           # ISO datetime
    duration_hours: Optional[float] = None
    is_external: bool = True                # False = hard internal deadline
    counterparty: Optional[str] = None


class Principle(BaseModel):
    """Cross-cutting definitional constraint — a value, standard, or non-negotiable.
    Governs *how* decisions are made, not *what* is pursued. Slow-changing."""
    name: str
    description: str
    rationale: str = ""                      # why this matters to Kent
    strictness: StrictnessEnum = StrictnessEnum.HARD
    is_global: bool = True                   # False = scoped via SCOPED_TO edges
```

---

### Edge Types

All edges carry `valid_from` / `valid_until` automatically via Graphiti's bi-temporal model.

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
| `DECIDED` | Episode | any | Decision recorded with timestamp and rationale |
| `SCOPED_TO` | Principle | Purpose/Domain | Principle applies only within this Purpose/Domain (absence = global) |
| `GOVERNED_BY` | Episode | Principle | A decision was constrained by / cited this Principle |
| `VIOLATES` | Task/Project | Principle | Agent-detected tension between a proposed action and a Principle |

---

## Life-Coach Agent Reasoning Model

The life-coach agent operates on this graph to perform trade-off reasoning. Its core loop when a new Task or Project is proposed:

1. Ingest proposed node as an episode; extract entity and upward relationships
2. Traverse upward to Outcome and Purpose; identify which life area this serves
3. Retrieve all Tasks and Projects scheduled for the relevant time window
4. Traverse each competing node upward to its Outcome; compare `priority_rank` and `target_date` urgency
5. Retrieve active Commitments for the time window (fixed points)
6. Calculate available effort: window capacity minus Commitments minus existing scheduled work
7. **Check applicable Principles** (global + those `SCOPED_TO` the traversed Purpose/Domain): does the proposed action violate any? A **hard** violation is never auto-handled — it surfaces regardless of priority; a **soft** violation is weighed against the action's value. Record the check via `GOVERNED_BY` (and `VIOLATES` when detected).
8. Determine fit: does the proposed node fit without displacing higher-priority work?
9. If no fit: identify the lowest-priority scheduled item whose Outcome ranks below the proposed node's Outcome
10. Surface the conflict: "You have [A] by [date], which needs [B]. This week also has [C] and [D] at [hours]. [E] would require displacing [F] (serving Outcome [X], priority [N]). Postpone E or trade off F?"
11. Ingest the decision as an episode → creates `DECIDED` edge (and `GOVERNED_BY` edges to any Principles that bore on it) with timestamp and rationale

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

Time-boxed investigation to kill the four make-or-break unknowns *before* committing to the
full #693→#698 build:

1. **office2 fit** — does Graphiti + FalkorDB run acceptably alongside the existing stack?
   (de-risks #693)
2. **Temporal-reasoning payoff on real data (the make-or-break)** — hand-seed 5–10 *real*
   nodes (an actual Purpose → Outcome → Project → Task chain) and test the target questions:
   upward traversal ("why this task?") and conflict/trade-off detection. If the temporal
   reasoning does not pay off on Kent's real data shape, nothing built above it matters — so
   prove this **first**.
3. **Privacy / extraction posture (hard gate)** — vault ingest uses an LLM to extract
   entities from sensitive life-planning content; the Lattice will hold it. Which LLM, and
   does anything cross the Tailscale boundary? Must be resolved before any vault ingest, and
   is bound by the absolute `~/second-brain/notes/04-Growth/_private/` rule. May force the
   local-LLM question early.
4. **Ontology fit** — does hand-seeding reveal friction in the tier model? (empirical answer
   to the #367 hierarchy-research question, on a slice rather than by exhaustive survey).

### Proof-feature ladder (each rung: parallel on prod, additive, reversible, one proof point)

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

2. **Vikunja sync direction:** One-way (Vikunja → Graphiti) or bidirectional? Bidirectional introduces write-back complexity. Start one-way.

3. **Privacy boundary:** Graphiti graph content will include sensitive life-planning data. Confirm vault content privacy posture before connecting any cloud-hosted LLM for extraction. This may accelerate the local LLM evaluation currently deferred pending observability data.

4. **Life-coach agent identity:** Implement as a named OpenClaw agent with its own system prompt and graph access, or as a mode of an existing agent? Recommend named agent — distinct persona and reasoning constraints matter for this use case.

---

## Out of Scope

- Architecture doc — Claude Code / spec-kitty concern; lives in `docs/design/architecture/`
- Docker Compose configuration — implementation artifact, produced during Epic execution
- Ingest pipeline code — implementation artifact, produced during Epic execution
- Vikunja webhook integration — follow-on work after core graph layer is proven
