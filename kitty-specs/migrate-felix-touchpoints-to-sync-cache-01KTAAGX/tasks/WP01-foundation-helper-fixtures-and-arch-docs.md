---
work_package_id: WP01
title: 'Foundation: shared helper + fixtures + arch docs'
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-migrate-felix-touchpoints-to-sync-cache-01KTAAGX
base_commit: cded9f2d0ca9649e0159c6278f6fd7f476b6d9f2
created_at: '2026-06-04T22:35:24.125840+00:00'
subtasks:
- T001
- T002
- T003
- T004
shell_pid: "19157"
agent: "claude:opus:reviewer:reviewer"
history:
- at: '2026-06-04T22:24:02Z'
  by: spec-kitty.tasks
  note: Created WP01 from plan.md + contracts/helper-api.md + contracts/test-fixture.md
authoritative_surface: scripts/common/
execution_mode: code_change
owned_files:
- scripts/common/sync_cache.py
- tests/common/__init__.py
- tests/common/conftest.py
- tests/common/test_sync_cache.py
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
tags: []
---

# WP01 — Foundation: shared helper + fixtures + arch docs

## Objective

Build the canonical cache-read entry point (`scripts/common/sync_cache.py`) and the shared pytest fixture (`tests/common/conftest.py`) every downstream WP consumes. Plus full unit-test coverage for the helper and the architecture-doc updates the standing directive in `CLAUDE.md` requires for any data-flow change.

After this WP, downstream WPs (WP02, WP03) can:
- `from scripts.common.sync_cache import read_cached_tasks, read_cached_task_by_id, read_completion_timestamps, SLA_NORMAL` — and start migrating touchpoints
- Use `mock_sync_cache_fixture` and `mock_state_log_fixture` in their test files — and stop maintaining per-touchpoint `mock_urlopen` patches for the read path

## Context

Mission #518 deployed the sync driver to office2 (verified at 21:48 UTC 2026-06-04: 50 tasks + 7 projects in cache, `cycle_error: null`, next tick at 21:53 UTC). The driver writes `task-cache.json` + `freshness.json` on every successful tick. **No touchpoint reads them yet**.

