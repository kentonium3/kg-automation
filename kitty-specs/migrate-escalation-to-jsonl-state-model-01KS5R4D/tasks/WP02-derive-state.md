---
work_package_id: WP02
title: derive_state pure function
dependencies:
- WP01
requirement_refs:
- FR-001
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-21T17:45:30+00:00'
subtasks:
- T006
- T007
- T008
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/escalation/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- scripts/escalation/derive_state.py
- tests/escalation/test_derive_state.py
tags: []
---

# WP02 — derive_state pure function

## Objective

Implement the pure function that converts a list of JSONL records for ONE task into the current escalation state. All escalation policy semantics (snooze expiry, next-level eligibility, terminal state detection) live here. This is the single source of truth that downstream consumers (record_completion, reconcile, the OpenClaw agent skill) call to answer "what state is this task in?"

## Context

- **Mission spec**: FR-001 (JSONL is sole state source), FR-008 (Q10 hard-fail surface for inconsistent records)
- **Research**: D7 (derive_state shape rationale)
- **API contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md` — `derive_state` signature, `EscalationState` dataclass, `EscalationStateError`
- **CLI contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md` — debug CLI flags + exit codes
- **Dependency**: WP01 (uses `scripts.escalation.schema.EVENT_TYPE_PARAMETERS` indirectly via existing JSONL records that conform to it; uses the WP01 conftest fixtures)
- **Existing escalation policy reference**: `scripts/openclaw/skills/escalation/SKILL.md` § "Level determination algorithm" — the policy this function encodes. WP02 reproduces that policy from the JSONL angle.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T006 — Implement `scripts/escalation/derive_state.py`

**Purpose**: Pure function + dataclasses. No I/O. No HTTP. All escalation policy semantics encoded here.

**Steps**:

1. Module docstring describing the function's role and the policy walk order.
2. Imports: stdlib only — `dataclasses`, `datetime`, `typing` (Literal, Optional), `zoneinfo` (for America/New_York TZ).
3. Module constants:
   ```python
   LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")
   LEVEL_1_OVERDUE_DAYS = 1
   LEVEL_2_OVERDUE_DAYS = 3
   LEVEL_1_TO_2_STALENESS_DAYS = 2
   ```
