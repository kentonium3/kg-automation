# API Contract: Vikunja endpoints used

Vikunja v0.24.6 REST API. `base_url` ends in `/api/v1`; the `VikunjaClient`
composes `base_url + path` (leading slash required). Auth: `Bearer` with the
**kent-owned** token (`vikunja-api-kent`).

## Read

### `GET /projects`
List all projects visible to the token owner (kent).

- Returns an array of Project objects (may be JSON `null` if empty — normalise to `[]`).
- Positive `id` = real project; `id <= -2` = saved-filter pseudo-project; `id == -1` = native Favorites.
- Used to: verify `Inbox`, resolve `Clients` parent id, detect already-present targets, discover legacy filter pseudo-projects.

Response element (relevant fields):
```json
{ "id": 6, "title": "Business Acquisition", "parent_project_id": 0, "is_archived": false }
```

### `GET /filters/{id}`
(Diagnostic only — used during research to confirm filter titles; the helper
does not require it for the delete path.)

## Write

### `PUT /projects`  — create a project
Request:
```json
{ "title": "Clients", "parent_project_id": 0 }
```
- `parent_project_id`: `0` for top-level; the resolved `Clients` id for sub-projects.
- Response: the created Project object (capture `id` for parent resolution).
- Idempotency is enforced client-side (only called when no project with that title exists).

### `DELETE /filters/{filter_id}`  — delete a saved filter
- `filter_id` derived as `-pseudo_project_id - 1` from the negative-id pseudo-project.
- Called only for legacy filters still present, and only when `--backup-confirmed` is set.
- Never called for `Favorites` (no filter id).

## Error handling contract

- Any non-2xx response → raise / abort with a non-zero exit and a descriptive
  message naming the operation and target. No further mutations after a failure.
- `401` (expired/invalid token) surfaces the credential name so the operator can
  refresh `vikunja-api-kent`.

## Out of contract (explicitly NOT called by this mission)

- `DELETE /projects/{id}` — no project deletion here (→ #717).
- Any `/tasks*` endpoint — no task reads or moves here (→ #717).
- Saved-filter **create** (`PUT /filters`) — canonical filters are #718's job.
