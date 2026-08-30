# Decision Moment `01M189SZZA92JDKH86N3CDCQRN`

- **Mission:** `pointer-key-ledger-01M189P6`
- **Origin flow:** `specify`
- **Slot key:** `specify.ledger.office2-adjudication-depth`
- **Input key:** `office2_adjudication_depth`
- **Status:** `resolved`
- **Created:** `2026-08-30T03:01:01.546406+00:00`
- **Resolved:** `2026-08-30T03:02:22.420437+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

For office2's ledger, how many of the v0.2 adjudication rules are adopted now: only integrity_check_passed (rest diagnostic_only), also the rules office2's already-emitted fields can support (snapshot_count wipe-detection, future-dated timestamp guard), or also add the fields office2 does not yet emit (files_processed, source_roots_present, repo_fs_free_bytes) for full parity?

## Options

- minimum-integrity-only
- adopt-rules-on-existing-fields
- full-parity-add-new-fields
- Other

## Final answer

adopt-rules-on-existing-fields: declare all 10 emitted keys; adjudicate integrity_check_passed (true|null good, false unhealthy), snapshot_count (>1 on an established repo, catching a wiped-and-reinitialised repo), and add a future-dating guard to the existing snapshot_timestamp_utc freshness rule; restic_exit_code {0,3} and prune_exit_code {0} keep their current good-sets. schema_version, snapshot_id, repo_size_bytes, script_finished_at_utc and integrity_check_run are declared diagnostic_only. NO change to scripts/office2/restic-backup.sh - every rule reads a field the producer already emits, so no Tier-2 producer deploy. Adding files_processed / source_roots_present / repo_fs_free_bytes to office2 is explicitly out of scope for this mission.

## Rationale

_(none)_

## Change log

- `2026-08-30T03:01:01.546406+00:00` — opened
- `2026-08-30T03:02:22.420437+00:00` — resolved (final_answer="adopt-rules-on-existing-fields: declare all 10 emitted keys; adjudicate integrity_check_passed (true|null good, false unhealthy), snapshot_count (>1 on an established repo, catching a wiped-and-reinitialised repo), and add a future-dating guard to the existing snapshot_timestamp_utc freshness rule; restic_exit_code {0,3} and prune_exit_code {0} keep their current good-sets. schema_version, snapshot_id, repo_size_bytes, script_finished_at_utc and integrity_check_run are declared diagnostic_only. NO change to scripts/office2/restic-backup.sh - every rule reads a field the producer already emits, so no Tier-2 producer deploy. Adding files_processed / source_roots_present / repo_fs_free_bytes to office2 is explicitly out of scope for this mission.")
