---
name: vikunja_api
description: Create, read, update, and query tasks in Vikunja via its REST API. Use when an agent needs to manage tasks, goals, labels, or projects in the Vikunja task store.
version: 1.0.0
---

# Vikunja API Skill

Vikunja is the task management system running on office2. It stores tasks, goals,
projects, labels, and saved filters. This skill teaches you how to interact with
the Vikunja REST API (v0.24.6) using curl via the `exec` tool.

**Supported operations**: Create, read, update, complete, and delete tasks.
Query projects and labels by name. Execute filters (Today, Upcoming, Overdue,
Goals). Add and read task comments.

**API Base URL**:

```
https://office2.tail0f5f56.ts.net/api/v1
```

All commands below use the `exec` tool to run curl. Replace placeholder values
(TASK_ID, PROJECT_ID, LABEL_ID) with actual values obtained from resolution
steps.

## Health Check

Before performing any operation, verify the Vikunja service is running:

```bash
curl -s https://office2.tail0f5f56.ts.net/api/v1/info
```

This endpoint requires **no authentication**. Expected response:

```json
{"version": "v0.24.6", "frontend_url": "https://office2.tail0f5f56.ts.net/", ...}
```

If this fails or returns a connection error, Vikunja is unreachable. Report this
to the user — do not attempt other operations until the service is confirmed
running.

## Authentication

All endpoints except `/info` require a Bearer token. The token is stored on
office2 at `/data/services/openclaw/secrets/vikunja-api` (mode 600, claude-owned).

Include this header in every authenticated request:

```bash
-H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)"
```

This reads the token from the credential store at runtime. **Never** log, print,
or include the token value in output. If you receive an HTTP 401 response, report
it as a credential error — the token may be expired or revoked. See the
vikunja-ops.md runbook for the token rotation procedure.

## Projects

### List All Projects

```bash
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/projects
```

Returns a JSON array of projects. Each project has `id`, `title`, and other
metadata.

### Resolve a Project by Name

To find a project's ID, list all projects and search for the one where `title`
matches the name you need. For example, to find the Goals project:

1. List all projects (command above)
2. Parse JSON and find the entry where `title` is `"Goals"`
3. Use its `id` value (currently 11, but always resolve by name)

**NEVER hardcode project IDs.** IDs can change if Vikunja is re-provisioned.
Always resolve by name at runtime.

### Pseudo-Projects (Built-in Filters)

Vikunja provides built-in pseudo-projects with negative IDs:

| Name | ID | Purpose |
| --- | --- | --- |
| Today | -2 | Tasks due today |
| Upcoming | -3 | Tasks due soon |
| Overdue | -4 | Past-due tasks |

Access them like regular projects: `GET /projects/{id}/tasks`. For example:

```bash
# Get today's tasks
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/projects/-2/tasks
```

### Current Projects (reference only — resolve by name)

| Name | Current ID | Notes |
| --- | --- | --- |
| Inbox | 1 | Default inbox |
| Everyday | 2 | Day-to-day tasks |
| Personal Growth & Transformation | 5 | |
| Business Acquisition | 6 | |
| Health & Conditioning | 8 | |
| Intentional LLC | 9 | |
| Metal Casework | 10 | |
| Goals | 11 | Goal declarations (F006) |

## Labels

### List All Labels

```bash
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/labels
```

Returns a JSON array. Each label has `id`, `title`, and `hex_color`.

### Resolve a Label by Name

Search the label list for the entry where `title` matches the name you need.

**NEVER hardcode label IDs.** Always resolve by name at runtime.

### Identity Labels

Every task created by an agent **MUST** have one of these identity labels:

| Name | Current ID | Color | Purpose |
| --- | --- | --- | --- |
| personal | 1 | #2196f3 (blue) | Kent's personal Google identity |
| intentional | 2 | #4caf50 (green) | Intentional LLC identity |
| metalcasework | 3 | #ff9800 (orange) | Metal Casework business |

If the caller does not specify which identity label to use, ask them before
creating the task. Do not guess or default — the identity label is a required
business rule.

## Tasks

### Create Task

Creating a task is a two-step process: create the task, then add an identity label.

**Step 1 — Create the task in a project:**

```bash
curl -s -X PUT \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00Z", "priority": 1}' \
  https://office2.tail0f5f56.ts.net/api/v1/projects/PROJECT_ID/tasks
```

