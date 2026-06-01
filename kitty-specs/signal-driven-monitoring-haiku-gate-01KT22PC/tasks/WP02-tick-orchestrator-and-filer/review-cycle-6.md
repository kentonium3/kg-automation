---
affected_files: []
cycle_number: 6
mission_slug: signal-driven-monitoring-haiku-gate-01KT22PC
reproduction_command:
reviewed_at: '2026-06-01T19:52:02Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue 1**: `run_cycle(replay_log=..., filing_enabled=True)` can still invoke the live filer without `force_replay_filing=True`.

The cycle-1 fix correctly forces `dry_run=True` when `replay_log` is provided and `force_replay_filing` is false, but it leaves an explicit `filing_enabled=True` override intact. `_process_signal()` gates filing on `filing_enabled`, not `dry_run`, so a direct Python caller can still trigger `file_threshold_trip()` during replay without using the explicit `force_replay_filing` escape hatch. The existing `test_replay_log_with_filing_enabled_does_call_filer` currently demonstrates this unsafe bypass.

Fix: in `run_cycle()`, when `replay_log is not None and not force_replay_filing`, force both `dry_run = True` and `filing_enabled = False` (or otherwise make `filing_enabled=True` invalid unless `force_replay_filing=True`). Update the replay tests so the only live-replay path requires `force_replay_filing=True`; remove or invert the current test that expects `filing_enabled=True` alone to call the filer.

Downstream note: WP03 and WP04 depend on WP02 and should rebase after this fix lands.
