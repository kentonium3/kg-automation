# Work Packages: Trustworthy Weekly Habit Report

**Mission**: `trustworthy-weekly-habit-report-01KV4GZ7`
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md) | **Issue**: [#605](https://github.com/kentonium3/issues/605)
**Branch contract**: current=main → planning/base=main → merge target=main
**Date**: 2026-06-15

## Subtask Index

| ID | Description | WP | Parallel |
| --- | --- | --- | --- |
| T001 | Create `scripts/habits/history.py` with three public operations | WP01 | |
| T002 | Add unit tests for `completion_events_in_window` | WP01 | [P] |
| T003 | Add unit tests for `completion_rate_for_habit` | WP01 | [P] |
| T004 | Add unit tests for `scheduled_vs_completed_for_habit` | WP01 | [P] |
| T005 | Add golden-week fixture file | WP01 | |
| T006 | Remove `VikunjaClient.done_at` completion-history path from `query_active_habits_weekly.py` | WP02 | |
| T007 | Switch completion-history reads to `scripts.habits.history` wrapper | WP02 | |
| T008 | Add `--as-of` CLI flag for deterministic windowing | WP02 | |
| T009 | Implement `rendered_text` generation inside the helper | WP02 | |
| T010 | Fix 7-day window label format (no more "Jun 7–14" 8-day span) | WP02 | |
| T011 | Update existing tests + add golden-week behavior tests | WP02 | |
| T012 | Create `tests/architectural/test_habits_history_canonical_read.py` module | WP03 | |
| T013 | Implement AST scanner for `VikunjaClient` imports in `scripts/habits/*.py` | WP03 | |
| T014 | Declare `VIKUNJA_CURRENT_STATE_ALLOWLIST` with reasons | WP03 | |
| T015 | Add negative-control test that proves the scanner fires | WP03 | [P] |
| T016 | Add allowlist-sanity test that catches stale entries | WP03 | [P] |
| T017 | Strip in-prompt rendering rules from felix-admin-habits AGENTS.md weekly section | WP04 | |
| T018 | Update AGENTS.md cron-schedule reference text to Monday 06:00 ET | WP04 | |
| T019 | Verify AGENTS.md effective character budget per `reference_openclaw_gotchas` | WP04 | |
| T020 | Create `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` manifest | WP05 | |
| T021 | Verify openclaw cron primitive TZ field name in `scripts/deploy/lib/` and align manifest | WP05 | |
| T022 | Update `docs/design/architecture/data/service-inventory.json` weekly-tick description | WP06 | [P] |
| T023 | Update `docs/design/architecture/data/data-flows.json` weekly-tick flow entry | WP06 | [P] |
| T024 | Update `docs/design/architecture/data/signal-to-doc-map.json` if relevant entry exists | WP06 | [P] |
| T025 | Update narrative architecture counterpart (`services.md` or equivalent) if it carries the description | WP06 | [P] |

---

## WP01 — Habits-domain query wrapper

**Goal**: Create `scripts/habits/history.py` as the canonical habits-domain read API on top of `scripts/common/state_log.py`. Expose three operations the weekly helper and future trend-analysis tooling will consume.

**Priority**: P1 (foundation for WP02–WP06; nothing else can land cleanly without this)
**Estimated prompt size**: ~350 lines
**Dependencies**: none
**Requirement refs**: FR-002, FR-003, FR-007, NFR-001, NFR-005, SC-005
**Owned files**: `scripts/habits/history.py`, `tests/habits/test_history.py`, `tests/habits/fixtures/golden_week_jsonl.py`
**Authoritative surface**: `scripts/habits/history.py`
**Execution mode**: code_change
**Independent test**: `pytest tests/habits/test_history.py -v` green; module is importable; all three public operations raise `ValueError` on naive datetimes / inverted windows.

### Included subtasks

- [ ] T001 Create `scripts/habits/history.py` with three public operations (`completion_events_in_window`, `completion_rate_for_habit`, `scheduled_vs_completed_for_habit`) per `contracts/habits_history_wrapper.md`. Imports allowed: stdlib + `scripts.common.state_log`. Imports forbidden: `VikunjaClient`. (WP01)
- [ ] T002 [P] Add unit tests for `completion_events_in_window` covering empty JSONL, `habit_id` filter, multi-day events, tz-naive arg rejection, inverted-window rejection. (WP01)
- [ ] T003 [P] Add unit tests for `completion_rate_for_habit` covering perfect week, partial week, day-specific habit, `scheduled_days_count=0` rejection. (WP01)
- [ ] T004 [P] Add unit tests for `scheduled_vs_completed_for_habit` mirroring T003 with `(scheduled, completed)` assertions. (WP01)
- [ ] T005 Add `tests/habits/fixtures/golden_week_jsonl.py` providing a fixture function that builds a known JSONL state covering daily, day-specific, and week-bounded habits. Used by T002–T004 and reused by WP02's tests. (WP01)

### Implementation sketch

1. Confirm `scripts/common/state_log.py` `read("habits", task_id=..., date=..., state=...)` signature and return shape before importing — keep the wrapper a thin shim.
2. Implement window-bounded read as filter over the full read result; dedupe by `(task_id, date)` for rate operations.
3. Use `zoneinfo.ZoneInfo("America/New_York")` only where ET semantics are needed; do NOT call `datetime.now()` inside the module (callers pass `as-of`).
4. Tests use the golden-week fixture exclusively. No production JSONL touched.

### Parallel opportunities

T002 / T003 / T004 share no files and run in parallel.

---

## WP02 — Weekly helper rewrite (canonical-read + rendering)

**Goal**: Switch `scripts/habits/query_active_habits_weekly.py` to read completion history via the WP01 wrapper, move WhatsApp rendering into the helper, and fix the 7-day window label.

**Priority**: P1 (the actual bug-fix payload)
**Estimated prompt size**: ~450 lines
**Dependencies**: WP01
**Requirement refs**: FR-002, FR-005, FR-006, FR-007, FR-009, FR-010, NFR-001, NFR-004, NFR-005, SC-001, SC-002, SC-004
**Owned files**: `scripts/habits/query_active_habits_weekly.py`, `tests/habits/test_query_active_habits_weekly.py`
**Authoritative surface**: `scripts/habits/query_active_habits_weekly.py`
**Execution mode**: code_change
**Independent test**: `pytest tests/habits/test_query_active_habits_weekly.py -v` green; running the helper against the golden-week fixture produces non-zero percentages for daily habits and matches expected per-habit rates byte-stably.

### Included subtasks

- [ ] T006 Remove `task.get("done_at")` reads and `_parse_done_at` calls from `query_active_habits_weekly.py`. (WP02)
- [ ] T007 Switch completion-history queries to `scripts.habits.history.completion_events_in_window` (and rate/count helpers as needed). Retain `VikunjaClient.get_tasks(...)` ONLY for current-state habit list + classification (titles + `repeat_after`). (WP02)
- [ ] T008 Add `--as-of <ISO 8601 datetime>` CLI flag. Default behavior unchanged (uses wall-clock now in ET). (WP02)
- [ ] T009 Implement `_render_whatsapp_text(payload)` in the helper and include the result as the top-level `rendered_text` field in the WeeklyHabitReport JSON. Template per `contracts/weekly_helper_cli.md`. (WP02)
- [ ] T010 Fix the date-range label to a true 7-day window: `(Mon Jun 8 – Sun Jun 14)` not `(Jun 7–14)`. Implement as a single `_format_window_label(window_start, window_end)` function. (WP02)
- [ ] T011 Update existing tests in `tests/habits/test_query_active_habits_weekly.py` and add golden-week tests covering: (a) byte-stable JSON output, (b) byte-stable `rendered_text`, (c) per-habit rates correct for daily and day-specific patterns, (d) Sunday-late-completion captured when as-of is Monday 06:00 ET. (WP02)

### Implementation sketch

1. Start by reading current `query_active_habits_weekly.py` end-to-end — the existing structure (argparse, `parse_weekday_in_title`, `classify_habit`, `scheduled_days_for_window`, `build_report`) is kept; only the data-fetch path changes.
2. Replace `query_completion_events` to call `scripts.habits.history` instead of iterating Vikunja `task.done_at`.
3. The helper's main flow: (i) fetch Vikunja habits for current-state info, (ii) for each habit, compute `scheduled_days_count` via existing `scheduled_days_for_window`, (iii) call `scripts.habits.history.scheduled_vs_completed_for_habit`, (iv) build per-habit row, (v) compose overall, (vi) call `_render_whatsapp_text`, (vii) emit JSON.
4. `_render_whatsapp_text` is a pure function of the JSON payload — same payload → byte-identical text.
5. Architectural test (WP03) will require this file to remain on the allowlist because of the current-state `VikunjaClient.get_tasks(...)` call. That's expected and correct.

### Parallel opportunities

None within WP02 — all subtasks touch the same file.

---

## WP03 — Architectural test ratchet

**Goal**: Add the architectural test that fails the build if any future `scripts/habits/*.py` script imports `VikunjaClient` for completion-history purposes.

**Priority**: P1 (ratchet — prevents this class of bug from recurring)
**Estimated prompt size**: ~300 lines
**Dependencies**: WP02 (the allowlist is correct only AFTER WP02 removes the bad path)
**Requirement refs**: FR-004, NFR-002, NFR-003, SC-003
**Owned files**: `tests/architectural/test_habits_history_canonical_read.py`
**Authoritative surface**: `tests/architectural/test_habits_history_canonical_read.py`
**Execution mode**: code_change
**Independent test**: `pytest tests/architectural/test_habits_history_canonical_read.py -v` green; negative-control case asserts the scanner fires; allowlist contains only currently-existing files.

### Included subtasks

- [ ] T012 Create `tests/architectural/test_habits_history_canonical_read.py` with a `pytest` collection-compatible top-level module. (WP03)
- [ ] T013 Implement the AST scanner: walk every `*.py` under `scripts/habits/`, parse with `ast.parse`, scan `Import` and `ImportFrom` nodes for `VikunjaClient` symbol references. Detect aliasing. (WP03)
- [ ] T014 Declare `VIKUNJA_CURRENT_STATE_ALLOWLIST: frozenset[str]` with the exact set of currently-existing habits files that legitimately need current-state Vikunja access. Include a one-line reason comment per entry. (WP03)
- [ ] T015 [P] Add `test_scanner_fires_on_unallowed_import` — uses a temp file or `tmp_path` fixture containing `from scripts.common.vikunja_client import VikunjaClient`; assert the scanner produces a violation with the temp file path and import line. (WP03)
- [ ] T016 [P] Add `test_allowlist_contains_no_stale_entries` — for each allowlist entry, assert `(scripts_habits_dir / entry).exists()`. Fails if a legacy habits script was removed but stayed on the allowlist. (WP03)

### Implementation sketch

1. Test uses `pathlib.Path(__file__).parents[2] / "scripts" / "habits"` to locate the habits directory (matches repo layout — verify with `repo_root` in the test).
2. AST scanner walks all `*.py` files (excluding `__pycache__/`, `__init__.py`).
3. For each file NOT in the allowlist, scan AST nodes; collect `(file_path, lineno, line_text)` for any `VikunjaClient` reference; fail the test with all violations enumerated.
4. Negative control uses an inline string with `ast.parse(source)` to assert the detection logic works without polluting `scripts/habits/`.
5. Performance target: <5s for ~10 habits files. AST parsing is sub-millisecond per file.

### Parallel opportunities

T015 / T016 are independent tests within the same file.

---

## WP04 — felix-admin-habits AGENTS.md simplification

**Goal**: Strip the in-prompt rendering logic and stale cron reference from `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`. The weekly section collapses to: invoke helper, post helper's `rendered_text` verbatim, preserve identity line, render contract-failure on non-zero exit.

**Priority**: P1 (Directive 6 follow-through; eliminates the LLM-as-renderer risk surface)
**Estimated prompt size**: ~250 lines
**Dependencies**: WP02 (helper must emit `rendered_text` before the prompt can rely on it)
**Requirement refs**: FR-005, FR-010, C-005
**Owned files**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
**Authoritative surface**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
**Execution mode**: code_change
**Independent test**: `grep -E '(0 6 \\* \\* 1|Monday 06:00)' scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns matches; `grep -E '(0 22 \\* \\* 0|Sunday 22:00)' ...` returns nothing; AGENTS.md effective character count under the openclaw budget (~14-15K).

### Included subtasks

- [x] T017 Strip in-prompt rendering rules from the "Weekly report (tick workflow)" section. Replace with: invoke helper, capture stdout, post `rendered_text` field verbatim to WhatsApp, preserve `Sent by felix-admin-habits:<model>` identity line. Keep the contract-failure render path. (WP04)
- [x] T018 Update every cron-schedule reference in AGENTS.md to `0 6 * * 1 America/New_York` (Monday 06:00 ET). Per `research.md` R-06, expect mentions near lines 76 and 119; verify by grep before editing. (WP04)
- [x] T019 Verify AGENTS.md effective character budget. Run `wc -c < scripts/openclaw/agents/felix-admin-habits/AGENTS.md`; raw char count after edits should be well under 20K (effective budget ~14-15K source after openclaw's ~26% inflation per memory). (WP04)

### Implementation sketch

1. Read existing AGENTS.md fully. Identify the weekly-tick section (header around line 117 per the planning grep).
2. The weekly section keeps: cron metadata bullet, Step 1 (invoke helper), failure render (contract-failure message + IDLE/skip semantics), output-discipline rules carried over to weekly.
3. The weekly section drops: any percentage-format template, trend-arrow logic, "renders the report from stdout JSON" — all of that lives in the helper now.
4. Touch only the weekly-tick paragraphs and the global cron references. Morning-tick paragraphs are out of scope (C-003).

### Parallel opportunities

None.

---

## WP05 — Cron reschedule via deploy manifest

**Goal**: Move openclaw cron from `0 22 * * 0` (Sunday 22:00 ET) to `0 6 * * 1` (Monday 06:00 ET) via a `deploys/queued/` manifest entry consumed by felix-deployer.

**Priority**: P1 (timing fix half of #605)
**Estimated prompt size**: ~200 lines
**Dependencies**: WP04 (coordinates with AGENTS.md cron text; same schedule string must agree across both surfaces)
**Requirement refs**: FR-001, C-006
**Owned files**: `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml`
**Authoritative surface**: `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml`
**Execution mode**: code_change
**Independent test**: `yamllint deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` clean; manifest content references the canonical openclaw cron primitive and the new schedule; deploy will be applied post-mission-merge by operator.

### Included subtasks

- [x] T020 Create `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` declaring an openclaw cron update from `0 22 * * 0` (`America/New_York`) to `0 6 * * 1` (`America/New_York`) for the felix-admin-habits weekly tick. Reference `docs/runbooks/deploy/discipline.md` for required manifest fields. (WP05)
- [x] T021 Verify the openclaw cron primitive in `scripts/deploy/lib/` supports the per-job TZ declaration we're using. Read the primitive source; align the manifest field names. If TZ isn't supported, the manifest schedule MUST be the UTC equivalent (`0 10 * * 1` for ET; check DST handling) and the WP prompt must declare this. (WP05)

### Implementation sketch

1. Read existing `deploys/queued/` manifests for shape templates — copy the closest existing openclaw-cron-update example.
2. The manifest's `target` is the felix-admin-habits openclaw cron entry; the operation is "update schedule"; the new value is `0 6 * * 1` with `tz: America/New_York` (or UTC equivalent per T021).
3. Include a brief `description` field explaining the change is the trustworthy-weekly-habit-report-01KV4GZ7 mission's timing fix.

### Parallel opportunities

None within WP05.

---

## WP06 — Architecture documentation update

**Goal**: Update the JSON architecture data files and any narrative counterparts so they accurately describe the canonical-read path post-merge.

**Priority**: P1 (Directive 5 standing requirement — docs land in same mission as code)
**Estimated prompt size**: ~250 lines
**Dependencies**: WP02 (description must be true after WP02 ships)
**Requirement refs**: FR-011, SC-006
**Owned files**: `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/data/data-flows.json`, `docs/design/architecture/data/signal-to-doc-map.json`, `docs/design/architecture/services.md`
**Authoritative surface**: `docs/design/architecture/data/service-inventory.json`
**Execution mode**: code_change
**Independent test**: All updated JSON files parse cleanly (`jq . <file> > /dev/null`); description of felix-admin-habits weekly tick references `habits-history.jsonl` and does NOT claim it reads Vikunja `done_at` for completion history.

### Included subtasks

- [x] T022 [P] Update `docs/design/architecture/data/service-inventory.json`: the felix-admin-habits agent's `purpose` field currently describes the weekly tick as "queries Vikunja directly via the new shared scripts/common/vikunja_client.py for `done_at` history". Rewrite that sentence to describe the canonical-read path through `habits-history.jsonl` via the new `scripts/habits/history.py` wrapper. (WP06)
- [x] T023 [P] Update `docs/design/architecture/data/data-flows.json`: locate any weekly-tick data flow entry (search for "weekly" or the prior mission slug `vikunja-client-and-habits-weekly-report-01KTKSFT`); update source-of-truth declarations to point at `habits-history.jsonl`. (WP06)
- [x] T024 [P] Update `docs/design/architecture/data/signal-to-doc-map.json` if there's an entry whose `doc_targets` include the affected docs (per CLAUDE.md the signal-to-doc-map is consulted during specify/plan; verify whether the mission's audit triggers require a new or updated entry). (WP06)
- [x] T025 [P] Update narrative architecture counterpart (e.g. `docs/design/architecture/services.md`) if it carries a description of the felix-admin-habits weekly tick. Grep first to confirm presence. (WP06)

### Implementation sketch

1. Run `grep -lE "(done_at|repeat_after|query_active_habits_weekly)" docs/design/architecture/` to discover all affected surfaces.
2. For each JSON file: read, edit the relevant string field, write back, verify with `jq . <file> > /dev/null`.
3. For the narrative counterpart: same edit applied to the matching prose paragraph.
4. The edits must preserve the existing per-mission cross-reference structure — only the description of the data source changes.

### Parallel opportunities

T022 / T023 / T024 / T025 each touch a different file; safe to do in parallel within one agent session.

---

## Sequencing summary

```
WP01 ──► WP02 ──┬──► WP03
                ├──► WP04 ──► WP05
                └──► WP06
```

WP01 is the foundation. WP02 is the bug fix. WP03/WP04/WP06 can run in parallel after WP02. WP05 follows WP04 (shared schedule-string concern).

## MVP scope recommendation

The Minimum Viable Pivot is **WP01 + WP02 + WP06** (wrapper + helper rewrite + architecture docs). That alone delivers the correctness fix and accurate docs. The timing fix (WP05) and the architectural-test ratchet (WP03) can land in a follow-up if necessary, though there's no reason to defer them — they're inexpensive.

The Recommended Full Scope is all 6 WPs.

## Definition of Done (mission-level)

- [ ] WP01–WP06 all green on `pytest`
- [ ] `pytest tests/architectural/test_habits_history_canonical_read.py` green
- [ ] Architecture data JSON files all parse with `jq`
- [ ] AGENTS.md char count under budget
- [ ] Deploy manifest committed to `deploys/queued/`
- [ ] Merge commit footer records `Rebaseline: completed at <ts>` (or `not required` with justification — but felix-admin-habits AGENTS.md is audited surface so it IS required)
- [ ] Issue #605 closed with merge commit hash + SC-001 spot-check summary
- [ ] First Monday tick produces accurate WhatsApp report (verified post-deploy)
