---
affected_files: []
cycle_number: 2
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T05:26:09Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP04
---

# WP04 review cycle 2 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (1 MEDIUM)

Reviewed `da0cfa81`. One deadline gap remains.

Cycle-1 findings:

1. **NOT fully resolved.** Inspections and untagging now recalculate timeouts against the shared deadline. Log capture still permits an additional wait after its deadline; see below.
2. **RESOLVED.** Replay strips private error details, preventing reconciliation failures from creating private logs. Tests now compare filesystem state for failed replay.
3. **RESOLVED.** Tests cover partial starts, teardown failure with a running rejected release, crash/replay boundaries, and realistic cumulative command costs. Cleanup correctly reports a surviving container as `PRESENT`.
4. **RESOLVED.** `stopped` is persisted immediately after successful `down`, before untagging (`scripts/deploy/deploy-vikunja-release-activate.py:519`).

Lock and invariant checks:

- **Apply lock: PASS.** The lock opens relative to the verified activation-root fd with `O_CREAT|O_NOFOLLOW|O_RDWR`, mode `0600`, and exclusive nonblocking `flock`. Acquisition precedes marker reading; release follows cleanup and output. Contention produces `ACTIVATE_LOCK_BUSY` before Docker calls (`:378`, `:441`, `:688`).
- **Name agreement: PASS.** ACTIVATE’s `ACTIVATION_LOCK_NAME` and lane-f’s rollback helper constant both equal `"activation.lock"` (`scripts/vikunja/rollback_release.py:104` in lane-f).
- **Dry-run distinction:** it probes and releases the lock before reading the marker; it does not retain the apply lock.
- **INV-1: PASS.** ACTIVATE only tags `active` to the release digest; cleanup never retags or starts an image.
- **INV-2 and marker order: PASS.** `started → down → stopped → untag → absence checks → snapshot → snapshotted → retagged → started_new → verified`.

New finding:

- **MEDIUM — Log capture can exceed the enclosing outage deadline.** `scripts/deploy/deploy-vikunja-release-activate.py:560` passes the entire remaining outage time to `capture_logs()`. After that deadline expires, `scripts/deploy/vikunja_release/readiness.py:270` calls `_stop()`, whose `:185` independently allows another five-second wait. Cleanup therefore can begin after the promised 300-second boundary. Pass the shared deadline through log capture and reaping, or reserve the reap allowance before capture. Add a hanging-log/reap budget case; the current timing assertions omit the `popen` path.

Validation was read-only inspection plus an in-memory probe confirming the independent five-second reap timeout. The test suite was not run. No files changed; no network, SSH, or Docker calls were made.

**REQUEST CHANGES**

## Orchestrator disposition
Fix inside WP04 only; readiness.py is approved WP02 code. Pass capture_logs timeout = max(0, remaining - READINESS_REAP_ALLOWANCE (5 s) - 1 s margin), and skip capture when that is <= 0. Add a hanging-log plus reap budget test through the popen path, asserting cleanup starts within 300 s.
