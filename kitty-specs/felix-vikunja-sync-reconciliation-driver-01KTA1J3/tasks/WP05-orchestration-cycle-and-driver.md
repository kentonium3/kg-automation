---
work_package_id: WP05
title: 'Orchestration: cycle pipeline + driver CLI'
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-008
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T018
- T019
- T020
- T021
agent: "claude"
shell_pid: "89521"
history:
- at: '2026-06-04T19:53:57Z'
  by: spec-kitty.tasks
  note: Created WP05 from plan.md + contracts/cycle-pipeline.md § cycle entry point
authoritative_surface: scripts/sync/
execution_mode: code_change
owned_files:
- scripts/sync/cycle.py
- scripts/sync/driver.py
- tests/sync/test_cycle.py
- tests/sync/test_driver.py
tags: []
---

# WP05 — Orchestration: cycle pipeline + driver CLI

## Objective

Compose the 6-phase cycle from the modules built in WP01–WP04, expose a CLI invokable from systemd, and implement bootstrap mode for first-run state population. This WP integrates everything that came before; correctness here means end-to-end correctness.

After this WP, the driver can be invoked as:

```bash
python3 -m scripts.sync.driver                              # steady-state tick
python3 -m scripts.sync.driver --bootstrap                  # first-run state seed
python3 -m scripts.sync.driver --dry-run                    # observation, no writes
python3 -m scripts.sync.driver --cadence-seconds 60         # override default cadence (test only)
```

## Context

The 6-phase cycle is documented in `contracts/cycle-pipeline.md`. The phases are:
1. `fetch` — Vikunja delta poll (WP02 fetch.py)
2. `diff` — compute divergences (WP02 diff.py)
3. `classify` — UC classification (WP03 classify.py)
4. `emit` — guards + JSONL append + WhatsApp delivery (WP04 emit.py)
5. `update` — replace cached values; advance felix_last_observed_at
6. `complete` — atomic state commit + last-tick.json write

Exit codes:
- 0: cycle succeeded; freshness pointer advanced
- 1: cycle failed in fetch/diff/classify; pointer NOT advanced; safe state
- 2: cycle failed in emit/update/complete; events may be partial-committed; operator action
- 3: validation error before any I/O; safe state

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree per WP; commits inside the worktree.

## Implementation command

```bash
spec-kitty agent action implement WP05 --agent <name>
```

Depends on WP01, WP02, WP03, WP04. All four must have merged into the mission lane before WP05's tests can run end-to-end.

---

## Subtask T018 — `scripts/sync/cycle.py`: 6-phase orchestration

**Purpose**: Compose the cycle phases into one `run_cycle` function. Handles per-phase failure, atomic state commit, and the tick-id / timestamp invariants.

**Steps**:

1. Define `@dataclass(frozen=True) class CycleConfig`:

   ```python
   @dataclass(frozen=True)
   class CycleConfig:
       state_dir: Path
       secrets_dir: Path
       api_base_url: str
       cadence_seconds: int
       whatsapp_recipient: str
       dry_run: bool
   ```

2. Define `@dataclass(frozen=True) class CycleResult`:

   ```python
   @dataclass(frozen=True)
   class CycleResult:
       success: bool
       exit_code: int          # 0, 1, or 2
       tick_id: str
       cycle_error: str | None
       events_emitted: dict    # {"auto_resolved": N, "unsafe_to_auto_resolve": M}
       layer_pointers_before: dict
       layer_pointers_after: dict
       duration_ms: int
   ```

