# Data Model: Sweeper tick signal extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP`

No new persistent state. The extractor reads an existing artifact and emits the same `SignalExtraction` dataclass the other three extractors use. The "data model" below is the input record shape and the trip truth table.

## Input: sweeper ledger record

Per `kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md`. Verified against live records on office2 on 2026-06-03.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Ledger schema version. Currently 1. |
| `tick_id` | str (ULID) | Unique per tick. Matches the corresponding `sweeper-tick-<date>.json`. |
| `started_at_utc` | str (ISO 8601, UTC, trailing Z) | Tick start. The extractor's staleness check is `now_utc - started_at_utc > 26 hours`. |
| `duration_ms` | int | Tick duration. Not consumed by the extractor. |
| `dry_run` | bool | True for developer invocations. The extractor SKIPS dry-run records when locating "latest." |
| `expired_checkin_dates_evaluated` | list[str] | Not consumed. |
| `habits_evaluated` | list[dict] | Not consumed. |
| `habits_auto_skipped` | list[dict] | Not consumed. |
| `errors` | list[dict] | The extractor trips when this is non-empty even if `exit_status == "success"`. |
| `exit_status` | str enum | The extractor trips when this is anything other than `"success"`. |

The extractor depends only on `started_at_utc`, `dry_run`, `errors`, and `exit_status`. All other fields are tolerated and ignored.

## Output: `SignalExtraction`

Same `dataclass` produced by the existing extractors. Fields:

- `signal_id`: `"sweeper_tick"`
- `count_cycle`: `0` (passing) or `1` (failing). Binary semantic per OD-1.
- `count_rolling`: `prior_rolling_count + count_cycle`. Inherited from the host pipeline pattern.
- `excerpts`: zero or one JSON-stringified line describing the failure. Empty list when `count_cycle == 0`.
- `last_event_at_utc`: the `started_at_utc` of the qualifying record (or `None` when the no-record path tripped).
- `new_cursor`: `None`. The extractor does not maintain a cursor — it always reads the tail of the ledger.

## Trip truth table

`now_utc` = the cycle's now-UTC. `latest_prod` = the most recent ledger record with `dry_run == false`, if any. `age_h` = `(now_utc - latest_prod.started_at_utc).total_seconds() / 3600`.

| # | Scenario | latest_prod | age_h | exit_status | errors | Output |
|---|---|---|---|---|---|---|
| 1 | Successful recent tick | present | <26 | `"success"` | `[]` | `count_cycle = 0` |
| 2 | Failed recent tick | present | <26 | `"vikunja_unreachable"` (or any non-success) | any | `count_cycle = 1` (failed exit_status) |
| 3 | Successful recent tick with per-habit errors | present | <26 | `"success"` | non-empty | `count_cycle = 1` (errors non-empty) |
| 4 | Stale recent tick | present | ≥26 | any | any | `count_cycle = 1` (stale started_at_utc) |
| 5 | Ledger has only dry-run records | absent (no prod record) | n/a | n/a | n/a | `count_cycle = 1` (no production record) |
| 6 | Ledger is empty | absent | n/a | n/a | n/a | `count_cycle = 1` (no production record) |
| 7 | Ledger file missing | absent | n/a | n/a | n/a | `count_cycle = 1` (no production record) |
| 8 | Trailing partial line; second-to-last is fresh success | present (second-to-last) | <26 | `"success"` | `[]` | `count_cycle = 0` (partial line tolerated) |

Rows 4–7 collapse into the same "stale or absent production record" trip reason. The excerpt text distinguishes them for operator triage.

## Excerpt content

When `count_cycle == 1`:

- **Row 2 (failed exit)**: the redacted ledger record as JSON.
- **Row 3 (errors non-empty)**: the redacted ledger record as JSON.
- **Row 4 (stale)**: a synthetic JSON object `{"reason": "stale_production_record", "latest_tick_started_at_utc": "...", "age_hours": <int>, "threshold_hours": 26}`.
- **Rows 5–7 (no production record)**: a synthetic JSON object `{"reason": "no_production_record", "ledger_path": "...", "ledger_exists": <bool>, "ledger_record_count": <int>, "dry_run_only_count": <int>}`.

The redaction policy from `_engine.redact_dict` applies uniformly (per FR-005).

## Invariants

- **I-1 (purity)**: the extractor MUST be a pure function of `(ledger_contents, now_utc, signal_def)`. No filesystem writes, no network calls, no environment reads beyond what's plumbed through arguments.
- **I-2 (now_utc source)**: the extractor MUST source `now_utc` from the cycle's `now_utc` parameter. No `datetime.now()` calls.
- **I-3 (output structure invariance)**: the `SignalExtraction` dataclass shape is unchanged. `signal_id` is `"sweeper_tick"`.

## State files untouched

- The sweeper ledger at `/data/services/openclaw/state/habits/sweeper-ledger.jsonl` is read-only from this extractor's perspective.
- Per-date artifacts at `/data/services/openclaw/state/habits/sweeper-tick-<date>.json` are NOT read by this extractor — the ledger is the source of truth for tick history.

## Cross-references

- Host pipeline contract: [`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md`](../signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md)
- Sweeper tick contract: [`kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md`](../habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md)
- This mission's extractor contract: [`contracts/sweeper-tick-extractor.contract.md`](contracts/sweeper-tick-extractor.contract.md)
