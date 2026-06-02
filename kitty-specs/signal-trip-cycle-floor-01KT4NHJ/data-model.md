# Data Model: Signal trip cycle floor

**Mission**: `signal-trip-cycle-floor-01KT4NHJ`

This mission introduces no new data entities and no schema changes. The only behavioral change is a more restrictive predicate over inputs the pipeline already computes. The "data model" below is the predicate's truth table — every observable outcome under the new semantics.

## Inputs

| Field | Source | Type | Notes |
|---|---|---|---|
| `count_cycle` | `SignalExtraction.count_cycle` from per-signal extractor | int ≥ 0 | Number of matching events in the current 15-min cycle. |
| `count_rolling` | `SignalExtraction.count_rolling` from per-signal extractor | int ≥ 0 | Sum of matching events in the trailing `rolling_window_minutes` (default 60). |
| `cycle_threshold` | `SignalDefinition.cycle_threshold` from `config.toml` | int ≥ 1 | Per-signal trip threshold for the current cycle. |
| `rolling_threshold` | `SignalDefinition.rolling_threshold` from `config.toml` | int ≥ 1 | Per-signal trip threshold for the rolling window. |

## Output

The predicate returns one of four `threshold_status` enum values:

- `below` — no trip; filer not invoked.
- `tripped_cycle` — current cycle alone trips; filer invoked.
- `tripped_rolling` — rolling window alone trips AND current cycle has at least one event; filer invoked.
- `tripped_both` — both branches trip (implies current cycle has ≥1 event); filer invoked.

## Truth table (new semantics)

`cycle_hit` ≜ `count_cycle ≥ cycle_threshold`; `rolling_hit` ≜ `count_rolling ≥ rolling_threshold`; `quiet` ≜ `count_cycle == 0`.

| # | quiet | cycle_hit | rolling_hit | Output |
|---|---|---|---|---|
| 1 | true | false | false | `below` |
| 2 | true | false | true | `below`  ← **NEW behavior** (was `tripped_rolling`) |
| 3 | true | true | * | impossible (`cycle_hit` implies `count_cycle ≥ 1 ≥ cycle_threshold ≥ 1`, contradicts `quiet`) |
| 4 | false | false | false | `below` |
| 5 | false | false | true | `tripped_rolling` |
| 6 | false | true | false | `tripped_cycle` |
| 7 | false | true | true | `tripped_both` |

The only row whose output changes is **#2**. All other rows preserve mission #490's behavior.

## Boundary cases

- `count_cycle = 1, count_rolling = rolling_threshold`: row #5 → `tripped_rolling`. The floor is inclusive at 1.
- `count_cycle = 0, count_rolling = 0`: row #1 → `below`. Trivially correct.
- `count_cycle = 0, count_rolling = huge` (the #502–#504 scenario): row #2 → `below`. Fix verified at this exact boundary.
- `count_cycle = cycle_threshold, count_rolling = 0`: row #6 → `tripped_cycle`. Cycle branch unchanged.
- `count_cycle = cycle_threshold, count_rolling = rolling_threshold`: row #7 → `tripped_both`. Both fire.

## State invariants preserved

- `SignalState.last_cycle_count` is set from `extraction.count_cycle` regardless of trip outcome. Persisted unchanged.
- Rolling-bucket eviction (`evict_old_buckets`) runs before the predicate is evaluated and is independent of trip outcome.
- `last_filed_issue_ref` only updates after a successful filer call; an `below` outcome (including the new "quiet cycle, hot rolling" case) leaves the dedup anchor untouched.

## Cross-references

- Production failure trace (#502/#503/#504): all three filed with `count_cycle=0, count_rolling∈{2794,2506,8685}` — row #2 under old semantics. Under new semantics: `below`, no file.
- Authoritative pipeline contract: [`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md`](../signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md) — code-level edit tracked in this mission's tasks.
