# Contract: trip-predicate (cycle-floor amendment)

**Mission**: `signal-trip-cycle-floor-01KT4NHJ`
**Authoritative pipeline contract**: [`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md`](../../signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md)

This contract amends mission #490's trip-predicate semantics with a quiet-cycle gate. The host pipeline contract in mission #490 is updated in lockstep with the code change; this document is the durable record of the predicate change.

## Predicate

Given a per-signal `SignalExtraction` (containing `count_cycle` and `count_rolling`) and the corresponding `SignalDefinition` (`cycle_threshold`, `rolling_threshold`), the trip-evaluator function MUST return exactly one of:

- `tripped_both`  — when `count_cycle ≥ cycle_threshold` AND `count_rolling ≥ rolling_threshold`
- `tripped_cycle` — when `count_cycle ≥ cycle_threshold` AND `count_rolling < rolling_threshold`
- `tripped_rolling` — when `count_cycle ≥ 1` AND `count_cycle < cycle_threshold` AND `count_rolling ≥ rolling_threshold`
- `below` — in every other case (notably: `count_cycle == 0`, regardless of `count_rolling`)

## Invariants

- **I-1 (quiet-cycle gate)**: `count_cycle == 0` MUST always yield `below`. This is the core invariant introduced by this mission.
- **I-2 (cycle-branch unchanged)**: any return of `tripped_cycle` or `tripped_both` under the new semantics MUST have also been the return under mission #490's original semantics (the cycle branch is strictly preserved).
- **I-3 (rolling branch tightened)**: the only difference vs mission #490 is row #2 in the truth table — `count_cycle == 0, count_rolling ≥ rolling_threshold` returns `below` instead of `tripped_rolling`.
- **I-4 (no side effects)**: the predicate is pure — it MUST NOT read or write `SignalState`, the cursor, the ledger, `last-tick.json`, or any external resource.

## Pseudocode (normative)

```
function trip_status(count_cycle, count_rolling, cycle_threshold, rolling_threshold):
    cycle_hit   = count_cycle   >= cycle_threshold
    rolling_hit = count_rolling >= rolling_threshold
    if cycle_hit and rolling_hit:
        return "tripped_both"
    if cycle_hit:
        return "tripped_cycle"
    if rolling_hit and count_cycle >= 1:
        return "tripped_rolling"
    return "below"
```

## Test obligations

The implementing test suite MUST cover, at minimum, these named cases:

| Case | Inputs (cycle, rolling, c_thr, r_thr) | Expected |
|---|---|---|
| `quiet_below`           | (0, 0, 5, 15)      | `below` |
| `quiet_hot_rolling`     | (0, 999, 5, 15)    | `below` ← key regression guard |
| `one_event_below`       | (1, 0, 5, 15)      | `below` |
| `one_event_rolling_hit` | (1, 15, 5, 15)     | `tripped_rolling` |
| `cycle_only`            | (5, 0, 5, 15)      | `tripped_cycle` |
| `cycle_just_above`      | (6, 14, 5, 15)     | `tripped_cycle` |
| `both`                  | (5, 15, 5, 15)     | `tripped_both` |
| `huge_both`             | (100, 1000, 5, 15) | `tripped_both` |

The boundary `quiet_hot_rolling` MUST exercise values comparable to the production trace (≥1000 rolling, 0 cycle) and assert `below`.

## Out of scope for this contract

- Threshold value selection (`cycle_threshold`, `rolling_threshold`) — owned by `config.toml`.
- Source resolution, cursor handling, multi-file iteration — owned by `_engine.py` and unchanged.
- State persistence, rolling-bucket eviction, dedup, filing — owned by `tick.py`'s downstream functions and unchanged.
