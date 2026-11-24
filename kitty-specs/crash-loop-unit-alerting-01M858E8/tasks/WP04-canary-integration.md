---
work_package_id: WP04
title: Canary integration and fault isolation
dependencies:
- WP02
- WP03
requirement_refs:
- FR-006
- FR-011
- FR-013
- NFR-002
- NFR-005
- C-001
- C-003
- C-005
- SC-005
planning_base_branch: fix/crash-loop-unit-alerting
merge_target_branch: fix/crash-loop-unit-alerting
branch_strategy: Planning artifacts for this mission were generated on fix/crash-loop-unit-alerting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/crash-loop-unit-alerting unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-crash-loop-unit-alerting-01M858E8
base_commit: d132d7b87592d8b0bb8d731ed2d24376fe27d0f4
created_at: '2026-11-23T23:45:42.924836+00:00'
subtasks:
- T016
- T017
- T018
- T019
history:
- at: '2026-11-23T23:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/canary/
create_intent:
- tests/canary/test_run_crash_loop.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/canary/run.py
- tests/canary/test_run_crash_loop.py
- tests/canary/test_run.py
- tests/canary/test_run_deadman.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Canary integration and fault isolation

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Objective

Wire the crash-loop stage into `scripts/canary/run.py`:

- `run_pass(..., crash_loop_check=None)` runs the stage **after** all inventory components and coverage gaps, and **before** the dedup save.
- `main()` passes the real check.
- Every existing component's outcome, dedup entry, ledger line, tick-signal key set and exit-code behaviour is unchanged (FR-013, SC-005).
- A fault in the stage never aborts the pass (NFR-005).

## Context to read first

- `scripts/canary/run.py`, all of it: especially `_route`, `_ledger`, the summary, the tick-signal exclusion list and `main()`'s dead-man logic.
- `research.md` R-07 (the lock and emit-then-save), R-08 (routing, delivery accounting, scope components), R-09 (wiring and harness adaptation) and R-15 (the cap).
- `contracts/crash-loop-alert.md` §5 to §7 (scope routing, ledger lines, summary).
- WP01 (`crash_loop_model`, `crash_loop_state`), WP02 (`crash_loop`) and WP03 (`crash_loop_readers`). Import them; do not modify them.
- `tests/canary/test_run.py`, `tests/canary/test_run_deadman.py` and `tests/canary/test_tick_ledger_reconciliation.py` with `tests/canary/ledger_reconcile.py`, for the key-ledger harness.

## Branch Strategy

Planning happened on `kitty/mission-crash-loop-unit-alerting-01M858E8`. The merge target is `fix/crash-loop-unit-alerting`. Get the worktree with `spec-kitty agent action implement WP04 --agent claude --mission crash-loop-unit-alerting-01M858E8`. Never edit `kitty-specs/` from the lane.

## Subtasks

### T016 — `CrashLoopCheck`

In `run.py` (or a small private section of it; there is no new module, since `run.py` owns the wiring):

```python
@dataclass(frozen=True)
class CrashLoopCheck:
    config_path: Path
    state_path: Path
    lock_path: Path
    read_scopes: Callable[[CrashLoopConfig], tuple[list[ScopeReading], str | None]]   # wraps crash_loop_readers.read_all_scopes(budget_seconds=config.read_budget_seconds); returns (readings, boot_id)
```

`_default_crash_loop_check()` returns the production instance: `crash_loop_model.DEFAULT_CONFIG_PATH`, `crash_loop_state.DEFAULT_STATE_PATH` and `DEFAULT_LOCK_PATH`, and the real readers.

### T017 — The stage inside `run_pass`

Add the keyword `crash_loop_check: CrashLoopCheck | None = None`. With `None`, the code path is **byte-for-byte** today's: no new summary keys besides `summary["crash_loop"] = {"enabled": False}`, and that key is excluded from the tick signal.

When the check is set, a `_run_crash_loop_stage(...)` call runs inside `try/except Exception as exc`. On an exception: `errors.append(f"crash_loop:{exc.__class__.__name__}:{exc}")`, then continue.

1. **Config**: `load_config(check.config_path)`. On `CrashLoopConfigError`, all three scope components are routed `unknown` with evidence `could not check: config invalid: …`, and nothing else happens. Do not touch the state.
2. **Lock** (skipped in `dry_run`): `with StateLock(check.lock_path)`. On `StateLockBusy`: `errors.append("crash_loop:locked")`, and skip the rest. Scope components are **not** routed that tick, because no reading happened, and dedup keeps their previous entries.
3. **Load** `prior, diags = load_state(check.state_path, now=now)`.
4. **Read** `readings, boot_id = check.read_scopes(config)`.
5. **Decide** `outcome = evaluate_tick(readings, prior, config, now, boot_id)`.
6. **Route the scope components** through the existing `_route(component_id, outcome, evidence, emit_on_first_seen=(outcome != "unknown"))` for `crash-loop:system`, `crash-loop:user` and `crash-loop:container`, in that order. Each adds 1 to `components_evaluated`. Append load diagnostics to the system scope's evidence, truncated.
7. **Emit**: for each `Emission` in `plan_emissions(outcome.events, config)`:
   - unless `dry_run`, `result = emit_fn(emission.alert)`; `delivered = getattr(result, "ok", True) is not False`;
   - if not delivered, `alerts_undelivered += 1`; `emitted += 1`;
   - for each covered event, write one ledger line in the contract §6 shape, with `emitted=True`, `delivered=delivered` and the `interval` (all the Proof fields). **The delivery result never changes the crash-loop state** (R-08: no retry, matching `_route`).
   - In `dry_run`, do not emit. Record the component lines only (`component_lines`). The ledger and the state are not written, the same as today's `_ledger` dry-run behaviour.

   Extend `_ledger` with optional `extra: dict | None` keys so event lines can carry `delivered` and `interval` **without changing the shape of existing lines**. Existing calls pass nothing, and their records must be unchanged.
