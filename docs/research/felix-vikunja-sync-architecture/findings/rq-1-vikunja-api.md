---
rq_id: "RQ-1"
title: "Vikunja API surface"
depends_on: []
wp: "WP01"
tags: [63, 336]
---

# RQ-1 — Vikunja API Surface

**Source of truth**: Live Vikunja instance at `https://office2.tail0f5f56.ts.net/api/v1` (v0.24.6). Probes executed 2026-06-03. Raw transcripts in `findings/probe-transcripts.md`. Secondary reference: `docs/design/research/vikunja-task-model-research.md`.

---

## 1. Server Version

Vikunja version **v0.24.6** — observed (`probe-transcripts.md` Probe 1). `GET /info` requires no authentication; returns server version, enabled features, and auth config.

---

## 2. Task Schema

Full task field set observed from `GET /tasks/all?per_page=1` and `GET /tasks/1` (`probe-transcripts.md` Probes 2–3):

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Vikunja-internal primary key. Auto-assigned. |
| `title` | string | Task title. |
| `description` | string | Free-form. May contain Markdown. |
| `done` | boolean | Current completion state. |
| `done_at` | ISO-8601 | Timestamp of most recent `done=true`. Zero sentinel: `0001-01-01T00:00:00Z`. Scalar — overwritten each cycle. |
| `due_date` | ISO-8601 | Zero sentinel same as `done_at`. |
| `start_date` | ISO-8601 | Zero sentinel same as `done_at`. |
| `end_date` | ISO-8601 | Zero sentinel same as `done_at`. |
| `reminders` | array or null | Array of reminder objects. |
| `project_id` | integer | Parent project. Required. |
| `repeat_after` | integer | Recurrence interval in seconds (0 = no recurrence). |
| `repeat_mode` | integer | 0=interval, 1=monthly, 2=from-current-date. |
| `priority` | integer | 0–5. |
| `assignees` | array or null | User assignees. |
| `labels` | array | Label objects with `id`, `title`, `hex_color`, `created_by`. |
| `hex_color` | string | Task color. |
| `percent_done` | float | 0–1. |
| `identifier` | string | Human-readable UI identifier (e.g., `#1`). Project-scoped. |
| `index` | integer | Sequential index within the project. |
| `related_tasks` | object | Relation map (empty `{}` if none). |
| `attachments` | array or null | File attachments. |
| `cover_image_attachment_id` | integer | 0 if no cover. |
| `is_favorite` | boolean | User-starred flag. |
| `created` | ISO-8601 | Creation timestamp. Immutable. |
| `updated` | ISO-8601 | Last-modified timestamp. Updated on any write. |
| `bucket_id` | integer | Kanban bucket ID (0 = unassigned). |
| `position` | float | Sort position. |
| `reactions` | object or null | Emoji reactions. |
| `created_by` | object | `{id, name, username, created, updated}` — the user who created the task. |

observed (`probe-transcripts.md` Probes 2–3)

---

## 3. Project Schema

Full project field set from `GET /projects` (`probe-transcripts.md` Probe 4):

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Vikunja-internal primary key. |
| `title` | string | Project name. |
| `description` | string | Free-form. |
| `identifier` | string | Empty string for most projects in this instance. |
| `hex_color` | string | Project color. |
| `parent_project_id` | integer | 0 if root project. |
| `owner` | object | `{id, name, username, created, updated}`. |
| `is_archived` | boolean | Archived flag. |
| `background_information` | null/object | Background image. |
| `background_blur_hash` | string | Blurhash for background. |
| `is_favorite` | boolean | User-starred. |
| `position` | float | Sort position. |
| `views` | array | Per-project saved view configs. Each: `{id, title, project_id, view_kind, filter, position, bucket_configuration_mode, ...}`. |
| `created` | ISO-8601 | Creation timestamp. |
| `updated` | ISO-8601 | Last-modified timestamp. |

