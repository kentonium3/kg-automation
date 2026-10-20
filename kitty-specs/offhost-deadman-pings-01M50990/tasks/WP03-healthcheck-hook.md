---
work_package_id: WP03
title: felix-health-check pings its dead-man check
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-004
- FR-006
- FR-010
- C-004
planning_base_branch: feat/offhost-deadman-pings
merge_target_branch: feat/offhost-deadman-pings
branch_strategy: Planning artifacts for this mission were generated on feat/offhost-deadman-pings. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/offhost-deadman-pings unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-offhost-deadman-pings-01M50990
base_commit: cd84582ded5af3b95ca5c9265f061001a68a9ef1
created_at: '2026-10-15T17:47:11.392530+00:00'
subtasks:
- T009
- T010
history:
- at: '2026-10-15T18:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/office2/felix_health_check/
create_intent:
- scripts/office2/felix_health_check/tests/test_run_deadman.py
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- scripts/office2/felix_health_check/run.py
- scripts/office2/felix_health_check/tests/test_run_deadman.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – felix-health-check pings its dead-man check

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `feat/offhost-deadman-pings` · **Merge target branch**: `feat/offhost-deadman-pings`. Worktrees come from `lanes.json`.

## Context

- **Inputs:** the `plan.md` dispositions and the health-check row of the `data-model.md` outcome table.
- **`scripts/office2/felix_health_check/run.py`:**
  - `STATUS_*` and `ALERTING_STATUSES` (~77-87);
  - `_run_script_guarded` (~235-253) returns `(script_status, exit_code, raw_output, script_note)`. A missing script gives `SCRIPT_MISSING`; a timeout, launch failure or decode failure gives `UNKNOWN` with a note;
  - `_evaluate_coverage_guarded`; `_delivery_record` (~261); `main()` (~369-404), which writes `last-run.json` and returns 0.
- **Tests:** `scripts/office2/felix_health_check/tests/test_run.py` and `test_run_record_contract.py` monkeypatch `SIGNAL_FILE`, `_evaluate_coverage_guarded`, `run_health_check_script` and `send_alert`.

## Subtasks

### T009 – Outcome and ping

- **Execution fault**, true when any of these holds:
  - `script_status == STATUS_SCRIPT_MISSING`;
  - the script did not produce output: `exit_code is None` together with a non-empty `script_note`, which covers timeout, launch and decode failures. Confirm against `_run_script_guarded`;
  - coverage "could not start", i.e. every finding is unknown with "coverage could not start". Find the exact marker in `coverage.py` (`_all_unknown`) and match on it robustly; if no clean marker exists, add none and record that in the WP history.
- **Delivery failed** when `status in ALERTING_STATUSES and not delivery["sent"]`. This covers a missing topic, where `attempted` is False (Codex round 1, HIGH).
- **Ping** after the record write: `ok, why = deadman.channel_ok(os.environ, not delivery_failed)`. Outcome is `success` if there is no execution fault and `ok`, else `fail`.
- **If the record write raises:** ping `fail`, then re-raise, preserving today's behaviour.
- The return code is unchanged (0 on the normal path).
- Import as `from scripts.common import deadman`.

### T010 – Tests (`scripts/office2/felix_health_check/tests/test_run_deadman.py`)

Use the existing patterns: a tmp `SIGNAL_FILE`, monkeypatched coverage, script and `send_alert`, and a recording `deadman`.
- **`ALL_HEALTHY` with the channel ok:** `success`.
- **`FAILURES_DETECTED` with the alert delivered and the channel ok:** `success` (FR-004).
- **An alerting status with `sent=False`:** both `attempted=False` (missing topic) and `attempted=True` (delivery error) give `fail`.
- **`SCRIPT_MISSING`:** `fail`. A script timeout gives `fail`. Coverage could not start gives `fail`.
- **`channel_ok` false:** `fail`.
- **Record write raises:** `fail` ping, then the exception propagates.
- **Contract unchanged:** `last-run.json` content equals what it would be without `deadman`. Run `test_run_record_contract.py` unchanged.
- **Totality:** `deadman` raising does not change rc 0.

## Definition of Done

`TMPDIR=/dev/shm .venv/bin/python3 -m pytest scripts/office2/felix_health_check tests/office2/felix_health_check -q` passes.

## Reviewer guidance

- Confirm the missing-topic case pings `fail`.
- Confirm `last-run.json` and the exit code are unchanged.
