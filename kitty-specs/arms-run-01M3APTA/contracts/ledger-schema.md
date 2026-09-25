# Contract: ledger schema and invariants

Fields: data-model.md §Ledger. Enforced by `run_849_harness`:

1. Header first, once, immutable. Record kinds after it: `attempt_start`, `run`, `calibration`, `event`.
2. `open_ledger(...)` on first use writes the Header; on resume compares corpus fingerprints,
   prompt digest, question-manifest digest, serving configuration (every field), code hashes,
   export content-manifest sha and preflight sha — refuses on any difference (D-16).
3. Lock: `path + ".lock"`, `fcntl.flock` exclusive, held for the session; a second opener is
   refused with the holder's pid (NFR-007).
4. Append: one JSON line, flush, `os.fsync`. Reader under the lock tolerates exactly one torn
   **final** line (truncates it, logs `recovered_torn_tail`), rejects any interior malformed line
   as corruption (D-12).
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
