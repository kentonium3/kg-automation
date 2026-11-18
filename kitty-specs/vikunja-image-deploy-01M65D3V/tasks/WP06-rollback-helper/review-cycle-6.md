---
affected_files: []
cycle_number: 6
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T06:11:42Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP06
---

# WP06 reopen cycle 2 review — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (1 P1, 1 P2, 1 not resolved)

Reviewed `199efef0`. Two blocking findings remain.

Prior findings:

- **RESOLVED — marker-write failure bypasses cleanup:** both `--finish` and recovery now protect marker persistence. Tests cover failure before replacement.
- **RESOLVED — misleading dry-run eligibility:** output now says `prelim_eligible`, reports DB presence and lock probes, and explicitly marks migration inspection unchecked.
- **NOT RESOLVED — recovery “up failure” coverage:** that test still injects wrong-version readiness rather than a Compose-up failure.

New findings:

- **[P1] Late marker-write failure leaves a false success marker.** [`marker_update()`](/home/kgale/repos/kg-automation-vikunja-deploy/.worktrees/vikunja-image-deploy-01M65D3V-lane-f/scripts/deploy/vikunja_release/core.py:892) replaces the marker before syncing its directory. If that sync fails, the new handlers stop and untag the service, but the marker already says `rolled_back`. Both retry paths then refuse. Cover failure after replacement and ensure the resulting marker permits recovery from the stopped state.

- **[P2] Broken output still prevents cleanup.** The catch-all handlers catch an output failure from `ROLLBACK_STARTED` or `ROLLBACK_READY`, but [`_cleanup_after_start()`](/home/kgale/repos/kg-automation-vikunja-deploy/.worktrees/vikunja-image-deploy-01M65D3V-lane-f/scripts/vikunja/rollback_release.py:655) immediately writes to that same stream before down/untag. A persistent `BrokenPipeError` aborts teardown, leaving the container running and `active` tagged. Make teardown independent of diagnostic writes and add fault coverage. This is a newly identified existing gap.

No `--prepare` regression found. INV-1, migration inspection, locks, and integer marker value remain unchanged.

Read-only review; no tests, network, SSH, Docker, or file edits.

REQUEST CHANGES

## Orchestrator disposition
P1: after a marker_update failure, re-read the marker. If it reads rolled_back, the replace landed and the service is verified running: keep it running, emit MARKER_DURABILITY_UNCERTAIN, exit 1, no teardown. If it reads the previous content, or is unreadable, run cleanup. P2: cleanup runs down and the untag BEFORE any diagnostic write, and every emit or print in cleanup is wrapped so that a write error cannot abort teardown. Add a real compose-up failure test for recover-pre-snapshot.