observed (`probe-transcripts.md` Probe 4)

**Instance projects** (14 total): Inbox (1), Everyday (2), Someday (4), Personal Growth (5), Business Acquisition (6), CT-90day (7), Health & Conditioning (8), Intentional LLC (9), Metal Casework (10), Goals (11), Research (12), Habits (13), Inbox/felix-bot (14). observed (`probe-transcripts.md` Probe 4)

---

## 4. Stable Identifier Candidates

Cross-reference: memory `reference_vikunja_id_vs_identifier` — UI shows `identifier` (e.g., `#10`); API uses `id` (e.g., 73).

| Candidate | stability_under_edit | stability_under_delete_recreate | cross_project_uniqueness | surfaced_in_ui | Verdict |
|---|---|---|---|---|---|
| `id` (integer) | Stable (auto-assigned, immutable) | Not stable (delete+recreate gets new id) | Yes — globally unique across all projects | No (not shown in UI by default) | **Suitable** as sync primary key |
| `identifier` (string, e.g. `#1`) | Stable under edits | Potentially reassigned (project-scoped index) | No — project-scoped; `#1` exists in every project | Yes — visible in UI | **Conditional** — suitable for UI display in WhatsApp pings; NOT suitable as primary sync key |
| `index` (integer) | Stable under edits | Potentially reassigned | No — project-scoped | No | **Not suitable** as primary key |
| `created` (ISO-8601) | Immutable (set-once) | Different on recreate | Yes (timestamp unique in practice) | No | **Not suitable** — not an ID field |

**Verdict**: `id` (integer) is the correct primary key for cross-cycle entity re-identification. `identifier` is suitable for human-readable references in WhatsApp conflict pings. observed (`probe-transcripts.md` Probes 2–3) + documented (`reference_vikunja_id_vs_identifier`)

---

## 5. Filter Behavior

Based on live probes (`probe-transcripts.md` Probes 5–9) and prior research (`vikunja-task-model-research.md` §1.4).

### 5.1 Working filter patterns (confirmed on v0.24.6)

