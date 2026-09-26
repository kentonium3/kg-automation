# Contract: ledger deltas

These are additive to arms-run-01M3APTA `contracts/ledger-schema.md`. Each is dated 2026-09-26 under design-lead rulings.

1. **Outcome `exceeds_memory_ceiling`**: a breach detected at `before_send`. It is terminal for the attempt, not scored, and never included in any average or summary statistic. It carries `memory_ceiling: {measured_gib, ceiling_gib, stage}`. It is never produced for an unreadable sampler; that remains `sampler_unreadable`, with no attempt.
2. **`memory_support`** (G ok rows): exact keys `window_start`, `window_end`, `in_window_readings`, `held_ts`, `peak_source`, `interval_s`, validated on write and replay (data-model.md). A G ok row without valid support is refused.
3. **`falkordb_cgroup_peak_mib`** replaces `falkordb_rss_peak_mib`. The retired name is refused if it appears on any row (rubric §5 @`ea3fbfc8`).
4. **`attempt_start.session_id`** is required. **Dated addition to item 2 (2026-09-26):** the per-session clause, "an attempt is authorised only by its own session's passing gates", becomes enforceable. Replay requires the attempt's `session_id` to equal that of the most recent `session_gates` above it, which must be passing, and must not be skipped unless the header binds `SKIP_GATES_SHA`.
5. **`premise_violated` event**: a ledger containing one is refused as a primary (`require_complete_primary`) and refused by the grading export. Rows are untouched, but they are not usable (correction C).
6. Sampler/series timestamps are accepted only in canonical UTC isoformat (C12).
