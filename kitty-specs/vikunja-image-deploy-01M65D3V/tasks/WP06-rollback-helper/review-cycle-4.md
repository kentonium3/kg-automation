---
affected_files: []
cycle_number: 4
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T05:58:13Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP06
---

# WP06 reopened — gap from WP09 review (Codex gpt-6.1-sol, 2026-10-30, HIGH cutover:589)

An ACTIVATE failure before a snapshot exists (marker failed_phase started or stopped, or any SNAPSHOT_* failure) leaves the service down, active untagged and the DB unmigrated, with no scripted recovery. Rollback requires snapshot.json and STAGE cannot recreate active while a marker exists. Add a guarded --recover-pre-snapshot mode to scripts/vikunja/rollback_release.py: hold deploylock and activation.lock; require marker outcome failed with failed_phase in the pre-retag set and no retag ever recorded; no container; active untagged; take a private copy of the LIVE db plus its wal and shm, and require is_migrated False on it; then tag active to 60fe1ee8, compose up -d, wait_ready v2.4.0, and set marker outcome rolled_back. On any guard failure: no tag, no up. On a post-up failure: the same cleanup as --finish. INV-1 holds because the DB is proven unmigrated.
