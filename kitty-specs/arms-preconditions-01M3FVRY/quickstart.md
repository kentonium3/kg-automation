# Quickstart — verifying the preconditions

All commands run on office4 from the repo root with `.venv`, with `ARMS849_CACHE=build/849-cache` set.

- **Full suite, both seeds**: run `pytest tests/research/` with `PYTHONHASHSEED=0` and again with `PYTHONHASHSEED=3`. Expect 0 failures. The only skips are the live-stack tests.
- **CI simulation**: `scripts/research/check_849_premerge.py` (IC-05). It creates a detached worktree of HEAD with no `build/`, puts a stub `graphiti_core` on PYTHONPATH, and runs `pytest -q --ignore=docs/archive`. Expect 0 failures and named, counted research skips. The record it writes is cited in the merge to main.
- **Condition A**: the no-arms test in `test_arms849_integration.py`. It is a REGRESSION guard that must stay green; the existing code already refuses a no-arms ledger. C13's red-first evidence is the live-registration test (FR-001).
- **Live smoke (integration verification; NOT the run)**:
  0. At the commit under test: prepare the export and run the host-side preflight (the four `check_849_*` gates plus the preflight record), so no earlier evidence is reused;
  1. `substrate up`, capturing the healthy `up_ts`;
  2. the host gate phase (`--host-gates --up-ts <up_ts>`), then `substrate run -- --smoke --up-ts <up_ts> --ledger <runs>/smoke-<ts>.jsonl`. This runs the container gate phase, then G r1 ×8, then calibration, then D C1 r1, then R C1 r1. The smoke ledger has its own immutable plan identity (see data-model) and can never be a primary;
  3. `ARMS849_LIVE=1 pytest` with the explicit live test node IDs listed in the pre-merge checker (not `-m live`, which selects nothing);
  4. `substrate down`.
  The pre-merge checker requires all of it to have run and passed at the recorded commit.
- **T039 (freeze-time gate, correction D)**: after the final WP, run `run_849_harness --measure` on the final commit. It fails unless the exceedance set equals the registered six, and it is re-run after any post-merge fix. The feat → main merge requires its commit to equal HEAD.
