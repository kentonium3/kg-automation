---
work_package_id: WP07
title: Habits reads, schedule and weekly report
dependencies:
- WP01
- WP02
requirement_refs:
- FR-012
- FR-013
- FR-017
- C-005
- C-008
- SC-002
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: 8a51e22ba6125eb52173a2bcbf475a9cae0bd136
created_at: '2026-11-19T23:19:50.149538+00:00'
subtasks:
- T030
- T031
- T032
- T033
- T034
- T035
phase: Phase 2 - Detection and reporting
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/habits/schedule_loader.py
create_intent:
- tests/habits/test_schedule_check_live.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/habits/schedule_loader.py
- scripts/habits/migrations/phase3-schedule.yaml
- scripts/sync/cleanup.py
- scripts/habits/query_active_habits_weekly.py
- scripts/habits/weekly_report_driver.py
- scripts/habits/query_active_habits_v2.py
- scripts/habits/identify_workout_task.py
- scripts/habits/history.py
- tests/habits/test_schedule_loader.py
- tests/habits/test_query_active_habits_weekly.py
- tests/habits/fixtures/weekly_report_responses.json
- tests/habits/fixtures/schedule_with_day_specific.yaml
- tests/habits/test_weekly_report_driver.py
- tests/habits/test_query_active_habits_v2.py
- tests/habits/test_query_active_habits_v2_day_of_week.py
- tests/habits/test_query_active_habits_v2_filter.py
- tests/habits/test_identify_workout_task.py
- tests/habits/test_morning_checkin_list.py
- tests/habits/test_morning_checkin_list_day_of_week.py
- tests/habits/test_exclude_completed_v2.py
- tests/habits/test_reconcile_completions.py
- tests/sync/test_cleanup.py
- tests/habits/test_schedule_check_live.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP07 – Habits reads, schedule and weekly report

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`, and address every item before going back to review.

---

## Objectives & Success Criteria

Fix audit rows 17–21 (#1111) and adopt O2 and O4:

1. **Schedule.** The habits block declares `rrule` per habit (RFC 5545 text) instead of `repeat_after_seconds`, and the #608 ratchet is re-expressed on the rule. The frozen `operations:` block is untouched (C-005).
2. **Drift check (O2, FR-013).** `python3 -m scripts.habits.schedule_loader --check-live` reads each **active** habit's live rule via `get_task_v2` and prints `match | missing | differs | inactive | unreadable` per habit. Its last line is a JSON summary. It never writes.
3. **Weekly report (O4, FR-012).** It classifies habits from the rule, not `repeat_after`, and counts scheduled days from the rule. On the converted fixture it lists every active habit.
4. **Reporters (FR-017).** `query_active_habits_v2` and `identify_workout_task` emit `repeat` instead of the dead fields.

## Context & Constraints

- Spec: FR-012, FR-013, FR-017, C-005, C-008. Plan IC-05. data-model.md, habit schedule entry. research.md R-012 (the weekly report ignores the YAML today).
- **Tasks 75–77 stay Done with no rule** (C-008).
  - Keep their schedule entries. The sweeper and check-in code read them, and removing them is out of scope.
  - Give them `rrule: "FREQ=WEEKLY;BYDAY=MO"` (`WE`, `FR`) as the *declared* rule.
  - The drift check reports them `inactive`, because the live task is done, and does not count them as drift.
  - The quickstart canary expects 7 `match` and 3 `inactive`.
- **Who reads the schedule.** `schedule_loader.load_schedule` is used by the sweeper (WP03), `set_due_dates` (WP03), `morning_checkin_list`, and `query_active_habits_v2` (L172, 289).
  - No production code reads `entry.repeat_after_seconds` (research.md R-012). Replacing it with `rrule` is safe for consumers, but check each one: grep `ScheduleEntry(` and `.repeat_after_seconds`.
- **`scripts/sync/cleanup.py:prune_schedule_yaml`** (docstring L85-110) rewrites `phase3-schedule.yaml`. It must preserve the new `rrule` key and the frozen `operations` block byte for byte.
- **Weekly report data source.** `query_completion_events` pages `GET /projects/{habits_pid}/tasks` (L318-322). List bodies carry `repeat` but not `repeats_rrule`, so classify on `repeat` parts.
- **Preview has a token dependency (R-004).** Simple rules are computed locally: `FREQ=DAILY;INTERVAL=1`, and `FREQ=WEEKLY;INTERVAL=1;BYDAY=...` with no COUNT, UNTIL or other `by_*`. Only other rules use `preview_occurrences`. If preview returns 401 or a timeout, report that habit's scheduled days as `null` with a note. Never guess.
- `history.py:12-13` has a docstring that mentions `repeat_after`. Fix it here.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP07 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T030 – Schedule `rrule`, ratchet, YAML

- **Steps**:
  1. `ScheduleEntry` (L63-79): replace `repeat_after_seconds: int = 0` with `rrule: str`, which is required.
  2. `_validate_entry` (L134-193):
     - parse `rrule` with `vikunja_rule.rrule_text_to_parts`, and on failure raise the loader's existing error type naming the entry index;
     - **ratchet** (replacing L172-182, #608): a day-specific entry (`designated_weekdays` set) must have `freq` `weekly` or coarser, and `by_day` equal to its designated weekdays (case-insensitive, using the loader's normalised weekday tokens);
     - a daily entry must have `freq: daily` and `interval: 1`;
     - reject a leftover `repeat_after_seconds` key with a clear migration message.
  3. YAML habits block (L158-195):
     - `repeat_after_seconds: 86400` → `rrule: "FREQ=DAILY;INTERVAL=1"`;
     - 75/76/77 → `rrule: "FREQ=WEEKLY;BYDAY=MO"`, `WE` and `FR`.
     - Update the header comments that reference `migrate_schedule` and `--reconcile-schedule` (L3, L21-30, L104, L135, L156). Keep the **`operations:` block byte-identical**.
  4. Update the module docstring (L8-14): reconcile is retired and migrate_schedule is retired.
- **Files**: `scripts/habits/schedule_loader.py`, `scripts/habits/migrations/phase3-schedule.yaml`, `tests/habits/fixtures/schedule_with_day_specific.yaml`

### Subtask T031 – `--check-live` drift check

- **Steps**:
  1. Add a `main()` to `schedule_loader.py`, invoked as `python3 -m scripts.habits.schedule_loader --check-live [--schedule-path P]`.
  2. For each entry:
     - `get_task_v2(task_id)`;
     - status is `inactive` if `done` is true; `missing` if it has no rule; `differs` if `not same_rule(rrule_text_to_parts(entry.rrule), task["repeat"])`; otherwise `match`. Any `VikunjaError` gives `unreadable`, with the error class only and no token.
  3. Print one line per habit, then a JSON summary: `{"ok": <no missing/differs/unreadable>, "match": n, "inactive": n, "missing": n, "differs": n, "unreadable": n}`. Exit 0 when ok, 1 otherwise.
  4. **No write calls.** A test asserts only GETs were made.

### Subtask T032 – `cleanup.py` compatibility

- Update `prune_schedule_yaml` and its docstring (L85-110; the `repeat_after` mention at L101) so it carries `rrule` through.
- Prove with a test that a prune round-trip leaves `operations:` byte-identical and keeps `rrule` values.

### Subtask T033 – Weekly report from the rule

- **Steps**:
  1. `classify_habit(task)`:
     - normalise `task["repeat"]`;
     - `freq == "daily"` with interval 1 → `"daily"`;
     - `freq == "weekly"` with `by_day` → `"weekly-by-day"`;
     - any other rule → `"rule"`, which goes through preview;
     - no rule → `"other"`, filtered as today.

     The title weekday parsing (`parse_weekday_in_title`) is **no longer the classifier**. Keep it only if something else uses it; otherwise delete it with its tests (no dead code).
  2. `scheduled_days_for_window(kind, task, window_start, window_end, *, preview=None) -> int | None`:
     - `daily`: day count, as today.
     - `weekly-by-day`: count the window days whose weekday is in `by_day`. Interval must be 1 for this local path; otherwise use preview.
     - `rule`: `preview(repeat=..., due_date=window_start_iso, count=100)`. Count the occurrences in `[start, end)`. 401 or a timeout gives `None`.
  3. The report renderer shows `None` as "scheduled: unknown (rule preview unavailable)" and never as 0.
  4. `weekly_report_driver.py`: pass `client.preview_occurrences` through.

### Subtask T034 – Reporters emit the rule

- `query_active_habits_v2.py:274-283`: replace the pass-through of `repeat_after`/`repeat_mode` with `repeat`. Confirm no consumer reads the old keys; `morning_checkin_list` does not, per the audit.
- `identify_workout_task.py:24, 137, 172`: emit `repeat` (and `repeats_rrule` when present) instead of `repeat_after`.

### Subtask T035 – Tests and fixture conversion

- `tests/habits/fixtures/weekly_report_responses.json`:
  - convert all 22 old-shape hits to the new shape (`repeat` dicts, no `repeats_rrule` since these are list bodies);
  - include the 7 daily habits plus 75–77 as done with no rule.
- `test_query_active_habits_weekly.py` assertions:
  - the 7 daily habits are classified `daily` with 7 scheduled days;
  - 75–77 are excluded;
  - a synthetic `FREQ=WEEKLY;BYDAY=MO,WE` habit gets 2 days per standard week;
  - a `rule` habit uses the fake preview;
  - preview 401 gives `None` and the "unknown" text.
- **Positive control**: the old code path classifies everything as `other`. Run the new test against `cc4f2154` and record the red result with `add-history`.
- `test_schedule_loader.py` (28 hits):
  - convert;
  - add ratchet tests (BYDAY mismatch rejected; daily with interval 2 rejected; a leftover `repeat_after_seconds` rejected).
- New `tests/habits/test_schedule_check_live.py`:
  - match, differs, missing, inactive and unreadable;
  - only GETs are made;
  - exit codes.
- Convert the remaining habits read-side tests listed in `owned_files`, wherever they encode `repeat_after`/`repeat_mode` (grep counts: morning_checkin 4+7, query_v2 9+8+2, exclude_completed_v2 1, reconcile_completions 4, identify_workout 3, cleanup 11).

```bash
python3 -m pytest -q tests/habits tests/sync/test_cleanup.py
```

```bash
make test
```

## Risks & Mitigations

- **Breaking schedule consumers** in WP03's files (sweeper, set_due_dates). They only read `task_id`, `designated_weekdays`, `is_day_specific` and `is_active_today`. If WP03 lands first, re-run its tests after rebasing.
- **`prune_schedule_yaml` re-serialisation** changing `operations:` formatting. Test byte-identity.

## Review Guidance

- Is the `operations:` block byte-identical? Check with `git diff` on the YAML.
- Is the drift check strictly read-only, with a test?
- Does the weekly report never show a guessed 0 for an unknown rule?

## Progress & Status

Use `spec-kitty agent tasks add-history WP07 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
