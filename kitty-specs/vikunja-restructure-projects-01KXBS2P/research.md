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

## R-04 — Parent/child creation ordering + match safety

**Decision**: Create `Clients` first, resolve its returned `id`, then create
`PointerHealth` and `spec-kitty` with `parent_project_id = <Clients id>`.

- **Match key is not title-only** (post-plan review HIGH #1/#2). Resolve a
  target against **active, correctly-parented** projects: `is_archived == false`
  and `parent_project_id` equal to the expected parent (0 for top-level). If a
  target title matches zero → create; exactly one active/correct → reuse; more
  than one, or an archived/wrong-parent collision → **abort fail-loud** for
  human reconciliation. `Clients` specifically must resolve to exactly one
  active top-level project before any sub-project is created.
- Live audit: none of the five create-targets currently exist, so the common
  path is create; the ambiguity guard is defensive.
- Top-level projects use `parent_project_id = 0`.

## R-05a — Pagination

**Decision**: Page `GET /projects` with `per_page=50&page=N` until an empty
batch (post-plan review MED #5). The live list is < 50, but a target or a legacy
filter pseudo-project could otherwise be missed if the list grows. Tests place a
target and a legacy filter on page 2.

## R-06 — Title readback before filter delete

**Decision**: Before each `DELETE /filters/{id}`, `GET /filters/{id}` and confirm
the returned title equals the intended legacy title, and that the pseudo id is
not `-1` (post-plan review HIGH #3). The `filter_id = -pseudo_id - 1` derivation
is correct here, but a readback prevents deleting the wrong filter if the
mapping ever shifts across versions.

## R-07 — Token-owner enforcement (enforce kent, not felix-bot)

Post-plan review HIGH #4. Two live findings shape the mechanism:

- **`GET /user` returns 401 for API tokens** (that endpoint is JWT/session
  scoped) — so there is **no whoami precheck**. The intuitive "assert username"
  approach does not work with an API token.
- **The felix-bot token sees Kent's projects too** (they are shared) **plus its
  own `Inbox` (id 14, owner `felix-bot`)**, and sees **none** of Kent's saved
  filters (filters are per-user). So a run under the wrong token would (a) see a
  duplicate `Inbox` and (b) create projects owned by `felix-bot`, invisible in
  Kent's UI — exactly the #715 failure.

**Decision** — enforce ownership two ways, both API-token-compatible:

1. **Explicit token file, no fallback.** `--token-file` defaults to
   `/data/services/openclaw/secrets/vikunja-api-kent`; the helper reads only
   that file and does **not** use `VikunjaClient`'s default token loading (which
   would pick the felix-bot token `/data/services/openclaw/secrets/vikunja-api`).
   Missing file → abort.
2. **Owner-scoped matching + create-response assertion.** Every project match
   considers only entries with `owner.username == "kent"` (this is what ignores
   felix-bot's `Inbox` id 14 and any felix-bot-owned collision). On each create,
   assert the response's `owner.username == "kent"` and abort fail-loud if not —
   catching a wrong token even if the path was overridden. `owner` is present on
   `GET /projects` list elements and on the create response.

This is idempotency-safe (unlike checking for kent-owned negative pseudo-projects,
which vanish once this mission deletes the legacy filters).

## R-05 — Backup gate (Tier-2)

**Decision**: The destructive filter-delete pass is refused unless
`--backup-confirmed` is supplied; the additive project-create pass runs without
it. This mirrors #715's label-delete gate. The operator confirms a recent Restic
backup exists (Vikunja is on the Tier-2 snapshot-required tier).