3. Implement `run_cycle(config: CycleConfig) → CycleResult`:

   - Phase 0 (preamble):
     - Generate `tick_id` (ULID).
     - Capture `started_at_utc` (`datetime.now(timezone.utc)` formatted ISO-8601 with Z).
     - Read freshness pointer → `pointer_before`. Missing file → exit code 3 (bootstrap not run).
     - Read task_cache, project_cache, guard_state.
     - Read vikunja token from `secrets_dir / "vikunja-api"`. Missing → exit 3.
   - Phase 1 (`fetch`):
     - Roll G-3 day if needed.
     - Call `fetch.fetch_delta(...)`. On failure → CycleResult(success=False, exit_code=1, ...). Write to `last-tick.errors.jsonl`.
   - Phase 2 (`diff`):
     - Call `diff.compute_divergences(...)`. On failure → exit 1.
   - Phase 3 (`classify`):
     - For each divergence, look up task in fetched delta; call `classify.classify(...)`.
   - Phase 4 (`emit`):
     - Read recent_events from JSONL (last 24h).
     - Call `emit.emit_events(...)`. On failure → exit 2 (events may have partial-committed).
     - Capture `committed_events` and `updated_guard_state`.
   - Phase 5 (`update`):
     - Apply cache updates per fetched delta (replace tracked fields, update `felix_last_observed_at`).
     - Apply first-observation cache creations.
     - On failure → exit 2.
   - Phase 6 (`complete`):
     - `state.write_task_cache(...)`.
     - `state.write_project_cache(...)`.
     - `state.write_guard_state(updated_guard_state)`.
     - `state.write_freshness(FreshnessPointer(last_polled_utc=started_at_utc))`.
     - `state.write_per_tick_health(...)`.
     - On any failure → exit 2.
     - On success → CycleResult(success=True, exit_code=0, ...).

4. Implement `run_bootstrap(config: CycleConfig) → CycleResult`:

   - Read all tasks via `fetch.fetch_delta(token, base_url, "0001-01-01T00:00:00Z", set())`.
   - For each task: treat as first observation; create cache entry.
   - For each fetched project: add to project_cache.
   - Initialize guard_state with day=today_et, count=0, cap=5.
   - Write all state files atomically.
   - DO NOT classify or emit. DO NOT write to conflict-events.jsonl.
   - Write `last-tick.json` with `tick_id`, `started_at_utc`, `duration_ms`, `cycle_error: null`, `events_emitted: {auto_resolved: 0, unsafe_to_auto_resolve: 0}`.
   - Return CycleResult(success=True, exit_code=0, ...).

5. **Atomicity invariants**:
   - State files written ONLY in the `complete` phase (phase 6). Earlier phases work entirely in-memory.
   - Phase 6 writes in dependency order: task_cache (largest), project_cache, guard_state, freshness, last-tick. Freshness MUST be the second-to-last write (last-tick.json is the marker that the cycle landed cleanly).
   - On any phase-6 file write failure, the freshness pointer state on disk is whatever state phase 6 reached. The next cycle re-polls from that pointer. Events emitted in phase 4 are already in the JSONL.

6. **Dry-run path**: when `config.dry_run == True`, run phases 1-5 in memory and SKIP all state writes in phase 6. Print a summary to stderr. Return success.

**Files**:
- `scripts/sync/cycle.py` (~340 lines)

**Validation**:
- [ ] Steady-state cycle: 0 events → exit 0, freshness advanced
- [ ] Phase-N failure: phases ≥ N skipped; freshness NOT advanced for phases 1-4; partial-commit possible for phases 5-6
- [ ] Bootstrap: empty state dir → all 5 state files populated; conflict-events.jsonl NOT created (or remains empty)
- [ ] Atomicity: simulated SIGTERM between emit (rows in JSONL) and complete (cache not advanced) → next cycle re-processes via event_id idempotency

---

## Subtask T019 — `scripts/sync/driver.py`: CLI entry + bootstrap + exit codes

**Purpose**: The `python3 -m scripts.sync.driver` entry point. Parses CLI flags, resolves env vars, validates inputs, dispatches to `run_cycle` or `run_bootstrap`, and translates the result into the exit code.

**Steps**:

1. Build argparse parser per `contracts/cycle-pipeline.md` § Cycle entry point:

   ```python
   parser = argparse.ArgumentParser(prog="scripts.sync.driver", ...)
   parser.add_argument("--cadence-seconds", type=int, default=None,
                       help="Cycle cadence (180-600). Default: env FELIX_SYNC_CADENCE_SECONDS or 300.")
   parser.add_argument("--state-dir", type=Path, default=None)
   parser.add_argument("--secrets-dir", type=Path, default=None)
   parser.add_argument("--api-base-url", type=str, default=None)
   parser.add_argument("--whatsapp-recipient", type=str, default=None)
   parser.add_argument("--dry-run", action="store_true")
   parser.add_argument("--bootstrap", action="store_true")
   ```

2. Implement `resolve_config(args, env) → CycleConfig`:
   - Resolve each value from CLI → env var → default (as documented).
   - **Cadence validation**: floor 180, ceiling 600. Outside → exit 3.
   - **Recipient validation**: must be E.164 format (regex `^\+\d{8,15}$`). Missing → exit 3.
   - All other env vars have safe defaults.

