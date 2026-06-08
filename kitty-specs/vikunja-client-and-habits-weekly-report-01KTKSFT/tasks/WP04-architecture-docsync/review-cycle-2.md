---
affected_files: []
cycle_number: 2
mission_slug: vikunja-client-and-habits-weekly-report-01KTKSFT
reproduction_command:
reviewed_at: '2026-06-08T17:55:11Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP04
---

**Issue 1**: Weekly-report schedule documentation is internally contradictory.

`docs/design/architecture/data/service-inventory.json` records the `habits-weekly-report` cron as `0 22 * * 0` but sets `local_time` to `Sunday 6:00 PM ET`. `docs/design/architecture/service-inventory.md` repeats the same contradiction in the scheduled-jobs row and the Felix Admin Habits schedule line: `Sunday 6PM ET` / `Sunday 6 PM ET` alongside `cron 0 22 * * 0 America/New_York`.

Per WP04 T018/T019 and FR-014, the weekly report cadence is `0 22 * * 0` in `America/New_York`, i.e. Sunday 10:00 PM ET. Update the JSON and markdown schedule text so every surface agrees on Sunday 10:00 PM ET / Sunday 22:00 America/New_York.

Anti-pattern checklist:

1. Dead code: N/A — doc-only WP, no new public functions/classes/modules.
2. Synthetic-fixture test: N/A — no tests modified by this WP.
3. Silent empty return: N/A — doc-only WP, no new code paths.
4. FR coverage: FAIL — FR-014 schedule documentation is inconsistent with the verified cron cadence.
5. Frozen surface: PASS — no frozen/untouchable source files identified in the WP prompt were modified.
6. Locked decision: PASS — no new code path contradicts a MUST NOT clause.
7. Shared-file ownership: PASS — WP04 commit touched only its documentation surfaces.
8. Production fragility: N/A — no new production raises.

Independent verification already passed: JSON parse checks for service inventory / signal map / data flows, `python3 tooling/scripts/validate_docs.py`, and no `scripts/` or `tests/` changes in WP04's implementation commit.
