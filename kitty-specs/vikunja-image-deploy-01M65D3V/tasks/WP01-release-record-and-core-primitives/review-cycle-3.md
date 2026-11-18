---
affected_files: []
cycle_number: 3
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:19:57Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP01
---

# WP01 review cycle 3 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (1 MEDIUM)

Reviewed `52ddfd39` read-only. One new **MEDIUM** finding remains.

Cycle-2 findings:

1. **RESOLVED — Pre-scan/parser boundary disagreement.** The custom pre-scan is removed.
2. **RESOLVED — Solaris PAX bypass.** The extension-limit mechanism and its tests are removed.
3. **RESOLVED — Base-256 overflow.** The custom decoder is removed; tar-parser `OverflowError` maps to `ARCHIVE_UNREADABLE`.
4. **RESOLVED — Nested malformed markers.** Decoder `RecursionError` and `MemoryError` map to `MARKER_UNREADABLE`. The recursion test uses an input below 64 KiB and includes a valid-marker control.

New finding:

- **MEDIUM — Hashing and parsing reopen the pathname, so they need not consume the same bytes.** [core.py:600](/home/kgale/repos/kg-automation-vikunja-deploy/.worktrees/vikunja-image-deploy-01M65D3V-lane-a/scripts/deploy/vikunja_release/core.py:600) hashes and closes one file; [core.py:675](/home/kgale/repos/kg-automation-vikunja-deploy/.worktrees/vikunja-image-deploy-01M65D3V-lane-a/scripts/deploy/vikunja_release/core.py:675) reopens the path. Concurrent replacement after hashing lets `tarfile` parse unpinned bytes without changing the trusted `release.json`. The documented private, create-only ingress reduces exposure but does not enforce immutability. Bind parsing to a stable verified snapshot and add a deterministic replacement regression test. A shared descriptor alone addresses pathname replacement, not concurrent in-place writes.

The ordinary call ordering is correct: size → streamed SHA-256 → `tarfile.open`. The spies are sound for the mismatch cases: they delegate, reset construction counts correctly, and include successful controls. They do not cover replacement between verification and parsing.

The pre-scan implementation, constants, limit tests and rehash helper are removed. The raw-header/PAX helpers remain used by the new hostile-input tests; no dead pre-scan code was found.

No regressions found in the previously resolved summary privacy, marker type validation, short-write handling, marker size bounds or positive controls.

Tests were read, not run. The reported 138 WP01 and 994 deploy-suite passes remain unverified. No files were edited; no network, SSH or Docker was used.

**REQUEST CHANGES**

## Orchestrator disposition
Bind the hash and the parse to one open file descriptor: open once, stream the sha256 from that handle, seek(0), and call tarfile.open(fileobj=the same handle). Concurrent in-place writes are excluded by the trust boundary (a claude-owned 0700 create-only ingress folder; only the applier can write to it). WP03's content-addressed post-load image-ID check against the pinned config digest is the binding guarantee for what docker loads.
