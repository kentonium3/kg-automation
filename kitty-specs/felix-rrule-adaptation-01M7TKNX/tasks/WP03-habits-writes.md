---
work_package_id: WP03
title: Habits writes keep the rule
dependencies:
- WP01
- WP02
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-014
- FR-020
- NFR-002
- SC-001
- SC-004
- SC-005
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: 45068ceab9b4d33f7f7250510db80595e2eeb58a
created_at: '2026-11-19T23:19:11.181222+00:00'
subtasks:
- T012
- T013
- T014
- T015
- T016
phase: Phase 1 - Destructive write paths
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/habits/
create_intent:
- tests/habits/test_habits_rule_roundtrip.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/habits/record_completion.py
- scripts/habits/sweeper.py
- scripts/habits/set_due_dates.py
- tests/habits/conftest.py
- tests/habits/test_record_completion.py
- tests/habits/test_sweeper_unit.py
- tests/habits/test_sweeper_idempotent.py
- tests/habits/test_set_due_dates.py
- tests/habits/test_set_due_dates_reconcile.py
- tests/habits/test_habits_rule_roundtrip.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – Habits writes keep the rule

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

Fix audit rows 1–4 (#1111):
- **Habit completion** (`record_completion.py:241-259`) and **sweeper auto-skip** (`sweeper.py:610-632`, used at L864-870) move onto WP02's `patch_task`.
- The sweeper takes a day-specific habit's next date from the **rule** (O1, FR-004).
- `set_due_dates`: the `--reconcile-schedule` mode is retired (redundant under O1), and the bulk `--iso-eod-et` mode moves to `patch_task`.

Done when:
- No habits file calls `replace_task_fields`.
- Completion records the outcome from `completion_outcome` (WP01).
- The sweeper still makes **no** Vikunja write for daily habits.
- A habit with no rule, or an occurrences 401 or timeout, becomes a `SweeperError` (tick status failure, which raises an alert through the existing `sweeper_tick` signal), never a guessed date.
- The round-trip tests in `tests/habits/test_habits_rule_roundtrip.py` fail against `cc4f2154` and pass after the change, with both results recorded with `add-history` (NFR-002).

## Context & Constraints

- Spec: FR-003, FR-004, FR-005, FR-014, FR-020, NFR-002. Plan IC-02. data-model.md Invariants 2, 3 and 6. research.md R-006 and R-010.
- WP02 client methods: `patch_task`, `get_task_v2`, `occurrences`, `preview_occurrences`. WP01 functions: `has_rule`, `same_rule`, `completion_outcome`, `exhaustion_expected`. WP01 factory: `tests/common/vikunja_v2_factory.py`.
- **Live facts:**
  - The 7 daily habits (14, 15, 16, 18, 19, 20, 65) carry `FREQ=DAILY;INTERVAL=1` and have no reminders.
  - Tasks 75–77 are Done with no rule and **stay that way** (C-008).
  - `felix-habit-sweeper.timer` is disabled until this ships (C-002).
- The sweeper imports `compute_next_eod_et_for_weekdays`, `validate_iso_eod_et` and `ISO_EOD_PATTERN` from `set_due_dates` (L107-123). Retiring the reconcile mode must not break that import, so keep those helpers if anything still uses them. After O1 the sweeper should not need the weekday maths; remove the import only once it has no use.
- `docs/runbooks/habits-ops.md:617-635` documents `--reconcile-schedule`. WP11 owns that doc. Do not edit it; leave a note in `add-history` so WP11 picks it up.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP03 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T012 – Habit completion via `patch_task`

- **Steps**:
  1. Replace step 2 (L226-264):
     - `before = client.get_task_v2(task_id)`;
     - `exhaustion = exhaustion_expected(before, preview=client.preview_occurrences)`;
     - `after = client.patch_task(task_id, {"done": True})`. If it returns `None` (304, already done), re-read.
     - `outcome = completion_outcome(before, after, exhaustion=exhaustion)`.
  2. Delete the narrow-body rationale comment (L227-240) and replace it with a short accurate one: v2 PATCH leaves omitted fields as stored, so there's no echo.
  3. Outcomes:
     - `advanced`: continue as today.
     - `series_ended`: continue, and put `series_ended` in the comment body and the state-log note, so the record says the series finished.
     - `unexpected`: still write the comment and state log, which are the facts, but raise `OSError("step 2: unexpected completion outcome ...")` **after** them, so the CLI exits non-zero and the habits agent reports it. Name the before and after `done`, `due_date` and `repeats_rrule` in the message.
  4. Construct the client exactly as today (`VikunjaClient(base_url=api_base_url, token=token)`), because `api_base_url` is the v1 base. WP02 derives v2.
- **Files**: `scripts/habits/record_completion.py`
- **Edge**: the `history.py` docstring mentions `repeat_after`, but that file belongs to WP07; don't touch it.

### Subtask T013 – Rule-driven sweeper auto-skip

- **Steps**:
  1. Replace `_vikunja_put_due_date` with `_advance_to_next_occurrence(*, client, task_id) -> str`, which:
     - (a) calls `get_task_v2`;
     - (b) if `not has_rule(task)`, raises `NoRuleError` (a local class);
     - (c) calls `occurrences(task_id, count=1)`; if the list is empty, raises `NoNextOccurrence(reason)`;
     - (d) converts `occurrences[0]` to an explicit-offset ET ISO string. Reuse `scripts/common/et_datetime.py`, then keep the `validate_iso_eod_et` and `ISO_EOD_PATTERN` guards, adapted if occurrences carry the rule's time rather than 23:59:59. **Check this against a real response shape**: the anchor is the due date's wall-clock time, so EOD stays EOD;
     - (e) calls `patch_task(task_id, {"due_date": iso})`;
     - (f) reads back and asserts `same_rule(before, after)`, raising `RuleChanged` otherwise.
  2. In `run_sweep`:
     - The day-specific branch calls it.
     - Map `NoRuleError` to error_type `no_rule`, `NoNextOccurrence` to `no_next_occurrence`, `VikunjaAuthError` to `occurrences_unauthorized` (the message names the permission), and other `VikunjaError` to `vikunja_put`. Each is a `SweeperError`, followed by `continue`.
     - Do **not** append the history event on failure. That matches today's retry semantics.
  3. Build **one** `VikunjaClient` per tick, lazily, instead of a token read per call. Keep `_ensure_token` semantics if tests depend on them.
  4. Daily habits: unchanged, with no Vikunja call. Add an assertion test.
  5. Update the module docstring: L11-14 still says "native repeat_after cadence".
- **Files**: `scripts/habits/sweeper.py`

### Subtask T014 – `set_due_dates`

- **Steps**:
  1. Remove `--reconcile-schedule` and the code that only it uses (L296-442 per the audit). It's redundant: the sweeper (T013) moves day-specific habits by rule, and no timer or cron runs reconcile (`git grep` shows runbook use only).
  2. Bulk `--iso-eod-et` mode (L707-719): replace `replace_task_fields(task_id, {"due_date": ...})` with `patch_task(task_id, {"due_date": ...})`, then read back and check `same_rule`.
  3. Keep `compute_next_eod_et_for_weekdays`, `validate_iso_eod_et` and `ISO_EOD_PATTERN` **only if** something still imports them after T013. Grep. If none remains, delete them and their tests, to satisfy the no-dead-code rule.
  4. Delete or convert `tests/habits/test_set_due_dates_reconcile.py`. If reconcile is gone, delete the file.
- **Files**: `scripts/habits/set_due_dates.py`, `tests/habits/test_set_due_dates.py`, `tests/habits/test_set_due_dates_reconcile.py`

### Subtask T015 – Test conversion

- `tests/habits/conftest.py`:
  - Make `sample_habit_task_response` produce the new shape, delegating to `tests/common/vikunja_v2_factory.make_task`.
  - Remove `migrate_schedule` from the base-URL patch loop at L191; the module is retired in WP08, and the ImportError is caught anyway.
- Convert `test_record_completion.py` (25 old-shape hits), `test_sweeper_unit.py` (8) and `test_sweeper_idempotent.py` (2) to the new shape. Assertions that a narrow body was sent must be **inverted**: the PATCH body is exactly `{"done": true}` or `{"due_date": ...}`.
- Keep test intent. Do not delete a test just because it encoded the old shape; convert it.

### Subtask T016 – Round-trip regression tests (red-then-green)

- New file `tests/habits/test_habits_rule_roundtrip.py`. Drive the real entry points (`record_completion` main or function, `run_sweep`, the `set_due_dates` bulk mode) through `mock_vikunja_urlopen`, with a factory task that has a rule, `repeats_from_current_date=True` and one reminder.
- **Cases**:
  - **Completion, advanced.** The fake server returns done=false, due date +1 day, same rule. Assert the PATCH body is exactly `{"done": true}`, with no null, and that the outcome is advanced.
  - **Completion, COUNT 2→1.** Advanced.
  - **Completion, COUNT 1.** The server returns done=true with no rule. The outcome is series_ended.
  - **Completion, unexpected.** The server returns done=true, the rule had no COUNT or UNTIL, and exhaustion is unknown. Assert a non-zero exit and `unexpected` in the message.
  - **Positive control.** The fake server returns `strip_rule(task)` after a due-date PATCH from the sweeper or bulk mode. Assert the site raises or reports `RuleChanged`. This test must fail on a do-nothing change.
  - **Sweeper.** A day-specific habit with a weekly BYDAY rule gets a due date equal to the converted `occurrences[0]`. A daily habit gets no HTTP call at all. A no-rule habit gives `no_rule` and no write. An occurrences 401 gives `occurrences_unauthorized` and no write.
- **Red-then-green evidence.** On a scratch checkout of `cc4f2154`, run the new file. Port only the test, and expect the failures; record the failing test names with `spec-kitty agent tasks add-history WP03 --note "red on cc4f2154: ..."`. Then show green on the WP branch.

```bash
python3 -m pytest -q tests/habits
```

```bash
make test
```

## Risks & Mitigations

- **Occurrence time-of-day.** The anchor is the due date's wall-clock time, so an EOD due date stays EOD. Verify with the fork source (`d7e202228:pkg/models/task_next_occurrence_engine.go:424-441`), not by assumption.
- **Overdue tasks.** Occurrences skip missed dates and start after now (research). That is the right auto-skip target.
- **Hidden importers** of the retired reconcile helpers. Grep the whole repo, including `scripts/openclaw/**`.

## Review Guidance

- Prove there's no daily-habit write (a test with zero HTTP calls).
- Prove there's no guessed date on no-rule or 401 (a test).
- Check the red-then-green evidence in history.
- Confirm `replace_task_fields` is absent from `scripts/habits/`.

## Progress & Status

Use `spec-kitty agent tasks add-history WP03 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
