# TOOLS.md

## Vikunja API

- Use the vikunja_api skill for all Vikunja operations:
  `cat ~/.openclaw/skills/vikunja-api/SKILL.md`
- Use the escalation skill for the escalation model:
  `cat ~/.openclaw/skills/escalation/SKILL.md`

## Key API operations for escalation

### Query overdue tasks

**`/tasks/all` returns HTTP 400 (code 2004) on Vikunja 2.4.0+** — a v1-layer
regression (#853). Do NOT use it. Query per-project instead:

```
GET /api/v1/projects/{id}/tasks?filter=done = false && priority >= 2&sort_by=due_date&order_by=asc&per_page=50
```

Enumerate in-scope projects via `GET /api/v1/projects` (skip Habits/13, which
is out of escalation scope), page each project, then filter in-agent for
`due_date < today` and merge the results across projects. (URL-encode filter
spaces/operators.)

### Mark task done

```
POST /api/v1/tasks/{id}
Content-Type: application/json

{"done": true}
```

### Reschedule a task (due date)

Reschedules flow through `record_completion --state rescheduled
--reschedule-to YYYY-MM-DD` (see SKILL.md / AGENTS.md). The helper performs
the Vikunja `due_date` PATCH itself, writing an **end-of-day Eastern Time**
instant with the correct DST offset — never a UTC `Z` value (see Date
handling below). Do not `POST`/`PATCH` `due_date` directly.

### Resolve project name

```
GET /api/v1/projects/{project_id}
```

Use the `title` field for the `[Project]` tag in alert messages.

## Priority values

| Value | Meaning | Escalated? |
|-------|---------|-----------|
| 0 | Unset | No |
| 1 | Low | No |
| 2 | Medium | Yes |
| 3 | High | Yes |
| 4 | Urgent | Yes |

## Project exclusions

| ID | Project | Reason |
|----|---------|--------|
| 13 | Habits | Managed by felix-admin-habits |

## Date handling

All dates must be resolved in Kent's timezone (America/New_York), not UTC.
office2 runs in UTC — always use `TZ=America/New_York date` for date
calculations. Due dates are written as **end-of-day ET** with the correct
DST offset (-04:00 for EDT, -05:00 for EST) — never the `Z` (UTC) suffix,
which lands in the prior ET day and mis-dates the task. Reschedules go
through `record_completion`, which enforces this; do not write `due_date`
directly.
