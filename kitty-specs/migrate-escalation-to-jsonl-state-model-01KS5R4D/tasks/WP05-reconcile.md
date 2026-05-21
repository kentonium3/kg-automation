---
work_package_id: WP05
title: reconcile_completions sweep
dependencies:
- WP03
- WP04
requirement_refs:
- FR-005
- FR-008
- NFR-001
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-21T17:45:30+00:00'
subtasks:
- T015
- T016
- T017
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "9013"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/escalation/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- scripts/escalation/reconcile_completions.py
- tests/escalation/test_reconcile_completions.py
tags: []
---

# WP05 — reconcile_completions sweep

## Objective

Implement the reconciliation sweep that detects Vikunja state drift vs JSONL state and emits synthetic records. Detects Kent UI-marking-done within one tick; detects due-date edits as synthetic `rescheduled` events; routes truly inconsistent state through WP04's Q10 hard-fail. Closes the vulnerability class that triggered the 2026-05-16 habits incident — escalation now reconciles Vikunja → JSONL on every tick.

## Context

- **Mission spec**: FR-005 (reconcile UI-marking-done within one tick), FR-008 (hard-fail integration), SC-002 (UI-mark-done detected), NFR-001 (60-second budget for 50 tasks)
- **Research**: D3 (rescheduled detection semantics), D8 (Q10 trigger conditions)
- **API contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md` — `reconcile_project`, `ReconcileReport`, `HardFailEvent`
- **CLI contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md` — flags + exit codes
- **Dependencies**:
  - **WP03**: uses `record_event` (with `--no-vikunja` / `source="reconcile"`) to emit synthetic records.
  - **WP04**: uses `file_hard_fail_bug` to route inconsistent state.
- **Habits Phase 3 precedent**: `scripts/habits/reconcile_completions.py` — same sweep pattern, different policy.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T015 — Implement `scripts/escalation/reconcile_completions.py`

**Purpose**: Library-level reconciliation per research D3.

**Steps**:

1. Module docstring describing the sweep + drift cases.
2. Imports: stdlib only plus `scripts.escalation.derive_state`, `scripts.escalation.record_completion`, `scripts.escalation.hard_fail`, `scripts.escalation.schema`.
3. Define `ReconcileReport` and `HardFailEvent` frozen dataclasses per contracts/api.md.
4. Module constants:
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
   DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
   JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")
   HTTP_TIMEOUT_SECONDS = 30
   ```
5. Helper `_fetch_vikunja_task(task_id: int, *, base_url, token) -> dict` — GET /tasks/{id}. Returns task dict (`done`, `due_date`, etc.).
6. Helper `_load_records_for_task(task_id: int, project_id: int, jsonl_dir: Path) -> list[dict]` — open `project-{id}-escalation-history.jsonl`, filter by task_id. Raise `EscalationSchemaError` for malformed lines.
7. Helper `_enumerate_subscribed_tasks(project_id: int, jsonl_dir: Path) -> list[tuple[int, list[dict]]]`:
   - Open the project's JSONL file.
   - Group records by `task_id`.
   - For each task, if there's at least one `level_sent` record AND no terminal record (`done`/`dismissed`) more recent than the most recent `level_sent` → "subscribed".
   - Return list of `(task_id, records_for_task)` tuples.
8. Implement `reconcile_project(project_id: int, *, base_url=..., token_path=..., jsonl_dir=..., dry_run=False, max_tasks=None) -> ReconcileReport`:
   - Read token.
   - Enumerate subscribed tasks.
   - Apply `--max-tasks` cap if set.
   - For each task:
     - Fetch Vikunja state.
     - Call `derive_state(records)`. Catch `EscalationStateError`:
       - File hard-fail via `hard_fail.file_hard_fail_bug` with reason `"derive_state_inconsistency"`.
       - Append `HardFailEvent` to report.
       - Continue.
     - **Done-drift detection** (research D3):
       - If `vikunja.done == True` AND no `done` record in records:
         - Emit synthetic via `record_completion.record_event` with `state="done"`, `source="reconcile"`, `--no-vikunja` semantics (do not re-PATCH; the Vikunja state already reflects done).
         - Increment `synthetic_done_emitted`.
     - **Rescheduled-drift detection** (research D3):
       - Compute `last_known_due_date`: the most recent `reschedule_to` from records, OR (if none) the original due_date inferred from when the task became escalation-subscribed (this requires comparing against the first `level_sent` record's snapshot — for simplicity, use a "best-effort" rule: if Vikunja due_date != last `reschedule_to` AND no terminal record → emit synthetic `rescheduled`).
       - Emit synthetic via `record_event` with `state="rescheduled"`, `source="reconcile"`, `reschedule_to=<vikunja due_date>`.
       - Increment `synthetic_rescheduled_emitted`.
     - **Phantom subscription detection (Q10)**:
       - If a Vikunja task has prior `[Felix-Escalation]` comments (count > 0) BUT records is empty → file hard-fail with reason `"phantom_subscription"`.
   - If `dry_run=True`: skip the actual `record_event` calls but report counts as if they would have been emitted.
   - Return populated `ReconcileReport`.
9. Implement `reconcile_all(*, base_url=..., token_path=..., jsonl_dir=..., dry_run=False) -> list[ReconcileReport]`:
   - Discover projects by globbing `<jsonl_dir>/project-*-escalation-history.jsonl`.
   - For each, extract `project_id` from filename and call `reconcile_project`.

**Files**:
- `scripts/escalation/reconcile_completions.py` (new, ~340 lines)

**Validation**:
- [ ] No third-party imports.
- [ ] `python3 -c "from scripts.escalation.reconcile_completions import reconcile_project, ReconcileReport, HardFailEvent; print('ok')"` prints `ok`.

---

### T016 — CLI surface

**Purpose**: Per contracts/cli.md.

**Steps**:

1. `def main(argv=None) -> int` with argparse:
   - Required: one of `--project-id <int>` or `--all`.
   - Optional: `--dry-run`, `--max-tasks <int>`, `--quiet`, `--base-url`, `--token-path`, `--jsonl-dir`.
2. Dispatch:
   - `--project-id`: call `reconcile_project(...)`.
   - `--all`: call `reconcile_all(...)`.
3. Stdout per contracts/cli.md:
   - One line per drift detection (unless `--quiet`): `DRIFT task=<id> project=<id> reason=<...> emitted_synthetic=<state>`.
   - One line per hard-fail: `HARDFAIL task=<id> project=<id> reason=<...> bug_url=<url-or-DEDUPED>`.
   - Final JSON summary line.
4. Exit codes per contracts/cli.md:
   - 0: completed (drift may have happened).
   - 1: Vikunja or JSONL fatal error (one project couldn't be reconciled).
   - 3: validation/usage error.
5. `if __name__ == "__main__": sys.exit(main())`.

**Files**:
- `scripts/escalation/reconcile_completions.py` (extended with CLI, +~100 lines)

**Validation**:
- [ ] `python3 -m scripts.escalation.reconcile_completions --help` prints help.
- [ ] CLI with no required flag exits 3.

---

### T017 — Tests for `reconcile_completions`

**Purpose**: Cover the three detection paths + hard-fail integration + multi-project sweep.

**Steps**:

1. Create `tests/escalation/test_reconcile_completions.py`.
2. Use conftest fixtures + a new `mock_subscribed_jsonl(tmp_path)` fixture that writes a sample JSONL file.
3. Test cases:
   - **Done-drift detection**:
     - `test_vikunja_done_emits_synthetic_done` — JSONL has `level_sent`; mock_urlopen returns `task.done=True`. Assert: synthetic `done` record appended to JSONL; `synthetic_done_emitted == 1`.
     - `test_vikunja_done_with_existing_done_record_no_emit` — JSONL already has a `done` record. Assert: no new emit; `synthetic_done_emitted == 0`.
   - **Rescheduled-drift detection**:
     - `test_due_date_change_emits_synthetic_rescheduled` — JSONL has `level_sent` with original due. Mock Vikunja returns different due. Assert: synthetic `rescheduled` emitted with `reschedule_to=<new due>`.
     - `test_due_date_unchanged_no_emit` — Vikunja due matches last-known. Assert: no emit.
     - `test_due_date_change_with_terminal_record_no_emit` — JSONL has `dismissed`. Assert: no emit (terminal short-circuits).
   - **Hard-fail integration**:
     - `test_derive_state_error_files_hard_fail` — JSONL has malformed record (missing `level`). Assert: `file_hard_fail_bug` called with `reason="derive_state_inconsistency"`.
     - `test_phantom_subscription_files_hard_fail` — mock Vikunja task has `[Felix-Escalation]` comment but JSONL is empty for this task. Assert: hard-fail with `reason="phantom_subscription"`.
     - `test_hard_fail_dedup_hit_does_not_double_file` — mock hard_fail.file_hard_fail_bug to return `deduped=True`. Assert no second invocation in same tick.
   - **Multi-project sweep**:
     - `test_reconcile_all_iterates_projects` — populate two JSONL files (`project-4-...`, `project-7-...`). Call `reconcile_all`. Assert two ReconcileReports returned.
   - **dry_run mode**:
     - `test_dry_run_reports_no_writes` — dry_run=True with detected drift. Assert: `synthetic_done_emitted` reported but no new JSONL line written.
   - **NFR-001 performance smoke** (not a strict gate, but record observed duration):
     - `test_reconcile_50_tasks_under_60s` — populate JSONL with 50 subscribed tasks (mock_urlopen returns immediately for each). Assert `report.duration_seconds < 60`.
4. Coverage target: ≥85% line + branch.

**Files**:
- `tests/escalation/test_reconcile_completions.py` (new, ~360 lines, ~13 test cases)

**Validation**:
- [ ] `pytest tests/escalation/test_reconcile_completions.py -v` all green.
- [ ] Coverage ≥85% line + branch.
- [ ] Performance smoke test passes (mocked Vikunja → 50 tasks < 60s).

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

pytest. Vikunja mocked via `mock_urlopen`. `hard_fail.file_hard_fail_bug` mocked via monkeypatch to avoid subprocess invocation. JSONL writes go to `tmp_path`. Performance smoke uses mocked Vikunja so 50-task sweep completes in seconds.

## Definition of Done

- [ ] T015-T017 subtasks complete with all validations green.
- [ ] `pytest tests/escalation/test_reconcile_completions.py -v` passes.
- [ ] Coverage ≥85% line + branch.
- [ ] All three detection paths (done-drift, rescheduled-drift, phantom-subscription) covered with explicit tests.
- [ ] Performance smoke test demonstrates 50-task sweep < 60s.

## Risks

- **Rescheduled-drift detection is subtle**: research D3 says "compare against last `reschedule_to`"; if no prior reschedule, the "original" due_date is unknown to the JSONL. Implementation MUST handle the no-prior-reschedule case explicitly (current decision: emit synthetic if no prior reschedule AND due_date != Vikunja's value; if both unknown, no emit).
- **synthetic record loop**: a synthetic `done` emit then must NOT trigger reconcile to re-fire on next tick. Because the synthetic record has `state="done"` (terminal), `derive_state` short-circuits at terminal and reconcile no longer treats the task as subscribed. Test must verify.
- **Hard-fail tick storm**: if reconcile encounters many malformed records in one tick, it could file many P2-bugs. Mitigation: WP04's dedup ensures only one bug per task. Reviewer should verify that a tick with 5 malformed records files at most 5 distinct bugs (one per unique task).

## Reviewer Guidance

1. Verify the three detection paths each have a passing test.
2. Verify `hard_fail.file_hard_fail_bug` is called with the correct `reason` per the trigger.
3. Verify the synthetic record emit uses `source="reconcile"` (so subsequent ticks can identify reconcile-origin records).
4. Verify the rescheduled-drift edge case logic against research D3.
5. Coverage ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP05 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T20:46:42Z – claude:opus:python-implementer:implementer – shell_pid=5187 – Started implementation via action command
- 2026-05-21T20:57:51Z – claude:opus:python-implementer:implementer – shell_pid=5187 – Ready for review — all 3 detection paths tested + hard-fail integration
- 2026-05-21T21:07:28Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=9013 – Started review via action command
