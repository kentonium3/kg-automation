---
work_package_id: WP04
title: Runner orchestration (run.py + dedup.py)
dependencies:
- WP02
- WP03
requirement_refs:
- FR-001
- FR-004
- FR-005
- FR-006
- FR-008
- FR-009
tracker_refs:
- kentonium3/kg-automation#327
planning_base_branch: feat/felix-canary-registry
merge_target_branch: feat/felix-canary-registry
branch_strategy: Planning artifacts for this mission were generated on feat/felix-canary-registry. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-canary-registry unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
- T019
- T020
- T021
agent: "claude"
shell_pid: "60916"
history:
- at: '2026-07-11T15:30:13Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
role: implementer
execution_mode: code_change
authoritative_surface: scripts/canary/
owned_files:
- scripts/canary/run.py
- scripts/canary/dedup.py
- tests/canary/test_run.py
- tests/canary/test_dedup.py
create_intent:
- scripts/canary/run.py
- scripts/canary/dedup.py
- tests/canary/test_run.py
- tests/canary/test_dedup.py
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load python-pedro`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Build the runner's two orchestration modules:
- `scripts/canary/dedup.py` — dedup state keyed by `component_id` with a **mandatory transition/recovery
  reset** (F7), so a health *change* always emits and `failed → healthy → failed` is never swallowed.
- `scripts/canary/run.py` — the systemd/CLI entrypoint that iterates targets → `evaluate` → dedup → emit,
  writes the aggregate tick-signal and the per-component JSONL ledger (F8), and is **fail-open** (a single
  component fault never aborts the pass, NFR-004).

This is the module `felix-canary.timer` executes. Model it on the proven `scripts/trust/run_trust_scan.py`
+ `scripts/trust/state.py` (atomic writes, injected `now`, exit-code discipline, fail-safe I/O).

Read first: `../data-model.md` (DedupState, ComponentLedger, TickSignal, Alert, state diagram, invariants),
`../contracts/canary-contracts.md` §3/§4/§5, `../research.md` R5 (dedup) + R6 (severity) + R9 (unknown/gap)
+ R10 (ledger), `../plan.md` IC-04. Study `scripts/trust/run_trust_scan.py` and `scripts/trust/state.py`
for the house pattern.

## Context

- **Inputs**: `scripts.canary.registry.load_targets` (targets + coverage-gap set) and
  `scripts.canary.health.evaluate` (per-target HealthResult).
- **Alert bus (F3 — the REAL API)**: `from scripts.common.alert_bus import emit, Alert, Severity`.
  `emit(alert) -> AlertResult` **never raises**; `AlertResult.ok` is the delivery result. The `Alert`
  dataclass is `Alert(source, severity: Severity, title, description, action=None, details: dict[str,str])`
  — there is **no** `signal_id`/`message` field; the message text goes in `description`, the stable signal
  identity is `source`. Severity is the enum (`Severity.ERROR`/`WARN`/`INFO`), never the string "warning".
- **State paths (module constants, injectable)**:
  - `DEFAULT_DEDUP_PATH = Path("/data/services/felix-canary/state/dedup.json")`
  - `DEFAULT_TICK_PATH = Path("/data/services/felix-canary/state/last-tick.json")`
  - `DEFAULT_LEDGER_DIR = Path("/data/services/felix-canary/ledger")`
- **Atomic writes**: temp file in the same dir + `os.replace` (copy the helper shape from
  `scripts/trust/state.py::save_state`). Best-effort ledger: a ledger write failure never aborts the pass.

## Subtasks

### T016 — `dedup.py`: DedupState with mandatory transition reset (F7)
- State file = JSON map `component_id -> {"last_outcome": str, "last_emitted_utc": ISO8601}`. `load`/`save`
  fail-safe + atomic (mirror `scripts/trust/state.py`).
- `decide(component_id, outcome, now, state, *, window=timedelta(hours=6)) -> (should_emit: bool,
  is_recovery: bool, new_entry)`:
  - `last_outcome` **differs** from `outcome` (any transition, including → `healthy`) ⇒ **always emit**;
    if the new outcome is `healthy` mark `is_recovery=True` (INFO "recovered"); update the entry.
  - unchanged **and** bad **and** `now - last_emitted_utc < window` ⇒ suppress (still ledger it).
  - unchanged, bad, window elapsed ⇒ re-emit; update `last_emitted_utc`.
  - `healthy` unchanged ⇒ no emit, no state churn beyond `last_outcome`.
- `now` injected; never call `datetime.now()` inside. This is the closes-`failed→healthy→failed` guarantee
  (INV-F) — key by `component_id` with `last_outcome`, NOT by `(component_id, outcome)`.

### T017 — `run.py`: orchestration (fail-open)
- `run_pass(*, now, inventory=None, dedup_path=..., tick_path=..., ledger_dir=..., emit_fn=emit,
  dry_run=False) -> dict` (the summary). Load targets + gaps; load dedup state.
- For each target: `evaluate(...)` in a try/except → on exception append to `errors[]`, record an `unknown`
  ledger line, **continue** (NFR-004 / INV-D). Never let one component abort the pass.
- Apply the F5 persistence rule for `unknown`/`gap`: they emit as WARN **once they persist past the dedup
  window** — run them through the same `dedup.decide` (their `outcome` is `"unknown"`/`"gap"`), so a
  first-seen unknown is recorded but not paged, and a persistent one pages once per window.
- Coverage gaps (from the registry) are emitted as WARN through the same dedup path (keyed by their
  `component_id`), so they don't re-page every tick.

### T018 — Emit via the alert bus (F3) + severity map
- Build the `Alert` for an emitting HealthResult:
  `emit(Alert(source=f"felix-canary:{component_id}", severity=<mapped>, title=f"{component_id} health:
  {outcome}", description=f"{evidence}", action=None, details={"component_id":component_id,
  "outcome":outcome,"evidence":evidence}))`.
- Severity map (R6): `failed`/`stale` → `Severity.ERROR`; `degraded`/`gap`/persistent-`unknown` →
  `Severity.WARN`; recovery → `Severity.INFO`. Recovery title/description say "recovered".
- `emit_fn` is injected (defaults to the real `emit`) so tests assert emitted alerts without touching ntfy.
  A failed `emit` (AlertResult.ok False) is still recorded in the ledger (INV-C is satisfied by the bus's
  own #706 ledger; do not double-write). Do **not** revert dedup on emit-failure this mission (simpler than
  trust-scan's keep_due; note the difference — a bus outage may drop one canary alert, acceptable given the
  15-min re-tick and the bus ledger).

### T019 — Per-component ledger (F8) + aggregate tick-signal
- **Ledger**: append one JSON line per component per tick to `DEFAULT_LEDGER_DIR/<YYYY-MM-DD>.jsonl`:
  `{component_id, outcome, evidence, emitted (bool), suppressed_dedup (bool), evaluated_at}`. Records
  **every** outcome incl. healthy/suppressed/gap/deduped (satisfies FR-008 — the tick-signal counts and the
  bus ledger do not). Best-effort: a write failure appends to `errors[]` and continues (INV-D).
- **Tick-signal**: atomic-write `DEFAULT_TICK_PATH` = `{status: success|error, completed_at_utc,
  components_evaluated, emitted, suppressed_dedup, coverage_gaps, suppressed_status, errors: [...],
  duration_ms}`. This is the runner's own health-pointer (FR-010; WP05 registers it with a
  `tick-signal-file` health_check whose `completed_at_utc` is the freshness anchor).
- `--dry-run` computes + prints but writes **nothing** (no dedup/tick/ledger) and emits nothing.

### T020 — CLI + exit-code discipline
- `argparse` mutually-exclusive-ish flags: `--once` (the deployed timer form — one full pass), `--dry-run`,
  `--self-check`. `python3 -m scripts.canary.run` entrypoint (`if __name__ == "__main__": sys.exit(main())`).
- **Exit codes** (mirror trust-scan): a completed pass exits **0** even when components are unhealthy
  (unhealthy → emits, not a process failure); exit non-zero **only** on a runner-level failure (inventory
  unreadable, state dir unwritable) — that non-zero is what `OnFailure=` (WP06) catches.
- `--self-check`: assert inventory readable + `scripts.common.alert_bus` importable + state dir writable;
  print `status=ok`/`status=error`; exit 0/1.

### T021 — Unit tests
- `tests/canary/test_dedup.py`: transition always emits (incl. recovery); within-window unchanged-bad
  suppresses; window-elapsed re-emits; the `failed→healthy→failed` sequence emits all three transitions.
- `tests/canary/test_run.py`: a full pass over a fixture inventory with injected `evaluate`/`emit_fn`;
  a component whose `evaluate` raises does **not** abort the pass (others still evaluated, error recorded,
  `unknown` ledgered); tick-signal + ledger written with expected counts; `--dry-run` writes nothing;
  emitted `Alert`s carry the right `source`/`Severity`; exit 0 on a completed pass with failures present.

## Branch Strategy

Planning base and merge target are both `feat/felix-canary-registry`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back to
`feat/felix-canary-registry`.

## Definition of Done

- [ ] `dedup.decide` always emits on a transition (incl. recovery INFO) and suppresses within-window
      unchanged-bad; `failed→healthy→failed` emits three times.
- [ ] A single component's `evaluate` raising never aborts the pass; it records `unknown` + an error and the
      pass continues (NFR-004).
- [ ] Emission uses the real `Alert(source, severity=Severity.…, title, description, details)` API; severity
      map matches R6; persistent `unknown`/`gap` emit as WARN via the same dedup window (F5).
- [ ] Per-component JSONL ledger records every outcome; aggregate tick-signal written atomically with counts
      + `completed_at_utc`.
- [ ] `python3 -m scripts.canary.run --dry-run` runs offline against the real inventory and prints a line
      per service-type entry; `--self-check` prints `status=ok`.
- [ ] Completed pass exits 0 even with unhealthy components; runner-level failure exits non-zero.
- [ ] `pytest tests/canary/test_run.py tests/canary/test_dedup.py` green; ntfy + real files never touched
      (injected `emit_fn`, temp dirs).

## Reviewer guidance

Verify: dedup keys by `component_id` with `last_outcome` (not `(id,outcome)`) so a re-failure after recovery
emits (F7); the pass is genuinely fail-open (wrap the per-component body, assert a raising component doesn't
stop the loop); `--dry-run` writes nothing; the `Alert` construction matches the real dataclass exactly
(`source`/`severity` enum/`description` — a wrong field name raises at construction); exit code is 0 for a
completed pass with failures (only runner-level faults are non-zero, feeding `OnFailure`); no `datetime.now()`
buried in the modules (inject `now`); atomic writes via temp+`os.replace`.

## Activity Log
- 2026-07-11T18:03:09Z – claude – shell_pid=60916 – Assigned agent via action command
- 2026-07-11T18:27:33Z – claude – shell_pid=60916 – WP04: runner orchestration; F5 fix; 98 tests.
- 2026-07-11T18:27:38Z – user – shell_pid=60916 – APPROVE (reviewer-renata, re-review): F5 fix correct + scoped; F7 intact; no regressions; 98 tests; no silent-never-paged path.