- Replace `PROJECT_ID` with the ID obtained from project resolution (never hardcode)
- `title` is required. `description`, `due_date`, and `priority` are optional.
- `due_date` must be ISO 8601 format (e.g., `2026-04-15T00:00:00Z`)
- `priority` is an integer (higher = more important)
- The response includes the new task's `id` — save it for the next step

**Step 2 — Add an identity label:**

```bash
curl -s -X PUT \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d '{"label_id": LABEL_ID}' \
  https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/labels
```

- Replace `LABEL_ID` with the ID obtained from label resolution (never hardcode)
- Replace `TASK_ID` with the ID returned in Step 1
- **Every agent-created task MUST have an identity label.** If the caller does not
  specify one, ask before creating.

**Required fields for task creation:**
- `title` — the task text
- Project — specified by name, resolved to ID via the Projects section
- Identity label — one of personal, intentional, or metalcasework

**Optional fields:**
- `description` — task description (supports markdown)
- `due_date` — ISO 8601 datetime
- `priority` — integer

If Step 2 (label assignment) fails after Step 1 succeeds, report that the task
was created but the label could not be assigned. Include the task ID so it can
be fixed manually.

### Duplicate Check (Idempotent Creation)

Before creating a task, check if one with the same title already exists in the
target project:

```bash
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  "https://office2.tail0f5f56.ts.net/api/v1/projects/PROJECT_ID/tasks?s=SEARCH_TERM"
```

- The `s` parameter searches task titles
- If a task with an **exact** title match is found, return it instead of creating
  a new one
- If partial matches are found, surface them to the caller for confirmation
- Only create a new task if no exact match exists

### Read Task

```bash
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
```

Returns the full task object including:
- `id`, `title`, `description` — task content
- `due_date`, `done`, `done_at` — status and dates
- `priority` — numeric priority
- `project_id` — which project the task belongs to
- `labels` — array of assigned labels (read-only here, populated automatically)
- `created`, `updated` — timestamps

### Update Task

```bash
curl -s -X POST \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated description"}' \
  https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
```

- Uses **POST** (not PUT) — this is the Vikunja convention for updates
- Send only the fields you want to change (partial update)
- Updatable fields: `title`, `description`, `due_date`, `priority`, `done`,
  `hex_color`, `percent_done`, `start_date`, `end_date`, `repeat_after`

### Complete Task

Mark a task as done:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d '{"done": true}' \
  https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
```

This is a convenience alias — it's just an update that sets `done: true`.
Vikunja will auto-populate `done_at` with the current timestamp.

### Delete Task

```bash
curl -s -X DELETE \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
```

**WARNING: DELETE IS PERMANENT.** Vikunja v0.24.6 has no soft-delete or archive
endpoint. Once deleted, a task cannot be recovered.

- Only use for test cleanup or when explicitly requested by Kent
- Prefer marking tasks as complete (`done: true`) rather than deleting
- Always confirm with the caller before deleting a task

## Filters and Queries

### Built-in Pseudo-Project Filters

Get tasks from the built-in filters using pseudo-project IDs:

```bash
# Today's tasks
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/projects/-2/tasks

# Upcoming tasks
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/projects/-3/tasks

# Overdue tasks
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/projects/-4/tasks
```

### Active Goals (Goals Project)

Goals is a real project (not a pseudo-project). Query active goal declarations:

```bash
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  "https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%20GOALS_PROJECT_ID&sort_by=due_date&order_by=asc"
```

Replace `GOALS_PROJECT_ID` with the ID resolved by name from the Projects section
(currently 11).

### Ad-Hoc Queries

Use `GET /tasks/all` with query parameters to filter tasks:

```bash
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  "https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=FILTER_EXPRESSION&sort_by=FIELD&order_by=ORDER&per_page=50"
```

**Filter syntax** (URL-encode spaces and operators):
- `done = false` — incomplete tasks
- `project_id = 11` — tasks in a specific project
- `due_date < 2026-04-01T00:00:00Z` — tasks due before a date
- Combine with `&&`: `done = false && project_id = 11`

**Sort options**:
- `sort_by=due_date&order_by=asc` — by due date, earliest first
- `sort_by=priority&order_by=desc` — by priority, highest first
- `sort_by=created&order_by=desc` — newest first

**Pagination**: `page=1&per_page=50` (default page size varies)

**Important**: URL-encode filter expressions. Spaces become `%20`, `=` becomes
`%3D`, `&&` becomes `%26%26`, `<` becomes `%3C`.

### Response Fields for Briefings

Filter results include these key fields per task:
- `title` — task text
- `due_date` — when the task is due
- `priority` — numeric priority
- `project_id` — which project it belongs to
- `labels` — array of assigned labels
- `done` — completion status

## Comments

### Add Comment

```bash
curl -s -X PUT \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d '{"comment": "[Felix] COMMENT_TEXT"}' \
  https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/comments
