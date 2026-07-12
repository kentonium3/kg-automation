# Research: Vikunja Project Restructure

Phase 0 findings. All probes were **read-only** GETs against the live Vikunja
instance (v0.24.6) on office2 using the kent-owned token.

## R-01 — Saved-filter delete endpoint (resolves spec C-005 / edge case)

**Decision**: Delete legacy saved filters via `DELETE /api/v1/filters/{filter_id}`.
Discover the target `filter_id`s from the negative-id pseudo-projects, not from a
list endpoint.

**Findings (live, v0.24.6):**
- `GET /api/v1/filters` → **404** (no collection/list endpoint in this version).
- `GET /api/v1/filters/{id}` → **200** (individual filters resolve).
- Saved filters surface in `GET /api/v1/projects` as **negative-id pseudo-projects**.
  The mapping is `pseudo_project_id = -(filter_id) - 1`, i.e.
  `filter_id = -pseudo_project_id - 1`.

**Confirmed mapping (live):**

| Pseudo-project | id | filter_id | Legacy? |
|---|---|---|---|
| Favorites | -1 | (none — native favorites) | keep — not deletable |
| Today | -2 | 1 | delete |
| Upcoming | -3 | 2 | delete |
| Overdue | -4 | 3 | delete |
| Goals | -5 | 4 | delete |
| Completed | -6 | 5 | delete |

**Rationale**: Because there is no list endpoint, the robust + idempotent
approach is: `GET /projects` → select negative-id entries with `id <= -2`
(excludes native `Favorites` at `-1`) whose `title` is in the legacy set →
compute `filter_id = -id - 1` → `DELETE /filters/{filter_id}`. On a converged
re-run those pseudo-projects are gone, so the pass is a no-op.

**Alternatives considered**:
- Hardcode filter ids 1–5 → rejected: ids are environment-specific and brittle.
- Probe `/filters/{1..N}` blindly → rejected: no natural upper bound; title
  match via the projects listing is cleaner and already available.

## R-02 — Client + invocation conventions (reuse, do not reinvent)

**Decision**: Build on `scripts/common/vikunja_client.py` (`VikunjaClient`),
invoked as `python3 -m scripts.vikunja.reconcile_projects`.

- `VikunjaClient` request paths need a **leading slash** (`/projects`,
  `/filters/{id}`); `base_url` already ends in `/api/v1` and `_compose_url`
  concatenates.
- Methods available: `get`, `post`, `put`, `delete`. Project create =
  `PUT /projects` with `{"title": ..., "parent_project_id": <id or 0>}`
  (mirrors the label-create pattern from #715's `create_taxonomy_labels.py`).
- Token loads from the client's default path; this helper must be pointed at the
  **kent-owned** token (`vikunja-api-kent`), not the felix-bot token — pass an
  explicit token/`--token-path`, since felix-bot-created objects are invisible
  in Kent's UI and felix-bot cannot own kent config (#715 two-token model).

## R-03 — v0.24.6 response quirks (defensive handling)

**Decision**: Treat JSON `null` as an empty collection.

- Vikunja returns literal `null` (not `[]`) for an empty label/collection
  response — this bit #715 (the `list_labels` null-vs-empty bug). The projects
  listing here is non-empty, but the helper must still normalise `null → []`
  defensively for any collection read.
- `per_page` caps at 50; paginate until an empty batch if a collection could
  exceed 50 (the projects list is well under 50, but the pattern is noted).

## R-04 — Parent/child creation ordering

**Decision**: Create `Clients` first, resolve its returned `id`, then create
`PointerHealth` and `spec-kitty` with `parent_project_id = <Clients id>`.

- Idempotency: match by `title`; if `Clients` already exists, reuse its id;
  if a sub-project already exists under the correct parent, skip.
- Top-level projects use `parent_project_id = 0`.

## R-05 — Backup gate (Tier-2)

**Decision**: The destructive filter-delete pass is refused unless
`--backup-confirmed` is supplied; the additive project-create pass runs without
it. This mirrors #715's label-delete gate. The operator confirms a recent Restic
backup exists (Vikunja is on the Tier-2 snapshot-required tier).