8. **Unverified rises** produce one ledger line each: outcome `crash-loop-unverified`, `emitted=False`, `delivered=False`, plus the `interval`.
9. **Save** (not in `dry_run`): `save_state(outcome.new_state, check.state_path, now=now)`. On failure, `errors.append(f"crash_loop_state_save:{...}")`. The save comes **after** emission (R-07).
10. **Summary**: `summary["crash_loop"] = {"enabled": True, "watched", "ignored", "events", "unverified", "scopes": {...}, "elapsed_ms"}`. Add `"crash_loop"` to the tick-signal exclusion tuple, beside `component_lines` and `alerts_undelivered`.

The stage must run **after** the coverage-gap loop and **before** `dedup_mod.save_state`, so the scope components' dedup entries are saved.

### T018 — `main()` wiring and the harness adaptation

- `main()` calls `run_pass(now=now, dry_run=args.dry_run, crash_loop_check=_default_crash_loop_check())` for both `--once` and `--dry-run`. The `--dry-run` preview therefore shows the crash-loop lines and writes nothing.
- Signature-only adaptation of the three existing fakes (R-09, CX-12): `tests/canary/test_run.py`'s two `def fake_run_pass(*, now, dry_run=False)` and `tests/canary/test_run_deadman.py`'s `def fake_run_pass(*, now, dry_run)` gain `**_ignored`. **Change nothing else in those files.** In particular, the fakes keep calling the real `run_pass` without the check.
- Extend the `--once` stdout line by appending ` crash_loop_events=<n>`. Check first that no test or deploy verifier parses that line strictly (grep `status=` consumers in `scripts/deploy/` and `tests/`). If one does, leave the line unchanged and note it.

### T019 — Tests (`tests/canary/test_run_crash_loop.py`)

Use a fake `CrashLoopCheck`: a `tmp_path` state and lock, the real repo config (or a tmp config), and `read_scopes` returning scripted `(readings, boot_id)` per tick.

- **SC-001 end to end**: two `run_pass` ticks (count 0, then 39, 16 min apart). Exactly one emitted ERROR alert, source `felix-canary:crash-loop:system:obsidian-sync.service`. One ledger event line with `delivered: true` and the interval. The state file is written.
- **SC-005 paired runs**: the same inventory and evaluate fakes as `test_run.py`, run once with `crash_loop_check=None` and once with a healthy fake check. Every **existing** component's ledger line, dedup entry and emitted alert is identical across both runs. The only differences are the new `crash-loop:*` lines and entries.
- **Key ledger with the stage enabled**: run the felix-canary tick-signal reconciliation from `tests/canary/ledger_reconcile.py` (follow `test_tick_ledger_reconciliation.py`) against a `last-tick.json` produced **with the check enabled**. It must reconcile. `crash_loop` must not be in the file.
- **Fault injection (FR-013, NFR-005)**: `read_scopes` raises, `evaluate_tick` is monkeypatched to raise, and `save_state` raises. In each case the pass completes, every inventory component is still evaluated, `errors` contains a `crash_loop` entry, and the tick signal is written with status `error`.
- **Config invalid**: all three scopes are routed `unknown` (first-seen, so not paged, per F5) and the state is untouched.
- **Lock busy**: hold a `StateLock` in the test. The pass records `crash_loop:locked`, emits nothing for crash loops and leaves the state file unchanged.
- **Undelivered**: `emit_fn` returns `_Result(ok=False)` for the crash-loop alert. `alerts_undelivered == 1`, and the ledger line has `delivered: false`. The episode is still open, and the next tick does **not** re-send (no retry). Through `main()` with the dead-man stubbed (as in `test_run_deadman.py`), the ping outcome is `fail`.
- **Dry run**: `main(["--dry-run"])` routed to the real `run_pass` with a fake check. Nothing is emitted, and no state file, ledger file or tick file appears. The output contains the `crash-loop:system` line.
- **main wiring**: monkeypatch `run_mod.run_pass` with a recorder. `main(["--once"])` passes a `crash_loop_check` that is a `CrashLoopCheck` built from the production defaults (no dead code).
- **Scope unknown path**: the container reading fails. `crash-loop:container` is ledgered `unknown`, system and user are healthy, and nothing is paged on first sight.
- **Cap**: 7 units cross at once. 4 emits happen (3 individual + 1 aggregate) and 7 ledger event lines are written. If the aggregate is undelivered, all 4 folded lines say `delivered: false`.

Then run the **whole** canary suite and the full repo suite. Record the counts in the WP history. The full suite must be ≥ the 10907-passed floor plus the new tests, with no new failures.

## Definition of Done

- [ ] All tests pass. `.venv/bin/python -m pytest tests/canary -q` and the full suite pass, with counts recorded.
- [ ] The diff in `tests/canary/test_run.py` and `test_run_deadman.py` is **only** the `**_ignored` signature additions. The reviewer checks `git diff`.
- [ ] `last-tick.json`'s key set is unchanged (the reconciliation test proves it).
- [ ] Commits use conventional messages and these trailers:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01AFaUqc3Puxhf5oxUb9LLP6`.

## Reviewer guidance

- The stage's placement relative to the dedup save.
- `dry_run` writes nothing (state, both ledgers, tick).
- `_ledger`'s existing record shape is unchanged when `extra` is not passed.
- Delivery accounting covers every crash-loop emit, including aggregate and cleared.
- An exception anywhere in the stage cannot skip the dedup save or the tick-signal write.
