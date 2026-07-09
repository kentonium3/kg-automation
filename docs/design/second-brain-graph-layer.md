---
title: "Second Brain Graph Layer — Design"
doc_type: design
status: draft
owners: ["@kentonium3"]
last_updated: '2026-07-09'
audience: agents_and_humans
---

# Second Brain Graph Layer — Design Document

**Status:** Draft
**Author:** Kent Gale
**Location:** `docs/design/second-brain-graph-layer.md`
**Related Epic:** (to be linked by Claude Code on creation)

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

---

## Life-Coach Agent Reasoning Model

The life-coach agent operates on this graph to perform trade-off reasoning. Its core loop when a new Task or Project is proposed:

1. Ingest proposed node as an episode; extract entity and upward relationships
2. Traverse upward to Outcome and Purpose; identify which life area this serves
3. Retrieve all Tasks and Projects scheduled for the relevant time window
4. Traverse each competing node upward to its Outcome; compare `priority_rank` and `target_date` urgency
5. Retrieve active Commitments for the time window (fixed points)
6. Calculate available effort: window capacity minus Commitments minus existing scheduled work
7. Determine fit: does the proposed node fit without displacing higher-priority work?
8. If no fit: identify the lowest-priority scheduled item whose Outcome ranks below the proposed node's Outcome
9. Surface the conflict: "You have [A] by [date], which needs [B]. This week also has [C] and [D] at [hours]. [E] would require displacing [F] (serving Outcome [X], priority [N]). Postpone E or trade off F?"
10. Ingest the decision as an episode → creates `DECIDED` edge with timestamp and rationale

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

## Open Questions

1. **Initial ontology seeding:** Does Kent define Purpose/Outcome/Domain nodes manually as a structured exercise before vault ingest, or does the first ingest attempt to extract them from existing notes? Recommendation: manual seeding first — these are definitional and too important to leave to LLM extraction from potentially inconsistent source material.

2. **Vikunja sync direction:** One-way (Vikunja → Graphiti) or bidirectional? Bidirectional introduces write-back complexity. Start one-way.

3. **Privacy boundary:** Graphiti graph content will include sensitive life-planning data. Confirm vault content privacy posture before connecting any cloud-hosted LLM for extraction. This may accelerate the local LLM evaluation currently deferred pending observability data.

4. **Life-coach agent identity:** Implement as a named OpenClaw agent with its own system prompt and graph access, or as a mode of an existing agent? Recommend named agent — distinct persona and reasoning constraints matter for this use case.

---

## Out of Scope

- Architecture doc — Claude Code / spec-kitty concern; lives in `docs/design/architecture/`
- Docker Compose configuration — implementation artifact, produced during Epic execution
- Ingest pipeline code — implementation artifact, produced during Epic execution
- Vikunja webhook integration — follow-on work after core graph layer is proven
