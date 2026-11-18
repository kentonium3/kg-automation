---
affected_files: []
cycle_number: 1
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T05:11:07Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP06
---

# WP06 review cycle 1 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (1 CRITICAL, 2 HIGH, 1 MEDIUM)

Reviewed commit `905af777`. Findings:

- **CRITICAL — `scripts/vikunja/rollback_release.py:213`: Concurrent activation can defeat INV-1.** The marker gate accepts an unfinished marker without establishing that its activation has stopped. That activation can resume after the rollback guard passes, migrate the restored DB, and then race with rollback’s tag/up at lines 462–466. Serialize activation and rollback across the critical section, with explicit recovery for crashed owners. Add an interleaving test.

- **HIGH — `scripts/vikunja/rollback_release.py:294`: The write count can undercount.** Existing tasks are counted only when `updated` differs. Changed payloads with unchanged timestamps, and task-related writes such as comments, can be lost while acknowledging zero. An in-memory check using the implementation’s SQL returned `[0, 0, 0]` for a changed title. Compare relevant persisted data conservatively or refuse when completeness cannot be established.

- **HIGH — `scripts/vikunja/rollback_release.py:474`: Readiness failure omits required cleanup.** R-14 requires private log capture followed by shutdown; this handler captures logs and raises, leaving the container and `active` tag present. Subsequent `--finish` fails its guard. The test at `tests/deploy/test_vikunja_rollback.py:633` manually clears both, masking the missing recovery behavior. Implement cleanup and test the resulting state and retry.

- **MEDIUM — `scripts/vikunja/rollback_release.py:439`: Runbook output is character-filtered, not semantically allowlisted.** The regex accepts arbitrary secret-bearing commands, including `ssh office2-claude 'echo password=hunter2'`. Lines are then printed directly. Restrict output to approved command templates. The prefix assertions at `tests/deploy/test_vikunja_rollback.py:714` do not establish privacy.

The sequential guard ordering is correct: no rollback tag or up occurs before it passes. Completed double-prepare is refused; the restore template matches the required command and validates substituted paths; no execution path invokes sudo. Private imports resolve to the approved primitives, though they introduce coupling.

No files changed. Full pytest was not run because its fixtures write files; tests were inspected and the two checks above ran entirely in memory.

**REQUEST CHANGES**

## Orchestrator disposition
CRITICAL: hold scripts/deploy/lib/deploylock.deploylock() (the felix-deployer checkout lock, which the tick holds while ACTIVATE runs) for the whole of each --prepare and --finish; LockUnavailable gives ROLLBACK_DEPLOYER_BUSY with no Docker call. HIGH count: a conservative diff across every table present in both DBs, on their shared columns, keyed by primary key (or the full row when there is no id); exclude only migration-owned tables; over-counting is acceptable. HIGH readiness: on a failure after up, capture logs, compose down, untag active, record the code privately; a retry then requires re-running Kent's restore (the guard's sha check enforces that). MEDIUM: print only hard-coded command templates, after verifying the runbook still contains them, otherwise a pointer line.
