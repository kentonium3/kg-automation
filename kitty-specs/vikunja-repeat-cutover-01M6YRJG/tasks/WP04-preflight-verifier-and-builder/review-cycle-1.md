---
affected_files: []
cycle_number: 1
mission_slug: vikunja-repeat-cutover-01M6YRJG
reproduction_command:
reviewed_at: '2026-11-09T20:53:44Z'
reviewer_agent: claude::reviewer-renata
wp_id: WP04
---

**Issue 1 (MATERIAL): SIGTERM and SIGHUP leave the private database copy behind.**
`scripts/vikunja/preflight_release_baseline.py` handles only KeyboardInterrupt. Python's default action for SIGTERM and SIGHUP ends the process without running `finally`, so a dropped ssh session or a timeout kill leaves private database copies under the failures root, breaking the contract line "Removes its private copy on every exit path".
Fix: at the start of `main`, before any copy, install handlers for SIGTERM and SIGHUP that raise an exception handled by the same cleanup path. Add a subprocess test that sends SIGTERM during the copy and asserts the failures root is empty and the public output is one stable failure code. If the private copy cannot be removed, report a stable non-zero code instead of swallowing the failure.

**Issue 2 (MATERIAL): the verifier can read a stale post-upgrade copy.**
`scripts/vikunja/verify_release_upgrade.py` opens the post-upgrade copy with `immutable=1`, which ignores a `-wal` sidecar. The runbook's B3 stable double copy produces `vikunja.db` plus `vikunja.db-wal`, so on the real path acceptance can read pre-WAL data and give a wrong result.
Fix: when a non-empty `-wal` sidecar sits beside the given post-upgrade copy, consolidate it through the same `dbsafety` route preflight uses into a private temporary directory, verify against the consolidated result, never modify the given copy, and remove the temporary directory on every exit path, including SIGTERM and SIGHUP. Add tests: a copy whose WAL holds a post-checkpoint change is verified from the WAL state, and the given copy's bytes are unchanged.

Reviewed by Claude Sonnet 5.5; issue 2 raised to MATERIAL by Claude Opus 5.5 from the review's EDGE list.
