# TOOLS.md

## Vikunja API

- Use the vikunja_api skill for all Vikunja operations:
  `cat ~/.openclaw/skills/vikunja-api/SKILL.md`
- Use the escalation skill for the escalation model:
  `cat ~/.openclaw/skills/escalation/SKILL.md`

## Key API operations for escalation

### Query overdue tasks

```
GET /api/v1/tasks/all?sort_by=due_date&order_by=asc
```

Then filter in-agent: `done = false`, `due_date < today`,
`priority >= 2`, `project_id NOT IN (11, 13)`.

Alternatively, query per-project for each in-scope project.

### Mark task done

```
POST /api/v1/tasks/{id}
Content-Type: application/json

{"done": true}
```

### Update task due date (reschedule)

```
POST /api/v1/tasks/{id}
Content-Type: application/json

{"due_date": "2026-04-10T00:00:00Z"}
```

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
| 11 | Goals | Goals are anchors, not completable tasks |
| 13 | Habits | Managed by felix-admin-habits |

## Privacy

- NEVER access: `/home/kgale/second-brain/notes/02-Growth/_private/`
