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
