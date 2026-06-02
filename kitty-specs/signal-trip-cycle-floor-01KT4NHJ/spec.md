# Signal trip cycle floor

**Mission**: `signal-trip-cycle-floor-01KT4NHJ`
**Mission type**: software-dev
**Source issue**: [#512](https://github.com/kentonium3/kg-automation/issues/512)
**Target branch**: `main`
**Created**: 2026-06-02

---

## Intent Summary

The felix-core-digest signal-extraction loop must stop re-filing GitHub issues for noise that has already stopped. Today the trip evaluator fires whenever either the current 15-minute cycle OR the rolling 60-minute window crosses its threshold; that "OR" path causes the rolling tail of a real-but-resolved burst to re-trip every cycle for up to ~60 minutes whenever the prior dedup-anchor issue is closed within the decay window. The fix introduces a quiet-cycle gate: the rolling-window branch only fires when the current cycle is non-empty, so a genuinely quiet cycle (`count_cycle == 0`) never re-files post-burst residue. The cycle-threshold branch is untouched.

## Background & Motivation

Mission #490 (`signal-driven-monitoring-haiku-gate`) delivered a deterministic three-signal extraction pipeline that walks OpenClaw logs every 15 minutes and files GitHub issues when thresholds trip. The mission's calibration assumed both branches of the trip — "cycle ≥ cycle_threshold" and "rolling ≥ rolling_threshold" — would always be amplifying signals about a live, ongoing condition.

Operational experience on 2026-06-01 → 2026-06-02 showed the assumption breaks for transient bursts: the upstream OpenClaw v2026.3.24 → v2026.5.28 upgrade fixed a chronic watchdog-reconnect race, cleanly halting the noise. Within fifteen minutes of the operator closing the prior dedup-anchor issues, the next cycle re-filed three new issues (#502, #503, #504) with `count_cycle = 0` for all three signals — purely from rolling-window residue of the now-resolved condition. The operator spent more than a day on this loop; the root cause is structural, not threshold-calibration.

The current behavior erodes operator trust in the issue queue (a triaged condition can resurrect itself), defeats the "close = handled" invariant the workflow depends on, and forces operators to either keep stale issues open for an extra hour or accept recurring false positives. This mission removes that failure mode at the design level.

## User Scenarios & Testing

### Primary scenario: post-burst recovery

1. A real noise condition (e.g., upstream OpenClaw bug) generates many matching events across multiple cycles.
2. The signal-extraction loop trips, files a P2 bug issue (the "anchor"), and dedup suppresses subsequent cycles while that issue stays open.
3. The root cause is resolved (upstream fix lands, service restarted, network recovers). Subsequent cycles record `count_cycle = 0`.
4. The operator closes the anchor issue as "not planned / transitional" with a closure comment.
5. **Expected**: no further issues are filed for this signal until a fresh burst occurs.
6. **Today's actual**: the next cycle's rolling 60-min window still contains pre-fix events; the trip evaluator returns `tripped_rolling`; the deterministic filer creates a new issue carrying the residue. This must stop.

### Secondary scenario: genuine sustained condition

1. A real condition is ongoing — every cycle sees `count_cycle ≥ 1`, and `count_rolling` continues to grow toward `rolling_threshold`.
2. After enough cycles, rolling crosses the threshold even though no single cycle exceeded `cycle_threshold`.
3. **Expected**: the rolling branch still fires (a slow-burn sustained condition deserves an issue). The fix must preserve this case.

### Edge cases

- A single phantom event in a quiet cycle: `count_cycle = 1`, `count_rolling >> rolling_threshold` (from a prior burst). With the gate in place, this WILL trip — one event after a prior burst is sufficient to confirm the condition is still recurring. This is intentional; the gate distinguishes "completely quiet" from "barely active."
- Cycle threshold breached on its own: behavior unchanged. The cycle branch never gated on rolling and continues not to.
- Empty rolling history (first cycle, fresh state): cannot trip rolling-only because `count_rolling` starts at 0.

## Requirements

### Functional

| ID | Status | Requirement |
|---|---|---|
| FR-001 | proposed | The signal-extraction trip evaluator MUST return `below` whenever the current cycle's event count is zero, regardless of the rolling-window count. |
| FR-002 | proposed | When the current cycle's event count is at least 1 AND the rolling-window count meets or exceeds the configured rolling threshold, the trip evaluator MUST return `tripped_rolling`. |
| FR-003 | proposed | When the current cycle's event count meets or exceeds the configured cycle threshold, the trip evaluator MUST return `tripped_cycle` (or `tripped_both` if rolling is also met), independent of whether the cycle-floor gate would otherwise apply. The cycle branch is unchanged by this mission. |
| FR-004 | proposed | The signal-extraction contract documentation MUST reflect the new trip semantics so operators reading the contract can predict pipeline behavior without inspecting code. |
| FR-005 | proposed | Each in-scope trip-status outcome (`below`, `tripped_cycle`, `tripped_rolling`, `tripped_both`) MUST be covered by an automated unit test that exercises the boundary conditions defined in FR-001 through FR-003. |

### Non-Functional

| ID | Status | Requirement |
|---|---|---|
| NFR-001 | proposed | The change MUST be backwards-compatible with persisted signal state (`SignalState`, rolling buckets, last-event metadata): no state schema changes; no migration step. |
| NFR-002 | proposed | The change MUST NOT alter the structure or fields of `last-tick.json` or the signals ledger; only the values of `threshold_status` for cycles meeting the new "quiet-cycle gate" condition will differ. |
| NFR-003 | proposed | The patch MUST keep the total module size and complexity within the spirit of mission #490's ~60-line-per-extractor target — the gate is a one-line predicate, not a refactor. |

### Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | proposed | The fix MUST live in `scripts/openclaw/observation/tick.py::_threshold_status` (the single trip-classification function). Any related helper or constant MUST live in the same module unless duplication elsewhere would be greater. |
| C-002 | proposed | The contract update MUST land in `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md` alongside the code change, so the two artifacts stay synchronized. |
| C-003 | proposed | The change is Tier 3 (Logic/Workflow) under the project change-risk taxonomy — no pre-flight checklist required, no architecture-data updates needed, no service-inventory edits. |
| C-004 | proposed | Test coverage MUST be added or updated in the existing tick orchestrator test suite (`scripts/openclaw/observation/tests/test_tick_orchestrator.py` or its sibling that exercises `_threshold_status`). No new test framework, fixture style, or runner introduced. |

## Success Criteria

| ID | Criterion | Measurement |
|---|---|---|
| SC-001 | A cycle with `count_cycle == 0` never produces a trip outcome and therefore never files an issue. | Automated unit test against `_threshold_status` exercising the zero-cycle, high-rolling state and asserting `below`. |
| SC-002 | A cycle with `count_cycle ≥ 1` and `count_rolling ≥ rolling_threshold` correctly returns `tripped_rolling`. | Automated unit test covering this boundary. |
| SC-003 | A cycle with `count_cycle ≥ cycle_threshold` returns the appropriate `tripped_cycle` or `tripped_both` regardless of the cycle-floor gate. | Existing tests continue to pass; new boundary tests cover both sub-cases. |
| SC-004 | Re-filing the #502/#503/#504 scenario against the post-fix code path produces zero filed issues. | Replay-mode test using captured fixture data with `count_cycle = 0` and the same residual rolling counts that produced #502–#504; assert `issues_filed == []`. |
| SC-005 | The trip-signal contract document accurately describes the new semantics in plain language. | Code-review confirmation that the contract update matches the implemented predicate. |

## Out of Scope

- Threshold value tuning (the recent `44c646db` cutover-wrap commit already lowered them; this mission does not re-touch numeric thresholds).
- Per-signal configurability of the cycle floor (deferred — current scope is a universal floor).
- Changes to the dedup strategy (`open_issue_present` remains as-is).
- Changes to the filer, state persistence, or rolling-bucket eviction logic.
- Anything related to the `whatsapp_session_signal` CLI parser break (tracked separately under #513).

## Assumptions

- The `count_cycle ≥ 1` boundary is the right threshold for the gate. A higher floor (e.g., 3 or 5) might further suppress jitter but would also delay genuine slow-burn detections. Plan-phase can revisit if there is evidence to prefer a higher floor.
- The contract doc is the authoritative human-readable description of trip semantics — kitty-specs missions historically maintain their contracts post-merge.
- Existing tests for `_threshold_status` (if any) follow the patterns established in mission #490's tick-orchestrator test suite; we extend rather than restructure.

## Dependencies

- Mission #490 (`signal-driven-monitoring-haiku-gate-01KT22PC`) delivered the pipeline being modified; its contracts/tests are the substrate.
- Linked issue: #512 (this mission resolves it).
- Related (separate) issue: #513 — `whatsapp_session_signal` CLI parser break. Independent fix; not blocked by or blocking this mission.

## Key Entities

- **Signal extraction cycle**: one 15-min run of the tick orchestrator over all enabled signals.
- **Cycle count (`count_cycle`)**: number of matching events observed in the current cycle.
- **Rolling count (`count_rolling`)**: sum of matching events across the trailing `rolling_window_minutes` (default 60).
- **Trip status**: one of `below`, `tripped_cycle`, `tripped_rolling`, `tripped_both` — the per-signal output of `_threshold_status` that drives filer dispatch.
- **Dedup anchor**: the most recent GitHub issue filed for a given `signal_id`; while it stays open, subsequent trips are suppressed.
