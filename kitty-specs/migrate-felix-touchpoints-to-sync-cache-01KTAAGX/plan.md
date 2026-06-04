# Implementation Plan: Migrate Felix Touchpoints to Sync Cache

**Branch**: `main` (planning + final merge target) | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/spec.md`

## Summary

Migrate the cron-fired, read-only Felix callsites that consume Vikunja task state from direct `urllib.request` HTTP reads to reads from the sync driver's `task-cache.json` (the artifact #518 deployed on office2 at 21:48 UTC 2026-06-04). Each migration is a clean cutover per Q1 (spec discovery): the old `_http_request("GET", …)` calls and their surrounding lookup helpers are deleted in the same change that adds the new cache read; no fallback path, no runtime config flag, no coexistence.

Phase 0 research surfaced a meaningful **scope correction**: the spec body's "18 touchpoints" figure was inherited from #518 RQ-2's literal TP-01..TP-18 numbering, but the RQ-2 catalog also includes (a) write-only callsites that #519's FR-010 already excludes, (b) maintenance/provisioning tools that are operator-invoked one-shots and would gain nothing from cache reads. Treating those as in-scope would be both incorrect and a scope expansion. After applying the spec's locked exclusions and an operator-utility filter, the actual migration set is **7 callsites in 4 domain clusters** (habits ×4, escalation ×1, enrichment ×1, plus shared helper + fixture).

Engineering approach (operator-confirmed during planning interrogation, 2026-06-04):

- **Per-touchpoint SLA tiers (Q1=A)**: four named tiers in `scripts/common/sync_cache.py` — `SLA_HOT` (60s), `SLA_NORMAL` (15 min), `SLA_BATCH` (1 h), `SLA_LOOSE` (24 h). Each touchpoint picks one. Per-touchpoint assignments derived in research.md.
- **Helper API surface**: three pure functions returning data + raising `OSError` on every failure path. No defensive defaults. The helper does NOT wrap the driver's `state.py` types — it returns the Python primitives the touchpoints already use.
- **Shared mock fixture**: a single `tests/common/conftest.py` providing `mock_sync_cache_fixture` that injects synthetic cache state, freshness pointer, and private-project ids. All migrated touchpoint tests share this fixture.
- **Migration order**: habits → escalation → enrichment. The `sync_cache.py` foundation precedes everything; no per-AGENTS.md edits are needed because the helper's CLI surface mirrors what the touchpoints already produce (exit codes, stderr).

## Technical Context

**Language/Version**: Python 3.12 (matches #518's runtime on office2 + Mac dev).

**Primary Dependencies**: Standard library only — `pathlib`, `json`, `datetime`. Imports from `scripts.sync.state` (for `read_task_cache`, `read_freshness`, `STATE_DIR_DEFAULT`). No third-party packages introduced.

**Storage**:
- Reads from `/data/services/openclaw/state/sync/task-cache.json` and `freshness.json` (produced by #518)
- Writes NOTHING to disk — the helper is read-only against driver state

**Testing**: All touchpoint tests + the new helper tests run under `pytest` with the shared `tests/common/conftest.py` fixture. No live `/data/services/openclaw/state/sync/` interaction. No live `urllib.request.urlopen` calls (existing test mocks for write-side calls retained where touchpoints retain writes). Per memory `feedback_no_live_integration_tests`.

**Target Platform**: office2 (Ubuntu 24.04 LTS) for production; Mac for development + tests. Driver state directory is `/data/services/openclaw/state/sync/`.

**Project Type**: single project. New files at `scripts/common/sync_cache.py` + `tests/common/conftest.py`; existing files modified in-place.

**Performance Goals**:
- Per-invocation latency NOT to regress (NFR-001)
- Single file-read per invocation; ≤50 ms at current cache size (NFR-003)
- 24-hour Vikunja read volume from Felix drops by ≥95% (NFR-002, SC-004)

**Constraints**:
- Clean cutover, no fallback (C-001, C-002)
- No silent failures (C-002)
- Helper is the only entry point — touchpoints don't import driver internals (C-004)
- Privacy boundary mirrors #518 C-009 (empty-fields → structured error)
- All test I/O is mocked (C-008)

**Scale/Scope**:
- New source modules: 2 (`scripts/common/sync_cache.py` + `tests/common/conftest.py`)
- Touchpoint files modified: 6 (per Phase-0 research scope correction)
- Approximate LOC: 200-300 (helper) + 100-200 (shared fixture) + 50-100 per touchpoint migration

## Charter Check

Same posture as #518: the project charter carries the known "governance unresolved" diagnostic about `pytest`/`python` not being in spec-kitty's built-in tool registry. This mission inherits the condition; no new charter conflicts introduced.

**Status**: charter check passes for this mission's scope.

## Project Structure

### Documentation (this feature)

```
kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/
├── plan.md                       # This file
├── spec.md                       # Feature specification
├── research.md                   # Phase 0 — scope correction + per-TP analysis + SLA assignments
├── data-model.md                 # Phase 1 — entities (helper API, SLA tiers, mock fixture, migration manifest)
├── quickstart.md                 # Phase 1 — operator post-merge verification commands
├── contracts/
│   ├── helper-api.md             # The sync_cache module API contract
│   ├── test-fixture.md           # Shared mock-cache fixture contract
│   └── migration-pattern.md      # Per-touchpoint clean-cutover pattern
├── meta.json                     # Mission identity + branch contract
├── checklists/requirements.md    # Spec quality checklist (all pass)
├── status.events.jsonl           # Spec-kitty workflow event log
└── tasks/                        # Populated by /spec-kitty.tasks (NOT this command)
```

### Source Code (repository root)

```
scripts/
├── common/                       # Existing dir (scripts/common/state_log.py lives here)
│   └── sync_cache.py             # NEW — canonical cache-read entry point
├── habits/                       # 4 touchpoints MODIFIED in-place (clean cutover)
│   ├── reconcile_completions.py  # TP-02 — direct GET → sync_cache.read_cached_tasks
│   ├── query_active_habits_v2.py # TP-03 — direct GET → sync_cache.read_cached_tasks
│   ├── set_due_dates.py          # TP-04 — direct GET → sync_cache.read_cached_tasks (GET phase only; write phase unchanged)
│   └── morning_checkin_list.py   # TP-07 — direct GET → sync_cache.read_cached_tasks
├── escalation/                   # 1 touchpoint MODIFIED in-place
│   └── reconcile_completions.py  # TP-10 — direct GET → sync_cache.read_cached_tasks
└── enrichment/                   # 1 touchpoint MODIFIED in-place
    └── reconcile_completions.py  # TP-12 — direct GET → sync_cache.read_cached_tasks

