---
affected_files: []
cycle_number: 2
mission_slug: signal-driven-monitoring-haiku-gate-01KT22PC
reproduction_command:
reviewed_at: '2026-06-01T19:31:23Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue 1**: `run_cycle(..., replay_log=...)` can still invoke the live filer by default.

The WP T012 requirement says replay mode forces dry-run semantics for filing unless `--no-dry-run-with-replay` is explicitly passed, and T014 says replay validation should call `tick.py` as a Python function so coverage is captured. The CLI path in `main()` sets `dry_run=True`, but the public `run_cycle()` API does not enforce the same default. With `dry_run=False` (the function default), `filing_enabled` becomes `True` at `scripts/openclaw/observation/tick.py:662`, so a replay function call with a tripped threshold invokes `_filer.file_threshold_trip`.

I verified this with a minimal `run_cycle(config_path=..., replay_log=...)` call using a replay log above threshold; it printed `filed=1` and the monkeypatched filer was called once. This is a live-filing footgun for the exact function-level replay surface the WP asks tests to exercise.

Remediation: make `run_cycle()` itself apply replay-safe defaults, not only `main()`. When `replay_log is not None` and `filing_enabled is None`, filing should be disabled by default and the cycle record should show dry-run/replay no-live-filing semantics. Only an explicit escape hatch should enable filing, e.g. `filing_enabled=True` from `--no-dry-run-with-replay`. Add a regression test that calls `run_cycle(replay_log=...)` without passing `dry_run=True` or `filing_enabled=True` and asserts the filer and GH dedup check are not invoked.

Downstream note: WP03 and WP04 depend on WP02, so those agents should rebase after this fix lands.
