# Data Model: Vikunja Project Restructure

The helper operates on two Vikunja entities plus an internal reconciliation
plan. No local persistence — all state lives in Vikunja.

## Entities

### Project

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | Positive = real user project. Negative = pseudo-project (saved filter / native Favorites). |
| `title` | str | Part of the match key (with owner + parent + active). |
| `parent_project_id` | int | `0` = top-level. Sub-projects reference their parent's `id`. |
| `is_archived` | bool | Not modified by this mission; excluded from match candidates. |
| `owner.username` | str | **Match filter**: only `owner == "kent"` projects are candidates. The felix-bot token also has its own `Inbox` (id 14, owner `felix-bot`) — excluded by this. |

**Match key** (resolves post-plan HIGH #1/#2): a target resolves against
candidates that are `owner == "kent"` AND `is_archived == false` AND
`parent_project_id == expected_parent`. Zero matches → create; exactly one →
reuse its id; more than one, or a title collision with an archived/wrong-parent/
wrong-owner project → **abort fail-loud** (FR-014). `Clients` must resolve to
exactly one active top-level kent-owned project before creating its children.

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

**Legacy filters to delete** (live-derived, ids are environment-specific — these
are examples from the current instance, not hardcoded): `Today`→1, `Upcoming`→2,
`Overdue`→3, `Goals`→4, `Completed`→5. **`Favorites`** (pseudo `-1`) is native
and has no deletable filter id — leave it.

Discovery + safety: enumerate negative-id pseudo-projects from `GET /projects`
(`id <= -2`, excludes Favorites at `-1`), match `title` against the legacy set,
compute `filter_id = -id - 1`, **read back** `GET /filters/{filter_id}` and
confirm its title equals the intended legacy title, then `DELETE
/filters/{filter_id}` (post-plan HIGH #3). Tests exercise non-`1..5` derived
ids so the code never assumes a fixed range.

## Reconciliation model (internal)

A `ReconcilePlan` computed from (desired state − live state):

- `projects_to_create`: ordered — parent (`Clients`) before children.
- `projects_verified`: already-present targets (no-op).
- `filters_to_delete`: legacy filters still present.
- `filters_absent`: legacy filters already gone (no-op).

**Invariants:**
1. **Idempotent** — a converged second run yields empty `to_create` /
   `to_delete` sets → zero mutating API calls (NFR-001).
2. **Owner-scoped match** — a target is created only if no active, correctly
   parented, **kent-owned** project with that title exists (no duplicates,
   FR-008/FR-014); ambiguous matches abort.
3. **Additive-safe** — the plan never contains a project *delete* (C-004,
   FR-010); only filter deletes, and only when `--delete-legacy` +
   `--backup-confirmed <ref>` (NFR-004).
4. **Fail-loud + partial-run report** — any non-2xx API response aborts with a
   non-zero exit before further mutation (NFR-002); the summary then reports
   which operations completed vs were skipped (NFR-005); a partial run never
   reports success.
5. **Do-no-harm** — `Habits` (id 13) and any project outside the create set are
   never the target of a write op (asserted in the plan + tests).
6. **Kent-owned** — token read only from the explicit kent token file; each
   create response's `owner.username` asserted `== "kent"` (FR-009).
7. **Paginated reads** — `GET /projects` paged at `per_page=50` until an empty
   batch; `null → []` normalisation on every collection read.

**Pagination + null handling**: collection reads page with `per_page=50&page=N`
and treat a `null` body as `[]`. Tests place a create-target and a legacy filter
on page 2.

**Partial-failure report**: outcomes accumulate as operations run; on an API
failure mid-run the helper stops and prints (and, with `--json`, emits) the list
of completed vs skipped operations. A test injects a failure after one
successful mutation.

## State transitions

```
live state ──(read: GET /projects)──► ReconcilePlan
   │
   ├─ additive pass:  for each projects_to_create → PUT /projects
   │                    (Clients first, then children with resolved parent id)
   │
   └─ destructive pass (only if --delete-legacy AND --backup-confirmed <ref>):
        for each filters_to_delete → GET /filters/{id} (title readback) → DELETE /filters/{id}

converged state ──► summary report (created / verified / deleted / skipped), exit 0
```
