# Vikunja API Contract (v0.24.6)

Base URL: `https://office2.tail0f5f56.ts.net/api/v1`
Auth: `Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)`

## Health Check

```
GET /info
→ 200: {"version": "v0.24.6", "frontend_url": "...", ...}
No auth required.
```

## Projects

```
GET /projects
→ 200: [{"id": 11, "title": "Goals", ...}, ...]
Includes pseudo-projects: Today (id=-2), Upcoming (id=-3), Overdue (id=-4).
```

## Tasks

### Create Task

```
PUT /projects/{project_id}/tasks
Body: {"title": "...", "description": "...", "due_date": "2026-04-15T00:00:00Z", "priority": 1}
→ 200: {"id": 42, "title": "...", ...}
Labels must be assigned separately after creation.
```

### Read Task

```
GET /tasks/{id}
→ 200: {"id": 42, "title": "...", "done": false, "labels": [...], ...}
```

### Update Task

```
POST /tasks/{id}
Body: {"description": "updated", "done": true}  (partial update)
→ 200: {"id": 42, ...}
```

### Delete Task

```
DELETE /tasks/{id}
→ 200
```

### List All Tasks (with filtering)

```
GET /tasks/all?filter=done%20%3D%20false&sort_by=due_date&order_by=asc&per_page=50
→ 200: [{"id": 42, ...}, ...]
```

Filter examples:
- `done = false` — incomplete tasks
- `project_id = 11` — tasks in Goals project
- `due_date < 2026-04-01T00:00:00Z` — tasks due before date

### Get Project Tasks

```
GET /projects/{project_id}/tasks
→ 200: [{"id": 42, ...}, ...]
Works with pseudo-projects: /projects/-2/tasks (Today), /projects/-3/tasks (Upcoming)
```

## Labels

### List All Labels

```
GET /labels
→ 200: [{"id": 1, "title": "personal", "hex_color": "2196f3"}, ...]
```

### Add Label to Task

```
PUT /tasks/{task_id}/labels
Body: {"label_id": 1}
→ 200
```

### Remove Label from Task

```
DELETE /tasks/{task_id}/labels/{label_id}
→ 200
```

### Get Task Labels

```
GET /tasks/{task_id}/labels
→ 200: [{"id": 1, "title": "personal", ...}, ...]
```

## Comments

### Add Comment

```
PUT /tasks/{task_id}/comments
Body: {"comment": "[Felix] Task created by OpenClaw agent"}
→ 200: {"id": 1, "comment": "...", ...}
```

### Get Comments

```
GET /tasks/{task_id}/comments
→ 200: [{"id": 1, "comment": "...", "author": {...}, ...}, ...]
```

## Saved Filters

### List Saved Filters

```
GET /filters
→ 200: [{"id": 1, "title": "Goals", "filters": "...", ...}]
Note: No user-created saved filters exist yet. Today/Upcoming/Overdue
are pseudo-projects, not saved filters.
```

## Error Responses

All error responses return JSON:

```json
{"message": "error description", "code": 400}
```

Common errors:
- 401: `{"message": "missing, malformed, expired or otherwise invalid token provided"}`
- 403: `{"message": "Forbidden"}`
- 404: `{"message": "Not Found"}`
- 500: `{"message": "Internal server error"}`
