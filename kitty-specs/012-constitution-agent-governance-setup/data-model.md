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
| gate | integer (1-3) | yes | Current autonomy gate level |
| observation_mode | enum: on/off | yes | Routine activity surfacing state |
| deployed_feature | string | yes | Feature that deployed this agent (e.g., `F008`) |
| registered | date (ISO 8601) | yes | Date agent was registered in the registry |
| gate_history | array | yes | Append-only list of gate transition events |

**Gate History Entry:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| date | date (ISO 8601) | yes | Date of gate transition |
| gate | integer (1-3) | yes | Gate level after transition |
| reason | string | yes | Rationale for transition |
| decided_by | string | yes | Who authorized the transition |

**Validation rules:**
- `gate` must be 1, 2, or 3
- `observation_mode` defaults to `on` for new agents
- `gate_history` is append-only — entries are never edited or removed
- Gate transitions require minimum 30 days at current gate (except initial registration)

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

| Category | Description | Surfacing behavior |
|----------|-------------|-------------------|
| routine | Normal successful operations | Summarized as counts |
| flagged | Items requiring Kent's attention (needs-review, potential-goals) | Elevated with detail |
| error | Operation failures | Always surfaced (critical alert) |
| security | Security concerns | Always surfaced (critical alert) |

### Surfaced Digest

Written by the centralized intelligence layer to `~/second-brain/notes/00-System/agent-activity/`.

**Format:** Markdown (no frontmatter — Obsidian vault file)

**Structure:**
- Header with date and time window
- Per-agent section with:
  - Routine summary (counts)
  - Elevated items (flagged, errors, security) with actionable detail
  - Reference to full audit log
- Cross-agent observations (if applicable)

### Constitution Document

`docs/constitution/FELIX-CONSTITUTION.md` — governance document, not a data entity. Version-stamped. Sections:

1. Preamble (purpose, version, change process)
2. Directive 1: Narrow Scope
3. Directive 2: Earned Autonomy (3-gate model)
4. Directive 3: Central Action Logging
5. Directive 4: Safety Parameters
6. Privacy & Communication Boundaries (extensible)
7. ClawHub Community Skill Constraint
8. Observation Mode Definition
9. Amendment Process

## State Transitions

### Gate Advancement

```
Gate 1 (Human In The Middle)
  → [30+ days + Kent's decision] → Gate 2 (Human Monitored)
    → [30+ days + Kent's decision] → Gate 3 (Autonomous)

Any gate → [Kent's decision, any time, any reason] → Gate 1 (regression)
```

### Observation Mode

```
on (default for new agents)
  → [Kent disables routine surfacing] → off
    → [Kent re-enables] → on

Note: Critical alerts surface regardless of on/off state
```

## Relationships

```
Constitution
  ├── referenced by → Agent Standing Orders (AGENTS.md preamble)
  ├── defines → Gate Model (used by Agent Registry)
  ├── defines → Observation Mode (state stored in Agent Registry)
  └── defines → ClawHub Constraint (encoded in Skill-Authoring Skill)

Agent Registry (JSON)
  ├── one entry per → Deployed Agent
  ├── rendered as → AGENT-REGISTRY.md (human-readable view)
  └── read by → Centralized Intelligence Layer (observation_mode state)

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