3. Implement `main(argv: list[str] | None = None) → int`:
   - Parse args.
   - Resolve config; on validation error → exit 3.
   - If `args.bootstrap`: call `run_bootstrap(config)`.
   - Else: call `run_cycle(config)`.
   - Return `result.exit_code`.

4. Add module-level `if __name__ == "__main__": sys.exit(main())`.

5. Stderr output: structured one-line summaries per phase. Format: `[sync] phase=fetch status=ok duration_ms=87` or `[sync] phase=emit status=error reason="..."`.

**Files**:
- `scripts/sync/driver.py` (~220 lines)

**Validation**:
- [ ] `python3 -m scripts.sync.driver --help` returns 0 and prints usage
- [ ] Missing recipient → exit 3 with clear error message
- [ ] Cadence out of range → exit 3
- [ ] `--dry-run` produces no state file writes (verified by mock state writers)

---

## Subtask T020 — `tests/sync/test_cycle.py`: end-to-end cycle tests [P]

**Purpose**: Cover the full cycle with mocked I/O, per-phase failure injection, bootstrap path, atomicity invariants.

**Steps**:

1. Build fixtures: temp state directory (`tmp_path`), patched HTTP via `mock_urlopen`, patched subprocess via `mock_subprocess_run`.

2. Test cases:

   - `test_steady_state_happy_path`: empty delta (no Vikunja changes since pointer) → exit 0, freshness advanced, last-tick.json written with all counts 0.
   - `test_one_unsafe_delivered`: one diverged due_date → emit happens, mock_subprocess called with the formatted message, JSONL has one row, freshness advanced.
   - `test_one_auto_resolved`: one task labeled `felix:ignore` with a divergence → JSONL row with class=auto_resolved, mock_subprocess.call_count == 0.
   - `test_phase_1_fetch_failure_exit_1`: mock urlopen raises HTTPError → exit 1, freshness NOT advanced, last-tick.errors.jsonl appended.
   - `test_phase_4_emit_failure_exit_2`: mock JSONL write fails → exit 2, partial state may be on disk, last-tick.errors.jsonl appended.
   - `test_phase_6_complete_failure_exit_2`: state write to freshness fails mid-phase-6 → exit 2.
   - `test_atomicity_simulated_crash_between_emit_and_complete`: mock causes phase 5 to raise → events from phase 4 are in JSONL, freshness pointer is OLD, next cycle re-processes.
   - `test_bootstrap_populates_cache`: empty state dir → after `run_bootstrap(...)`, freshness.json + task-cache.json + project-cache.json + guard-state.json + last-tick.json all exist, conflict-events.jsonl does NOT.
   - `test_dry_run_no_state_writes`: dry_run=True, divergences detected → no state files mutated; stderr summary printed.

3. Use mocks at the urllib + subprocess level (NOT at the function level — test the integration).

4. Verify exit codes: `result.exit_code` matches the documented mapping in each scenario.

