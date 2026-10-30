---
affected_files: []
cycle_number: 2
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T05:18:51Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP06
---

# WP06 review cycle 2 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (CRITICAL not resolved)

Reviewed `dd169940`.

- **CRITICAL concurrency — NOT RESOLVED.** Normal execution is serialized, but crashed-owner recovery remains unsafe. At `scripts/vikunja/rollback_release.py:698`, acquiring deploylock does not prove ACTIVATE has stopped: the tick owns the non-inheritable lock descriptor (`scripts/deploy/lib/deploylock.py:92`), while its entrypoint subprocess receives no lock descriptor (`scripts/deploy/lib/apply.py:136`). If the tick dies while ACTIVATE survives, rollback can acquire the lock and pass its guard before activation resumes. Tie exclusion to activation’s lifetime or verify termination before rollback; add a parent-crash interleaving test.
- **HIGH write undercount — RESOLVED.** Shared persisted columns are compared across tables, with the documented migration exclusions. In-memory checks confirmed detection of an unchanged-timestamp title edit and a duplicate relation insertion.
- **HIGH readiness cleanup — RESOLVED.** Failed startup/readiness now captures logs, runs down, untags active, and preserves the marker. Revised tests inspect cleanup and retry without manually clearing Docker state.
- **MEDIUM runbook output — RESOLVED.** Only hard-coded commands are printed after verbatim confirmation; runbook text is never echoed.

Tick verification: `_tick.py:498–499` holds deploylock around `_run_tick_locked`; its synchronous apply call at line 680 spans the entrypoint run during normal execution.

No additional findings. No files changed; no network, SSH, or Docker used. Full pytest was not run because fixtures write files.

**REQUEST CHANGES**

## Orchestrator disposition
Tie the exclusion to activation's own lifetime. ACTIVATE (WP04) opens <activation_root>/activation.lock (O_CREAT|O_NOFOLLOW, 0600, relative to the verified activation-root fd) and takes a non-blocking exclusive flock before the marker is created, holding it until it exits; if the lock is held it refuses with ACTIVATE_LOCK_BUSY before any Docker call. Rollback (WP06) takes the same lock, as well as deploylock, for the whole of --prepare and --finish; ROLLBACK_ACTIVATION_RUNNING if held. Because flock is held by the ACTIVATE process itself, an orphaned ACTIVATE still excludes rollback, and a crashed one releases it. Add the parent-crash interleaving test: a separate process holds activation.lock, deploylock is free, and rollback must refuse.
