# Implementation Plan: Sweeper tick signal extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP`
**Branch**: `main` (planning + merge target) | **Date**: 2026-06-03
**Spec**: [spec.md](spec.md) | **Source issue**: [#510](https://github.com/kentonium3/kg-automation/issues/510)

## Branch Strategy

- Current branch at plan start: `main`
- Planning/base branch: `main`
- Final merge target: `main`
- `branch_matches_target`: true

## Summary

Add a `sweeper_tick` signal extractor to the felix-core-digest signal-extraction loop. The extractor reads the latest non-dry-run record from `/data/services/openclaw/state/habits/sweeper-ledger.jsonl` and trips on three binary conditions: (1) `exit_status != "success"`, (2) `errors[]` non-empty, (3) `started_at_utc` older than 26 hours or no parseable record exists. The extractor returns `count_cycle = 1` when ANY condition holds and `0` otherwise; the quiet-cycle gate from #512 keeps the no-fail case below threshold without filing. Net surface: one new module, one tests file, three small additions to existing files (`config.toml`, `config_loader.py`, `tick.py`), and one architecture-data entry.

## Technical Context

**Language/Version**: Python 3.11 (matches mission #490 substrate)
**Primary Dependencies**: stdlib only — no new imports
**Storage**: no schema or state-file changes; reads existing sweeper ledger
**Testing**: pytest, existing patterns in `scripts/openclaw/observation/tests/`
**Target Platform**: office2, `felix-core-digest-signals` systemd timer (15-min cycle)
**Project Type**: single — extension of the `scripts/openclaw/observation/` package
**Performance Goals**: <500 ms per cycle (NFR-001); the ledger is small and the extractor reads only the tail
**Constraints**: no `datetime.now()` in extractor body (C-004 — `now_utc` plumbed via `extract()` signature); no changes to `_threshold_status` predicate (NFR-002); no changes to `SignalState` schema (NFR-003)
**Scale/Scope**: one new source_kind; one new signal_id; ~120 lines of extractor + ~250 lines of tests + ~30 lines of config/dispatch/JSON

## Charter Check

- **Tool registry mismatch (known, deferred)**: charter reports `pytest`/`python` unavailable per `project_charter_tool_registry_mismatch` memory. Tools are in active use; non-blocking.
- **Tier classification**: Tier 3 (Logic/Workflow). No pre-flight checklist.
- **Directive 5 (documentation standards)**: machine-readable `signal-to-doc-map.json` update is the authoritative record; the per-signal contract lives inside the existing mission #490 `tick-signal.contract.md` and is extended in this mission's `contracts/sweeper-tick-extractor.contract.md`.
- **Directive 6 (deterministic vs stochastic split)**: the extractor is purely deterministic — JSON parse + field checks + timestamp arithmetic. No LLM step.
- **Directive 7 (migration completeness)**: this is a feature addition, not a migration. The principle still applies via C-003 — all surfaces ship together (extractor + tests + config + dispatch + doc-map entry), no follow-on issues queued.

No charter violations. Charter Check passes.

## Project Structure

### Documentation (this mission)

```
kitty-specs/sweeper-tick-signal-extractor-01KT6MJP/
├── plan.md                              # This file
├── research.md                          # Phase 0 — Open Decisions
├── data-model.md                        # Phase 1 — trip truth table + ledger record shape
├── quickstart.md                        # Phase 1 — local + office2 verification
├── contracts/
│   └── sweeper-tick-extractor.contract.md
├── spec.md
└── tasks/                               # /spec-kitty.tasks output
```

### Source Code (repository root)

```
scripts/openclaw/observation/
├── signals/
│   ├── sweeper_tick.py                  # NEW — extractor module
│   ├── config_loader.py                 # EDIT — add "sweeper_ledger_jsonl" to _VALID_SOURCE_KINDS
│   └── config.toml                      # EDIT — add [signals.sweeper_tick] section
├── tick.py                              # EDIT — wire into build_extractor_dispatch()
└── tests/
    └── test_signals_sweeper_tick.py     # NEW — extractor tests

docs/design/architecture/data/
└── signal-to-doc-map.json               # EDIT — add "sweeper-tick-stale-or-failed" entry
```

**Structure Decision**: Single Python project (kg-automation). Six files touched: one new module, one new test file, three small in-place edits, one architecture-data edit. Mirrors the layout of the three existing extractors.

## Complexity Tracking

No charter violations to justify. Section intentionally empty.

## Phase 0 Deliverable

See [research.md](research.md). Three Open Decisions resolved at /specify time: (OD-1) trip semantic, (OD-2) dry-run handling, (OD-3) staleness threshold value.

## Phase 1 Deliverables

- [data-model.md](data-model.md) — ledger record shape and the trip truth table (8 named cases including each edge-case scenario from spec).
- [contracts/sweeper-tick-extractor.contract.md](contracts/sweeper-tick-extractor.contract.md) — authoritative interface description; references mission #490's `tick-signal.contract.md` for the host-pipeline contract.
- [quickstart.md](quickstart.md) — local pytest + office2 replay verification.

## Risk & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Ledger format drifts (sweeper.py changes the contract without us noticing) | Low | Medium | The extractor reads only `started_at_utc`, `exit_status`, `errors`, `dry_run`. Missing fields are treated as failure (defensive). Test coverage pins the field set. |
| 26-hour threshold off-by-one against the actual cron cadence | Low | Low | Verified the sweeper runs daily ~11:30 UTC; 26 h gives 2 h slack. Threshold is parameterized in `config.toml`; tune in production if needed. |
| Ledger file becomes huge (years of entries) and we read it all | Low | Low | The extractor reads from the tail and processes the most recent records first. Practical ceiling: 1 year ≈ 365 entries × ~1 KB ≈ 365 KB. Even 10 years stays in memory comfortably. |
| Test fixture authoring captures stale field set | Low | Low | Fixtures cite the live ledger as of 2026-06-03 and the sweeper-tick contract path. |
| Replay mode incompatibility | Low | Low | The existing `--replay-log` flag patches `resolve_log_files`. For the JSONL ledger source, we'll keep replay mode out of scope (FR-009 covers integration via unit tests; the replay flag stays log-only). |

## Phase Plan

- **Phase 0 (research)**: complete; all decisions resolved at specify time.
- **Phase 1 (design)**: artifacts authored as part of /plan.
- **Phase 2 (tasks)**: produced by `/spec-kitty.tasks` next. Anticipated WP shape: single WP, six subtasks (module, config_loader update, config.toml entry, dispatch wiring, tests, signal-to-doc-map entry).

## Branch Strategy (reiteration)

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: true

## Next step

Run `/spec-kitty.tasks` to materialize the work package.