**Files**:
- `tests/sync/test_cycle.py` (~380 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_cycle.py -q` passes
- [ ] Atomicity test confirms next cycle re-processes without duplicates (event_id idempotency)

---

## Subtask T021 — `tests/sync/test_driver.py`: CLI surface tests [P]

**Purpose**: Cover the argparse surface, env-var resolution, validation errors, and the bootstrap/dry-run flags.

**Steps**:

1. Test cases:

   - `test_help_exits_zero`: `--help` → exit 0, usage in stdout.
   - `test_missing_recipient_exits_3`: no CLI arg, no env → exit 3, "recipient" in stderr.
   - `test_recipient_via_cli_overrides_env`: both set → CLI wins.
   - `test_recipient_via_env`: only env set → resolves from env.
   - `test_recipient_not_e164_exits_3`: recipient = "notaphone" → exit 3.
   - `test_cadence_out_of_range_high_exits_3`: --cadence-seconds 700 → exit 3.
   - `test_cadence_out_of_range_low_exits_3`: --cadence-seconds 60 → exit 3.
   - `test_bootstrap_flag_dispatches_to_run_bootstrap`: monkeypatch run_bootstrap; --bootstrap → run_bootstrap called, run_cycle NOT called.
   - `test_no_flags_dispatches_to_run_cycle`: monkeypatch both; no --bootstrap → run_cycle called.
   - `test_dry_run_flag_propagates_to_config`: --dry-run → CycleConfig.dry_run is True.

2. Use `pytest.MonkeyPatch` for env var manipulation and function patching.

3. `main(argv=[...])` rather than invoking subprocess (faster, easier to assert).

**Files**:
- `tests/sync/test_driver.py` (~220 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_driver.py -q` passes
- [ ] All exit-code-3 paths covered
- [ ] Recipient validation (E.164) tested in both directions

---

## Test strategy

Combined test suite at WP05 completion:

```bash
python3 -m pytest tests/sync/ -q --cov=scripts/sync --cov-report=term
```

Target ≥80% line coverage across the entire `scripts/sync/` package. Per memory `reference_pytest_branch_coverage_pragma`, use `# pragma: no branch` for defensive checks that are unreachable in practice (e.g., guards after early-return invariants).

---

## Definition of Done

- [ ] All 4 subtasks complete; all listed files committed in the WP05 worktree
- [ ] `python3 -m pytest tests/sync/ -q` passes (WP01..WP05 tests combined)
- [ ] `python3 -m scripts.sync.driver --help` returns 0 from repo root
- [ ] `python3 -m scripts.sync.driver --dry-run` runs end-to-end with mocked Vikunja (operator-side smoke test deferred to WP06's runbook)
- [ ] No edits to files outside the WP's `owned_files` list
- [ ] Exit codes 0/1/2/3 all reachable and tested

---

## Risks and mitigations

- **Risk: phase 6 write order is wrong; last-tick.json is written before freshness, signaling success when freshness didn't land.** Mitigation: tests assert the write order. Reviewer guidance below makes this an explicit check.
- **Risk: bootstrap accidentally emits events.** Mitigation: bootstrap code path skips classify and emit entirely. Tests assert conflict-events.jsonl is NOT created during bootstrap.
- **Risk: cycle takes longer than the cadence (cycle takes 6 min on a slow Vikunja).** Mitigation: systemd timer uses `OnUnitInactiveSec=300s` which means "300s after the previous tick exited," not "every 300s." Even slow cycles serialize correctly. Documented in WP06 timer comments.
- **Risk: dry-run output looks like real activity.** Mitigation: stderr summary lines are prefixed `[sync DRY-RUN]` distinguishing from production. Tests assert this.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Phase 6 write order**: read `cycle.py:run_cycle` and confirm the order is task_cache → project_cache → guard_state → freshness → last-tick. The freshness MUST be second-to-last; last-tick is the marker of full success.
2. **Phase failure invariants**: tests for exit codes 1 and 2 verify the freshness-pointer behavior. Exit 1 = pointer untouched. Exit 2 = pointer state depends on which phase 6 file write succeeded.
3. **Bootstrap does NOT emit**: read `run_bootstrap` and confirm classify and emit are skipped entirely. Test asserts conflict-events.jsonl absence.
4. **CLI exit codes**: all four exit codes (0, 1, 2, 3) are tested with deterministic paths.
5. **No silent failure**: every failure surfaces via stderr + the last-tick.errors.jsonl record. Spec FR-010 enforced.
6. **No edits to WP01-WP04 owned files**.

Reject if phase 6 write order is wrong, if bootstrap emits events, or if any exit-code path is missing test coverage.

---

## References

- Mission spec: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`
- Pipeline contract: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/cycle-pipeline.md`
- State layout: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/state-directory.md`
- From WP01: `scripts/sync/state.py` (all state I/O), `scripts/sync/http.py`
- From WP02: `scripts/sync/fetch.py`, `scripts/sync/diff.py`
- From WP03: `scripts/sync/classify.py`, `scripts/sync/guards.py`
- From WP04: `scripts/sync/emit.py`, `scripts/sync/send_whatsapp.py`
- Existing CLI pattern: `scripts/habits/record_completion.py:_read_token` and the `main()` function
- Existing driver pattern: `scripts/security/credential_health_check/listing.py` (deterministic-driver CLI shape)

## Activity Log

- 2026-06-04T20:48:00Z – claude – shell_pid=87326 – Started implementation via action command
- 2026-06-04T20:52:52Z – claude – shell_pid=87326 – All 4 subtasks committed (7e9c9312 on lane-a). 30 new tests pass; full sync suite 194/194. Phase 6 write order verified (freshness before last-tick); bootstrap doesn't emit; dry-run skips writes; CLI exit codes 0/1/2/3 all reachable.
- 2026-06-04T20:56:08Z – claude – shell_pid=89521 – Started review via action command
