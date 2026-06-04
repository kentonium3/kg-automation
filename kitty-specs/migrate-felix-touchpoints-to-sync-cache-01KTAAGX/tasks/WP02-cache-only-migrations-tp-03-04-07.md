---
work_package_id: WP02
title: 'Cache-only touchpoint migrations: TP-03, TP-04, TP-07'
dependencies:
- WP01
requirement_refs:
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: lane-per-WP; merge to main at mission end
subtasks:
- T005
- T006
- T007
- T008
- T009
- T010
history:
- at: '2026-06-04T22:24:02Z'
  by: spec-kitty.tasks
  note: Created WP02 from plan.md + contracts/migration-pattern.md for 3 cache-only TPs
authoritative_surface: scripts/habits/
execution_mode: code_change
owned_files:
- scripts/habits/query_active_habits_v2.py
- scripts/habits/set_due_dates.py
- scripts/habits/morning_checkin_list.py
- tests/habits/test_query_active_habits_v2.py
- tests/habits/test_set_due_dates.py
- tests/habits/test_morning_checkin_list.py
tags: []
---

# WP02 — Cache-only touchpoint migrations: TP-03, TP-04, TP-07

## Objective

Migrate the 3 cache-only habit touchpoints (TP-03, TP-04, TP-07) from direct Vikunja HTTP reads to reads from the `scripts/common/sync_cache.py` helper introduced in WP01. Each migration follows the 6-step pattern in [`contracts/migration-pattern.md`](../contracts/migration-pattern.md). "Cache-only" means the touchpoint needs only `read_cached_tasks` and/or `read_cached_task_by_id` — no state-log lookup (that's WP03's job).

After this WP, the 3 habit touchpoints listed in `owned_files` operate end-to-end against the on-disk cache. Zero Vikunja HTTP calls from those scripts during normal invocation. Per Q1's clean cutover: the old direct-read code is **deleted** in the same change.

## Context

Per [research.md § Scope Correction](../research.md), the actual #519 migration set is 6 touchpoints — 3 in this WP and 3 in WP03. The 3 in this WP are all in the habits domain because they happen to be the cache-only habit callsites:

- **TP-03** `scripts/habits/query_active_habits_v2.py` — enumerates active habit tasks; invoked by TP-07
- **TP-04** `scripts/habits/set_due_dates.py` (GET phase only) — reads tasks before computing new due dates; PUT phase stays on direct Vikunja per FR-010
- **TP-07** `scripts/habits/morning_checkin_list.py` — assembles the morning WhatsApp message; invokes TP-03

All 3 land on `SLA_NORMAL` (15 min) per research.md § Unknown 1. None need state-log access; their existing logic uses only fields already in `TRACKED_TASK_FIELDS`.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree per WP; commits inside the worktree.

## Implementation command

```bash
spec-kitty agent action implement WP02 --agent <name>
```

Depends on WP01.

---

## Subtask T005 — TP-03 migrate `scripts/habits/query_active_habits_v2.py`

**Purpose**: Replace TP-03's `GET /tasks/all?...` Vikunja call with `read_cached_tasks(SLA_NORMAL, touchpoint_name="habits.query_active_habits_v2")`. The function's return shape (list of active habit dicts, sorted by `position`) is preserved.

**Steps**:

1. Open `scripts/habits/query_active_habits_v2.py`. Locate the direct-Vikunja-read code (typically a `_http_request("GET", ...)` call or imports from `record_completion`'s `_http_request` helper).

2. Add the canonical imports near the top:
   ```python
   from scripts.common.sync_cache import (
       read_cached_tasks,
       SLA_NORMAL,
       SLATier,
   )
   ```

3. Add module-level constants:
   ```python
   TOUCHPOINT_SLA: SLATier = SLA_NORMAL
   TOUCHPOINT_NAME = "habits.query_active_habits_v2"
   ```

4. Replace the direct-Vikunja read with the helper invocation. Example pattern:
   ```python
   cached_tasks = read_cached_tasks(
       sla=TOUCHPOINT_SLA,
       touchpoint_name=TOUCHPOINT_NAME,
   )
   active_tasks = []
   for task_id, view in cached_tasks.items():
       if view.is_private:
           continue  # skip private-project tasks
       if view.fields.get("done") is True:
           continue  # only active = not done
       if view.fields.get("project_id") != HABITS_PROJECT_ID:
           continue  # only habits project
       active_tasks.append({
           "id": task_id,
           "title": view.fields.get("title"),
           "due_date": view.fields.get("due_date"),
           "repeat_after": view.fields.get("repeat_after"),
           # ... other fields the existing logic uses
       })
   ```
   The exact field-set in each dict matches the pre-migration return shape — verify by inspecting the existing return tuple/dict.

5. Let `OSError` from `read_cached_tasks` propagate. If the function has a top-level `main()` or CLI entry point: catch OSError, write to stderr with prefix `[habits.query_active_habits_v2]`, exit 3. Match the spec's "no silent fallback" contract (FR-006).

6. Delete the old direct-Vikunja-read code: the `_http_request` call, any `_read_token` or `vikunja-api` token-read code, any Vikunja URL constants used ONLY by the deleted GETs, and `import urllib.request` if it was used only for this read.

7. Update the module docstring: from "Reads from Vikunja's /tasks/all endpoint" to "Reads from the sync cache at /data/services/openclaw/state/sync/task-cache.json (see scripts/common/sync_cache.py for the canonical entry point)."

**Files**: `scripts/habits/query_active_habits_v2.py` (modified).

**Validation**:
- [ ] `grep -E 'urlopen|_http_request' scripts/habits/query_active_habits_v2.py` returns zero hits
- [ ] `grep 'import urllib' scripts/habits/query_active_habits_v2.py` either absent OR confirmed used only by retained code
- [ ] Existing callers of `query_active_today()` (e.g., TP-07) still get the same return shape
- [ ] Docstring updated

---

## Subtask T006 — TP-03 update `tests/habits/test_query_active_habits_v2.py` [P]

**Purpose**: Replace `mock_urlopen` for the GET path with `mock_sync_cache_fixture`. Verify every documented failure path produces structured stderr + non-zero exit.

**Steps**:

1. Remove any test fixtures or class-level setup that mocks `urllib.request.urlopen` for the GET path. (If the test file mixes GET+other I/O mocks, retain non-GET mocks.)

2. Add `from tests.common.conftest import mock_sync_cache_fixture` import where needed. (Pytest auto-discovers fixtures via conftest; the import is for static-analysis clarity.)

3. Rewrite test cases:

   - **Happy path**: synthesize 3 active habit tasks + 2 done tasks in `mock_sync_cache_fixture`. Call `query_active_today()`. Assert: returns the 3 active tasks in correct order; zero Vikunja calls (verified via the global urlopen guard from WP01 T002).

   - **Cache missing**: synthesize no cache. Call `query_active_today()`. Assert: raises `OSError` with substring "freshness pointer missing" and `[habits.query_active_habits_v2]` prefix.

   - **Stale cache**: synthesize cache with `freshness_age_seconds=1500` (beyond SLA_NORMAL's 900s). Assert: raises with substring "stale beyond SLA_NORMAL".

   - **Private-project tasks skipped**: synthesize 1 private-project task (`private_project_ids={X}`) + 2 normal. Assert: returns only the 2 normal tasks; private one is skipped (NOT raised — bulk enumeration treats private as "skip" per migration-pattern EC-7).

   - **Empty cache (no tasks)**: synthesize empty `tasks={}`. Assert: returns empty list.

**Files**: `tests/habits/test_query_active_habits_v2.py` (modified).

**Validation**:
- [ ] `python3 -m pytest tests/habits/test_query_active_habits_v2.py -q` passes
- [ ] No `mock_urlopen` calls in the test file for the GET path
- [ ] All documented failure modes tested

---

## Subtask T007 — TP-04 migrate `scripts/habits/set_due_dates.py` (GET phase only)

**Purpose**: Replace the GET phase of `set_due_dates.py` with `read_cached_tasks`. **The PUT phase (writes new due dates back to Vikunja) is unchanged** — TP-05 is write-only and out of scope per FR-010. This is the trickiest subtask because the file has both read and write paths in the same module.

**Steps**:

1. Open `scripts/habits/set_due_dates.py`. Identify the GET-phase code (where it reads task state before computing new due dates) and the PUT-phase code (where it writes new due_dates back via `POST /tasks/<id>` per #524's read-modify-write pattern).

2. Apply the standard migration pattern to the GET phase ONLY:
   - Add imports: `from scripts.common.sync_cache import read_cached_tasks, SLA_NORMAL, SLATier`
   - Add constants: `TOUCHPOINT_SLA = SLA_NORMAL`, `TOUCHPOINT_NAME = "habits.set_due_dates"`
   - Replace the GET call with `read_cached_tasks(sla=TOUCHPOINT_SLA, touchpoint_name=TOUCHPOINT_NAME)`
   - Propagate OSError to non-zero exit
   - **Delete ONLY the GET-side direct-read code**: the `_http_request("GET", ...)` calls and any Vikunja URL constants used only by those GETs.

3. **CRITICAL**: do NOT delete the PUT-side code. Specifically:
   - The `_http_request` helper function itself stays (used by PUT)
   - The `_read_token` function stays (PUT needs the token)
   - `import urllib.request` stays
   - The Vikunja URL constants for PUT endpoints stay
   - The PUT phase logic stays verbatim — including the read-modify-write pattern from #524 (re-read task before POST to preserve `repeat_after` etc.)

4. Update the module docstring: GET-phase comment updated to mention cache reads; PUT-phase comment unchanged.

**Files**: `scripts/habits/set_due_dates.py` (modified in-place; mixed GET+PUT changes).

**Validation**:
- [ ] `grep -nE 'urlopen|_http_request.*GET' scripts/habits/set_due_dates.py` returns zero hits matching the GET phase
- [ ] `grep -nE '_http_request.*POST|_http_request.*PUT' scripts/habits/set_due_dates.py` returns hits — the PUT phase is intact
- [ ] `_read_token` and `import urllib.request` retained
- [ ] PUT phase's read-modify-write pattern (from #524) is untouched

---

## Subtask T008 — TP-04 update `tests/habits/test_set_due_dates.py` [P]

**Purpose**: Replace GET-side test mocks with `mock_sync_cache_fixture`. Retain PUT-side `mock_urlopen` mocks verbatim.

**Steps**:

1. Identify which test cases exercise the GET phase vs. PUT phase. (Most test files mix them; the implementer reads the existing structure.)

2. For GET-phase tests:
   - Drop `mock_urlopen` setup for that test
   - Add `mock_sync_cache_fixture` parameter to the test function
   - Synthesize cache state appropriate to the test's setup
   - Same failure-mode tests as T006: cache missing, stale, private (skip)

3. For PUT-phase tests:
   - Leave verbatim. Existing `mock_urlopen` patches for PUT calls stay.
   - Add a NOTE comment at the top of those tests: "PUT phase tests retained verbatim — TP-05 is write-only and out of scope per spec FR-010."

4. End-to-end test (if exists — a test that exercises GET → compute → PUT in one flow): combine `mock_sync_cache_fixture` (for the GET) + `mock_urlopen` (for the PUT). Both fixtures should coexist in the same test.

**Files**: `tests/habits/test_set_due_dates.py` (modified).

**Validation**:
- [ ] `python3 -m pytest tests/habits/test_set_due_dates.py -q` passes
- [ ] GET-phase tests use `mock_sync_cache_fixture`
- [ ] PUT-phase tests retain `mock_urlopen`
- [ ] End-to-end tests (if any) successfully combine both fixtures

---

## Subtask T009 — TP-07 migrate `scripts/habits/morning_checkin_list.py`

**Purpose**: TP-07 invokes TP-03's `query_active_today()` and assembles the morning WhatsApp payload. After TP-03 is migrated (T005), TP-07's invocation of it automatically benefits from the cache. But TP-07 may have its OWN direct Vikunja calls (e.g., to fetch project metadata or task details beyond what `query_active_today` returns). Verify and migrate those.

**Steps**:

1. Open `scripts/habits/morning_checkin_list.py`. Read it carefully:
   - Does it invoke `query_active_today()` only? Then no GET calls of its own — DELETE no Vikunja code from this file (TP-03's migration is what helps).
   - Does it ALSO `_http_request("GET", ...)` for additional data (project lookups, etc.)? Then apply the standard migration pattern to THOSE calls.

2. If migration is needed (additional GETs): standard 6-step pattern (imports, constants `TOUCHPOINT_NAME = "habits.morning_checkin_list"`, helper call, OSError propagation, delete direct code, docstring update).

3. If no additional GETs: just update the docstring to reflect the indirect cache usage via TP-03 ("Reads active habits via scripts/habits/query_active_habits_v2, which now reads from the sync cache").

**Files**: `scripts/habits/morning_checkin_list.py` (modified or docstring-only-modified depending on inspection).

**Validation**:
- [ ] `grep -nE 'urlopen|_http_request' scripts/habits/morning_checkin_list.py` returns zero hits
- [ ] The morning check-in output is unchanged (verified in T010 tests)

---

## Subtask T010 — TP-07 update `tests/habits/test_morning_checkin_list.py` [P]

**Purpose**: If T009 modified `morning_checkin_list.py` to use the helper, replace its test mocks. If T009 was docstring-only, this test file may need MINOR adjustments: it likely mocks `query_active_today()` indirectly via `mock_urlopen` for the GET that happened in TP-03 — that mock is now obsolete and should be replaced with `mock_sync_cache_fixture`.

**Steps**:

1. Identify how the existing tests stub TP-03's `query_active_today` for TP-07's tests:
   - If they call `query_active_today` and mock urlopen → replace urlopen mock with `mock_sync_cache_fixture` so the call resolves against the cache instead.
   - If they mock `query_active_today` directly → can stay as-is (function-level mock unaffected by the cache change).

2. Either way: add at least one test that uses the real `query_active_today` call against `mock_sync_cache_fixture` to verify end-to-end cache → check-in flow works.

3. Same failure-mode tests: cache missing → exit 3, stale → exit 3.

**Files**: `tests/habits/test_morning_checkin_list.py` (modified).

**Validation**:
- [ ] `python3 -m pytest tests/habits/test_morning_checkin_list.py -q` passes
- [ ] No `mock_urlopen` for the cache read path
- [ ] End-to-end cache → check-in test included

---

## Test strategy

All 3 touchpoints' test suites run under fully-mocked I/O via WP01's `mock_sync_cache_fixture`. Combined run:

```bash
python3 -m pytest tests/habits/test_query_active_habits_v2.py tests/habits/test_set_due_dates.py tests/habits/test_morning_checkin_list.py -q
```

Plus the global suite for regression check:

```bash
python3 -m pytest tests/sync/ tests/common/ tests/habits/ -q
```

---

## Definition of Done

- [ ] All 6 subtasks complete; all listed files committed in the WP02 worktree
- [ ] Full sync + common + habits test suites pass
- [ ] `grep -E 'urlopen|_http_request.*GET' scripts/habits/query_active_habits_v2.py scripts/habits/morning_checkin_list.py` returns zero hits
- [ ] `grep -E '_http_request.*POST|_http_request.*PUT' scripts/habits/set_due_dates.py` returns hits (PUT phase intact)
- [ ] All 3 touchpoints have `TOUCHPOINT_SLA = SLA_NORMAL` + `TOUCHPOINT_NAME` constants
- [ ] No edits outside the WP's `owned_files` list
- [ ] No edits to WP01-owned files (sync_cache.py, conftest.py, etc.)

---

## Risks and mitigations

- **TP-04 regression**: the GET/PUT split in `set_due_dates.py` is the trickiest migration in this WP. If the implementer accidentally deletes a PUT-side line, the daily sweeper that advances due_dates breaks. Mitigation: explicit grep validation step + dedicated PUT-side tests retained verbatim.
- **TP-03/TP-07 coupling**: TP-07 calls TP-03 at runtime. If TP-03 changes its return shape, TP-07 silently breaks. Mitigation: T005 explicitly preserves the existing return shape; T010 includes an end-to-end test that exercises both together.
- **Cache schema field absence**: spec FR-008 prohibits silent widening of `TRACKED_TASK_FIELDS`. If TP-03/TP-04/TP-07 needs a field outside the set, the WP must surface this as a research-extension finding (back to plan) rather than silently extending. Mitigation: research.md § Unknown 3 already verified all 3 touchpoints' field-sets fit; reviewer cross-checks by grep.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Each touchpoint follows the migration-pattern.md 6-step contract verbatim**: imports, constants, helper call, OSError propagation, deletion, docstring.
2. **TP-04's PUT phase is intact**: read `scripts/habits/set_due_dates.py` carefully and confirm `_http_request` + `_read_token` + URL constants + the read-modify-write pattern from #524 are all retained.
3. **Tests use the right fixtures**: GET-side tests use `mock_sync_cache_fixture`; PUT-side tests retain `mock_urlopen`.
4. **No leaked-Vikunja-call**: run the grep commands from the DoD verbatim; expect them to pass.
5. **Privacy boundary respected**: T005's bulk enumeration skips private tasks (per migration-pattern EC-7) rather than raising. Reviewer confirms `if view.is_private: continue` appears in the migrated code.

Reject if TP-04's PUT phase is broken, if any touchpoint silently widens TRACKED_TASK_FIELDS, or if tests still use `mock_urlopen` for read paths.

---

## References

- Mission spec: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/spec.md`
- Migration pattern contract: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/contracts/migration-pattern.md`
- WP01 helper module: `scripts/common/sync_cache.py` (post-WP01)
- WP01 test fixtures: `tests/common/conftest.py` (post-WP01)
- #518's #524 fix (read-modify-write pattern): `scripts/habits/record_completion.py` (TP-04 should follow the same pattern in its PUT phase, already established)
- RQ-2 per-TP citations: `docs/research/felix-vikunja-sync-architecture/findings/rq-2-touchpoints.md` § TP-03, TP-04, TP-07