| Pattern | Example | Status |
|---|---|---|
| Boolean equality | `done = false` | Works — observed (Probe 5) |
| Boolean inequality | `done != false` | Works — observed (Probe 9) |
| Boolean equality (true) | `done = true` | Works — observed (Probe 6) |
| Date comparison with anchor | `due_date < now` | Works — observed (Probe 7) |
| Numeric equality | `project_id = 13` | Works — observed (Probe 8) |
| Date math (offset) | `done_at >= now-7d` | Works — documented (`vikunja-task-model-research.md` §1.4) |
| Combined AND | `done = false && priority >= 2 && due_date < now/d` | Works — documented (verified task #63) |
| Label membership | `labels in 1` | Works — documented |

### 5.2 G6/G7 filter rejection class

**G6** — `is_archived` field rejected by server-side filter: observed (`vikunja-task-model-research.md` §Appendix G6). `GET /api/v1/projects/<id>/tasks?filter=is_archived=false` returns HTTP 400 with error code 4019. **Workaround**: enumerate all tasks, filter `is_archived` client-side.

**G7** — Compound filter `due_date <= <iso> AND done = false` rejected by server. observed (`vikunja-task-model-research.md` §Appendix G7). Fixed in issue #336 via workaround: enumerate `GET /projects/<id>/tasks` without filter, apply compound filter client-side.

**Current status (2026-06-03 probe)**: Single-clause `done = false` and `done != false` filters work (Probes 5, 6, 9). The G7 compound rejection was a bug specific to the AND-composition of date + done; simple filters are not affected. The workaround (client-side filtering) is already in place in `query_active_habits_v2.py` and `reconcile_completions.py`.

### 5.3 Incremental polling via updated_since

`GET /tasks/all?updated_since=<ISO>` accepts an ISO datetime and returns only tasks with `updated >= <ISO>`. observed (`probe-transcripts.md` Probe 12). This is the correct mechanism for delta polling — fetch only changed tasks since last poll cycle.

---

## 6. Batch Capability

`GET /tasks/bulk` does not exist — the path is parsed as `GET /tasks/{id}` where id="bulk" fails with HTTP 400. observed (`probe-transcripts.md` Probe 10).

Write-side batch: `POST /tasks/bulk` exists for bulk task updates (documented in Vikunja API docs; not probed — write-only scope constraint per C-006). documented (https://vikunja.io/docs/api)

**Implication for sync**: No batch read. Fetching N tasks by ID requires N sequential `GET /tasks/{id}` calls, or use `GET /tasks/all` with pagination + `?filter=project_id=<N>` or `?updated_since=<ISO>`. The `updated_since` approach is more efficient for polling cycles.

---

## 7. Subscribe / Webhook Capability

`webhooks_enabled: true` in `/info` — observed (Probe 1). `GET /projects/1/webhooks` returns `[]` — no webhooks configured — observed (Probe 11).

Per-project webhook endpoints: `GET/POST/PUT/DELETE /projects/{id}/webhooks`. Webhook payload shape: `{event_name, time, data: {task, doer}}`. HMAC-SHA256 signature available. At-most-once delivery; no retry on failure; 30-second timeout. documented (`vikunja-task-model-research.md` §1.5, https://vikunja.io/docs/webhooks)

**Decision locked per C-001**: polling only; webhook integration deferred. This section is for historical record. The webhook surface is available for future implementation.

---

## 8. Auth Model

Token type: long-lived Bearer token (prefix `tk_`). Stored at `/data/services/openclaw/secrets/vikunja-api`. documented (`vikunja-task-model-research.md` §1.6)

The `tk_` prefix and long-lived token model are documented in `vikunja-task-model-research.md` §1.6 and confirmed by the felix-bot provisioning mission (`felix-bot-vikunja-provisioning-01KRT3N4`). The specific character count (43 characters) was not captured in a probe transcript; that claim has been removed to preserve NFR-006 tagging discipline — length is not load-bearing for the sync architecture.

All authenticated endpoints require `Authorization: Bearer <token>`. The current token is owned by Vikunja user `felix-bot` (rotated per ADR-0002 Phase 1). `felix-bot` provisioning (ADR-0002 Q6) has completed — the `vikunja-api` secret was rotated per ADR-0002 Phase 1 (mission `felix-bot-vikunja-provisioning-01KRT3N4`). documented (`vikunja-task-model-research.md` §1.6, ADR-0002 §Q6)

---

## 9. Pagination

`GET /tasks/all` supports `per_page` (integer) and `page` parameters. Response headers expose: `x-pagination-total-pages`, `x-pagination-result-count`. observed (Probes 2, 5, 6). Default behavior returns all tasks; `per_page=1` was used for probe efficiency.

---

## Deferred to implementation

- **Batch-write semantics**: `POST /tasks/bulk` behavior (idempotency, partial failure handling) was not probed per C-006 (no write probes). Implementation mission must verify.
- **Webhook delivery reliability in practice**: At-most-once delivery is documented but not empirically tested. If webhook-based reconciliation is re-evaluated (ADR-0002 Q4 re-evaluation criteria), the delivery gap must be characterized under load.
- **Per-project vs cross-project filter performance**: `GET /tasks/all` fetches all projects; `GET /projects/{id}/tasks` is project-scoped. At scale, the relative performance of these two approaches needs measurement to inform polling strategy choice.
- **`updated_since` ordering semantics**: whether `updated_since` returns tasks in a deterministic order, and whether it handles clock-skew on write timestamps, is not yet verified. Implementation must validate before relying on it for delta detection.
- **Comment API (G3/G4 gotchas)**: Write endpoint is `PUT /tasks/{id}/comments` (not POST — G4). Comment attribution is under `author.username` not `created_by` (G3). These are write-path details deferred per C-006.
