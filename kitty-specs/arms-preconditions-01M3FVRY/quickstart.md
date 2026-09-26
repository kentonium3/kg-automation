# Quickstart — verifying the preconditions

All commands run on office4 from the repo root with `.venv`, with `ARMS849_CACHE=build/849-cache` set.

- **Full suite, both seeds**: run `pytest tests/research/` with `PYTHONHASHSEED=0` and again with `PYTHONHASHSEED=3`. Expect 0 failures. The only skips are the live-stack tests.
- **CI simulation**: `scripts/research/check_849_premerge.py` (IC-05). It creates a detached worktree of HEAD with no `build/`, puts a stub `graphiti_core` on PYTHONPATH, and runs `pytest -q --ignore=docs/archive`. Expect 0 failures and named, counted research skips. The record it writes is cited in the merge to main.
- **Condition A**: the no-arms test in `test_arms849_integration.py`. It must fail on the pre-change code.
- **Live smoke (integration verification; NOT the run)**:
  1. `substrate up`;
  2. a harness run on a throwaway ledger with `--limit 3`, one cell per arm;
  3. `ARMS849_LIVE=1 pytest -m live tests/research/`;
  4. `substrate down`.
  Record the results in the pre-merge record.
- **T039 (freeze-time, correction D)**: after the final WP, run `run_849_harness --measure` on the final commit. Hand the §2 table, citing the commit and `preflight_sha`, to the design lead as a dated amendment.
