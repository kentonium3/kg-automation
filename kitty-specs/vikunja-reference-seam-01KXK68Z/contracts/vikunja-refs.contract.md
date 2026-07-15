# Contract: vikunja_refs accessor + validator

This is a library contract (no HTTP surface). It defines the behavior call sites depend on.

## Accessor

| Call | Success | Failure |
|------|---------|---------|
| `project_id("inbox")` | returns pinned int id (e.g. `1`) | — |
| `project_id("nonexistent")` | — | raises `VikunjaRefError` (undeclared name) |
| `label_id("q:schedule", "kent")` | returns pinned int id in that token's namespace | raises `VikunjaRefError` if undeclared for token |
| any accessor call | performs **no** network I/O (NFR-001) | — |

- Resolution NEVER returns `None`/`0`/empty to signal "not found" — it raises (FR-003). This is the #743 regression guard: a deleted reference fails loud, never silently mis-routes.

## Validator

| Call | Behavior |
|------|----------|
| `validate(live_projects, live_labels_by_token)` | pure; returns `list[ValidationFinding]` (empty == clean) |
| CLI `validate_refs` | lists live Vikunja ≤2 times (NFR-002), prints findings, exit 0 if clean else non-zero (FR-004) |

Finding kinds: `missing` (declared name absent live), `id_drift` (title present but id changed), `title_drift` (id present but title changed).

## Migration contract (call sites)

After migration, each of these resolves via the accessor and its old lookup is deleted (FR-005):

| Call site | Old mechanism (removed) | New |
|-----------|-------------------------|-----|
| `route_someday.py` | `find_someday_project` (by title) | accessor |
| `credential_health_check/vikunja_writer.py` | `lookup_inbox_project_id` (by title) | accessor `project_id("inbox")` |
| `vikunja_scope.py` | hardcoded `13` | accessor `project_id("habits")` |
| `sync/…` | `PRIVATE_PROJECT_IDS` literal | accessor-derived |