```

**All agent comments MUST be prefixed with `[Felix]`** to distinguish them from
human comments. For example:
- `[Felix] Task created from inbox processing`
- `[Felix] Escalation: task overdue by 3 days`
- `[Felix] Goal progress update: 60% complete`

### Read Comments

```bash
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/comments
```

Returns a JSON array of comments. Each comment has `id`, `comment` (text),
`author` (user object), `created`, and `updated`.

## Error Handling

### Pre-Flight Validation

Before making any API call, validate the inputs:

- **Missing title** on task creation: reject immediately with a clear error
- **Missing identity label** on task creation: reject — ask the caller which label
- **Missing project** on task creation: reject — ask the caller which project
- **Malformed date**: reject if `due_date` is not valid ISO 8601
- **Unknown project name**: reject if name resolution returns no match
- **Unknown label name**: reject if name resolution returns no match

**Do not make the API call if validation fails.** Return a specific validation
error describing what is missing or invalid.

### HTTP Error Responses

Vikunja returns JSON errors: `{"message": "error description"}`

**401 — Authentication failure**:
- Message: `"missing, malformed, expired or otherwise invalid token provided"`
- This is a **permanent error** — do not retry
- Report as a credential error: the API token may be expired or revoked
- Refer to vikunja-ops.md for the token rotation procedure

**403 — Permission denied**:
- The API token has insufficient permissions for this operation
- Report the error with the operation that was attempted

**404 — Not found**:
- Task, project, or resource does not exist
- Report the specific ID or name that was not found
- Do not guess alternatives — report exactly what was searched

**500 — Server error**:
- This is a **transient error** — may succeed on retry
- Report the error and suggest checking Vikunja logs on office2

**Network / connection errors** (curl returns non-zero, no HTTP response):
- Vikunja is unreachable — this is a **transient error**
- Report that the service is down and do not retry automatically
- Suggest checking the service status on office2

### Constitution Directives

**NEVER fail silently.** Every error — validation, HTTP, or network — must
produce a clear error message to the caller explaining what happened and what
to do about it.

**NEVER invent data.** If a project name doesn't resolve, a label doesn't exist,
or a required field is missing — halt and report. Do not substitute defaults,
guess values, or proceed with partial data.

**HALT on ambiguity.** If the input is unclear or incomplete, return a specific
error explaining what is needed. Do not attempt partial execution.

## Usage Examples

### Create a Goal Declaration

1. Check health: `curl -s https://office2.tail0f5f56.ts.net/api/v1/info`
2. Resolve Goals project ID: list projects, find "Goals", get its `id`
3. Resolve metalcasework label ID: list labels, find "metalcasework", get its `id`
4. Check for duplicates: search tasks in Goals project for the same title
5. Create task: `PUT /projects/{goals_id}/tasks` with title, description, due date
6. Add label: `PUT /tasks/{task_id}/labels` with metalcasework label ID
7. Confirm to the caller: "Created goal declaration '{title}' in Goals project with metalcasework label, due {date}"

### Show Overdue Tasks

1. Check health
2. Get overdue tasks: `GET /projects/-4/tasks`
3. Present results with title, due date, project, and labels for each task

### Add a Note to a Task

1. Read the task to confirm it exists: `GET /tasks/{id}`
2. If not found, report the error
3. Add comment: `PUT /tasks/{id}/comments` with `[Felix]` prefix
4. Confirm: "Added comment to task #{id}: '{title}'"

### Show Active Goals Sorted by Deadline

1. Check health
2. Resolve Goals project ID by name
3. Query: `GET /tasks/all?filter=done = false && project_id = {goals_id}&sort_by=due_date&order_by=asc`
4. Present results sorted by due date with title, deadline, and labels
