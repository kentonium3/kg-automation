# Research: Vikunja API Skill

## Decision 1: Skill Architecture

**Decision**: The skill is a SKILL.md instruction document, not executable code.

**Rationale**: OpenClaw skills are SKILL.md files with YAML frontmatter and markdown
instructions. The agent reads the instructions and uses the `exec` tool to run curl
commands. This matches the deployed Whisper skill pattern exactly.

**Alternatives considered**:
- Python module skill — not supported by OpenClaw skill format
- MCP server — over-engineered for a REST API wrapper
- Direct tool declaration in frontmatter — not needed; `exec` + curl is sufficient

## Decision 2: Credential Access

**Decision**: The SKILL.md instructs the agent to read the API token from
`/data/services/openclaw/secrets/vikunja-api` via `$(cat ...)` in curl commands.

**Rationale**: This keeps the token out of the SKILL.md source while making it
available at runtime. The Whisper skill uses a similar pattern (hardcoded URL,
no auth needed). For Vikunja, Bearer auth is required, and the token is already
in the credential store.

**Alternatives considered**:
- `skills.entries.vikunja-api.env` in openclaw.json — would require putting the
  token value in a config file; less secure than reading from the 600-mode secret file
- `skills.entries.vikunja-api.apiKey` with SecretRef — designed for env vars, not
  file-based secrets; would require restructuring the credential store

## Decision 3: Saved Filters vs Pseudo-Projects

**Decision**: "Today" (id=-2), "Upcoming" (id=-3), and "Overdue" (id=-4) are
pseudo-projects accessed via `/projects/{id}/tasks`. "Goals" is a real project
(id=11), not a saved filter. User-created saved filters use `/filters` endpoint.

**Rationale**: Verified via live API exploration. The pseudo-projects have negative
IDs and are returned by the `/projects` endpoint. The `/filters` endpoint is for
user-created saved filters (none exist yet for Goals — the F006 "Goals" saved
filter is actually a pseudo-project shortcut in the Vikunja UI, not an API filter).

**Alternatives considered**: None — this is how Vikunja works in v0.24.6.

## Decision 4: Skill Deployment Location

**Decision**: Deploy to `~/.openclaw/skills/vikunja-api/SKILL.md` on office2.

**Rationale**: This is the "managed/local" skills location, shared across all
agents. The Whisper skill is deployed here. Consistent with the single-agent
setup on office2.

**Alternatives considered**:
- Workspace-level skills — higher precedence but per-agent; unnecessary for
  single-agent setup
- ClawHub publish — premature; this is a private skill for this system

## Decision 5: Task Label Assignment

**Decision**: Labels are assigned via a separate endpoint `PUT /tasks/{task}/labels`
with body `{"label_id": <id>}`, not inline during task creation.

**Rationale**: The Task model's `labels` field is read-only per the API docs:
"This property is read-only, you must use the separate endpoint to add labels
to a task." Task creation returns the task ID, then labels are assigned in a
follow-up call.

## Vikunja API Reference (v0.24.6)

### Verified Endpoints

| Operation | Method | Path | Auth | Notes |
| --- | --- | --- | --- | --- |
| Service info | GET | /api/v1/info | No | Health check, version info |
| List projects | GET | /api/v1/projects | Yes | Includes pseudo-projects (negative IDs) |
| Create task | PUT | /api/v1/projects/{id}/tasks | Yes | Body: models.Task |
| Get task | GET | /api/v1/tasks/{id} | Yes | Returns full task object |
| Update task | POST | /api/v1/tasks/{id} | Yes | Body: models.Task (partial) |
| Delete task | DELETE | /api/v1/tasks/{id} | Yes | |
| List all tasks | GET | /api/v1/tasks/all | Yes | Supports filter, sort, pagination |
| Get task labels | GET | /api/v1/tasks/{task}/labels | Yes | |
| Add label to task | PUT | /api/v1/tasks/{task}/labels | Yes | Body: {"label_id": N} |
| Remove label | DELETE | /api/v1/tasks/{task}/labels/{label} | Yes | |
| List labels | GET | /api/v1/labels | Yes | |
| Get comments | GET | /api/v1/tasks/{taskID}/comments | Yes | |
| Add comment | PUT | /api/v1/tasks/{taskID}/comments | Yes | Body: {"comment": "text"} |
| List saved filters | GET | /api/v1/filters | Yes | User-created filters |
| Get saved filter | GET | /api/v1/filters/{id} | Yes | |

### Pseudo-Projects (built-in)

| ID | Name | Purpose |
| --- | --- | --- |
| -2 | Today | Tasks due today |
| -3 | Upcoming | Tasks due soon |
| -4 | Overdue | Past-due tasks |

### Real Projects (current state)

| ID | Name |
| --- | --- |
| 1 | Inbox |
| 2 | Everyday |
| 5 | Personal Growth & Transformation |
| 6 | Business Acquisition |
| 8 | Health & Conditioning |
| 9 | Intentional LLC |
| 10 | Metal Casework |
| 11 | Goals |

### Labels (current state)

| ID | Name | Color |
| --- | --- | --- |
| 1 | personal | #2196f3 (blue) |
| 2 | intentional | #4caf50 (green) |
| 3 | metalcasework | #ff9800 (orange) |

### Authentication

- Header: `Authorization: Bearer <token>`
- Token location: `/data/services/openclaw/secrets/vikunja-api` (mode 600, claude-owned)
- Token verified working as of 2026-03-30

### Task Model Key Fields

| Field | Type | Notes |
| --- | --- | --- |
| title | string | Required for creation |
| description | string | Optional |
| due_date | string | ISO 8601 datetime |
| priority | integer | User-defined numeric priority |
| done | boolean | Completion status |
| project_id | integer | Read-only on response; set via URL on create |
| labels | array | Read-only; use separate endpoint |
| percent_done | number | 0.0 to 1.0 |

### Filter Query Syntax (GET /tasks/all)

The `filter` query parameter uses Vikunja's filter syntax. Key operators:
- `done = false` — incomplete tasks
- `project_id = 11` — tasks in Goals project
- Combinable with `sort_by` and `order_by` params

### OpenClaw Skill System (verified)

- Whisper skill is deployed at `~/.openclaw/skills/whisper/SKILL.md` (status: ready)
- Skills are loaded on new session or gateway restart
- `openclaw skills list` shows installed skills
- Skills watcher auto-refreshes when SKILL.md files change
- 51 bundled skills, 10 ready (including whisper)
