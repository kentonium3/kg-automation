---
affected_files: []
cycle_number: 2
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:52:08Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP02
---

# WP02 review cycle 2 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES

Reviewed `5582cf9c`. **REQUEST CHANGES**: readiness still exceeds its deadline; two additional defects remain.

Cycle-1 findings:

1. **NOT RESOLVED — HIGH: readiness deadline.** [readiness.py:95](scripts/deploy/vikunja_release/readiness.py#L95) still uses `HTTPResponse.read(n)`, which can wait for all requested bytes while socket activity keeps resetting the inactivity timeout. Checking between chunks cannot interrupt that read. An in-memory reproduction using a real `HTTPResponse` and buffered trickling input consumed **66 simulated seconds under a 1-second budget**, then returned `READY_TIMEOUT`. Late success is prevented, but the overall deadline remains unenforced. Use deadline-aware reading that bounds each blocking operation.
2. **RESOLVED — unbounded log buffering.** Capture streams through `select` and bounded `os.read`, stops at the byte cap, and kills/reaps the child. The endless-writer test measures bytes actually read and verifies termination, so it addresses the original defect.
3. **RESOLVED within the documented trust boundary — private-root races.** Root validation uses a no-follow directory descriptor and `fstat`; file creation is descriptor-relative and exclusive. SQLite and returned paths retain the explicitly documented pathname risk.
4. **RESOLVED — retained raw hashes.** Raw files remain 0400; checkpointing uses `work/`. The new WAL test checks retained files against recorded hashes and source hashes, while verifying WAL-only rows survive consolidation.

Additional findings:

- **MEDIUM — restrictive umasks break directory initialization and file modes.** [dbsafety.py:193](scripts/deploy/vikunja_release/dbsafety.py#L193), also lines 226, 327 and 488. With umask `0400`, `mkdir(0700)` creates a `0300` directory; an unprivileged process cannot open it with `O_RDONLY` to perform the corrective `fchmod`. SQLite output is likewise reopened before its mode is repaired. Separately, `_write_new_json` never calls `fchmod`, so umask `0277` leaves `snapshot.json` at 0400 rather than 0600. The new umask test exercises only root creation with a mask that preserves owner read permission. Test complete snapshots under restrictive masks as an unprivileged user.

- **LOW — log-file descriptor leaks on permission-setting failure.** [readiness.py:174](scripts/deploy/vikunja_release/readiness.py#L174). If `os.open` succeeds but `os.fchmod` raises, `_new_private_file` never returns the descriptor, so `capture_logs` cannot close it. An in-memory fault injection confirmed that only the root descriptor was closed. Close the newly opened descriptor on initialization failure and add a failure-path assertion.

The readiness tests have meaningful positive controls, but `SlowResp.read` returns after each small fragment. It does not model production buffered reads waiting through many underlying receives, so its elapsed-time assertion misses the remaining HIGH finding.

The log `select` loop has bounded reads and waits; cleanup closes the pipe and attempts bounded kill/reaping. Ordinary snapshot descriptor lifetimes look sound. Partial capture files remain private on failure.

No files changed; no network, SSH or Docker used. Filesystem-writing tests were not run.

**REQUEST CHANGES**

## Orchestrator disposition
HIGH: make each readiness probe a killable subprocess: curl -sS --max-time <t> --max-filesize 65536 -w '
%{http_code}' <url>, run through core.run with timeout=t+2, where t = min(5, deadline.remaining()). The deadline is then hard-enforced by subprocess kill. MEDIUM: entrypoints call os.umask(0o077) first; dbsafety creation helpers temporarily set umask 0o077 around mkdir and open (and restore it), and _write_new_json fchmods 0600; test complete snapshots under umask 0400 and 0277. LOW: close the fd on fchmod failure in _new_private_file and assert it.
