---
affected_files: []
cycle_number: 5
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T06:06:35Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP06
---

# WP06 reopen review — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (1 P1)

Found one blocking issue.

- **[P1] Marker-write failure bypasses post-up cleanup.** At [rollback_release.py:841](/home/kgale/repos/kg-automation-vikunja-deploy/.worktrees/vikunja-image-deploy-01M65D3V-lane-f/scripts/vikunja/rollback_release.py:841), `marker_update()` runs outside the cleanup-protected `try`. If it raises `MARKER_WRITE_FAILED` after readiness succeeds, recovery reports failure but leaves the container running and `active` tagged; the marker may still say `failed`. This violates the requested cleanup on a post-up failure. Extend cleanup protection through marker persistence and add a fault-injection test asserting logs, down, and untag. `--finish` already has this gap; reusing its structure carries it into recovery.

Other checks:

- **INV-1:** The accepted sets are conservative. ACTIVATE completes `_advance("snapshotted")` before tagging the release. Tag/start failures cannot retain both an accepted `phase` and `failed_phase`; failed phase persistence also refuses conservatively.
- **Migration check:** No concrete false negative found for the stopped, valid SQLite state. Recovery copies DB, WAL, and SHM; inspection uses `mode=ro` without `immutable`, so committed WAL changes remain visible. SQLite errors and missing `tasks` refuse before tag/up.
- **Locks:** Both locks remain held through guards, copying, startup, readiness, marker persistence, and cleanup.
- **Dry-run:** `eligible=1` is only preliminary: it omits migration inspection, DB existence, and lock availability. Report that limitation explicitly in the output; currently a missing DB or held lock can coexist with `eligible=1`.
- **`--prepare` / `--finish`:** No new behavioral regression found in the diff. Argument requirements remain intact, and extracting `_followups()` preserves their behavior.
- **Tests:** The WAL rejection test is non-vacuous: main-file-only inspection returns unmigrated, while recovery with the WAL refuses. Guard tests include positive controls. The “up failure” test actually exercises wrong-version readiness, and marker-write failure is uncovered.
- **Marker value:** `recovered_pre_snapshot: 1` is correct because marker validation rejects booleans.

Review was read-only; no network, SSH, Docker, or filesystem-writing tests were run.

REQUEST CHANGES
