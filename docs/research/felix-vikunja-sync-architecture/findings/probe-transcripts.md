---
rq_id: "RQ-1"
title: "Vikunja API probe transcripts"
wp: "WP01"
---

# RQ-1 — Probe Transcripts

Raw HTTP probes against `https://office2.tail0f5f56.ts.net/api/v1` (Vikunja v0.24.6).
Probes executed via SSH to office2-claude on 2026-06-03. Token file: `/data/services/openclaw/secrets/vikunja-api` (read on-server; never echoed). Token length: 43 characters (prefix `tk_`).

---

## Probe 1 — GET /info (no auth)

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/info
```

**Response**: HTTP 200
```json
{
  "version": "v0.24.6",
  "frontend_url": "https://office2.tail0f5f56.ts.net/",
  "motd": "",
  "link_sharing_enabled": true,
  "max_file_size": "20MB",
  "registration_enabled": true,
  "available_migrators": ["vikunja-file", "ticktick"],
  "task_attachments_enabled": true,
  "enabled_background_providers": ["upload"],
  "totp_enabled": true,
  "legal": {"imprint_url": "", "privacy_policy_url": ""},
  "caldav_enabled": true,
  "auth": {
    "local": {"enabled": true},
    "openid_connect": {"enabled": false, "providers": null}
  },
  "email_reminders_enabled": true,
  "user_deletion_enabled": true,
  "task_comments_enabled": true,
  "demo_mode_enabled": false,
  "webhooks_enabled": true,
  "public_teams_enabled": false
}
```

**Key facts**: Server version `v0.24.6`. `webhooks_enabled: true`. `caldav_enabled: true`. `registration_enabled: true`. No auth required for this endpoint.

---

## Probe 2 — GET /tasks/all?per_page=1 (representative task schema)

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/all?per_page=1
Authorization: Bearer <token>
```

**Response**: HTTP 200, `x-pagination-result-count: 1`, `x-pagination-total-pages: 21`
```json
[{
  "id": 1,
  "title": "Intentional: $5K/month consulting income",
  "description": "...",
  "done": false,
  "done_at": "0001-01-01T00:00:00Z",
  "due_date": "2026-09-30T00:00:00Z",
  "reminders": null,
  "project_id": 11,
  "repeat_after": 0,
  "repeat_mode": 0,
  "priority": 0,
  "start_date": "0001-01-01T00:00:00Z",
  "end_date": "0001-01-01T00:00:00Z",
  "assignees": null,
  "labels": [{"id": 2, "title": "intentional", "description": "", "hex_color": "4caf50", "created_by": {...}, "created": "...", "updated": "..."}],
  "hex_color": "",
  "percent_done": 0,
  "identifier": "#1",
  "index": 1,
  "related_tasks": {},
  "attachments": null,
  "cover_image_attachment_id": 0,
  "is_favorite": false,
  "created": "2026-03-30T14:48:55Z",
  "updated": "2026-05-17T08:21:06Z",
  "bucket_id": 0,
  "position": 0,
  "reactions": null,
  "created_by": {"id": 1, "name": "", "username": "kent", "created": "...", "updated": "..."}
}]
```

**Pagination headers**: `x-pagination-total-pages` and `x-pagination-result-count` are exposed per the `access-control-expose-headers` header. Total task count derivable via `per_page=1` trick.

---

## Probe 3 — GET /tasks/1 (full task representation)

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/1
Authorization: Bearer <token>
```

**Response**: HTTP 200 — same schema as Probe 2 (single object, not array). Full field set confirmed identical to array item shape. `identifier: "#1"`, `id: 1`, `index: 1`.

---

## Probe 4 — GET /projects (project schema)

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/projects
Authorization: Bearer <token>
```

