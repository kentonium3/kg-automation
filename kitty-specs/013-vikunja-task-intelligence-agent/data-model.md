# Data Model: Vikunja Task Intelligence Agent

**Feature**: 013-vikunja-task-intelligence-agent
**Date**: 2026-04-02

## Entities

### Raw Task Input

The payload passed from felix-admin-capture to felix-admin-tasker via agent delegation.

| Field | Type | Required | Description |
|---|---|---|---|
| raw_text | string | yes | Original task description from inbox note |
| source_reference | string | yes | Path or identifier of the originating inbox note |
| inferred_identity | string | no | Identity label inferred by capture agent (personal/intentional/metalcasework) |
| date_signals | string[] | no | Date/time references extracted from the inbox note text |
| context_signals | string[] | no | Additional context clues (project hints, priority keywords, goal references) |

### Enrichment Proposal

The structured task proposal presented to Kent for confirmation via the primary interaction channel.

| Field | Type | Required | Description |
|---|---|---|---|
| title | string | yes | Cleaned task title |
| identity_label | string | yes | Identity: personal, intentional, or metalcasework |
| project | string | yes | Target Vikunja project name (resolved at runtime, never hardcoded ID) |
| due_date | ISO 8601 string | yes | Proposed due date |
| priority | integer (1-5) | yes | Vikunja priority: 1=low, 2=medium, 3=high, 4=urgent, 5=critical |
| start_date | ISO 8601 string | no | Proposed start date (only if lead time or dependencies) |
| repeat_after | integer | no | Repeat interval in seconds (0 = no repeat) |
| repeat_mode | integer (0-2) | no | 0=default, 1=monthly, 2=from current date |
| goal_relationship | object | no | `{goal_task_id, relation_kind}` if goal link proposed |
| task_relationships | object[] | no | `[{other_task_id, relation_kind}]` for subtask/blocking/related |
| description | string | no | Task description including source reference |
| confidence_notes | object | no | Per-attribute confidence indicators for transparency |
| clarification_questions | string[] | no | Questions to ask Kent for low-confidence attributes |

### Enrichment State

Tracking state for retroactive enrichment and duplicate proposal prevention. Stored as Vikunja task comments with the `[Felix]` prefix.

| Field | Type | Description |
|---|---|---|
| task_id | integer | Vikunja task ID |
| enrichment_status | enum | `proposed`, `confirmed`, `skipped`, `declined` |
| proposed_at | ISO 8601 string | When the enrichment proposal was sent |
| resolved_at | ISO 8601 string | When Kent confirmed, skipped, or declined |

**Storage**: Enrichment state is encoded in Vikunja task comments using the format:
```
[Felix] enrichment | <status> | <ISO timestamp> | <optional notes>
```

This avoids external state storage — the Vikunja comment API is the single source of truth.

### Vikunja Task (target output)

The fully structured task written to Vikunja after Kent's confirmation. Uses existing Vikunja API fields.

| Field | API Field | Type | Description |
|---|---|---|---|
| Title | title | string | Task title |
| Description | description | string | Includes source reference and any notes |
| Due date | due_date | ISO 8601 | When the task is due |
| Start date | start_date | ISO 8601 | When work should begin (optional) |
| Priority | priority | integer | 1-5 scale |
| Project | project_id | integer | Resolved at runtime by project name |
| Identity label | label_id | integer | Resolved at runtime by label name |
| Repeat interval | repeat_after | integer | Seconds between repetitions |
| Repeat mode | repeat_mode | integer | 0/1/2 enum |

### Task Relation (Vikunja native)

Created via `PUT /api/v1/tasks/{taskID}/relations`.

| Field | Type | Description |
|---|---|---|
| task_id | integer | Base task (path parameter) |
| other_task_id | integer | Related task |
| relation_kind | string | subtask, parenttask, related, blocking, blocked, precedes, follows |

## State Transitions

### Enrichment Flow

```
raw_input → reasoning → [clarification_needed?]
                          ├── yes → ask_questions → receive_answers → propose
                          └── no → propose
propose → [confirmed?]
            ├── yes → create_task → done
            ├── modified → update_proposal → propose (loop)
            └── rejected → discard → done
```

### Retroactive Enrichment Batch Flow

```
scan_inbox → identify_flat_tasks → filter_already_proposed → batch(3-5)
batch → propose_via_channel → [per task: confirm/skip/defer]
  ├── confirmed → enrich_task
  ├── skipped → flag_comment("skipped") → never_repropose
  └── deferred → pause → repropose_later
[batch complete] → pause(≥15min) → next_batch
```

### Operating Mode Progression

```
Assisted (Level 1) → [30+ days + Kent approval] → Observed (Level 2) → [30+ days + Kent approval] → Autonomous (Level 3)
```

At Assisted: Every task creation requires Kent's explicit confirmation.
At Observed: Tasks created autonomously; daily digest shows all actions.
At Autonomous: Tasks created autonomously; only exceptions surfaced.

## Project Placement Mapping

| Content Signal | Identity | Target Project |
|---|---|---|
| Consulting, client work, marketing, thought leadership, revenue | intentional | Intentional LLC |
| Business acquisition, CT course | personal | Business Acquisition |
| Health, fitness, PT, medical, physical therapy | personal | Health & Conditioning |
| Personal growth, habits, mindset, learning | personal | Personal Growth |
| Metal casework, fabrication, ecommerce research | metalcasework | Metal Casework |
| Ambiguous / no clear signal | — | Ask Kent; default to Inbox |

## Identity Label Inference Rules

| Signal Words | Label |
|---|---|
| business, consulting, client, Intentional LLC, marketing, thought leadership, revenue | intentional |
| metal casework, fabrication, ecommerce research | metalcasework |
| Everything else (default when ambiguous) | personal |
