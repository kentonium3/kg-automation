# Tasks: Sweeper tick signal extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP`
**Planning base**: `main` | **Merge target**: `main`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Implement extractor module at `scripts/openclaw/observation/signals/sweeper_tick.py` | WP01 | | [D] |
| T002 | Add `"sweeper_ledger_jsonl"` to `_VALID_SOURCE_KINDS` in `config_loader.py` | WP01 | [D] |
| T003 | Add `[signals.sweeper_tick]` block to `signals/config.toml` | WP01 | [D] |
| T004 | Wire extractor into `build_extractor_dispatch()` in `tick.py` | WP01 | | [D] |
| T005 | Add `scripts/openclaw/observation/tests/test_signals_sweeper_tick.py` covering the 8 named cases | WP01 | | [D] |
| T006 | Add `sweeper-tick-stale-or-failed` entry to `docs/design/architecture/data/signal-to-doc-map.json` | WP01 | [D] |
| T007 | Run full `pytest scripts/openclaw/observation/tests/ -v` and confirm green | WP01 | | [D] |

7 subtasks in a single WP. Mirrors the structure of mission #61 (one cohesive change touching code + tests + contract + arch-data).

## Work Package WP01 — Sweeper tick extractor

**Goal**: Land the `sweeper_tick` signal so felix-habit-sweeper failures escalate automatically. All six source surfaces (extractor, config_loader, config.toml, dispatch wiring, tests, signal-to-doc-map) ship together; no follow-on issues.

**Priority**: P1 (sole WP)

**Independent test**: `pytest scripts/openclaw/observation/tests/test_signals_sweeper_tick.py -v` exercises all 8 named cases from `contracts/sweeper-tick-extractor.contract.md`; the broader observation suite (`pytest scripts/openclaw/observation/tests/ -v`) stays green.

**Estimated prompt size**: ~600 lines

### Included subtasks

- [x] T001 Implement extractor module at `scripts/openclaw/observation/signals/sweeper_tick.py` (WP01)
- [x] T002 Add `"sweeper_ledger_jsonl"` to `_VALID_SOURCE_KINDS` in `config_loader.py` (WP01)
- [x] T003 Add `[signals.sweeper_tick]` block to `signals/config.toml` (WP01)
- [x] T004 Wire extractor into `build_extractor_dispatch()` in `tick.py` (WP01)
- [x] T005 Add `scripts/openclaw/observation/tests/test_signals_sweeper_tick.py` covering the 8 named cases (WP01)
- [x] T006 Add `sweeper-tick-stale-or-failed` entry to `docs/design/architecture/data/signal-to-doc-map.json` (WP01)
- [x] T007 Run full `pytest scripts/openclaw/observation/tests/ -v` and confirm green (WP01)

### Dependencies

None — all subtasks share the same code surface and are sequenced for clarity, not for build-order requirements.

## Branch strategy

- Planning base: `main`
- Merge target: `main`
- Execution worktree: created by `spec-kitty next` per `lanes.json`. Single-lane mission.