**Response**: HTTP 200 — array of 14 project objects. Sample (project id=1, "Inbox"):
```json
{
  "id": 1,
  "title": "Inbox",
  "description": "",
  "identifier": "",
  "hex_color": "",
  "parent_project_id": 0,
  "owner": {"id": 1, "name": "", "username": "kent", ...},
  "is_archived": false,
  "background_information": null,
  "background_blur_hash": "",
  "is_favorite": false,
  "position": 65536,
  "views": [
    {"id": 1, "title": "List", "project_id": 1, "view_kind": "list", "filter": "done = false", ...},
    {"id": 2, "title": "Gantt", "project_id": 1, "view_kind": "gantt", "filter": "", ...},
    {"id": 3, "title": "Table", "project_id": 1, "view_kind": "table", "filter": "", ...},
    {"id": 4, "title": "Kanban", "project_id": 1, "view_kind": "kanban", "filter": "", ...}
  ],
  "created": "2026-03-26T15:23:35Z",
  "updated": "2026-05-28T22:15:31Z"
}
```

**Key facts**: 14 projects total. Projects include Inbox (id=1), Everyday (2), Someday (4), Goals (11), Habits (13), Inbox/felix-bot-owned (14). Project identifier field is empty string (not populated for these projects). Views are per-project saved configurations with `filter` field. Default "List" view on Inbox uses `filter: "done = false"`.

---

## Probe 5 — Filter probe 1: done = false

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done+%3D+false&per_page=1
Authorization: Bearer <token>
```

**Response**: HTTP 200, `x-pagination-total-pages: 21` (21 undone tasks). Returns undone tasks. Filter accepted.

---

## Probe 6 — Filter probe 2: done = true

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done+%3D+true&per_page=1
Authorization: Bearer <token>
```

**Response**: HTTP 200, `x-pagination-total-pages: 44` (44 done tasks). Filter accepted.

---

## Probe 7 — Filter probe 3: due_date < now

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=due_date+%3C+now&per_page=1
Authorization: Bearer <token>
```

**Response**: HTTP 200. Returns overdue tasks (task id=7, done=true, due 2026-04-01). Filter accepted. Date math with `now` anchor works.

---

## Probe 8 — Filter probe 4: project_id = 13

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=project_id+%3D+13&per_page=1
Authorization: Bearer <token>
```

**Response**: HTTP 200. Returns habits tasks (project_id=13). Filter accepted on numeric project_id.

---

## Probe 9 — Filter probe 5: done != false (G7 class test)

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done+%21%3D+false&per_page=1
Authorization: Bearer <token>
```

**Response**: HTTP 200. Returns done tasks. `!=` operator works on boolean fields. **G7 rejection class (compound AND) is not triggered here** — this was a simple single-clause filter. G7 applies specifically to compound expressions combining date comparison AND done=false in a single filter string. The compound rejection was fixed in issue #336.

---

## Probe 10 — Batch probe: GET /tasks/bulk

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/bulk
Authorization: Bearer <token>
```

**Response**: HTTP 400
```json
{"message": "strconv.ParseInt: parsing \"bulk\": invalid syntax"}
```

**Finding**: No `GET /tasks/bulk` endpoint. The path `/tasks/bulk` is parsed as `/tasks/{id}` where `id=bulk` fails integer parsing. There is no batch-GET endpoint for tasks; bulk operations in Vikunja v0.24.6 are write-only (bulk task updates via `POST /tasks/bulk` for writes). Read access is per-task or via `/tasks/all` with pagination.

---

## Probe 11 — Webhook probe: GET /projects/1/webhooks

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/projects/1/webhooks
Authorization: Bearer <token>
```

**Response**: HTTP 200
```json
[]
```

**Finding**: Webhook endpoint exists and is accessible. Zero webhooks configured on project 1. Server-side webhooks are available (consistent with `webhooks_enabled: true` from /info) but unconfigured on all projects per operational status (confirmed via prior research in `vikunja-task-model-research.md`).

---

## Probe 12 — updated_since probe

**Request**:
```
GET https://office2.tail0f5f56.ts.net/api/v1/tasks/all?updated_since=2026-06-01T00:00:00Z&per_page=3
Authorization: Bearer <token>
```

**Response**: HTTP 200 — returns tasks updated since 2026-06-01. The `updated_since` parameter is accepted and filters by the task's `updated` field. This is the primary mechanism for incremental polling (delta detection).
