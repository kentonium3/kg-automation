# Research: Signal trip cycle floor

**Mission**: `signal-trip-cycle-floor-01KT4NHJ`
**Date**: 2026-06-02

## Open Decisions

### OD-1: Exact shape of the quiet-cycle gate predicate

**Question**: Three candidate fix shapes were enumerated in issue #512:
- A. Add a current-cycle floor to rolling trips (`count_cycle ≥ 1 AND count_rolling ≥ rolling_threshold`)
- B. Require both branches (drop independent rolling-trip entirely; AND-only)
- C. Make the floor per-signal configurable in `config.toml`

**Decision**: Option A — cycle-floor on rolling trip.

**Rationale**:
- A is the minimum-change fix that preserves the original "rolling-as-amplifier under bursty cycles" use case. A slow-burn condition with one or two events per cycle accumulating toward `rolling_threshold` still fires.
- B is structurally simpler but removes detection for conditions that never breach `cycle_threshold` in a single 15-min window — defeats the rolling-window design intent.
- C adds per-signal surface area (config schema change, loader change, more tests) for a problem that has not been observed to vary per signal. Premature optimization.

**Confirmed via**: `/spec-kitty.specify` discovery (AskUserQuestion → "Cycle-floor on rolling trip (Recommended)" selected by user 2026-06-02).

**Alternatives considered**: Higher floor values (`count_cycle ≥ 3` or `≥ 5`) would further suppress jitter but at the cost of delaying genuine slow-burn detections by additional cycles. The floor of 1 is the natural minimum that distinguishes "genuinely quiet" from "any activity" — adequate for the failure mode we observed (zero events of residue).

## Closed Items (no further research needed)

- **Cycle counter accuracy**: `count_cycle` is the deterministic per-cycle return of `run_extraction()` in `scripts/openclaw/observation/signals/_engine.py`. No proxy or approximation; tested in mission #490.
- **Rolling-window semantics**: `evict_old_buckets` already drops buckets older than `rolling_window_minutes`; `count_rolling` is the sum across remaining buckets. No change needed.
- **State persistence**: `SignalState`'s rolling buckets and cursor fields are unaffected by the trip predicate; the predicate runs after extraction and before filing.

## Decisions

| ID | Decision | Rationale |
|---|---|---|
| D-001 | Add `count_cycle ≥ 1` gate to the rolling branch in `_threshold_status` | Cheapest correct fix; preserves rolling-as-amplifier semantic for active bursts. |
| D-002 | Keep the `tripped_rolling` enum value rather than collapsing into `tripped_cycle` | Allows operators inspecting `last-tick.json` to see which threshold tripped. No structural cost. |
| D-003 | Both `tripped_rolling` and `tripped_both` are gated by the cycle floor | `tripped_both` already implies `cycle_hit`, so it cannot fire with `count_cycle == 0` by construction. No additional logic needed; the existing first-match return chain ensures correctness. |
| D-004 | Land the trip-predicate contract update in mission #490's contract doc (`tick-signal.contract.md`) AND mirror the relevant rules in this mission's `contracts/trip-predicate.contract.md` | The #490 contract is the authoritative pipeline contract; this mission's contract is the durable record of the predicate change. Both update together. |
