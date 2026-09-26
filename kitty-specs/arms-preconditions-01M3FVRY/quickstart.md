# Quickstart — verifying the preconditions

All commands run on office4 from the repo root with `.venv`, with `ARMS849_CACHE=build/849-cache` set.

- **Full suite, both seeds**: run `pytest tests/research/` with `PYTHONHASHSEED=0` and again with `PYTHONHASHSEED=3`. Expect 0 failures. The only skips are the live-stack tests.
- **CI simulation**: `scripts/research/check_849_premerge.py` (IC-05). It creates a detached worktree of HEAD with no `build/`, puts a stub `graphiti_core` on PYTHONPATH, and runs `pytest -q --ignore=docs/archive`. Expect 0 failures and named, counted research skips. The record it writes is cited in the merge to main.
- **Condition A**: the no-arms test in `test_arms849_integration.py`. It must fail on the pre-change code.
- **Live smoke (integration verification; NOT the run)**:
  1. `substrate up`;
  2. `substrate run -- --smoke --ledger <runs>/smoke-<ts>.jsonl`, which runs G r1 ×8, then calibration, then D C1 r1, then R C1 r1. The ledger's plan kind is `smoke` and can never be a primary;
  3. `ARMS849_LIVE=1 pytest` with the explicit live test node IDs listed in the pre-merge checker (not `-m live`, which selects nothing);
  4. `substrate down`.
  The pre-merge checker requires all of it to have run and passed at the recorded commit.
- **T039 (freeze-time gate, correction D)**: after the final WP, run `run_849_harness --measure` on the final commit. It fails unless the exceedance set equals the registered six, and it is re-run after any post-merge fix. The feat → main merge requires its commit to equal HEAD.
