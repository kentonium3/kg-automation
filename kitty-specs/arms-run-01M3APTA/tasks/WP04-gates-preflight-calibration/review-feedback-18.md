# WP04 reopen review — cycle 17 (lane-d @11d9bffc): REJECT

Reviewer: Codex gpt-6-astra (OpenAI), read-only, 2026-09-26. Implementer: Claude Opus 5.5. Codex ran the 31 new tests and all passed. Its full-suite run showed 204 failures from sandbox-denied socket creation; the orchestrator's runs pass 848 under both seeds. The cross-lane merge into lane-h passed 1035.

Codex confirmed:
- the header, interval, and header/record identity checks;
- freshness and gaps, where exactly 5 s passes and 5 s + 1 µs fails, and a gap from the held reading into the window counts;
- header-first flushing, and a failed read omitting its line;
- UTC normalisation;
- require_breached;
- RssSampler and GttSampler are source-identical.

## Codex finding 1 (sample-and-hold imports pre-window memory): OVERRULED BY DESIGN-LEAD RULING, not folded
Design lead, bus 20260926T022404602680Ze1ac0a34c8, registered in rubric §5 on main @5665aa94 ("Window reconstruction, added 2026-09-26 02:25Z"):
- SAMPLE-AND-HOLD is the registered rule. The alternative would refuse cells for a sampling artifact.
- Its over-attribution inflates G's cost, so it runs against the hypothesis.

The ruling carries two RIDERS, and both are REQUIRED in this cycle:
- **R1 — freshness at both ends.** The held pre-window reading may be no more than GAP_INTERVALS × interval before the window start. Beyond that it is a gap, and the sampler fails closed. Verify this against the existing held-to-window gap check, and pin it with an explicit boundary test: exactly 5 intervals is allowed, and 5 + ε is refused.
- **R2 — support recorded.** The sample detail records the number of IN-WINDOW samples, the window bounds, and whether the reported peak came from the HELD pre-window reading or from a sample inside the window, e.g. `peak_source: "held" | "in_window"`. This goes in the detail, with no new ledger column.

## Required fixes (Codex findings 2–5, genuine defects)
2. **[MAJOR] Equal timestamps at the window start.** `held[-1:]` keeps only the last record at or before the start. With `(0s,999), (0s,10), (1s,20)` and window `[0s,1s]`, the peak comes out 20. Every record whose ts equals the window start is a reading within the window, so include them all. More generally, never drop a record that ties the boundary.
3. **[MAJOR] Writer samples by mutable NAME.** The writer resolves the container id once but keeps sampling the mutable name. A replacement container B's 999 MiB was recorded under A's id, and the reader accepted it. Bind the default docker read to the resolved IMMUTABLE container id.
4. **[MAJOR] Unconverted failures escape the reader.** Invalid UTF-8 raises UnicodeDecodeError, and `10**400` raises OverflowError during record validation. Both escape the context manager. Translate every decode, number, and timestamp conversion failure into the fail-closed unreadable path: None plus a reason, never an exception.
5. **[MAJOR] Inverted window accepted.** Entering at 1s and exiting at 0s, for example after a backward clock step, returns a numeric peak. Reject `end < start` as unreadable, with a reason.

Each fix needs a can-fail regression test.
