# Research: Vikunja Task Intelligence Agent

**Feature**: 013-vikunja-task-intelligence-agent
**Date**: 2026-04-02

## Research Item 1: Vikunja Task Relations API (v0.24.6)

**Decision**: Use Vikunja's native task relation API for subtask, related, and blocking relationships.

**Findings**:

### Endpoints

- **Create relation**: `PUT /api/v1/tasks/{taskID}/relations`
  - Body: `{"other_task_id": <int>, "relation_kind": "<kind>"}`
  - Response 201: Returns `TaskRelation` object with `task_id`, `other_task_id`, `relation_kind`, `created_by`, `created`
  - Permissions: Update on base task, read on other task. Tasks can be in different projects.

- **Delete relation**: `DELETE /api/v1/tasks/{taskID}/relations/{relationKind}/{otherTaskID}`
  - Response 200: `{"message": "Successfully deleted."}`

- **Read relations**: Returned as part of the task object via `GET /api/v1/tasks/{id}` — no dedicated list endpoint.

### Supported Relation Kinds

| Value | Meaning |
|---|---|
| `subtask` | Other task is a subtask of base task |
| `parenttask` | Other task is parent of base task |
| `related` | Tasks are related (symmetric) |
| `blocking` | Base task blocks the other task |
| `blocked` | Base task is blocked by other task |
| `precedes` | Base task precedes other task |
| `follows` | Base task follows other task |
| `duplicateof` | Base task duplicates other task |
| `duplicates` | Inverse of duplicateof |
| `copiedfrom` | Base task copied from other task |
| `copiedto` | Base task copied to other task |

**Rationale**: Native API is clean and supports all relation types needed by the spec (subtask/parent, related, blocking/blocked). No workaround needed.

**Alternatives considered**: Using Vikunja comments to encode relationships as text. Rejected — native API provides queryable, structured relations.

---

## Research Item 2: Vikunja repeat_after Field Format

**Decision**: Use `repeat_after` as integer seconds with `repeat_mode` to control repeat behavior.

**Findings**:

### Field Format

- **`repeat_after`**: `int64`, value in **seconds**. `0` = no repeat (unless `repeat_mode` is 1/Month).
- **`repeat_mode`**: Integer enum controlling how the interval is applied.

| repeat_mode | Name | Behavior |
|---|---|---|
| `0` | Default | Adds `repeat_after` seconds to all dates. Skips forward past missed intervals. |
| `1` | Month | Adds one calendar month. **Ignores `repeat_after` entirely.** |
| `2` | FromCurrentDate | Adds `repeat_after` seconds to current time (not old date). |

### Common Intervals

| Interval | repeat_after | repeat_mode |
|---|---|---|
| Daily | 86400 | 0 |
| Weekly | 604800 | 0 |
| Bi-weekly | 1209600 | 0 |
| Monthly | 0 | 1 |
| Every 3 months | 7776000 | 0 |
| Every N days from completion | N * 86400 | 2 |

### Critical API Caveat

When marking a repeating task as done via `POST /tasks/{id}` with `{"done": true}`, Go's zero-value semantics can clear `repeat_after` to 0. **Always include `repeat_after` and `repeat_mode` in the update payload when marking a repeating task done.**

### Completion Behavior

When a repeating task is marked done:
1. `done_at` set to current timestamp
2. All dates (due_date, start_date, end_date, reminders) advanced by the interval
3. `done` set back to `false` — task automatically reappears

**Rationale**: Seconds-based format is simple and covers all common intervals. The task-intelligence skill must include a conversion table (human-readable interval → seconds) so the agent can translate Kent's natural language ("every 3 months") to the correct value.

**Alternatives considered**: ISO 8601 duration strings — not supported by Vikunja's data model.

---

## Research Item 3: OpenClaw Agent-to-Agent Communication

**Decision**: Use OpenClaw's explicit delegation pattern (`openclaw agent --agent`) for felix-admin-capture → felix-admin-tasker handoff, with polling fallback for incomplete task detection.

**Findings**:

### Delegation Mechanism

OpenClaw supports agent-to-agent delegation via CLI:

```bash
openclaw agent --agent <target-agent> --message "<message>" --json --timeout <seconds>
```

### Existing Patterns

Two deployed delegation patterns confirm the mechanism works:

1. **Inbox delegation** (main → felix-admin-capture):
   ```bash
   openclaw agent --agent felix-admin-capture \
     --message "Process the inbox now..." --json --timeout 300
   ```

2. **Habits delegation** (main → felix-admin-habits):
   ```bash
   openclaw agent --agent felix-admin-habits \
     --message "<Kent's exact message>" --json --timeout 120
   ```

### Design Principles

- **Message-passing**: Agents communicate by sending messages, not function calls
- **Isolation**: Each agent runs in an isolated session (no shared state)
- **Timeout**: Every delegation includes a timeout (120-300 seconds typical)
- **JSON responses**: Agents return JSON for structured processing
- **Explicit pairs**: Agent-to-agent messaging must be explicitly enabled per pair

### Handoff Architecture for F013

**Primary pattern (agent delegation)**:
- felix-admin-capture delegates to felix-admin-tasker via `openclaw agent --agent felix-admin-tasker --message "<raw task JSON>" --json --timeout 120`
- The message includes: raw task text, source reference, inferred identity label, date/context signals
- felix-admin-tasker processes and initiates WhatsApp conversation for confirmation

**Fallback pattern (flat task + polling)**:
- If felix-admin-tasker delegation fails (timeout, unavailable), felix-admin-capture creates flat task in Inbox (existing behavior)
- felix-admin-tasker's polling loop (FR-015) picks up incomplete tasks and offers enrichment

**Rationale**: Delegation is the proven pattern (two agents already use it). Polling is the natural fallback and also serves the FR-015 requirement for detecting directly-created incomplete tasks.

**Alternatives considered**: Shared filesystem/queue between agents. Rejected — OpenClaw's message-passing is simpler and already deployed.

---

## Research Item 4: Vikunja API Skill Update Requirements

**Decision**: The vikunja-api skill needs additions for task relations and repeat fields. These additions should be part of the task-intelligence skill (FR-021) rather than modifying the existing vikunja-api skill, to keep the API skill generic and the intelligence skill self-contained.

**Findings**:

The existing vikunja-api skill covers task CRUD, labels, projects, comments, and queries. It lists `repeat_after` as an updatable field but does not document:
- The seconds-based format
- The `repeat_mode` field
- The API caveat about zero-value clearing on done
- Task relation endpoints

**Rationale**: The task-intelligence skill will document the complete repeat and relation patterns in its own context, referencing the vikunja-api skill for base CRUD. This keeps the vikunja-api skill stable for other agents while giving felix-admin-tasker complete self-contained instructions.

**Alternative**: Update vikunja-api skill directly. This would benefit all agents but risks breaking existing agents if the skill format changes. Better to update vikunja-api skill in a separate, focused change after F013 is stable.
