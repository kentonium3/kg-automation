---
work_package_id: WP02
title: felix-canary pings its dead-man check
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-003
- FR-004
- FR-006
- FR-010
- C-004
- SC-001
planning_base_branch: feat/offhost-deadman-pings
merge_target_branch: feat/offhost-deadman-pings
branch_strategy: Planning artifacts for this mission were generated on feat/offhost-deadman-pings. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/offhost-deadman-pings unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-offhost-deadman-pings-01M50990
base_commit: cd84582ded5af3b95ca5c9265f061001a68a9ef1
created_at: '2026-10-15T17:46:50.689841+00:00'
subtasks:
- T006
- T007
- T008
history:
- at: '2026-10-15T18:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/canary/
create_intent:
- tests/canary/test_run_deadman.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/canary/run.py
- tests/canary/test_run_deadman.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – felix-canary pings its dead-man check

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

- **Inputs:** `plan.md` dispositions (rounds 3 and 4 are authoritative) and the canary row of the `data-model.md` outcome table.
- **Code:**
  - `scripts/canary/run.py`: `run_pass` (~201); the emit site at about :325 (`emit_fn(alert)` discards its result); the summary at about :462-477; the tick-signal filter at about :483 (`k != "component_lines"`); `main()` at about :559.
  - Exit policy: 0 for a completed pass even when components are unhealthy, 1 when `run_pass` raises (`OnFailure` fires).
- **Tests:** `tests/canary/test_run.py`, especially `_recording_emit` (which returns None) and the CLI tests that monkeypatch `run_pass`.
- **Tick-signal schema:** pinned by `tests/canary/test_tick_ledger_reconciliation.py`. **It must not change.**

## Subtasks

### T006 – Count undelivered alerts

- At the emit site, keep the result: `result = emit_fn(alert)`.
- Count it undelivered when `getattr(result, "ok", True) is False`. A fake returning None stays "delivered", so existing tests keep their meaning.
- Add `"alerts_undelivered"` to the summary.
- Exclude it from the persisted tick signal: extend the filter to `k not in {"component_lines", "alerts_undelivered"}`. Keep the comment's meaning.

### T007 – Ping from `main()`

- Ping only when not `--dry-run` and not `--self-check`.
- **If `run_pass` raised**, the existing path returns 1. Before returning, call `deadman.ping("canary", "fail")` inside a try (it is total anyway). Keep the return of 1.
- **Otherwise:**
  - `ok, why = deadman.channel_ok(os.environ, summary.get("alerts_undelivered", 0) == 0)`.
  - The outcome is `success` when `summary["status"] == "success"` and `ok`, else `fail`.
  - Call `deadman.ping("canary", outcome)`.
  - Log one line naming `why` when it is not ok. Never include a URL.
- **The exit code is unchanged.**
- Import `deadman` at module level as `from scripts.common import deadman` so tests can monkeypatch `run_mod.deadman`.

### T008 – Tests (`tests/canary/test_run_deadman.py`)

Monkeypatch `run_mod.deadman.ping` and `channel_ok` with recorders. Use the `test_run.py` CLI pattern (a monkeypatched `run_pass` that routes to the real pass with injected `emit_fn` and paths).
- **Healthy channel, all delivered:** one `ping("canary","success")`, rc 0.
- **Unhealthy components with alerts delivered:** still `success` (FR-004).
- **An emit returning an object with `ok=False`:** `alerts_undelivered==1` in the summary, `channel_ok` called with `delivered_ok=False`, and the ping is `fail`.
- **`channel_ok` false** (topic missing or probe failed): `fail`.
- **Pass status `error`**: `fail`, rc 0.
- **`run_pass` raises:** `ping("canary","fail")`, rc 1.
- **`--dry-run` and `--self-check`:** no ping.
- **Tick signal unchanged:** the persisted tick-signal JSON has no `alerts_undelivered` key and equals today's key set.
- **Totality:** `deadman.ping` raising must not change rc. The real module is total, but guard anyway.
- Run `tests/canary` in full; `test_tick_ledger_reconciliation.py` must stay green.

## Definition of Done

`TMPDIR=/dev/shm .venv/bin/python3 -m pytest tests/canary -q` passes.

## Reviewer guidance

- Confirm exit codes and the tick-signal key set are unchanged.
- Confirm no URL is ever handled in `run.py`.
