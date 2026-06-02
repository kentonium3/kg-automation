# Implementation Plan: Signal trip cycle floor

**Mission**: `signal-trip-cycle-floor-01KT4NHJ`
**Branch**: `main` (planning + merge target) | **Date**: 2026-06-02
**Spec**: [spec.md](spec.md) | **Source issue**: [#512](https://github.com/kentonium3/kg-automation/issues/512)

## Branch Strategy

- Current branch at plan start: `main`
- Planning/base branch: `main`
- Final merge target: `main`
- `branch_matches_target`: true

## Summary

Add a "quiet-cycle gate" to the signal-extraction trip evaluator: the rolling-window branch must require at least one event in the current 15-minute cycle before it can return `tripped_rolling`. The cycle-threshold branch is unchanged. Implementation is a single-predicate edit in `scripts/openclaw/observation/tick.py::_threshold_status`, plus the matching update to the trip-signal contract document and pytest coverage for all four trip outcomes under the new semantics.

## Technical Context

**Language/Version**: Python 3.11 (matches mission #490 substrate)
**Primary Dependencies**: stdlib only — no new imports introduced by this fix
**Storage**: no schema or state-file changes; persisted `SignalState` and rolling-bucket eviction logic untouched
**Testing**: pytest, existing tick-orchestrator test suite at `scripts/openclaw/observation/tests/test_tick_orchestrator.py`; existing fixtures and conftest patterns reused
**Target Platform**: office2 (Ubuntu 24.04 LTS), systemd-timer-driven `felix-core-digest-signals` service
**Project Type**: single — scripts/ subtree of kg-automation
**Performance Goals**: nominal — the predicate adds one boolean comparison; cycle duration target stays well under 1 second
**Constraints**: backwards-compatible with persisted state; no field changes in `last-tick.json`; module size delta ≈ +1 line in source, +N lines in tests/contract
**Scale/Scope**: three currently-enabled signals (`whatsapp_creds_restore`, `web_watchdog_reconnect`, `openclaw_unhandled_error`); pipeline runs every 15 min on a single host

## Charter Check

- **Tool registry mismatch (known, deferred)**: charter resolution reports `pytest`/`python` unavailable per `project_charter_tool_registry_mismatch` memory. The tools are present and in active use; this is a registration gap in the charter, not a real constraint. Mission proceeds; this issue is tracked separately and out of scope here.
- **Tier classification**: change-risk taxonomy Tier 3 (Logic/Workflow). No pre-flight checklist, no architecture-data updates, no service-inventory edits.
- **Directive 6 (deterministic vs stochastic split)**: the fix is entirely deterministic — a one-line predicate plus tests. No LLM step. Already aligned.
- **Documentation standards (Directive 5)**: contract doc update is the authoritative human description; spec.md + plan.md sit alongside.

No charter violations. Charter Check passes.

## Project Structure

### Documentation (this mission)

```
kitty-specs/signal-trip-cycle-floor-01KT4NHJ/
├── plan.md                  # This file
├── research.md              # Phase 0 — Open Decisions and resolutions
├── data-model.md            # Phase 1 — Trip predicate state-table
├── quickstart.md            # Phase 1 — How to verify the fix locally + on office2
├── contracts/
│   └── trip-predicate.contract.md   # Updated trip semantics
├── spec.md                  # /spec-kitty.specify output
└── tasks/                   # /spec-kitty.tasks output (created later)
```

### Source Code (repository root)

```
scripts/openclaw/observation/
├── tick.py                                # EDIT: _threshold_status predicate
└── tests/
    └── test_tick_orchestrator.py          # EDIT: extend coverage for new semantics

kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/
└── contracts/
    └── tick-signal.contract.md            # EDIT: reflect new trip semantics
```

**Structure Decision**: Single Python project (kg-automation). No new modules; surgical edit inside the existing `scripts/openclaw/observation/` package.

## Complexity Tracking

No charter violations to justify. Section intentionally empty.

## Phase 0 Deliverable

See [research.md](research.md). The single Open Decision (OD-1: cycle-floor predicate exact shape) was resolved during `/spec-kitty.specify` discovery.

## Phase 1 Deliverables

- [data-model.md](data-model.md) — trip-predicate state table covering all four outcomes under the new semantics.
- [contracts/trip-predicate.contract.md](contracts/trip-predicate.contract.md) — authoritative description of the new trip predicate; the matching update in mission #490's `tick-signal.contract.md` is a code-level edit tracked in tasks.
- [quickstart.md](quickstart.md) — local + office2 verification recipe.

## Risk & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Predicate regression — a future edit re-introduces OR-trip semantics | Low | Medium | Boundary-test coverage for all four outcomes (`below`, `tripped_cycle`, `tripped_rolling`, `tripped_both`) including the `count_cycle=0, count_rolling=high` case explicitly. Contract doc names the gate. |
| Suppressed real condition — a slow-burn condition trips rolling only when it first hits ≥1 event in a single cycle | Low | Low | This is intentional behavior per spec (FR-002 + spec Edge Cases). A truly silent condition is unobservable by definition; one event per 15-min cycle is a vanishingly low bar. |
| Coupling to mission #490 contract doc | Medium (text drift) | Low | Treat as paired edit in the same WP. Contract update + code change land together; reviewer compares text to predicate. |

## Phase Plan

- **Phase 0 (research)**: complete — single Open Decision resolved at /specify time. See research.md.
- **Phase 1 (design)**: artifacts authored as part of /plan. See data-model.md, contracts/, quickstart.md.
- **Phase 2 (tasks)**: produced by `/spec-kitty.tasks` next — expect a single work package.

## Branch Strategy (reiteration)

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: true

## Next step

Run `/spec-kitty.tasks` to materialize the work package.