This mission (#519) changes that. Per Q1's clean-cutover decision: each touchpoint's old direct-Vikunja-read code is deleted in the same change that introduces the cache read. There is no fallback path, no runtime flag, no coexistence period. When a touchpoint can't serve its read from the cache (missing, stale-beyond-SLA, task absent, private), it surfaces a structured stderr error and exits non-zero — never silently falls back to Vikunja.

WP01 is the substrate. Its three artifacts (helper, fixture, helper tests) plus the architecture-doc updates anchor the rest of the mission. WP02 and WP03 are mechanical applications of the migration pattern against this substrate.

**Phase 0 research confirmed** all 6 in-scope touchpoints land on `SLA_NORMAL` (15 min). The other 3 tiers (`SLA_HOT`, `SLA_BATCH`, `SLA_LOOSE`) are defined in this WP for future missions but consumed nowhere in #519.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree per WP; commits inside the worktree.

## Implementation command

```bash
spec-kitty agent action implement WP01 --agent <name>
```

No dependencies. WP01 starts as soon as the mission is ready for implementation.

---

## Subtask T001 — `scripts/common/sync_cache.py`: full helper module

**Purpose**: Provide the canonical 5-function API every migrated touchpoint reads through. Per spec C-004, this is the only entry point — no touchpoint imports `scripts.sync.state` or any state-log code directly.

**Steps**:

1. **Module header + imports**: standard library + `from scripts.sync.state import STATE_DIR_DEFAULT, read_freshness, read_task_cache`. NO third-party packages.

2. **Constants and dataclasses**: define `SLA_HOT`, `SLA_NORMAL` (900s), `SLA_BATCH`, `SLA_LOOSE` as `SLATier(name, seconds)` frozen dataclasses per [`contracts/helper-api.md` § Module imports + module-level constants](../contracts/helper-api.md). Define `TaskCacheView` and `CompletionTimestamps` frozen dataclasses.

3. **`read_cached_tasks(sla, state_dir=STATE_DIR_DEFAULT, *, touchpoint_name=None) → dict[int, TaskCacheView]`**: read `freshness.json` → compute pointer age → compare against `sla.seconds` → on stale, raise `OSError` with the structured message format. On fresh, read `task-cache.json` via `state.read_task_cache(state_dir)` → translate `TaskCacheRecord.tasks` to `dict[int, TaskCacheView]` (setting `is_private` based on `fields == {}`). Behavior contract in `contracts/helper-api.md § Function 1`.

4. **`read_cached_task_by_id(task_id, sla, state_dir=STATE_DIR_DEFAULT, *, touchpoint_name=None) → TaskCacheView`**: calls `read_cached_tasks` then looks up `task_id`. On missing → `OSError` with the task_id and cache's `last_polled_utc` in the message. On private → `OSError` (NO field content in the message). Contract in `contracts/helper-api.md § Function 2`.

5. **`read_freshness_pointer(state_dir=STATE_DIR_DEFAULT, *, touchpoint_name=None) → datetime`**: thin wrapper over `state.read_freshness` returning a UTC datetime. Used by tests + ad-hoc operator queries.

6. **`read_completion_timestamps(domain, task_id, state_log_dir) → CompletionTimestamps`**: stream-read `{state_log_dir}/{domain}-history.jsonl`; find the row with latest `timestamp` where `state == "complete"` and `task_id` matches. Return `(at_utc, date_et)` or `(None, None)` if no matching row. Contract in `contracts/helper-api.md § Function 4`.

7. **`is_cache_healthy(sla, state_dir=STATE_DIR_DEFAULT) → bool`**: non-raising utility. Wraps `read_cached_tasks` in try/except OSError → return False; else True. Used by operator quickstart commands (per `quickstart.md`).

8. **Error message format**: every `OSError` raised by this module follows `[<touchpoint_name>] <one-line summary>. Recovery: <one-line recovery hint>.` Implementation suggestion: a private `_format_error(touchpoint_name, summary, recovery)` helper.

**Files**:
- `scripts/common/sync_cache.py` (~220 lines)

**Reference precedent**: `scripts/common/state_log.py` lives in the same directory and uses the same import conventions. Match its style.

**Validation**:
- [ ] Module imports cleanly with no I/O (no `STATE_DIR_DEFAULT` directory access at import time)
- [ ] All 5 public functions exposed at module scope
- [ ] All 4 SLA constants exposed
- [ ] Error message format matches the contract verbatim (verified in tests via substring assertions)
- [ ] `read_cached_task_by_id` does NOT include the private task's title or fields in any error message (privacy boundary; verified in tests)

---

## Subtask T002 — `tests/common/__init__.py` + `tests/common/conftest.py`: shared fixtures [P]

**Purpose**: Provide the pytest fixtures every WP02/WP03 test consumes. `mock_sync_cache_fixture` builds synthetic cache state on `tmp_path` + monkeypatches `STATE_DIR_DEFAULT`. `mock_state_log_fixture` writes a synthetic per-domain JSONL log.

**Steps**:

1. Create `tests/common/__init__.py` (empty package marker).

2. Create `tests/common/conftest.py` per [`contracts/test-fixture.md`](../contracts/test-fixture.md). Two fixtures:

   - **`mock_sync_cache_fixture`**: returns a builder function. Builder signature: `(*, tasks: dict[int, dict], freshness_age_seconds: float = 60.0, private_project_ids: frozenset[int] = frozenset(), vikunja_updated_at_per_task: dict[int, str] | None = None, felix_last_observed_at: str | None = None) -> Path`. Implementation:
     - Compute pointer UTC = `now_utc - freshness_age_seconds`.
     - For each task: construct `TaskCacheEntry`-shaped data. `is_private = task.get("project_id") in private_project_ids`; if private, `fields = {}`; else fields contains the 7 TRACKED_TASK_FIELDS values.
     - Construct `TaskCacheRecord` + `FreshnessPointer` via `state.TaskCacheRecord(...)` constructors (use the typed dataclasses).
     - Write to `tmp_path / "sync"` via `state.write_freshness(...)` and `state.write_task_cache(...)`.
     - `monkeypatch.setattr` on both `scripts.common.sync_cache.STATE_DIR_DEFAULT` and `scripts.sync.state.STATE_DIR_DEFAULT` to point at `tmp_path / "sync"`.
     - Assertion that `build` may only be called once per test (set a flag; subsequent calls raise `AssertionError`).
     - Return the `tmp_path / "sync"` path.

   - **`mock_state_log_fixture`**: returns a builder. Signature: `(*, domain: str, entries: list[dict]) -> Path`. Writes `tmp_path / "state-logs" / f"{domain}-history.jsonl"` with one JSON record per line. Returns the log path. No monkeypatch needed — `read_completion_timestamps` takes `state_log_dir` as an explicit argument.

3. Top-level `tests/conftest.py` (the existing file) needs a small addition: a fixture that patches `urllib.request.urlopen` to raise `RuntimeError("test attempted live HTTP")` by default. Tests that need real urlopen mocking (write-side tests) re-patch over this guard. **This is a global test-isolation guard, not the mock_sync_cache_fixture itself.** Implementer adds it to existing conftest if it isn't there already.

**Files**:
- `tests/common/__init__.py` (3 lines)
- `tests/common/conftest.py` (~120 lines)
- `tests/conftest.py` may receive a small addition (~10 lines) — verify whether the global urlopen guard already exists; if not, add it.

**Validation**:
- [ ] `mock_sync_cache_fixture` builder is single-call per test (asserts on second call)
- [ ] After build runs, the synthetic cache exists on `tmp_path` and the monkeypatch is in effect
- [ ] `mock_state_log_fixture` writes valid JSONL (each line is a valid JSON record)
- [ ] No live I/O — tests using the fixtures pass on a system without `/data/services/openclaw/state/`

---

## Subtask T003 — `tests/common/test_sync_cache.py`: full helper unit tests [P]

**Purpose**: Cover every public function of `sync_cache.py` with happy path + every documented failure path. This is the foundation contract; downstream WPs trust these tests as the helper's quality gate.

**Steps**:

1. Build test cases grouped by function. Reference set (mirror the testing contract in [`contracts/helper-api.md` § Testing contract](../contracts/helper-api.md)):

   - `TestReadCachedTasks`:
     - happy path (3 synthetic tasks, fresh pointer)
     - cache missing (no `task-cache.json` exists) → raises with "freshness pointer missing" or equivalent
     - stale (freshness_age_seconds > SLA's seconds) → raises with "stale beyond SLA_NORMAL" + pointer age
     - schema version mismatch → propagates the underlying `state.py` error message
     - touchpoint_name appears in error messages

   - `TestReadCachedTaskById`:
     - happy path (task in cache)
     - task not found → raises with task_id in message + cache's last_polled_utc
     - private task (empty fields) → raises with task_id in message but NO field content (assert "title" NOT in message body)
     - propagates `read_cached_tasks` errors

   - `TestReadFreshnessPointer`:
     - returns datetime with `tzinfo=timezone.utc`
     - missing freshness file → raises

   - `TestReadCompletionTimestamps`:
     - happy path: latest "complete" event returned
     - no completions for task_id: returns `CompletionTimestamps(None, None)` — NOT an error
     - missing state log file → raises
     - malformed JSONL line: skips (defensive)
     - multiple "complete" events: returns the latest by `timestamp`

   - `TestSLATiers`:
     - all 4 constants have expected `(name, seconds)` values
     - SLA_HOT.seconds == 60, SLA_NORMAL.seconds == 900, etc.

   - `TestIsCacheHealthy`:
     - True on fresh cache
     - False on stale cache
     - False on missing cache
     - never raises

2. Tests use `mock_sync_cache_fixture` + `mock_state_log_fixture` for synthetic state. `monkeypatch` for `datetime.now(timezone.utc)` where deterministic stale tests need it.

3. Error message format assertions: each "raises" test checks for the specific substring the contract requires (e.g., `"stale beyond SLA_NORMAL"`, `"task 14 not in sync cache"`, `"is private-project (data unavailable in cache)"`).

**Files**:
- `tests/common/test_sync_cache.py` (~200 lines)

**Validation**:
- [ ] `python3 -m pytest tests/common/test_sync_cache.py -q` passes
- [ ] Every public function has at least one happy-path test + at least one failure-path test
- [ ] Privacy boundary test asserts the title/field content is absent from the error message

---

## Subtask T004 — Architecture-doc updates per change-control [P]

**Purpose**: Discharge the standing directive in `CLAUDE.md` for data-flow changes. The mission changes WHICH source the 6 affected services consume — that IS a data-flow change.

**Steps**:

1. **`docs/design/architecture/data/service-inventory.json`**: locate the 6 affected services (their crons / scripts):
   - `habits-checkin` / `habits-cron` / `habits-sweeper` (whichever invokes the migrated touchpoints; verify by inspecting the existing inventory)
   - `escalation-cron`
   - `enrichment-cron`

   For each, add an entry to the service's `dependencies` array (or equivalent field per the existing schema):
   ```json
   {
     "target": "felix-vikunja-sync-driver",
     "type": "consumes",
     "description": "Reads task state from /data/services/openclaw/state/sync/task-cache.json via scripts/common/sync_cache.py (post-#519 migration)"
   }
   ```

   Update top-level `last_updated` to `2026-06-04` and prepend `#519-touchpoint-migration` to the `updated_by` string.

2. **`docs/design/architecture/data/data-flows.json`** (if it exists): add or update entries documenting the new flow:
   - From: each of the 6 migrated touchpoints
   - To: `/data/services/openclaw/state/sync/task-cache.json` (via `scripts/common/sync_cache.py`)
   - Direction: read
   - Pre-#519 flow: deprecate / mark as removed

   Update top-level metadata.

3. Run `python3 tooling/scripts/validate_docs.py` from repo root. Expected: exit 0. **Important lesson from #518 WP06**: if a runbook block in any doc requires regeneration, run `python3 tooling/scripts/build_runbook_filter.py --write` first. No new runbook in this mission, so unlikely to apply — but verify.

**Files**:
- `docs/design/architecture/data/service-inventory.json` (edit)
- `docs/design/architecture/data/data-flows.json` (edit if it exists; may not exist yet — verify before editing)

**Validation**:
- [ ] `python3 tooling/scripts/validate_docs.py` returns 0
- [ ] Top-level `updated_by` in each edited JSON includes `#519`
- [ ] The 6 affected services each have a "consumes from sync-driver" entry

---

## Test strategy

Mocked unit tests for the helper. No live integration tests (per memory `feedback_no_live_integration_tests`). Verify the full sync test suite from #518 still passes — this WP doesn't touch `scripts/sync/`, but a sanity run guards against unforeseen cross-dependencies.

```bash
python3 -m pytest tests/sync/ tests/common/ -q
```

Combined target: existing 194 sync tests still pass + new ~30 helper tests pass. Total: ~225+ passing.

---

## Definition of Done

- [ ] All 4 subtasks complete; all listed files committed in the WP01 worktree
- [ ] `python3 -m pytest tests/sync/ tests/common/ -q` passes
- [ ] `python3 -c "from scripts.common.sync_cache import read_cached_tasks, SLA_NORMAL; print('OK')"` succeeds
- [ ] `python3 tooling/scripts/validate_docs.py` returns 0
- [ ] No edits outside the WP's `owned_files` list
- [ ] Error message format from helper matches the contract verbatim (tested)
- [ ] No unused imports (lint cleanup pattern from #518 final WPs)

---

## Risks and mitigations

- **Risk**: The shared fixture pattern (single-call builder) is unusual for tests that want to vary cache state across multiple test cases. Mitigation: documented in contracts/test-fixture.md as a deliberate design choice; downstream WPs handle multi-scenario testing by writing multiple separate tests, not by re-calling the builder.
- **Risk**: Architecture-doc edits may conflict with concurrent mission edits to the same JSON files. Mitigation: WP01 runs first; no parallel mission is touching architecture data right now (per `git log -1 docs/design/architecture/data/`).
- **Risk**: `tooling/scripts/validate_docs.py` may surface a stale-block error this WP didn't cause (same pattern as #518 WP06 cycle-1 rejection). Mitigation: run `build_runbook_filter.py --write` before commit if validate_docs flags any portal-filter issue, even though this WP doesn't add a runbook.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Module surface matches contract**: read `contracts/helper-api.md` side-by-side with `scripts/common/sync_cache.py`. Every function signature + return type + behavior contract item lines up.
2. **Error message format is exact**: a `grep '_format_error\|Recovery:' scripts/common/sync_cache.py` should show the format constructor centralized; error messages assembled from it. Tests assert substrings.
3. **No I/O at import time**: importing `sync_cache` does NOT create any directories or read any files.
4. **Fixture is single-call**: try calling the builder twice in a single test; should raise `AssertionError`.
5. **Architecture data: verify the 6 affected services are correctly identified.** This is the load-bearing accuracy check — wrong services here means wrong downstream consumer assumptions in future missions.
6. **`validate_docs.py` was run and passed**: re-run as part of review.

Reject if the helper has I/O at import, if error messages leak field content for private tasks, if architecture data isn't updated, or if `validate_docs.py` fails.

---

## References

- Mission spec: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/spec.md`
- Mission plan: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/plan.md`
- Helper API contract: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/contracts/helper-api.md`
- Test fixture contract: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/contracts/test-fixture.md`
- Phase 0 research: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/research.md`
- #518 state.py (the driver's cache writers/readers): `scripts/sync/state.py`
- Existing shared helper precedent: `scripts/common/state_log.py`
- Test pattern precedent (the fixture style): `tests/sync/test_state.py`, `tests/habits/test_record_completion.py`

## Activity Log

- 2026-06-04T22:35:26Z – claude:sonnet:implementer:implementer – shell_pid=15240 – Assigned agent via action command
- 2026-06-04T22:47:10Z – claude:sonnet:implementer:implementer – shell_pid=15240 – Ready for review: sync cache helper (5 functions, 4 SLA tiers, privacy boundary), shared fixtures (mock_sync_cache_fixture + mock_state_log_fixture), 48 tests (all passing), arch doc updates (habit-checkin + escalation-daily + enrichment-helpers dependencies + data-flows entry).
- 2026-06-04T22:47:46Z – claude:opus:reviewer:reviewer – shell_pid=19157 – Started review via action command
