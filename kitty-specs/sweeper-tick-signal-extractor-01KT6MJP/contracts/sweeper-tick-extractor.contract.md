# Contract: sweeper_tick extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP`
**Host pipeline contract**: [`kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md`](../../signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md)
**Source artifact contract**: [`kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md`](../../habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md)

The sweeper-tick extractor adheres to the same `extract(state_dir, signal_def, now_utc, prior_cursor, prior_rolling_count) -> SignalExtraction` signature the other three extractors in `scripts/openclaw/observation/signals/` expose. This contract describes its semantics; the host pipeline contract is the authoritative cross-extractor contract for the `SignalExtraction` envelope.

## Inputs

| Arg | Type | Used |
|---|---|---|
| `state_dir` | `Path` | Ignored. The extractor maintains no per-signal state. |
| `signal_def` | `SignalDefinition` | `signal_def.source_path_pattern` provides the ledger path; `signal_def.excerpt_lines` caps excerpts at 1 (per config). |
| `now_utc` | `datetime` (tz-aware UTC) | Used for the staleness comparison. Sourced from the cycle. |
| `prior_cursor` | `Optional[LogCursor]` | Ignored. The extractor reads the ledger tail every cycle. |
| `prior_rolling_count` | `int` | Added to `count_cycle` to produce `count_rolling`, per the host pipeline pattern. |

## Output

A `SignalExtraction` dataclass:

```text
SignalExtraction(
    signal_id="sweeper_tick",
    count_cycle = 0 or 1,                       # binary, per OD-1
    count_rolling = prior_rolling_count + count_cycle,
    excerpts = [json_str] when count_cycle==1 else [],
    last_event_at_utc = latest_prod.started_at_utc or None,
    new_cursor = None,                           # extractor is cursorless
)
```

## Predicate

```text
STALE_THRESHOLD_HOURS = 26

Resolve ledger_path from signal_def.source_path_pattern.
If ledger_path does not exist OR is unreadable OR has zero parseable records:
    return TRIP("no_production_record")

Read the ledger from the tail. Walk lines in reverse (newest first).
Parse each line as JSON; tolerate JSONDecodeError and skip silently
(captures the "trailing partial line" case in the truth table).

For each parsed record in reverse order:
    If record["dry_run"] is true: continue
    # First non-dry-run record found — this is `latest_prod`.
    age_h = (now_utc - parse_iso8601(record["started_at_utc"])) / 1 hour
    if age_h >= STALE_THRESHOLD_HOURS:
        return TRIP("stale_production_record", record, age_h)
    if record["exit_status"] != "success":
        return TRIP("failed_exit_status", record)
    if record["errors"] (list) is non-empty:
        return TRIP("errors_non_empty", record)
    # All three conditions passed.
    return PASS(last_event_at_utc = record["started_at_utc"])

# Reached only if every parsed record was a dry-run.
return TRIP("no_production_record")
```

`TRIP(reason, record=None, age_h=None)` builds the appropriate excerpt per the data-model § "Excerpt content" table and returns `count_cycle=1`. `PASS(last_event_at_utc)` returns `count_cycle=0` with an empty excerpt list.

## Invariants

- **I-1 (purity)**: pure function of `(ledger file contents, now_utc, signal_def)`. No filesystem writes, no network calls. Already enforced by the host pipeline's calling pattern; this extractor introduces no new I/O channels.
- **I-2 (no-clock-call)**: the extractor MUST NOT call `datetime.now()`. The cycle's `now_utc` is the sole clock source.
- **I-3 (tail-read)**: the extractor MUST read the ledger from the tail and walk newest-first. Implementations that scan the full file from byte 0 every cycle still produce correct outputs but violate the NFR-001 performance budget.
- **I-4 (binary mapping)**: `count_cycle` is `0` or `1`. Never any other value.

## Test obligations

The implementing test suite (`scripts/openclaw/observation/tests/test_signals_sweeper_tick.py`) MUST cover the eight named cases from the data-model truth table:

| Case | Setup | Expected |
|---|---|---|
| `success_recent` | one record: dry_run=false, exit_status="success", errors=[], started_at_utc=now-1h | count_cycle=0; excerpts=[]; last_event_at_utc=started_at_utc |
| `failed_exit` | one record: dry_run=false, exit_status="vikunja_unreachable", errors=[], started_at_utc=now-1h | count_cycle=1; excerpt is the record JSON |
| `errors_non_empty` | one record: dry_run=false, exit_status="success", errors=[{...}], started_at_utc=now-1h | count_cycle=1; excerpt is the record JSON |
| `stale_recent` | one record: dry_run=false, exit_status="success", errors=[], started_at_utc=now-27h | count_cycle=1; excerpt is synthetic stale-reason JSON |
| `dry_run_only` | three records, all dry_run=true | count_cycle=1; excerpt is synthetic no-prod-record JSON |
| `empty_ledger` | ledger file exists but empty | count_cycle=1; excerpt is synthetic no-prod-record JSON |
| `missing_ledger` | ledger file does not exist | count_cycle=1; excerpt is synthetic no-prod-record JSON |
| `partial_line_tolerated` | two records; last line is truncated JSON; second-to-last is success_recent | count_cycle=0; the partial line is ignored |

Each case asserts `count_cycle`, the structural shape of `excerpts`, and the presence/absence of `last_event_at_utc`.

## Out of scope for this contract

- The `SignalState` schema (owned by mission #490's `tick-signal.contract.md`; unchanged).
- The trip evaluator predicate (owned by mission #61's `trip-predicate.contract.md`; unchanged).
- Replay-mode integration (the existing `--replay-log` flag targets `openclaw_log` source kinds; extending replay to JSONL ledgers is a separable concern, not load-bearing for this mission).
- Per-error-category breakdown (e.g., separate signals for `vikunja_unreachable` vs `malformed_schedule_yaml`). One coarse-grained signal until operational experience says otherwise.
