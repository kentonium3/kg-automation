# API Contract: Vikunja endpoints used

Vikunja v0.24.6 REST API. `base_url` ends in `/api/v1`; the `VikunjaClient`
composes `base_url + path` (leading slash required). Auth: `Bearer` with the
**kent-owned** token (`vikunja-api-kent`).

## Auth / token owner

- Token read only from an explicit `--token-file` (default:
  `/data/services/openclaw/secrets/vikunja-api-kent`). Never the `VikunjaClient`
  default (felix-bot) path.
- `GET /user` is **401 for API tokens** — not usable as a whoami. Owner is
  enforced via the `owner` field on `GET /projects` and on create responses
  (match/act only on `owner.username == "kent"`; assert create-response owner).

## Read

### `GET /projects?per_page=50&page={N}`
List projects visible to the token owner. **Paginate** until an empty batch.

- Returns an array of Project objects (may be JSON `null` if empty — normalise to `[]`).
- Positive `id` = real project; `id <= -2` = saved-filter pseudo-project; `id == -1` = native Favorites.
- Each element includes `owner` (`{ "username": "kent", ... }`); Favorites (`-1`) has `owner: null`.
- The felix-bot token additionally returns its own `Inbox` (id 14, `owner.username == "felix-bot"`) — filtered out by owner-scoped matching.
- Used to: verify Kent's `Inbox` (id 1, owner kent), resolve `Clients` parent id, detect already-present kent-owned targets, discover legacy filter pseudo-projects.

Response element (relevant fields):
```json
{ "id": 6, "title": "Business Acquisition", "parent_project_id": 0, "is_archived": false, "owner": { "username": "kent" } }
```

### `GET /filters/{id}`  — title readback before delete
Fetch the filter to confirm its `title` matches the intended legacy target
before deleting (guards the `filter_id = -pseudo_id - 1` derivation).

## Write

### `PUT /projects`  — create a project
Request:
```json
{ "title": "Clients", "parent_project_id": 0 }
```
- `parent_project_id`: `0` for top-level; the resolved `Clients` id for sub-projects.
- Response: the created Project object, including `owner` — **assert
  `owner.username == "kent"`** (abort if not); capture `id` for parent resolution.
- Idempotency enforced client-side (only called when no active, correctly-parented, kent-owned project with that title exists).

### `DELETE /filters/{filter_id}`  — delete a saved filter
- `filter_id` derived as `-pseudo_project_id - 1` from the negative-id pseudo-project.
- Preceded by a `GET /filters/{filter_id}` title readback.
- Called only for legacy filters still present, and only when both `--delete-legacy` and a non-blank `--backup-confirmed <ref>` are set.
- Never called for `Favorites` (`-1`, no filter id).

## CLI contract (exit codes)

| Invocation | Behavior | Exit |
|---|---|---|
| (default, no flags) | create-only pass: create missing kent-owned projects, verify Inbox; no filter deletes | 0 success / 1 API error |
| `--delete-legacy --backup-confirmed <ref>` | also delete legacy filters (with readback) | 0 success / 1 API error |
| `--delete-legacy` without non-blank `<ref>` | refuse before any mutation | 2 |
| `--dry-run` | compute + print plan, no mutation | 0 |
| `--json` | machine-readable summary | (as above) |
| `--token-file <path>` | token source (default = kent secret) | — |

## Error handling contract

- Any non-2xx response → raise / abort with a non-zero exit and a descriptive
  message naming the operation and target. No further mutations after a failure.
- `401` (expired/invalid token) surfaces the credential name so the operator can
  refresh `vikunja-api-kent`.

## Out of contract (explicitly NOT called by this mission)

- `DELETE /projects/{id}` — no project deletion here (→ #717).
- Any `/tasks*` endpoint — no task reads or moves here (→ #717).
- Saved-filter **create** (`PUT /filters`) — canonical filters are #718's job.
