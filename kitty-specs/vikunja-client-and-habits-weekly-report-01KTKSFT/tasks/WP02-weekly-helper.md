---
work_package_id: WP02
title: Weekly habit-report helper + tests
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-006
- FR-011
- FR-012
- FR-013
tracker_refs: []
planning_base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
merge_target_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
base_commit: 7c8fab05f589d715516b71b2b03c65692e86ed65
created_at: '2026-06-08T16:17:10.430691+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
- T013
shell_pid: "25911"
history: []
authoritative_surface: scripts/habits/
execution_mode: code_change
owned_files:
- scripts/habits/query_active_habits_weekly.py
- tests/habits/test_query_active_habits_weekly.py
- tests/habits/fixtures/weekly_report_responses.json
tags: []
agent: "codex:gpt-5:reviewer-renata:reviewer"
---

# WP02: Weekly habit-report helper + tests

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Deliver `scripts/habits/query_active_habits_weekly.py` — the deterministic helper that queries Vikunja's `done_at` history via WP01's shared client, classifies habits per the daily / weekday-in-title rules, computes per-habit completion percentages over a current + prior 7-day window, and emits the WeeklyHabitReport JSON on stdout. Replaces felix-admin-habits' LLM-improvised data path entirely.

Per Felix Constitution Directive 6, this is the deterministic surface of the mission's user-facing fix. The helper is pure: same Vikunja state + same args → same JSON output (NFR-004 idempotency).

## Context

