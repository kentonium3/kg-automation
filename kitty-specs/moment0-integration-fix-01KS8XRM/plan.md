# Implementation Plan: Fix Moment 0 wiring — integrate at signals adapter

**Branch**: `main` | **Date**: 2026-05-22 | **Spec**: [spec.md](spec.md)
**Mission ID**: `01KS8XRMC0EQZ8HCJ52GXCJ226`
**Parent mission**: `drift-event-auto-resolution-01KS8J32` (#362, mission_number=47, commit `cdc91f6`)

## Summary

Extract the Moment 0 routing logic from `handle_drift_events.py::process_events()` into a new shared helper `scripts/doc_audit/routing/drift_moment0.py`. Invoke that helper from BOTH the cron entry point (`signals/drift_event.py::DriftEventSignalSource.commit()`) and the library/CLI entry point (`handle_drift_events.py::process_events()`). Bulk-close #378-#390 as part of cutover.

This is a focused fix mission, not a feature build. Most logic already exists from #362 — we're relocating it to the correct seam and adding the cron-path tests that #362 should have had. Estimated total work: 3 WPs.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: existing `anthropic` SDK (unchanged from #362)
**Storage**: existing JSONL ledger at `/data/services/security-monitor/logs/drift-events-ledger.jsonl` (file will be CREATED on first successful Moment 0 invocation post-fix)
**Testing**: pytest, mocked `JudgmentClient`, mocked `subprocess` for gh calls. ≥85% coverage on new + modified modules.
**Target Platform**: office2 (Ubuntu 24.04 LTS) via systemd user timer
**Project Type**: single project (additive refactor in existing scripts/ tree)
**Performance Goals**: P95 per-tick latency ≤90s (inherits #362's NFR-006); no degradation vs broken-but-fast pre-fix state
**Constraints**: no changes to existing #362 modules (drift_interpretation, drift_ledger, etc.); no new third-party deps; cursor + drain semantics preserved
**Scale/Scope**: ~3-10 drift events/day; same cost envelope as #362

## Charter Check

**Status**: Skipped (charter absent / governance unresolved per pre-existing tool-registry issue — not a blocker).

## Project Structure

### Documentation (this feature)

```
kitty-specs/moment0-integration-fix-01KS8XRM/
├── plan.md              # This file
├── spec.md              # Mission spec
├── research.md          # Phase 0 — D1..D5 decisions (this file's siblings)
├── data-model.md        # Phase 1 — entities (mostly inherits from #362)
├── contracts/
│   └── routing-helper.md  # The shared helper API contract
└── checklists/requirements.md
```

(No `quickstart.md` — operator runs are covered by the existing #362 quickstart with the corrected entry-point note.)

### Source Code (repository root)

```
scripts/doc_audit/
├── routing/
│   ├── __init__.py                  # MODIFIED — re-export route_drift_event
│   ├── drift_to_proposed_edit.py    # unchanged (from #362)
│   ├── apply_decisions.py           # unchanged (existing)
│   └── drift_moment0.py             # NEW — extracted Moment 0 routing
├── signals/
│   └── drift_event.py               # MODIFIED — commit() invokes route_drift_event
├── helpers/
│   └── handle_drift_events.py       # MODIFIED — process_events() calls route_drift_event (dedup)
└── (all other modules unchanged from #362)

tests/doc_audit/
├── routing/
│   ├── test_drift_to_proposed_edit.py        # unchanged
│   └── test_drift_moment0.py                 # NEW — shared helper tests
├── signals/
│   └── test_drift_event.py                   # MODIFIED — new Moment 0 path tests
└── helpers/
    └── test_handle_drift_events.py           # MODIFIED — assert calls to shared helper
```

**Structure Decision**: minimal additive change. One new file in `routing/`, one new test file, plus edits to two existing modules + their tests.

## Phase 0 — Research

Five decisions, all locked from the #362 post-mortem:

- **D1**: Shared helper module path: `scripts/doc_audit/routing/drift_moment0.py` (joins existing `drift_to_proposed_edit.py` and `apply_decisions.py` in the routing package).
- **D2**: `JudgmentClient` lifecycle in the signals adapter: lazy construction on first need; held as `self._judgment_client` for tick lifetime; never constructed when `[drift_interpretation].enabled = false` (FR-010).
- **D3**: Shared helper signature: `route_drift_event(*, event, mapping, config, client, ledger_path, repo, event_id, timestamp_utc) -> RoutingOutcome` (per spec Key Entities section). Returns metadata; raises `DriftInterpretationError` on retry exhaustion (caller handles fallback).
- **D4**: Cleanup script for #378-390: thin analog to `cutover_362.py` named `cleanup_391.py`. Idempotent marker `~/.config/doc-audit/cleanup-391.done`. Same `gh issue close` + comment pattern as #362.
- **D5**: Test strategy: WP01 (shared helper) gets full coverage of all 6 verdict paths from #362 (PROPOSED_EDIT × {Tier A/B/judgment}, JUDGMENT_REQUIRED, NO_CHANGE_NEEDED, RETRY_EXHAUSTED). WP02 (cron-path integration) adds tests that the adapter calls the shared helper correctly and preserves cursor/drain semantics. WP03 (cleanup) gets mocked-subprocess tests like cutover_362.

See [research.md](research.md) for fuller rationale (mostly inherits #362's D1-D10).

## Phase 1 — Design & Contracts

### Entities

Inherits all from #362 (DriftVerdict, DriftInterpretationContext, AuditLedgerEntry, DriftInterpretationError, RoutingOutcome). No new entities.

Promoted from #362's WP04: `RoutingOutcome` (was local to handle_drift_events.py) moves to `routing/drift_moment0.py` and becomes the public type.

### Contract

[contracts/routing-helper.md](contracts/routing-helper.md) — the shared helper's Python API surface, pre/post-conditions, and side-effect contract.

### Quickstart

Inherits #362's [quickstart.md](../drift-event-auto-resolution-01KS8J32/quickstart.md) with one correction: §1 ("Deploy the code") and §5 ("Smoke tests") refer to `signals/drift_event.py` as the Moment 0 integration site, not `handle_drift_events.py`.

## Charter Re-Check

Same status as initial: absent. No new gate violations.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- branch_matches_target: true

## Complexity Tracking

No violations to track (charter absent).

## Open Decisions

All resolved. The shared-helper extraction is the only architectural question and it was locked during the #362 post-mortem.
