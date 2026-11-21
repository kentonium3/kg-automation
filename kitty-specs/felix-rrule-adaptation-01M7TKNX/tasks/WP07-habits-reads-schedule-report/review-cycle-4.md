---
affected_files: []
cycle_number: 4
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-21T11:57:46Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP07
---

# WP07 reopened for consolidation (not a code defect)

`spec-kitty consolidate --mission felix-rrule-adaptation-01M7TKNX --yes` (2026-11-21, build 06af0c52e) refused lane-g as stale:
overlapping files tests/habits/test_set_due_dates_reconcile.py, tests/habits/test_sweeper_idempotent.py, tests/habits/test_sweeper_unit.py.
The overlap is with sibling lane-c (WP03). The run rolled back cleanly.

Remedy (upstream spec-kitty/spec-kitty#7754 / #7755, fixed by PR #7780, which prescribes exactly this route):
1. In the lane-g checkout, `git merge kitty/mission-felix-rrule-adaptation-01M7TKNX-lane-c`.
2. Resolve toward WP03's versions, the same resolution already used in the WP08 (lane-h) merge.
3. Run the full suite, then submit for a fresh independent review, re-approve, and re-run consolidate.

No WP07 behaviour changes are expected; the diff is the merge resolution only.