4. Define `class EscalationStateError(Exception)` with attributes `task_id`, `records`, `reason`. Reason taxonomy: `"missing_required_param"`, `"unknown_state"`, `"impossible_ordering"`.
5. Define `EscalationState` frozen dataclass per contracts/api.md.
6. Helper `_today_local() -> date` returning today's date in America/New_York TZ. Wrap `datetime.now(LOCAL_TZ).date()` so tests can monkeypatch.
7. Implement `derive_state(records: list[dict]) -> EscalationState`:
   - **Empty input guard**: return `EscalationState(current_state="new", last_event=None, ...)` with all-None fields.
   - **Sort**: copy input, sort newest-first by `record["timestamp"]` (parsed). Raise `EscalationStateError(reason="impossible_ordering")` if any timestamp fails to parse.
   - **Per-record validation**: for each record, call into `scripts.escalation.schema.validate_event_params`. Catch `EscalationSchemaError` and rewrap as `EscalationStateError(reason="missing_required_param", records=[r])`.
   - **Walk** (in order — return early on first match):
     - If most recent is `state="done"`: return `current_state="done"`, `next_eligible_level=None`.
     - If most recent is `state="dismissed"`: return `current_state="dismissed"`, `next_eligible_level=None`.
     - If most recent is `state="snoozed"`:
       - Parse `snooze_until` as `date.fromisoformat`.
       - If `_today_local() <= snooze_until`: `current_state="snoozed"`, `snooze_active_until=snooze_until`, `next_eligible_level=None`.
       - Else: `current_state="snoozed_expired"`, `snooze_active_until=snooze_until`, `next_eligible_level=1` (re-enter at Level 1 per existing SKILL.md rule 4).
     - If most recent is `state="rescheduled"`:
       - `current_state="rescheduled"`, `next_eligible_level=None`. (Caller decides if the new due_date is now overdue; that's a Vikunja-state check, not JSONL-state.)
     - If most recent is `state="level_sent"`:
       - Look at `level` parameter. If `1`:
         - Compute days_since: `(_today_local() - record_date).days` where `record_date = date.fromisoformat(record["date"])`.
         - If `days_since >= LEVEL_1_TO_2_STALENESS_DAYS`: `current_state="level_1_sent"`, `next_eligible_level=2`.
         - Else: `current_state="level_1_sent"`, `next_eligible_level=None` (already alerted, not yet stale).
       - If `2`:
         - `current_state="level_2_sent"`, `next_eligible_level=2` (repeat insistence is allowed by daily dedup at the caller).
       - If any other `level` value: `EscalationStateError(reason="missing_required_param")`.
   - Always populate `last_event` (the newest record) and `last_event_recorded_at` (parsed timestamp).
8. Total module length target: ~250-280 lines including docstring + comments.

**Files**:
- `scripts/escalation/derive_state.py` (new, ~280 lines)

**Validation**:
- [ ] No third-party imports.
- [ ] `python3 -c "from scripts.escalation.derive_state import derive_state, EscalationState, EscalationStateError; print('ok')"` prints `ok`.
- [ ] Policy walk order verified against SKILL.md § "Level determination algorithm".

---

### T007 — Debug CLI for `derive_state.py`

**Purpose**: Operator-facing CLI for inspecting any task's derived state per contracts/cli.md.

**Steps**:

1. Add `def main(argv=None) -> int` to `derive_state.py`.
2. argparse:
   - `--task-id` (int, required)
   - `--project-id` (int, required)
   - `--jsonl-dir` (path, default `/data/services/openclaw/state/escalation`)
   - `--project-slug` (str, optional — overrides default slug-from-project_id lookup)
3. JSONL lookup logic (helper `_load_records_for_task`):
   - Open `<jsonl-dir>/<project-slug>-escalation-history.jsonl` (or each `*-escalation-history.jsonl` file if no slug override, filtering by `record["task_id"] == args.task_id and record["project_id"] == args.project_id`).
   - Read line-by-line, JSON-parse each, collect matching records.
   - On FileNotFoundError: print error to stderr, exit 2.
4. Call `derive_state(records)`. Catch `EscalationStateError`:
   - Print structured error JSON to stderr.
   - Exit 3.
5. Empty-records case: print `{"task_id": ..., "current_state": "new", "records_found": 0}` and exit 4.
6. Happy path: serialize the `EscalationState` dataclass as JSON (use `dataclasses.asdict` + custom encoder for date/datetime), print to stdout, exit 0.
7. `if __name__ == "__main__": sys.exit(main())`.

**Files**:
- `scripts/escalation/derive_state.py` (extended with CLI, +~80 lines)

**Validation**:
- [ ] `python3 -m scripts.escalation.derive_state --help` prints help, exits 0.
- [ ] CLI exits 4 for unknown task.
- [ ] CLI exits 3 with structured error JSON on `EscalationStateError`.

---

### T008 — Tests for `derive_state`

**Purpose**: Exhaustive coverage of every policy walk path + every error surface.

**Steps**:

1. Create `tests/escalation/test_derive_state.py`.
2. Test cases (use `make_jsonl_record` fixture):
   - **Empty input**:
     - `test_empty_records_returns_new` — `derive_state([])` returns `current_state="new"`.
   - **Terminal states**:
     - `test_done_terminal` — single `state="done"` record → `current_state="done"`, `next_eligible_level=None`.
     - `test_dismissed_terminal` — single `state="dismissed"` → terminal.
     - `test_done_overrides_earlier_level_sent` — `level_sent` then `done` → `done`.
   - **Snooze states**:
     - `test_snoozed_active_future` — `snoozed` with `snooze_until` in future (monkeypatch `_today_local`) → `current_state="snoozed"`, `next_eligible_level=None`.
     - `test_snoozed_active_today_boundary` — `snooze_until == today` → still `snoozed` (`<=` boundary).
     - `test_snoozed_expired` — `snooze_until` in past → `current_state="snoozed_expired"`, `next_eligible_level=1`.
   - **Rescheduled**:
     - `test_rescheduled` — single `state="rescheduled"` → `current_state="rescheduled"`, `next_eligible_level=None`.
   - **level_sent walks**:
     - `test_level_1_fresh` — `level=1`, recorded today → `current_state="level_1_sent"`, `next_eligible_level=None`.
     - `test_level_1_stale_2_days` — `level=1`, recorded 2 days ago → `next_eligible_level=2`.
     - `test_level_1_stale_5_days` — `level=1`, recorded 5 days ago → `next_eligible_level=2`.
     - `test_level_2_sent` — `level=2`, recorded today → `current_state="level_2_sent"`, `next_eligible_level=2`.
     - `test_level_2_stale_3_days` — `level=2`, recorded 3 days ago → still `level_2_sent`, `next_eligible_level=2`.
   - **Ordering**:
     - `test_newest_record_wins` — `level_1_sent` 3 days ago, then `done` 1 day ago → `current_state="done"`.
     - `test_snoozed_after_level_1` — `level_1_sent` then `snoozed:3d` → `current_state="snoozed"`.
   - **Error surface (EscalationStateError)**:
     - `test_level_sent_missing_level_raises` — record with `state="level_sent"` but no `level` param → raises with `reason="missing_required_param"`.
     - `test_unknown_state_raises` — record with `state="acknowledged"` (not in vocabulary) → raises.
     - `test_unparseable_timestamp_raises` — record with `timestamp="not a real ts"` → raises with `reason="impossible_ordering"`.
   - **Last event always populated**:
     - `test_last_event_recorded_at` — any non-empty input → `last_event_recorded_at` is the newest record's timestamp parsed as datetime.
3. Use `freezegun` if available; otherwise monkeypatch `_today_local`. The conftest may add a `freeze_today` fixture for this purpose.
4. Coverage target: ≥85% line + branch.

**Files**:
- `tests/escalation/test_derive_state.py` (new, ~280 lines, ~18 test cases)

**Validation**:
- [ ] `pytest tests/escalation/test_derive_state.py -v` all green.
- [ ] `pytest tests/escalation/test_derive_state.py --cov=scripts.escalation.derive_state --cov-report=term-missing` ≥85% line + branch.
- [ ] At least one test per `EscalationStateError` reason taxonomy value.

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

pytest-based unit tests. Pure function = trivially mockable. Time-dependent paths use a monkeypatched `_today_local` helper. No HTTP or filesystem mocking needed.

## Definition of Done

- [ ] T006-T008 subtasks complete with all validations green.
- [ ] `pytest tests/escalation/test_derive_state.py -v` passes.
- [ ] Coverage ≥85% line + branch on `scripts.escalation.derive_state`.
- [ ] Every entry in the `EscalationState.current_state` Literal has at least one test that reaches it.
- [ ] Every `EscalationStateError.reason` value has at least one test.

## Risks

- **Policy walk ordering**: terminal → snoozed-active → rescheduled → most-recent-level. If this ordering is wrong, the JSONL state is wrong. Tests must verify every ordering edge (e.g., `done` after `level_sent` means terminal, not "fresh level_sent").
- **TZ handling**: snooze expiry uses local TZ. Tests must monkeypatch `_today_local`, not real `date.today()`.
- **Coverage gap risk**: easy to leave `EscalationStateError("impossible_ordering")` paths untested. Reviewer must verify each path.

## Reviewer Guidance

1. Read `derive_state.py` end-to-end. Confirm the policy walk matches SKILL.md § "Level determination algorithm" (specifically rules 1-7).
2. Verify every `current_state` literal value is reachable from test fixtures.
3. Verify the `EscalationStateError` reason taxonomy matches contracts/api.md.
4. Coverage report must show ≥85% line + branch.

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```
