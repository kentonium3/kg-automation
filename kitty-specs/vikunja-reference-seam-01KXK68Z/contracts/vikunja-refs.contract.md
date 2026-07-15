# Contract: vikunja_refs accessor + validator

This is a library contract (no HTTP surface). It defines the behavior runtime call sites depend on.

## Accessor

| Call | Success | Failure |
|------|---------|---------|
| `project_id("inbox")` | returns pinned int id (e.g. `1`) | — |
| `project_id("nonexistent")` | — | raises `VikunjaRefError` (undeclared name) |
| `project_id("personal")` when declared but unprovisioned (`value: null`) | — | raises `VikunjaRefError` ("declared but unprovisioned", FR-009) |
| `project_id("habits")` when selector `kind == "label"` | — | raises `VikunjaRefError` (wrong accessor for a label selector) |
| `label_id("felix:ignore", "kent")` | returns pinned int id in that token's namespace | raises `VikunjaRefError` if undeclared/unprovisioned for token |
| `selector("habits")` | returns raw `{kind, value}` (for the vikunja_scope selector layer) | raises `VikunjaRefError` if undeclared |
| `private_project_ids()` | returns `frozenset[int]` resolved from `private_projects` names (empty if none) | raises `VikunjaRefError` if a listed name is undeclared/unprovisioned |
| any accessor call | performs **no** network I/O (NFR-001) | — |

- Resolution NEVER returns `None`/`0`/empty to signal "not found" — it raises (FR-003). This is the #743 regression guard: a deleted or unprovisioned reference fails loud, never silently mis-routes.

## Validator

| Call | Behavior |
|------|----------|
| `validate(live_projects, live_labels_by_token)` | pure; returns `list[ValidationFinding]` (empty == clean) |
| CLI `validate_refs` (Vikunja reachable) | lists live Vikunja ≤2 times (NFR-002), prints findings, exit 0 if clean else non-zero (FR-004) |
| CLI `validate_refs` (Vikunja **unreachable**) | emits a single `unreachable` finding and exits non-zero as "could not validate" — distinct from "registry clean" (FR-004) |

Finding kinds: `missing` (declared name absent live), `id_drift` (title present but id changed), `title_drift` (id present but title changed), `unprovisioned` (declared with `value: null`), `unreachable` (live list could not be fetched).

## Non-modeling note

The registry is **flat**: it does not model sub-project parent/child hierarchy
(Clients › PointerHealth/spec-kitty). This is sufficient for id resolution;
consumers must not expect hierarchy information from the accessor.

## Migration contract (runtime call sites — full inventory in spec.md FR-005)

After migration, each runtime site resolves via the accessor and its old lookup is deleted (FR-005):

| Call site | Old mechanism (removed) | New |
|-----------|-------------------------|-----|
| `inbox/route_someday.py` | `find_someday_project` (by title `"Someday"`) | **retired** — reworked to `q:schedule`+no-due-date in Inbox/topic project (#745, FR-011) |
| `security/credential_health_check/vikunja_writer.py` | `lookup_inbox_project_id` (by title) | accessor `project_id("inbox")` |
| `common/vikunja_scope.py` | hardcoded `13` / `[13]` | `selector("habits")` + derive `ESCALATION_EXCLUDED` from `project_id("habits")` |
| `sync/diff.py` | `PRIVATE_PROJECT_IDS` literal set | accessor `private_project_ids()` (or explicitly scoped out) |
| `sync/classify.py` | `felix:ignore` by `title ==` | accessor `label_id("felix:ignore", token)` |
| `habits/query_active_habits_v2.py` | `HABITS_PROJECT_ID = 13` | accessor |
| `habits/reconcile_completions.py` | `HABITS_PROJECT_ID` (=2 on branch) | accessor |
| `habits/backfill_jsonl_from_comments.py` | Habits by `title == "Habits"` | accessor |
| `habits/query_active_habits_weekly.py` | module-level `HABITS_PROJECT_ID` mirror | collapse onto seam via vikunja_scope |

**Exempt (C-005), not migrated:** the `scripts/vikunja/` provisioning tools + `scripts/vikunja/create_task.py`.
