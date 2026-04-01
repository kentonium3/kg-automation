# Data Model: Constitution & Agent Governance Setup

**Feature**: 012-constitution-agent-governance-setup
**Date**: 2026-04-01

## Entities

### Agent Registry Entry

The centralized JSON registry (`docs/constitution/agent-registry.json`) is the authoritative operational record for all deployed Felix agents.

**Fields per agent:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Agent identifier (e.g., `felix-admin-capture`) |
| team | string | yes | Team assignment (e.g., `SuperAdmin (B)`) |
| scope | string | yes | One-line description of agent's responsibility |
| autonomy_level | enum: assisted/observed/autonomous | yes | Current operating mode |
| deployed_feature | string | yes | Feature that deployed this agent (e.g., `F008`) |
| registered | date (ISO 8601) | yes | Date agent was registered in the registry |
| transition_history | array | yes | Append-only list of autonomy level transition events |

**Autonomy Level Values:**

| Value | Level | Behavior |
|-------|-------|----------|
| `assisted` | 1 | Agent proposes, Kent confirms. All activity surfaced in daily digest. |
| `observed` | 2 | Agent executes autonomously. All activity surfaced in daily digest. |
| `autonomous` | 3 | Agent executes autonomously. Only exceptions surfaced in daily digest. |

**Transition History Entry:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| date | date (ISO 8601) | yes | Date of transition |
| autonomy_level | enum: assisted/observed/autonomous | yes | Level after transition |
| direction | enum: promotion/demotion/registration | yes | Type of transition |
| reason | string | yes | Rationale for transition |
| decided_by | string | yes | Who authorized the transition |

**Validation rules:**
- `autonomy_level` must be one of: `assisted`, `observed`, `autonomous`
- New agents default to `assisted`
- `transition_history` is append-only — entries are never edited or removed
- Promotions require minimum 30 days at current level (except initial registration)
- Demotions have no minimum time requirement — can happen at any time

### Structured Activity Log

Written by each agent after every run to `~/second-brain/agents/logs/`.

**Format:** Markdown with YAML frontmatter (follows existing processing log format)

| Field | Location | Required | Description |
|-------|----------|----------|-------------|
| domain | frontmatter | yes | Always `resources` |
| type | frontmatter | yes | Always `log` |
| updated | frontmatter | yes | Date (YYYY-MM-DD) |
| status | frontmatter | yes | Always `reference` |
| agent_name | body | yes | Which agent produced this log |
| run_time | body | yes | Timestamp of the run |
| actions | body | yes | List of actions taken with descriptions |
| tasks_created | body | conditional | Vikunja tasks created (if any) |
| items_flagged | body | conditional | Needs-review, potential-goals, errors |
| failures | body | conditional | Error details (if any) |
| summary | body | yes | Counts: files processed, notes created/updated, tasks created, items flagged |

**Log categories (for standardized logging across agents):**

| Category | Description | Surfacing at Assisted/Observed | Surfacing at Autonomous |
|----------|-------------|-------------------------------|------------------------|
| routine | Normal successful operations | Summarized as counts | Not surfaced |
| flagged | Items requiring Kent's attention | Elevated with detail | Elevated with detail |
| error | Operation failures | Always surfaced (critical alert) | Always surfaced (critical alert) |
| security | Security concerns | Always surfaced (critical alert) | Always surfaced (critical alert) |

### Surfaced Digest

Written by the centralized intelligence layer to `~/second-brain/notes/00-System/agent-activity/`.

**Format:** Markdown (no frontmatter — Obsidian vault file)

**Structure:**
- Header with date and time window
- Per-agent section with:
  - Agent name and current autonomy level
  - Routine summary (counts) — included for Assisted/Observed agents; omitted for Autonomous
  - Elevated items (flagged, errors, security) with actionable detail — included at all levels
  - Reference to full audit log
- Cross-agent observations (if applicable)

### Constitution Document

`docs/constitution/FELIX-CONSTITUTION.md` — governance document, not a data entity. Version-stamped. Sections:

1. Preamble (purpose, version, change process)
2. Directive 1: Narrow Scope
3. Directive 2: Earned Autonomy (autonomy level model)
4. Directive 3: Central Action Logging
5. Directive 4: Safety Parameters
6. Privacy & Communication Boundaries (extensible)
7. ClawHub Community Skill Constraint
8. Activity Surfacing (behavior per autonomy level)
9. Amendment Process

## State Transitions

### Autonomy Level Transitions

```
Assisted (Level 1)
  → [30+ days + Kent's decision] → Observed (Level 2)
    → [30+ days + Kent's decision] → Autonomous (Level 3)

Any level → [Kent's decision, any time, any reason] → Assisted (demotion)
Autonomous → [Kent's decision, any time, any reason] → Observed (partial demotion)
```

**Surfacing behavior follows autonomy level automatically — no separate toggle.**

## Relationships

```
Constitution
  ├── referenced by → Agent Standing Orders (AGENTS.md preamble)
  ├── defines → Autonomy Level Model (used by Agent Registry)
  ├── defines → Activity Surfacing Behavior (per autonomy level)
  └── defines → ClawHub Constraint (encoded in Skill-Authoring Skill)

Agent Registry (JSON)
  ├── one entry per → Deployed Agent
  ├── rendered as → AGENT-REGISTRY.md (human-readable view)
  └── read by → Centralized Intelligence Layer (autonomy_level determines surfacing depth)

Activity Logs
  ├── written by → Each Agent (per run)
  └── read by → Centralized Intelligence Layer

Centralized Intelligence Layer
  ├── reads → Activity Logs + Agent Registry
  ├── writes → Surfaced Digest (Obsidian notes)
  └── sends → Critical Alerts (WhatsApp)

Skill-Authoring Skill
  ├── encodes → Project conventions + ClawHub constraint
  └── references → Whisper Skill, Vikunja API Skill (as pattern examples)
```
