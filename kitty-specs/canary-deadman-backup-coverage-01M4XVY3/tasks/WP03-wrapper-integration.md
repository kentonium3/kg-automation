---
work_package_id: WP03
title: 'Wrapper integration: verdict, alert, run record, script location'
dependencies:
- WP02
requirement_refs:
- FR-004
- FR-005
- FR-006
- FR-007
- NFR-003
- C-003
- SC-004
planning_base_branch: fix/canary-deadman-backup-coverage
merge_target_branch: fix/canary-deadman-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on fix/canary-deadman-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/canary-deadman-backup-coverage unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-canary-deadman-backup-coverage-01M4XVY3
base_commit: 0f7009f6a384fbaeded6c183df657abb84b2e1aa
created_at: '2026-10-14T19:33:01.442750+00:00'
subtasks:
- T011
- T012
- T013
- T014
- T015
phase: Phase 2 - Core behavior
history:
- at: '2026-10-14T19:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan IC-02; research R5–R8; contract)
agent_profile: python-pedro
authoritative_surface: scripts/office2/felix_health_check/
create_intent:
- scripts/office2/felix_health_check/health-check.sh
- scripts/office2/felix_health_check/tests/test_run_record_contract.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/office2/felix_health_check/run.py
- scripts/office2/felix_health_check/health-check.sh
- scripts/office2/felix_health_check/__init__.py
- scripts/office2/felix_health_check/tests/test_run.py
- scripts/office2/felix_health_check/tests/test_run_record_contract.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – Wrapper integration: verdict, alert, run record, script location

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history WP03 --note "..."`.

---

## Objectives & Success Criteria

`scripts/office2/felix_health_check/run.py:main` does the following, in order:
1. Evaluates coverage, behind its own guard.
2. Runs the **repo-tracked** shell script, with every exception contained.
3. Classifies the shell output with the unchanged `classify()`.
4. Combines both into one status by precedence.
5. Emits one bus-safe alert when that status is not `ALL_HEALTHY`.
6. Writes the extended run record exactly per [contracts/health-check-run-record.md](../contracts/health-check-run-record.md).
7. Exits 0.

Done when SC-001 holds end to end through `main()`: the incident fixtures produce `FAILURES_DETECTED`, and the rendered alert shows both coverage findings even with more than 4 KB of shell output. The contract invariants are pinned (T015), and the 16 existing tests in `test_run.py` stay green, updated only where the script path or record keys legitimately changed.

## Context & Constraints

- Spec FR-004–FR-007, NFR-003, C-003. Plan IC-02. Research R5–R8 and the review dispositions (Codex-3/5/6, paula-2/5/6, re-review 2). The contract (authoritative for record keys and alert details).
- Alert bus: `scripts/common/alert_bus` (`Alert`, `emit`, `render`). `render.py` truncates **each** `details` value to 500 characters (`DETAIL_VALUE_MAX`) and preserves insertion order.
- The canary reads `last-run.json` via the legacy `signal-file` path (`scripts/canary/probes.py` `_explicit_error`, `TIMESTAMP_KEYS`). See the contract's invariants. Never add a top-level `error`, `errors`, `exit_status`, `cycle_error`, `restic_exit_code` or `prune_exit_code`, or any timestamp key ranked before `ran_at_utc`.
- Fixtures/helpers from WP02 (`scripts/office2/felix_health_check/tests/fixtures/`) may be read.

## Branch Strategy

- **Planning base branch**: `fix/canary-deadman-backup-coverage` · **Merge target branch**: `fix/canary-deadman-backup-coverage`.

## Subtasks & Detailed Guidance

### Subtask T011 – The script moves into the repo

- Create `scripts/office2/felix_health_check/health-check.sh` from the live copy (sha256 `7880bf9734e2ca5b6aa37309622f8d748a95a992764caa664b6dcdd796e3f1d2`, captured 2026-10-14; text in the session scratchpad `real-health-check.sh`, or `ssh office2-claude cat ~/helper-scripts/health-check.sh`, which is read-only).
- Changes allowed:
  - Replace the stale header "Called by OpenClaw cron — outputs findings for agent to relay" with an accurate header (run by `run.py` from the deployed checkout, #676, #1063).
  - Add a comment above the `felix-core-digest.timer` `is-active` check: it cannot see a dormant timer, follow-up kentonium3/kg-automation#1068.
  - **No behavioral change**: its output tokens and checks stay identical.
- `git update-index --chmod=+x` (repo memory: `git add` re-reads the working-tree mode, so set it after the final add and verify with `git ls-files -s` showing `100755`).
- `run.py`: `HEALTH_CHECK_SCRIPT = Path(__file__).resolve().with_name("health-check.sh")`. Update module docstrings that name the old path. Update `__init__.py`'s docstring if it names it.

### Subtask T012 – Restructure `main` (research R5, R6; Codex-6)

New flow:

```
ran_at = now
findings = _evaluate_coverage_guarded(now)    # import + call inside try/except BaseException-safe (Exception)
script_status, exit_code, out, err, script_note = _run_script_guarded()
status = combine(script_status, findings)
delivery = no-alert record, or send_alert(status, script_note, findings, out+err)
write record
return 0
```

- `_evaluate_coverage_guarded`: `from scripts.office2.felix_health_check import coverage` **inside** the try. Any exception → two `unknown` findings with `outcome="unavailable"`, evidence `"<ExcType>: <msg>"`.
- `_run_script_guarded`: missing or non-executable → `SCRIPT_MISSING`; `TimeoutExpired` → `UNKNOWN`; **any other exception** (`OSError` on launch, `UnicodeDecodeError`, …) → `UNKNOWN` with a note naming it. Otherwise `classify(...)`.
- `combine(script_status, findings)`: implement data-model.md's precedence table verbatim (`FAILURES_DETECTED` > `SCRIPT_MISSING` > `UNKNOWN` > `ALL_HEALTHY`). Pure and unit-tested over the full grid of 4 script statuses × {ok, failure, unknown} per finding.
- `main` must not raise for any of the above (NFR-003). Test: monkeypatch coverage to raise `RuntimeError`; `main()` returns 0 and writes a record with `status: "UNKNOWN"` (paula-6).

### Subtask T013 – Run record (contract)

Keys, exactly:
- `status`, `ran_at_utc`, `exit_code` (int or `null`), `delivery` (unchanged shapes);
- `script_status` (the shell's own verdict);
- `script_path` (str);
- `coverage_checks` (2 × `to_record()`).

`exit_code` keeps today's meaning (the shell's return code; `null` when it did not run).

### Subtask T014 – Alert details (contract; Codex-3, paula-5)

`send_alert(status, findings, script_note, raw_output)` builds `details` in **insertion order**:
1. `script`: only when `script_note` (missing/timeout/launch failure);
2. `coverage:<component>`: one per non-ok finding, `"<FINDING> (<outcome>): <evidence>"`;
3. `status`;
4. `output`: shell output, truncated as today.

`description`: `"Felix health check on office2 reported: <status>."`, plus `" Coverage: <comma-separated non-ok components>."` when any. Title, source and severity are unchanged.

Test through the **real renderer**: build the `Alert` the code would emit, render it with the bus's render function (find the public one in `scripts/common/alert_bus/render.py`), and assert both coverage findings and the script line appear in the rendered text when `raw_output` is 6 KB of filler. The no-op control: the same test against a details dict with coverage appended after `output` would lose them. Assert that the ordering helper places them first.

### Subtask T015 – Run-record contract tests (`test_run_record_contract.py`)

- Invariant 3, using the **real** canary probe and the real inventory's `felix-health-check` declaration: `scripts.canary.probes.run_probe(decl, now, http_get=…, run_cmd=…, read_state=lambda p: record)`. The records are produced by running `main()` with patched effects, not built by hand:

| case | expect canary |
|---|---|
| (a) all healthy | ok, not stale |
| (b) coverage failure, shell exit 0 | ok, not stale (runner fine, data bad) |
| (c) coverage unknown | not ok (status `UNKNOWN`) |
| (d) coverage failure, shell exit 1 | not ok (non-zero `exit_code`, existing behavior) |

  All four must anchor on `ran_at_utc`: assert the evidence names `ran_at_utc`.
- Invariants 1–2, **derived dynamically** (paula-2): `ranked = TIMESTAMP_KEYS[:TIMESTAMP_KEYS.index("ran_at_utc")]`. Assert that no key of a real record is in `ranked`, nor in `{"restic_exit_code", "prune_exit_code", "exit_status", "errors", "error", "cycle_error"}`. Then, for each `k` in `ranked`, add `record[k] = <stale timestamp>` and assert the probe's evidence no longer names `ran_at_utc`. That proves the probe would be hijacked, so the guard is meaningful (the non-vacuity control).
- Invariant 4: `coverage_checks` has exactly two entries in records from script-missing, timeout, launch-failure and coverage-raise runs.

## Test Strategy

```bash
python3 -m pytest scripts/office2/felix_health_check/tests -q
python3 -m pytest -q -x
bash -n scripts/office2/felix_health_check/health-check.sh
```

## Risks & Mitigations

- **Breaking the canary's #891 watch**: T015 pins it with the real probe.
- **A silent crash** (no `OnFailure=`): T012 contains every path. Backstop: the canary's 13 h freshness probe.
- **Executable bit lost**: verify `git ls-files -s`.

## Review Guidance

- Run T015's hijack control mentally: does adding `completed_at_utc` really flip the anchor? The test must show it.
- `combine` grid coverage is complete (4×9).
- `test_run.py` changes are limited to the path and record-key updates; there are no weakened assertions.

## Progress & Status

`spec-kitty agent tasks add-history WP03 --note "…"` · implement: `spec-kitty agent action implement WP03 --agent claude --mission canary-deadman-backup-coverage-01M4XVY3`
