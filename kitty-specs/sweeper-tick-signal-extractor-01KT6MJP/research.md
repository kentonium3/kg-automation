# Research: Sweeper tick signal extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP`
**Date**: 2026-06-03

## Open Decisions

### OD-1: Trip semantic — binary or count-based

**Question**: The existing three extractors (creds_restore, watchdog_reconnect, openclaw_unhandled_error) count matching events per cycle and trip when the count meets `cycle_threshold`. The sweeper-tick signal is naturally binary: the latest tick is either OK or NOT OK. Two ways to map this onto the existing trip evaluator:

- A. **Map binary to count**: extractor returns `count_cycle = 1` for "bad" and `0` for "good"; `cycle_threshold = 1` trips when bad.
- B. **Add a new trip evaluator path** for boolean-status signals (a separate code path in `tick.py::_threshold_status`).

**Decision**: A — binary-to-count mapping.

**Rationale**:
- Zero new code in the orchestrator. The quiet-cycle gate from #512 already guarantees `count_cycle = 0` produces `threshold_status = "below"` (no trip). The trip evaluator is unchanged.
- Consistent with the spec lessons learned from #61 (`signal-trip-cycle-floor`): small, targeted predicate changes are preferable to evaluator refactors.
- The rolling-window field stays meaningful — if the sweeper fails repeatedly, `count_rolling` accumulates and the same dedup machinery applies.
- The "binary" framing lives in the extractor's docstring + contract; the host pipeline sees it as just another counting extractor.

### OD-2: Dry-run handling

**Question**: The ledger contains records with `dry_run: true` (developer invocations). A dry-run's `exit_status` and `errors[]` reflect a non-production code path. Two options:

- A. **Skip dry-runs** when locating the "latest" record. Fall back to the most recent `dry_run: false` record.
- B. **Treat dry-runs as authoritative** — if the latest line says `exit_status="vikunja_unreachable"` with `dry_run: true`, file the issue.

**Decision**: A — skip dry-runs; the "latest" semantic operates on production records only.

**Rationale**:
- Dry-runs are diagnostic invocations the operator runs intentionally to inspect behavior without side effects. Production health is what we want to surface; mixing developer signal with production health creates false positives.
- If the operator runs three dry-runs in a row right before the daily cron, option B would suppress real-tick visibility while option A correctly walks back to the most recent natural tick.
- The cost: one extra field check in the iteration. Trivial.

**Edge case**: if EVERY record in the recent window is a dry-run (no production tick ever ran), the extractor correctly trips on the "no-record" path of FR-003 condition (c). This is the desired behavior — no production tick means no production health signal.

### OD-3: Staleness threshold

**Question**: How many hours past the expected fire time before the extractor trips on "timer didn't fire"?

**Decision**: 26 hours.

**Rationale**:
- Sweeper cadence is daily at 07:30 ET (11:30 UTC standard / 12:30 UTC DST). Effective cadence ≤ 24 hours.
- 2-hour slack absorbs: late timer fire (systemd `Persistent=true` plus delayed boot recovery), an in-flight tick still running, time-skew, and clock-adjustment edge cases.
- The threshold lives in the extractor module as a named constant (not in `config.toml`) because it's a property of the sweeper's cadence, not a tunable signal threshold. If the sweeper cadence changes, the constant changes in lockstep with the sweeper.
- If 26 h proves too tight in production, easy follow-up tune.

## Closed Items (no further research needed)

- **Read pattern**: read the tail of the JSONL ledger and walk backward to find the most recent qualifying record. No need to scan the full file.
- **Source kind enum**: `_VALID_SOURCE_KINDS` already exists; add `"sweeper_ledger_jsonl"`. The reserved values `agent_jsonl` and `systemd_journal` could each fit this signal stylistically but neither is in use yet; introducing the more specific name keeps the source-kind taxonomy honest.
- **Replay mode**: out of scope for this mission. The existing `--replay-log` flag patches log-file resolution; extending it to JSONL ledgers is a separable concern. Integration tests cover the production read path via unit tests.

## Decisions

| ID | Decision | Rationale |
|---|---|---|
| D-001 | Binary-to-count mapping (1=bad, 0=good); cycle_threshold=1 | Path A from OD-1 |
| D-002 | Skip `dry_run: true` records when locating "latest" | Path A from OD-2 |
| D-003 | Staleness threshold = 26 hours, as a named constant in the extractor module | Path A from OD-3 |
| D-004 | New `source_kind = "sweeper_ledger_jsonl"` rather than reusing the reserved `agent_jsonl` | Specific name keeps taxonomy honest; the reserved value can land later with its first concrete use |
| D-005 | Single WP for the mission | Cohesive change; six small surfaces; fits within spec-kitty's WP size guideline (~6 subtasks) |
| D-006 | Replay-mode integration deferred | The host pipeline's `--replay-log` flag is log-specific; extending it to JSONL is its own concern, not load-bearing for #510 |
