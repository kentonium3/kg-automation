# Data Model: Vikunja Project Restructure

The helper operates on two Vikunja entities plus an internal reconciliation
plan. No local persistence — all state lives in Vikunja.

## Entities

### Project

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | Positive = real user project. Negative = pseudo-project (saved filter / native Favorites). |
| `title` | str | Match key for reconciliation (target projects identified by exact title). |
| `parent_project_id` | int | `0` = top-level. Sub-projects reference their parent's `id`. |
| `is_archived` | bool | Not modified by this mission. |

**Target project set (desired state):**

| Title | Parent | Action |
|-------|--------|--------|
| `Inbox` | 0 | verify exists (id 1) — never recreate |
| `Felix / kg-automation` | 0 | create if absent |
| `Clients` | 0 | create if absent (holds no tasks) |
| `PointerHealth` | `Clients`.id | create if absent |
| `spec-kitty` | `Clients`.id | create if absent |
| `Personal` | 0 | create if absent |

**Retained, untouched** (present, not in create set, not deleted here):
`Business Acquisition`, `Health & Conditioning`, `Intentional LLC`, `CT-90day`,
`Metal Casework`, `Habits`.

**Never deleted here** (task-bearing; → #717): `Everyday`, `Someday`,
`Personal Growth & Transformation`, `Household`, `Goals`, `Research`.

### SavedFilter

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | Filter id. Surfaces as pseudo-project `-(id) - 1`. |
| `title` | str | Match against the legacy set. |

**Legacy filters to delete** (title → filter_id): `Today`→1, `Upcoming`→2,
`Overdue`→3, `Goals`→4, `Completed`→5. **`Favorites`** (pseudo `-1`) is native
and has no deletable filter id — leave it.

Discovery: enumerate negative-id pseudo-projects from `GET /projects`
(`id <= -2`), match `title` against the legacy set, compute
`filter_id = -id - 1`, then `DELETE /filters/{filter_id}`.

## Reconciliation model (internal)

A `ReconcilePlan` computed from (desired state − live state):

- `projects_to_create`: ordered — parent (`Clients`) before children.
- `projects_verified`: already-present targets (no-op).
- `filters_to_delete`: legacy filters still present.
- `filters_absent`: legacy filters already gone (no-op).

**Invariants:**
1. **Idempotent** — a converged second run yields empty `to_create` /
   `to_delete` sets → zero mutating API calls (NFR-001).
2. **Match by title** — no project/filter is created if one with the target
   title already exists (no duplicates, FR-008).
3. **Additive-safe** — the plan never contains a project *delete* (C-004,
   FR-010); only filter deletes, and only when `--backup-confirmed` (NFR-004).
4. **Fail-loud** — any non-2xx API response aborts with a non-zero exit before
   further mutation (NFR-002); a partial run never reports success.
5. **Do-no-harm** — `Habits` (id 13) and any positive-id project outside the
   create set are never mutated.

## State transitions

```
live state ──(read: GET /projects)──► ReconcilePlan
   │
   ├─ additive pass:  for each projects_to_create → PUT /projects
   │                    (Clients first, then children with resolved parent id)
   │
   └─ destructive pass (only if --backup-confirmed):
        for each filters_to_delete → DELETE /filters/{filter_id}

converged state ──► summary report (created / verified / deleted / skipped), exit 0
```