- **Authority docs**: `spec.md` FR-003 / FR-004 / FR-005 / FR-006 / FR-011 / FR-012 / FR-013; `contracts/query_active_habits_weekly.md` (CLI + algorithm + fixtures); `contracts/weekly_report_payload.md` (output JSON shape); `data-model.md` (HabitClassifier + WeeklyHabitReport entities); `research.md` § R-001 (recurrence model: daily=86400, weekday-in-title=0+title parse), R-002 (`done_at` queryable), R-003 (sync cache untouched).
- **Existing patterns to follow**:
  - `scripts/habits/query_active_habits_v2.py` — UNCHANGED in this mission; read it end-to-end to mirror the day-of-week filter from mission #408 (specifically `_weekday_name_for_date` + `_WEEKDAY_BY_INDEX`).
  - WP01's `scripts/common/vikunja_client.py` — the shared client this helper consumes.
  - `scripts/calendar_routing/validate_calendar_event.py` (#558) — most recent stdlib-only helper precedent for stdin/stdout + exit-code conventions.
- **Standard library only beyond the client**.
- **The morning check-in path is UNCHANGED**: do NOT modify `query_active_habits_v2.py` or `scripts/common/sync_cache.py`.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP02 --agent <name>` (depends on WP01; finalize-tasks computes lane base)
- Depends on: WP01 (the VikunjaClient must exist).

---

## Subtask T007: Scaffold module

**Purpose**: Establish the module file with imports, docstring, top-level constants.

**Steps**:
1. Create `scripts/habits/query_active_habits_weekly.py`. Stdlib only.
2. Module docstring summarizing purpose + references to spec FRs + contracts.
3. Imports: `argparse`, `json`, `re`, `sys`, `dataclasses`, `datetime` (datetime, timezone, timedelta), `typing`, plus `from scripts.common.vikunja_client import VikunjaClient, VikunjaError`.
4. Top-level constants:
   ```python
   HABITS_PROJECT_ID = 13
   DAILY_REPEAT_AFTER = 86400  # seconds
   WEEKDAY_PATTERN = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(day)?\b", re.IGNORECASE)
   WEEKDAY_TO_ISO = {"mon": "MON", "tue": "TUE", "wed": "WED", "thu": "THU", "fri": "FRI", "sat": "SAT", "sun": "SUN"}
   ```

**Files**:
- `scripts/habits/query_active_habits_weekly.py` (NEW — scaffold ~30 lines)

**Validation**:
- [ ] Module imports cleanly: `python3 -c "from scripts.habits import query_active_habits_weekly"`
- [ ] `HABITS_PROJECT_ID == 13` (mirrors v2)
- [ ] `WEEKDAY_PATTERN.search("Strength training — Wednesday").group(1).lower()` returns `"wed"`

---

## Subtask T008: Implement `HabitClassifier`

**Purpose**: Pure functions for habit classification + scheduled-day computation. Per FR-004.

**Steps**:
1. Implement `parse_weekday_in_title(title: str) -> frozenset[str]`:
   - Find all matches of `WEEKDAY_PATTERN` in `title`.
   - Convert to uppercase ISO weekday names (MON, TUE, WED, ...).
   - Return as frozenset (empty if no matches).
2. Implement `classify_habit(task: dict) -> str` returning `"daily"`, `"weekday-in-title"`, or `"other"`:
   - If `task["repeat_after"] == DAILY_REPEAT_AFTER` AND `parse_weekday_in_title(task["title"])` is empty → `"daily"`
   - If `task["repeat_after"] == 0` AND `parse_weekday_in_title(task["title"])` non-empty → `"weekday-in-title"`
   - Otherwise → `"other"`
3. Implement `scheduled_days_for_window(kind: str, title: str, window_start: datetime, window_end: datetime) -> int`:
   - `kind == "daily"`: return number of complete days in `[window_start, window_end)`. For a 7-day window, this is 7.
   - `kind == "weekday-in-title"`: parse weekdays from title; count days in window where the day-of-week matches any parsed weekday. For a 7-day window with one weekday in title, this is 1.
   - `kind == "other"`: return 0 (these are filtered before reaching the report).

**Files**:
- `scripts/habits/query_active_habits_weekly.py` (extends to ~90 lines total)

**Validation**:
- [ ] `parse_weekday_in_title("Strength training — Wednesday")` → `frozenset({"WED"})`
- [ ] `parse_weekday_in_title("Read 30 min minimum")` → empty frozenset
- [ ] `classify_habit({"repeat_after": 86400, "title": "Meditate"})` → `"daily"`
- [ ] `classify_habit({"repeat_after": 0, "title": "Strength training — Wednesday"})` → `"weekday-in-title"`
- [ ] `classify_habit({"repeat_after": 0, "title": "Upload cardiac lab history"})` → `"other"`
- [ ] `scheduled_days_for_window("daily", "...", <Mon>, <Mon+7>)` → 7
- [ ] `scheduled_days_for_window("weekday-in-title", "X — Wednesday", <Mon>, <Mon+7>)` → 1

---

## Subtask T009: Vikunja query loop + done_at filtering + aggregation

**Purpose**: Fetch all done tasks in project 13, paginate, filter by `done_at` window, aggregate by habit_title.

**Steps**:
1. Implement `query_completion_events(client: VikunjaClient, window_start: datetime, window_end: datetime, prior_window_start: datetime, prior_window_end: datetime) -> dict[str, dict]`:
   - Paginate `client.get(f"/projects/{HABITS_PROJECT_ID}/tasks", params={"filter": "done=true", "per_page": "200", "page": str(n)})` until response is empty or shorter than 200.
   - For each task, parse `done_at` (handle missing/None — skip with warning).
   - Classify via `classify_habit`. Skip kind="other".
   - For each event whose `done_at` falls in current window: increment `events_by_title[title]["current"]++`.
   - For each event whose `done_at` falls in prior window: increment `events_by_title[title]["prior"]++`.
   - Also store `events_by_title[title]["kind"]` and `events_by_title[title]["sample_title"]`.
2. Also fetch ACTIVE (not-done) tasks via `?filter=done=false` for the same project; classify; ensure habits with zero completions are still represented with 0 counts.
3. Return a dict keyed by canonical title.

**Files**:
- `scripts/habits/query_active_habits_weekly.py` (extends to ~180 lines total)

**Validation**:
- [ ] Helper handles pagination correctly (200 records per page)
- [ ] Tasks with `done_at` outside both windows are excluded
- [ ] Tasks classified as "other" are excluded
- [ ] Habits with 0 completions in the window are still represented in the output dict (from the active-tasks pass)
- [ ] Handles missing `done_at` gracefully (skip with stderr warning, don't crash)

---

## Subtask T010: WeeklyHabitReport JSON + CLI + exit codes

**Purpose**: Compute final report JSON shape per `contracts/weekly_report_payload.md`; wire CLI args; implement exit codes per contract.

**Steps**:
1. Implement `build_report(events_by_title, window_start, window_end, prior_window_start, prior_window_end) -> dict`:
   - For each habit, compute `scheduled_days_current` + `scheduled_days_prior` via `scheduled_days_for_window`.
   - Compute `percent_current` = `100.0 * completed_events_current / scheduled_days_current` (0.0 if scheduled is 0).
   - Compute `percent_prior` same way.
   - Sort: daily first (alphabetical), then weekday-in-title (sorted by primary weekday Mon→Sun, then title).
   - Compute overall: `100.0 * sum(completed_current) / sum(scheduled_current)`.
   - Return dict matching the JSON schema.
2. Implement `main(argv: list[str] | None = None) -> int`:
   - Parse `--window-end` (default today UTC), `--window-days` (default 7), `--include-baseline` / `--no-include-baseline` flags.
   - Compute window datetimes.
   - Instantiate `VikunjaClient`.
   - Try: query events, build report, write JSON to stdout, log `weekly_report_generated`, return 0.
   - Except `VikunjaError` as exc: write stderr diagnostic, log `weekly_report_failed`, return 3.
   - Except `ValueError` (bad args): return 2.
   - Except (BaseException) for unknown errors: return 4.
3. Add `if __name__ == "__main__": sys.exit(main())`.

**Files**:
- `scripts/habits/query_active_habits_weekly.py` (extends to ~250 lines total)

**Validation**:
- [ ] `python3 -m scripts.habits.query_active_habits_weekly --help` exits 0 and shows the documented flags
- [ ] `python3 scripts/habits/query_active_habits_weekly.py` with mocked client returns valid JSON on stdout
- [ ] Exit codes: 0 (success), 2 (bad args), 3 (VikunjaError), 4 (internal)
- [ ] JSON output validates against `contracts/weekly_report_payload.md` shape

---

## Subtask T011: log_action calls

**Purpose**: Wire observability per FR-013.

**Steps**:
1. Add import: `import subprocess` (or use a Python-side helper if log_action.py exposes one — check existing usage in `scripts/inbox/` and `scripts/habits/`).
2. In `main()`'s success branch: invoke log_action.py with `--action weekly_report_generated --category routine --context '<json>'` where the JSON includes window dates, habit_count, overall_percent_current.
3. In `main()`'s VikunjaError branch: invoke with `--action weekly_report_failed --category error --context '<json>'` where the JSON includes error_class, error_detail (the redaction-safe `str(exc)`), and the path.
4. Use `subprocess.run` with `check=False` (don't propagate log_action failures into the helper's exit code).

**Files**:
- `scripts/habits/query_active_habits_weekly.py` (extends to ~280 lines total)

**Validation**:
- [ ] On successful run, log_action.py is invoked with `weekly_report_generated`
- [ ] On VikunjaError, log_action.py is invoked with `weekly_report_failed`
- [ ] log_action failure does not affect the helper's exit code

---

## Subtask T012 [P]: Curate test fixtures

**Purpose**: Author the 8 fixture scenarios per `contracts/query_active_habits_weekly.md` § Test fixtures. Can run in parallel with implementation.

**Steps**:
1. Create `tests/habits/fixtures/weekly_report_responses.json`. Each scenario is a list of mocked Vikunja API responses (sequentially returned to paginated calls) plus optional metadata.
2. Specifically populate the 8 scenarios:
   - `weekly_normal_data` — full week of varied completions for 7 daily + 3 weekday-in-title habits
   - `weekly_cardiac_non_habit_present` — adds a `repeat_after=0, title="Upload cardiac lab history"` task; verifies filtering
   - `weekly_baseline_nonzero` — prior window has real completions
   - `weekly_weekday_in_title_completed_on_match` — "Strength training — Wednesday" done on Wed in window
   - `weekly_weekday_in_title_skipped` — same habit NOT done
   - `weekly_partial_pagination` — >200 done tasks in window
   - `weekly_vikunja_unreachable` — mock client raises `VikunjaTimeoutError`
   - `weekly_bad_filter_syntax` — mock client raises `VikunjaBadRequestError`
3. Each scenario captures the expected report-output shape for direct comparison in tests.

**Files**:
- `tests/habits/fixtures/weekly_report_responses.json` (NEW)
- `tests/habits/conftest.py` (NEW or extended) — mock-client helpers

**Validation**:
- [ ] All 8 scenarios present
- [ ] JSON file parses cleanly
- [ ] Mock-client helpers can be imported by `test_query_active_habits_weekly.py`

---

## Subtask T013: Unit tests + coverage gate

**Purpose**: Test the full helper. Coverage ≥90% line, ≥85% branch.

**Steps**:
1. Create `tests/habits/test_query_active_habits_weekly.py`. Organize by area:
   - HabitClassifier tests (8+): one per kind + edge cases (empty title, all-uppercase, weekday in middle, etc.)
   - `scheduled_days_for_window` tests (6+): daily, weekday-in-title with various window shapes
   - Aggregation tests (5+): single-habit, multi-habit, empty result, duplicate-title rollup
   - End-to-end tests (8+): one per fixture scenario from T012
   - Exit-code tests (4+): one per exit code class
2. Coverage gate: add to pytest config (likely already done in WP01's T006) and verify `pytest tests/habits/test_query_active_habits_weekly.py --cov=scripts/habits/query_active_habits_weekly --cov-branch --cov-fail-under=90`.
3. Verify the 8 explicit regression-test scenarios from FR-012 (a-f) all pass.

**Files**:
- `tests/habits/test_query_active_habits_weekly.py` (NEW, ~300 lines)

**Validation**:
- [ ] `pytest tests/habits/test_query_active_habits_weekly.py -v` runs all tests
- [ ] All tests pass
- [ ] Coverage gate passes (line ≥90%, branch ≥85%)
- [ ] FR-012 (a-f) regression tests are explicitly named and pass

---

## Definition of Done

- [ ] All 7 subtasks complete with their per-subtask validation items checked.
- [ ] `pytest tests/habits/test_query_active_habits_weekly.py --cov=scripts/habits/query_active_habits_weekly --cov-branch --cov-fail-under=90` passes from clean checkout.
- [ ] No changes to `scripts/habits/query_active_habits_v2.py` or `scripts/common/sync_cache.py` (morning check-in path untouched per C-004).
- [ ] No uncommitted changes outside this WP's `owned_files`.

## Risks

1. **Vikunja's date-range filter syntax for `done_at`** — research.md OP-001 is unresolved. Mitigation: T009 fetches all done tasks and date-filters client-side. If Vikunja's server-side filter syntax can be confirmed later, optimize. The client-side filter is correct; it's just less efficient.
2. **Habit-title rollup edge cases** — e.g., a task renamed mid-week could produce two rows with similar titles. Mitigation: T009 uses verbatim title as the rollup key; document the behavior; treat renamed habits as separate (will surface to operator as two rows; operator can rename Vikunja tasks to merge).
3. **Coverage gate friction** — sonnet-driven implementation may hit edge cases hard to test. Mitigation: T013 emphasizes coverage-driven test design before implementation finalization.

## Reviewer guidance

- Reviewer runs the coverage command independently and verifies actuals.
- Reviewer checks: does the helper actually filter `kind == "other"` BEFORE aggregation? Cardiac task should never appear.
- Reviewer checks: weekday-in-title habits with multiple weekdays in title (e.g., "Yoga — Mon and Wed") — does parse_weekday_in_title return both? Does scheduled_days_for_window count both? Plan-phase did not encounter this case but it's a logical extension.
- Reviewer verifies log_action calls don't leak sensitive content (just window dates + counts).

## Activity Log

- 2026-06-08T16:17:13Z – claude:sonnet:python-pedro:implementer – shell_pid=12214 – Assigned agent via action command
- 2026-06-08T16:48:57Z – claude:sonnet:python-pedro:implementer – shell_pid=12214 – 67 tests, 98%/96% coverage. --force used: lane-b was manually rebased onto lane-a (per upstream spec-kitty#1684 / local #492 workaround) so lane-a's coord-tracked planning artifacts appear in lane-b's history. Code itself is clean WP02-only. Mission merge handles dedup via -X theirs (precedent #559).
- 2026-06-08T16:49:05Z – codex:gpt-5:reviewer-renata:reviewer – shell_pid=20185 – Started review via action command
- 2026-06-08T16:52:05Z – user – shell_pid=20185 – Moved to planned
- 2026-06-08T16:52:41Z – claude:sonnet:python-pedro:implementer – shell_pid=21673 – Started implementation via action command
- 2026-06-08T16:57:09Z – claude:sonnet:python-pedro:implementer – shell_pid=21673 – Cycle 2: emits weekly_report_anomaly log_action on cap (3 new tests). 70 tests, 98% coverage. NOTE: implementer flagged that log_action.py VALID_CATEGORIES rejects 'warning' so anomaly subprocess will fail silently per swallowed-failure design — contract emit happens, but JSONL doesn't receive. Reviewer please weigh in: accept as-is, or require switching category to 'flagged'?
- 2026-06-08T16:57:18Z – codex:gpt-5:reviewer-renata:reviewer – shell_pid=23035 – Started review via action command
- 2026-06-08T17:00:31Z – user – shell_pid=23035 – Moved to planned
- 2026-06-08T17:01:57Z – claude:sonnet:python-pedro:implementer – shell_pid=24941 – Started implementation via action command
- 2026-06-08T17:04:39Z – claude:sonnet:python-pedro:implementer – shell_pid=24941 – Cycle 3: category=flagged (per codex; warning was rejected by log_action.py). Real subprocess sanity check passed. 70 tests, 98.33% coverage.
- 2026-06-08T17:04:49Z – codex:gpt-5:reviewer-renata:reviewer – shell_pid=25911 – Started review via action command
- 2026-06-08T17:09:42Z – user – shell_pid=25911 – Arbiter override: review-cycle-4's sole objection was category=warning being rejected by log_action.py. Cycle 3 changed it to category=flagged; real subprocess exits 0, warning exits 1, and 70 tests pass at 98.33% coverage. Force acknowledges pre-existing coordination artifacts in lane history from the documented dependency rebase workaround. Review passed; anti-pattern checks 1-8 pass.