tests/
├── common/                       # NEW — shared test infrastructure
│   ├── __init__.py
│   ├── conftest.py               # NEW — `mock_sync_cache_fixture` shared across touchpoint tests
│   └── test_sync_cache.py        # NEW — helper unit tests
├── habits/                       # Existing test files MODIFIED to use mock_sync_cache_fixture
│   ├── test_reconcile_completions.py
│   ├── test_query_active_habits_v2.py
│   ├── test_set_due_dates.py     # GET-phase tests only
│   └── test_morning_checkin_list.py
├── escalation/
│   └── test_reconcile_completions.py
└── enrichment/
    └── test_reconcile_completions.py

# OUT OF SCOPE per Phase 0 research (rationale in research.md § Scope Correction):
# - Write-only callsites (TP-01, TP-05, TP-06, TP-09, TP-11, TP-16A) — already excluded by FR-010 / C-003
# - Mixed write+read callsites where the read is post-write verification (TP-13, TP-14, TP-15C, TP-15D, TP-15E, TP-16C, TP-16D, TP-16E) — read remains direct
# - Legacy/superseded read callsites (TP-15A, TP-15B, TP-18) — deprecated; do not migrate
# - Maintenance/provisioning tools (TP-16B) — operator-invoked one-shots, cache reads gain nothing
# - Pre-bootstrap callsites (TP-08 backfill_jsonl_from_comments.py) — runs against pre-cache historical data
```

**Structure Decision**: Single project (same as #518). All new code lives under `scripts/common/sync_cache.py` + `tests/common/conftest.py`; existing touchpoint files are modified in-place. Matches #518's pattern precedent.

## Complexity Tracking

| Complexity | Why Needed | Simpler Alternative Rejected Because |
|------------|------------|--------------------------------------|
| None | — | — |

Phase 0's scope correction REMOVED complexity (smaller migration set than the spec body's "18 touchpoints" figure). No complexity additions vs. the spec.
