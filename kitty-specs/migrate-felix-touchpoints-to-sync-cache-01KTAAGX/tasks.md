# Work Packages: Migrate Felix Touchpoints to Sync Cache

**Mission**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Mission ID**: `01KTAAGXA149W5F6GVW5N8N5XW`
**Date**: 2026-06-04
**Branch contract**: planning_base_branch=`main`; merge_target_branch=`main`
**Mission type**: software-dev
**Change mode**: regular

This document decomposes the plan into **3 work packages (WP01–WP03)** covering 16 subtasks. Per Phase-0 research, the migration scope is 6 touchpoint files (not the spec's "18"; rationale in [research.md § Scope Correction](./research.md)). The 3-WP structure separates:

- **WP01 — Foundation**: the new shared helper `scripts/common/sync_cache.py` + the shared test fixture in `tests/common/conftest.py` + helper unit tests + architecture-doc updates per change-control protocol.
- **WP02 — Cache-only touchpoint migrations**: TP-03, TP-04 (GET phase), TP-07. These touchpoints only need `read_cached_tasks` / `read_cached_task_by_id` — no state-log lookup.
- **WP03 — Reconciler touchpoint migrations**: TP-02, TP-10, TP-12. These reconcilers also use `read_completion_timestamps` to compare cache state against the per-domain JSONL state log.

Dependencies (computed by `finalize-tasks`):
- WP01: no deps
- WP02: depends on WP01
- WP03: depends on WP01

WP02 and WP03 can execute in parallel (different files, both depend only on WP01). `finalize-tasks` is expected to compute 2 lanes (or 1 if it elects to serialize given they share `tests/habits/test_reconcile_completions.py` — actually they don't; WP02 touches non-reconciler habits tests, WP03 touches the reconciler tests).

---

## Subtask Index (reference table — `[P]` indicates parallel-safe within the WP, not status)

| ID   | Description | WP | Parallel |
|------|-------------|----|----------|
| T001 | `scripts/common/sync_cache.py` — full helper module: SLA tiers, dataclasses, 5 public functions, structured error messages | WP01 | — | [D] |
| T002 | `tests/common/__init__.py` + `tests/common/conftest.py` — `mock_sync_cache_fixture` + `mock_state_log_fixture` | WP01 | [D] |
| T003 | `tests/common/test_sync_cache.py` — full helper unit test suite | WP01 | [D] |
| T004 | `docs/design/architecture/data/service-inventory.json` + `data-flows.json` — note that 6 cron services now consume from sync cache | WP01 | [D] |
| T005 | TP-03 migrate `scripts/habits/query_active_habits_v2.py` — direct GET → `read_cached_tasks` | WP02 | — |
| T006 | TP-03 update `tests/habits/test_query_active_habits_v2.py` — `mock_sync_cache_fixture` | WP02 | [P] |
| T007 | TP-04 migrate `scripts/habits/set_due_dates.py` (GET phase only; PUT phase unchanged) | WP02 | — |
| T008 | TP-04 update `tests/habits/test_set_due_dates.py` — `mock_sync_cache_fixture` for GET-phase tests; existing PUT-phase mocks retained | WP02 | [P] |
| T009 | TP-07 migrate `scripts/habits/morning_checkin_list.py` — direct GET → `read_cached_tasks` | WP02 | — |
| T010 | TP-07 update `tests/habits/test_morning_checkin_list.py` — `mock_sync_cache_fixture` | WP02 | [P] |
| T011 | TP-02 migrate `scripts/habits/reconcile_completions.py` — uses `read_cached_tasks` + `read_completion_timestamps` | WP03 | — |
| T012 | TP-02 update `tests/habits/test_reconcile_completions.py` — `mock_sync_cache_fixture` + `mock_state_log_fixture` | WP03 | [P] |
| T013 | TP-10 migrate `scripts/escalation/reconcile_completions.py` — uses `read_cached_tasks` + `read_completion_timestamps` | WP03 | — |
| T014 | TP-10 update `tests/escalation/test_reconcile_completions.py` — both fixtures | WP03 | [P] |
| T015 | TP-12 migrate `scripts/enrichment/reconcile_completions.py` — uses `read_cached_tasks` + (optional) `read_completion_timestamps` | WP03 | — |
| T016 | TP-12 update `tests/enrichment/test_reconcile_completions.py` — fixtures | WP03 | [P] |

---

## WP01 — Foundation: shared helper + fixtures + arch docs

**Goal**: Build the canonical cache-read entry point that every migration consumes. Make every downstream WP's per-touchpoint cutover a small, structurally identical change.

**Priority**: Foundation. Blocks WP02 and WP03.

**Independent test**: WP01 alone produces a usable `sync_cache.py` module with full unit-test coverage. The shared fixture is exercised by `test_sync_cache.py` itself, so the fixture's behavior is verified before any touchpoint uses it.

**Estimated prompt size**: ~470 lines.

**Included subtasks**:
- [x] T001 `scripts/common/sync_cache.py` — full helper module (WP01)
- [x] T002 `tests/common/__init__.py` + `tests/common/conftest.py` — both fixtures (WP01)
- [x] T003 `tests/common/test_sync_cache.py` — full helper unit test suite (WP01)
- [x] T004 Architecture-doc updates per change-control (WP01)

**Implementation sketch**:
1. Build `scripts/common/sync_cache.py` per [`contracts/helper-api.md`](./contracts/helper-api.md). Includes SLA tier constants, 4 dataclasses, 5 public functions (`read_cached_tasks`, `read_cached_task_by_id`, `read_freshness_pointer`, `read_completion_timestamps`, `is_cache_healthy`), structured error message format. Imports from `scripts.sync.state` only.
2. Build the shared fixtures in `tests/common/conftest.py` per [`contracts/test-fixture.md`](./contracts/test-fixture.md). Includes `mock_sync_cache_fixture` (builds synthetic cache state on `tmp_path`) and `mock_state_log_fixture` (builds synthetic JSONL state log).
3. Build the helper test suite — every function has happy-path + every documented failure path tested. Uses the new fixtures.
4. Update `docs/design/architecture/data/service-inventory.json` to add a "consumes from sync cache" note for the 6 affected cron services. Update `data-flows.json` if it exists. Bump top-level `last_updated` + `updated_by`.

**Parallel opportunities**: T002 + T003 + T004 are all parallel-safe relative to T001's helper module. The fixture, tests, and arch docs all consume the helper's external API; they don't need to be written serially with T001 once the API is locked.

**Dependencies**: None.

**Risks**:
- The helper's error message format is operator-facing; reviewer should verify it matches the contract verbatim (per-touchpoint stderr is operator's primary troubleshooting signal). Tests assert exact substrings.
- The shared fixture must reuse `scripts.sync.state.write_freshness` + `write_task_cache` (not invent its own write path) so cache reads via `state.read_task_cache` find the right schema. Reviewer verifies.
- Architecture docs are a real obligation per CLAUDE.md's standing directive; missing them blocks merge per #518's WP06 pattern. Don't skip.

**FR coverage**: FR-001 (helper module), FR-002 (freshness check), FR-003 (failure detection), FR-009 (shared mock fixture). Also satisfies the helper's contribution to FR-006 (structured error format) and NFR-005 (operator-visible error format).

---

## WP02 — Cache-only touchpoint migrations (TP-03, TP-04, TP-07)

**Goal**: Migrate the 3 touchpoints whose Vikunja reads can be satisfied entirely from `task-cache.json` (no state-log involvement). Each follows the 6-step pattern in [`contracts/migration-pattern.md`](./contracts/migration-pattern.md).

**Priority**: First migration cluster — habits is the highest-volume domain and any regression here is operator-visible within ~12 hours via the next morning's WhatsApp check-in.

**Independent test**: Each touchpoint's test suite runs in isolation under fully-mocked I/O via `mock_sync_cache_fixture`. The implementer can verify each migration's correctness without running the others.

**Estimated prompt size**: ~510 lines (target upper bound).

**Included subtasks**:
- [ ] T005 TP-03 migrate `scripts/habits/query_active_habits_v2.py` (WP02)
- [ ] T006 TP-03 update `tests/habits/test_query_active_habits_v2.py` (WP02)
- [ ] T007 TP-04 migrate `scripts/habits/set_due_dates.py` (GET phase only) (WP02)
- [ ] T008 TP-04 update `tests/habits/test_set_due_dates.py` (WP02)
- [ ] T009 TP-07 migrate `scripts/habits/morning_checkin_list.py` (WP02)
- [ ] T010 TP-07 update `tests/habits/test_morning_checkin_list.py` (WP02)

**Implementation sketch**:
1. For each (source, test) pair, follow the migration pattern: identify the direct-GET code, add helper imports, set `TOUCHPOINT_SLA = SLA_NORMAL` + `TOUCHPOINT_NAME = "habits.<filename_stem>"`, replace the read call with the helper invocation, let `OSError` propagate to non-zero exit, delete the old read code.
2. TP-04 special case: `set_due_dates.py` retains its PUT phase. Migrate only the GET-phase code. Existing PUT-side `_http_request` + token-read code stays. Existing PUT-side `mock_urlopen` fixtures in tests stay.
3. Each test file: drop `mock_urlopen` for GET-side tests; add `mock_sync_cache_fixture`. Tests cover happy path + cache-missing + stale + (where applicable) task-not-found + private. Existing PUT-side tests stay verbatim.

**Parallel opportunities**: Within WP02, each (source, test) pair can be worked in parallel (different files). Tests are `[P]` parallel to their source. Across WPs, WP02 and WP03 are parallel after WP01 completes.

**Dependencies**: WP01.

**Risks**:
- `query_active_habits_v2.py` (TP-03) is invoked by `morning_checkin_list.py` (TP-07) at runtime. If TP-03 and TP-07's migrations are inconsistent (e.g., TP-03 returns view objects but TP-07 expected dicts), the runtime breaks. Mitigation: both touchpoints' tests run together; the implementer is the same agent (within the WP); the contract document `migration-pattern.md` documents the canonical shape.
- `set_due_dates.py` has BOTH GET and PUT paths. The GET migration must not change any state the PUT depends on. The PUT phase's `_http_request` + token-read code must remain untouched by this WP. Reviewer verifies via grep.
- Test fixture sharing: WP02 introduces no new shared test setup; it consumes WP01's `mock_sync_cache_fixture`. If WP01's fixture doesn't support a scenario WP02's tests need (e.g., a specific empty-fields case), WP02 must work around it via fixture parameter — NOT extend the fixture (that's WP01 territory).

**FR coverage**: FR-004 (3 of 6 migrations), FR-005 (steady-state behavior), FR-006 (structured errors), FR-007 (SLA tier assignment), FR-008 (field-set fits TRACKED_TASK_FIELDS — confirmed in research), FR-010 (TP-04 retains write paths).

---

## WP03 — Reconciler touchpoint migrations (TP-02, TP-10, TP-12)

**Goal**: Migrate the 3 reconciler touchpoints. Each uses `read_cached_tasks` for the cache half AND `read_completion_timestamps` for the state-log half. The reconcilers compare cache `done` state against the JSONL state log's completion events to detect operator-side completions.

**Priority**: Second cluster after WP02. Reconcilers are functionally cohesive (same pattern across 3 domains); easier to review when migrated together.

**Independent test**: Each reconciler's test suite runs in isolation via `mock_sync_cache_fixture` + `mock_state_log_fixture`. The companion state-log fixture lets tests parameterize the JSONL contents alongside the cache.

**Estimated prompt size**: ~510 lines (target upper bound).

**Included subtasks**:
- [ ] T011 TP-02 migrate `scripts/habits/reconcile_completions.py` (WP03)
- [ ] T012 TP-02 update `tests/habits/test_reconcile_completions.py` (WP03)
- [ ] T013 TP-10 migrate `scripts/escalation/reconcile_completions.py` (WP03)
- [ ] T014 TP-10 update `tests/escalation/test_reconcile_completions.py` (WP03)
- [ ] T015 TP-12 migrate `scripts/enrichment/reconcile_completions.py` (WP03)
- [ ] T016 TP-12 update `tests/enrichment/test_reconcile_completions.py` (WP03)

**Implementation sketch**:
1. For each reconciler: same 6-step pattern as WP02 PLUS:
   - Add `from scripts.common.sync_cache import read_completion_timestamps` to the imports.
   - Each task being reconciled gets a `read_completion_timestamps(domain="<X>", task_id=tid, state_log_dir=STATE_LOG_DIR)` call alongside its `read_cached_task_by_id` call.
   - The reconciler's existing logic comparing Vikunja's `done_at` against the JSONL's `complete` event timestamp now uses `ts.most_recent_complete_at_utc` from the helper's `CompletionTimestamps`.
2. Each test file: parameterize both fixtures together. Test the matrix:
   - Cache says done + state log has matching complete event → reconciler agrees, no action
   - Cache says done + state log has NO complete event → reconciler detects operator-side completion → existing reconciler logic fires
   - Cache says NOT done + state log has stale complete event → reconciler detects operator-side incompletion (rare; cache wins per C-002)
3. Pay special attention to the `date_et` field semantics: the JSONL uses ET dates; the cache uses UTC timestamps. The `CompletionTimestamps` dataclass exposes both so the reconciler doesn't re-do the conversion.

**Parallel opportunities**: Within WP03, the 3 domain reconcilers are independent (different files, different state-log files). Each (source, test) pair runs in parallel. Across WPs, WP03 is parallel with WP02 after WP01 completes.

**Dependencies**: WP01.

**Risks**:
- The 3 reconcilers were written at different times and have subtly different internal structures (per RQ-2 file:line citations). The migration's "same pattern" still requires per-file judgment about which existing lines to delete and which to keep. Reviewer checks each file's diff against the migration-pattern contract.
- `read_completion_timestamps` returns `(None, None)` for tasks with no completion history — the reconciler must handle this as "task has never been completed" not as an error. Tests must cover this case explicitly.
- TP-12 (`enrichment/reconcile_completions.py`) may not actually use `done_at` per the RQ-2 catalog (only reads `id`, `title`, `updated`). If so, T015 skips the `read_completion_timestamps` import and falls back to the WP02 shape — implementer verifies during T015 by reading the existing logic.

**FR coverage**: FR-004 (3 of 6 migrations), FR-005, FR-006, FR-007, FR-008, FR-010. Plus FR-002 (freshness check applied to every reconciler invocation).

---

## Parallel-execution summary

Per the dependency graph, `finalize-tasks` is expected to compute 2-3 lanes:
- **Lane a**: WP01 (foundation), serially required by both downstream lanes
- **Lane b**: WP02 (after WP01)
- **Lane c**: WP03 (after WP01)

Lanes b and c are parallel-able; implementer-side parallelism within each WP follows the `[P]` markers in the Subtask Index.

If `finalize-tasks` collapses to 1 lane (e.g., on the grounds that WP02 and WP03 share `tests/habits/` as authoritative surface), the mission still executes correctly — just serially.

---

## MVP scope recommendation

**WP01 + WP02 alone is a meaningful MVP**: the helper exists, the shared fixture exists, and the 3 cache-only habit touchpoints are migrated. The reconcilers (WP03) could land in a follow-up if a hard deadline materialized. However: per the operator's "operational reliability is the priority" framing from #518, **ship the full mission**. WP03 closes the loop on reconciler reads; deferring it leaves visible inconsistency in the system (some habits read from cache, the reconciler that verifies them reads from Vikunja).

---

## Next: Implement

Once `finalize-tasks` and `map-requirements` complete, this mission is ready for `/spec-kitty.implement`. Natural starting point: `spec-kitty agent action implement WP01 --agent <name>` (no dependencies).
