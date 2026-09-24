# Contract: ledger schema and invariants

See data-model.md §Ledger for fields. Enforced by `run_849_harness`:

1. Header first, once; every later line `record: "run"`.
2. `open_ledger(path, corpus_dir, serving, prompt_hash)`: on first use writes the Header; on
   resume compares `corpus`, `prompt_hash`, `serving` (all fields) against the environment and
   refuses on any difference (`LedgerBoundToAnotherCorpus` / `LedgerBoundToAnotherConfig`).
3. Lock: `path + ".lock"`, `fcntl.flock` exclusive, held for the session; a second opener is
   refused with the holder's pid.
4. Append: `json.dumps(row, sort_keys=True, default=str)` + `\n`, flush, `os.fsync`.
5. `summarise(rows)`: per (arm, question) over `ok` rows only: `n_scored`, mean/range of
   `assembled_context_tokens`, mean/range of `prompt_tokens`, cache split sums, cold (repeat 1)
   vs warm (repeats 2–3) prefill; counts of every other outcome. Never averages a non-`ok` row.
6. `grading_view(rows, seed)` and `seal(rows, seed)` per data-model.md.
7. A secondary ledger is a different file with a different `serving`; `--secondary` refuses
   unless the primary ledger at the given path is complete (72 cells, no `not_implemented`).
