# Vikunja Task Enrichment API Contract

**Feature**: 013-vikunja-task-intelligence-agent
**Date**: 2026-04-02

## Base URL

```
https://office2.tail0f5f56.ts.net/api/v1
```

## Authentication

Bearer token from `/data/services/openclaw/secrets/vikunja-api`.

## Task Creation (Two-Step)

### Step 1: Create Task

```
PUT /projects/{PROJECT_ID}/tasks
```

```json
{
  "title": "Schedule car for oil change",
  "description": "[Felix] Created from inbox: 00-Inbox/2026-04-02-voice-note.md",
  "due_date": "2026-04-11T17:00:00Z",
  "priority": 2,
  "start_date": null,
  "repeat_after": 7776000,
  "repeat_mode": 0
}
```

Response: Task object with `id` field.

**Rules**:
- `PROJECT_ID` resolved at runtime by project name via `GET /projects` — never hardcoded
- `description` prefixed with `[Felix]` per agent comment convention
- `priority`: 1=low, 2=medium, 3=high, 4=urgent, 5=critical
- `repeat_after` in seconds; `repeat_mode`: 0=default, 1=monthly, 2=from-current-date

### Step 2: Add Identity Label

```
PUT /tasks/{TASK_ID}/labels
```

```json
{
  "label_id": 1
}
```

**Rules**:
- `label_id` resolved at runtime by label name via `GET /labels` — never hardcoded
- Identity labels: personal (blue), intentional (green), metalcasework (orange)

## Task Relation Creation

```
PUT /tasks/{TASK_ID}/relations
```

```json
{
  "other_task_id": 42,
  "relation_kind": "subtask"
}
```

**Supported relation kinds for F013**: `subtask`, `parenttask`, `related`, `blocking`, `blocked`

**Rules**:
- Relations are directional — `subtask` on task A pointing to task B means B is a subtask of A
- Goal relationships use `related` relation kind (linking task to goal task in Goals project)
- Task and related task can be in different projects

## Enrichment State Comments

### Write enrichment state

```
PUT /tasks/{TASK_ID}/comments
```

```json
{
  "comment": "[Felix] enrichment | proposed | 2026-04-02T12:00:00Z"
}
```

### Check for existing enrichment state

```
GET /tasks/{TASK_ID}/comments
```

Parse response array for comments matching `[Felix] enrichment |` prefix. Statuses:
- `proposed` — enrichment offered, awaiting response
- `confirmed` — enrichment accepted and applied
- `skipped` — Kent skipped this task
- `declined` — Kent declined enrichment

**Rules**:
- Before proposing enrichment, check for existing enrichment comments
- If `skipped` or `declined` comment exists, do not re-propose
- If `proposed` comment exists and is older than 24 hours with no resolution, may re-propose once

## Duplicate Detection

Before creating any task:

```
GET /projects/{PROJECT_ID}/tasks?s=SEARCH_TERM
```

Search by title. If exact match found, do not create duplicate.

## Incomplete Task Detection Query

```
GET /tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%201&sort_by=created&order_by=asc&per_page=50
```

Identifies incomplete tasks in Inbox (project_id=1) that are not done. Then filter client-side for:
- No due_date (null or zero)
- No identity label (empty labels array)
- No enrichment comment already present

## Marking Repeating Tasks Done (Caveat)

When marking a repeating task as done, always include repeat fields to prevent zero-value clearing:

```
POST /tasks/{TASK_ID}
```

```json
{
  "done": true,
  "repeat_after": 604800,
  "repeat_mode": 0
}
```

## Error Handling

| Status | Meaning | Action |
|---|---|---|
| 401 | Auth failure | Log, alert Kent, halt |
| 403 | Permission denied | Log, alert Kent, halt |
| 404 | Resource not found | Log, skip task, continue batch |
| 500 | Server error | Log, retry with backoff (max 3), then alert |
| Network error | Service unreachable | Log, alert Kent, halt batch |
