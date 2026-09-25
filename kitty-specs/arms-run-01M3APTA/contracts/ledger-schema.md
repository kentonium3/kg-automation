# Contract: ledger schema and invariants

Fields: data-model.md §Ledger. Enforced by `run_849_harness`:

1. Header first, once, immutable. Record kinds after it: `attempt_start`, `run`, `calibration`, `event`.
2. `open_ledger(...)` on first use writes the Header; on resume compares corpus fingerprints,
   prompt digest, question-manifest digest, serving configuration (every field), code hashes,
   export content-manifest sha and preflight sha — refuses on any difference (D-16).
   **Dated addition 2026-09-25 (design-lead ruling, bus msg 20260925T184915053450Z261fc226da, landed
   with the WP03 cycle-14 fold @0b56fdc6):** resume compares the header AND re-validates every
   persisted row, in file order, through the same invariants `record()` / `begin_attempt()` /
   `write_calibration()` enforce on a live write (outcome vocabulary, attempt sequencing, one scored
   row per key, R `ok` requires the calibration record, D limit coherent with the header, mandatory
   telemetry, serving identity; key and attempt fields by TYPE, never coerced). Any violation is
   `LedgerCorrupt` with the file untouched; repair never runs on a file that fails validation.
3. Lock: `path + ".lock"`, `fcntl.flock` exclusive, held for the session; a second opener is
   refused with the holder's pid (NFR-007).
4. Append: one JSON line, flush, `os.fsync`. Reader under the lock tolerates exactly one torn
   **final** line (truncates it, logs `recovered_torn_tail`), rejects any interior malformed line
   as corruption (D-12). **Dated addition 2026-09-25 (same ruling):** exactly one torn final line is
   tolerated, and "torn" means the bytes do not parse as JSON. A final line that parses to anything
   other than an object (e.g. `null`) is corruption, never truncated away.
5. Attempts: an `attempt_start` row precedes every attempt; attempts for a key = count of
   `attempt_start` rows; at 3 with no `ok`, the key is terminal `error` (FR-007, D-12).
6. Calibration: exactly one `calibration` record, written only when all eight G repeat-1 cells
   are `ok`; if any is terminal `error`, the run halts (`event: halt,
   calibration_population_incomplete`) and posts `blocked` (D-10). Every R cell requires it.
7. `summarise(rows)`: per (arm, question) over `ok` rows only — n_scored, mean/range of
   assembled and prompt tokens, cache split sums, cold vs warm by **observed** `cache_state`,
   r_g_ratio — plus counts of every other outcome. Never averages a non-`ok` row.
8. Exports per contracts/grading-view.md. `--secondary` refuses unless the named primary ledger
   is complete (72 cells, zero `not_implemented`) and its own context gate has passed.
9. **Append failure (dated addition 2026-09-25, same ruling — the design lead's "item 5"):** any
   `OSError` in append (write, flush, fsync) poisons the writer: `LedgerWriteFailed`, every further
   write refused, the lock released; reopen re-reads the file. A row that reached disk before the
   failure is visible on reopen and a retry of the same scored key is refused as `SecondScoredRow`.
