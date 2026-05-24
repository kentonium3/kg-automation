# Implementation Plan: Drift Ledger Retry Count Hardening

**Mission**: `drift-ledger-retry-count-hardening-01KSC6AJ` (`01KSC6AJ2JK8N2NJT4QB6AB36Z`)
**Date**: 2026-05-24
**Spec**: [spec.md](spec.md)
**Source issue**: [#403](https://github.com/kentonium3/gg-automation/issues/403)
**Branch**: `main` → `main`

## Summary

Re-align the drift-ledger schema bound with the retry policy. The validator currently enforces `retry_count in [0, 3]` while the retry policy attempts up to 4 calls. When retries exhaust, `signals/drift_event.py:464` writes the unclamped `exc.attempts = 4` into a ledger row, and the validator raises `ValueError`, crashing the drift event. The fix widens the validator bound to `[0, retry_max]`, derives `retry_max` from `RETRY_DELAYS_SECONDS`, clamps both ledger-write sites defensively, lifts the contract doc to a live arch-docs location, and updates the three existing tests that pin specific `retry_count` values.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: existing — `dataclasses`, stdlib `json`; no new dependencies
**Storage**: Append-only JSONL at `/data/services/security-monitor/logs/drift-events-ledger.jsonl` on office2 (read-only for this mission — schema change is additive and backward-compatible)
**Testing**: `pytest` against `tests/doc_audit/` (existing test layout; new regression test added in same tree)
**Target Platform**: Linux server (office2, Ubuntu 24.04 LTS) — runs under `felix-doc-auditor.service`
**Project Type**: single project (Python scripts, no web/mobile)
**Performance Goals**: no perf impact — schema validation is O(1) per row; clamp is a single `min()`
**Constraints**: NFR-001 (on-disk JSON structure unchanged); NFR-003 (all existing tests still pass after fixture updates); C-005 (additive widening only — existing `retry_count ≤ 3` rows must continue to validate)
**Scale/Scope**: ~5 files touched in `scripts/`; 1 new doc; 1 new test fn; 3 existing tests updated

## Charter Check

**Status**: SKIPPED — charter governance is in `compact` mode (per `spec-kitty charter context --action plan --json`) and reports the pre-existing tool-registry unresolved diagnostic (charter's `available_tools` doesn't list `pytest`/`python` despite them being in the default registry). This is documented in user memory as deferred until after mission #343. Not a blocker for this mission.

No Charter gate violations identified. The mission is a localized bug fix that does not touch governance-sensitive code paths.

## Project Structure

### Documentation (this feature)

```
kitty-specs/drift-ledger-retry-count-hardening-01KSC6AJ/
├── spec.md                  # /spec-kitty.specify output
├── plan.md                  # this file
├── research.md              # Phase 0 — resolved assumptions
├── data-model.md            # Phase 1 — AuditLedgerEntry schema (post-fix)
├── quickstart.md            # Phase 1 — verification path
├── contracts/
│   └── drift-ledger-schema.md   # Phase 1 — planning-time copy of the lifted contract
├── checklists/
│   └── requirements.md      # spec quality checklist
└── tasks/                   # populated by /spec-kitty.tasks
```

### Source Code (repository root)

```
scripts/doc_audit/
├── output/
│   └── drift_ledger.py             # validator: widen [0,3] → [0,retry_max]; update dataclass docstring
├── signals/
│   └── drift_event.py              # write site at :464 — add defensive clamp (THE BUG FIX)
├── helpers/
│   └── handle_drift_events.py      # clamp at :645 — update min(3,...) → min(retry_max,...)
└── judgment/
    └── drift_interpretation.py     # source of RETRY_DELAYS_SECONDS (referenced, not modified)

tests/doc_audit/
├── output/
│   └── test_drift_ledger.py        # update test at :307 (rejection-case retry_count)
├── signals/
│   └── test_drift_event.py         # update assertion at :925; ADD parametrized regression test
└── helpers/
    └── test_handle_drift_events.py # update assertion at :1076

docs/design/architecture/
└── contracts/                      # NEW directory (sibling to data/)
    └── drift-ledger-schema.md      # lifted from kitty-specs archive; widened bound
```

**Structure Decision**: Single project. Code lives in `scripts/doc_audit/`; tests mirror in `tests/doc_audit/`; the lifted contract doc joins the existing arch-docs at `docs/design/architecture/contracts/` (NEW subdirectory, parallel to `data/`).

## Phase 0 — Research

All four spec-flagged assumptions resolved deterministically by code inspection. One new finding (existing clamp at `handle_drift_events.py:645` needs widening too) was added to scope. See [research.md](research.md) for the full Decision / Rationale / Alternatives breakdown.

## Phase 1 — Design & Contracts

- **Data model** ([data-model.md](data-model.md)): `AuditLedgerEntry` (drift-ledger variant). Only the `retry_count` bound changes; all other fields, types, and serialization rules are unchanged. Additive widening preserves backward compatibility for existing rows.
- **Contracts** ([contracts/drift-ledger-schema.md](contracts/drift-ledger-schema.md)): planning-time copy of the lifted live contract doc. The live version will be created at `docs/design/architecture/contracts/drift-ledger-schema.md` during implementation.
- **Quickstart** ([quickstart.md](quickstart.md)): how to run the new regression test locally, then how to verify end-to-end on office2 post-merge.

## Implementation Sequencing

Three lanes of work that the WP-finalize step (`/spec-kitty.tasks`) will arrange:

1. **Schema + clamps** (one atomic change for the code surface):
   - Widen `output/drift_ledger.py` validator bound
   - Update `output/drift_ledger.py` dataclass docstring
   - Add clamp at `signals/drift_event.py:464`
   - Update clamp at `helpers/handle_drift_events.py:645`
   - Update the three existing test assertions that pin `retry_count` to the old bound

2. **New regression test**:
   - Parametrized test in `tests/doc_audit/signals/test_drift_event.py` exercising `exc.attempts ∈ {0, 1, retry_max-1, retry_max}` through the full `drift_event.commit` ledger-write path; asserts no exception and the ledger row's `retry_count` equals the input

3. **Contract doc lift**:
   - Create `docs/design/architecture/contracts/drift-ledger-schema.md` (lift content from `kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md` with the widened bound)
   - Update the `See ...` reference in `output/drift_ledger.py` dataclass docstring

Lane 3 is independent of lanes 1+2 and can run in parallel. Lanes 1 and 2 are sequenced (test depends on the clamp+widening landing first, or it must be marked `xfail` in the failing-test-first style).

**Office2 verification is post-merge operator work, not a WP.** Per SC-006: re-enable `felix-doc-auditor.timer`, trigger one tick, confirm ledger rows appear and no `ValueError` in journalctl.

## Complexity Tracking

No Charter Check violations. No complexity-tracking entries.

## Branch Strategy (restated per command file)

- Current branch: `main`
- Planning/base branch: `main`
- Final merge target: `main`
- `branch_matches_target`: true
- No worktree at plan time; worktrees created at `/spec-kitty.implement`

## Next Step

`/spec-kitty.tasks` — finalize WP breakdown for the three sequencing lanes above.
