---
affected_files: []
cycle_number: 2
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:14:29Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP01
---

# WP01 review cycle 2 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES

Reviewed `3dc11658` and both complete final files. **Four findings remain.**

Cycle-1 findings:

1. **RESOLVED — Free-text summary leakage.** `emit()` now requires registry membership, and tests cover each seeded string in the summary position. Registration remains a trusted caller boundary: `register_summaries()` accepts any matching uppercase identifier; its literal-only rule is documented rather than enforced. Likewise, code keys still accept any code-shaped string.
2. **RESOLVED — Malformed marker field types.** Types are checked before set membership, with valid-marker controls.
3. **RESOLVED — Short writes and oversized markers.** Both marker writers loop until completion, reject stalled writes, and enforce the serialized 64 KiB limit before filesystem mutation. Tests exercise create and update.
4. **PARTIAL — Tar metadata bounds.** Ordinary PAX examples are covered, but the pre-scan has the bypasses below.
5. **RESOLVED — Previously missing positive controls.** The cited refusal tests now include successful controls, and summary privacy coverage includes the seeded strings.

New findings:

1. **MEDIUM — Pre-scan and `tarfile` disagree on member boundaries.** [core.py:660](scripts/deploy/vikunja_release/core.py:660) always skips the raw header size. `tarfile` ignores that size for directories, links, devices and FIFOs, and local PAX `size` overrides can change subsequent boundaries. A directory header can therefore declare a size spanning hostile metadata: the pre-scan skips it while `tarfile` parses it. GNU sparse headers also consume additional map blocks that this walk does not recognize. Consequently, the pre-scan does not reliably bound the parser’s work. Reject unsupported forms or make the bounded walk agree with the parser before calling `getmembers()`.

2. **MEDIUM — Solaris PAX headers bypass extension limits.** [core.py:626](scripts/deploy/vikunja_release/core.py:626) omits type `b"X"`, which `tarfile` processes as a recursive PAX extension. These headers receive neither the four-extension run limit nor the 64 KiB extension-size limit. Catching a later `RecursionError` provides a stable failure but does not enforce the intended resource bounds.

3. **MEDIUM — Base-256 sizes can escape stable archive errors.** [core.py:630](scripts/deploy/vikunja_release/core.py:630) treats GNU signed base-256 values as unsigned. For example, twelve `0xff` bytes mean `-1` to `tarfile`, but become `2**95-1` here. The resulting seek at [core.py:675](scripts/deploy/vikunja_release/core.py:675) exceeds the supported file offset and can raise uncaught `OverflowError`. Huge positive base-256 sizes have the same issue. Decode consistently and validate sizes against the remaining archive bytes before seeking.

4. **MEDIUM — Deeply nested malformed markers still escape the required refusal.** [core.py:922](scripts/deploy/vikunja_release/core.py:922) catches JSON syntax and Unicode errors, but not `RecursionError`. A deeply nested array fits comfortably below 64 KiB and can fail during decoding before validation, escaping as `RecursionError` instead of `MARKER_UNREADABLE`. Add that refusal case with a valid-marker control.

GNU long-name (`L`) and long-link (`K`) headers receive the intended limits **while the walk remains synchronized**. Tests omit those forms, Solaris PAX, PAX size overrides, sparse headers and base-256 sizes; the new bounds need adversarial cases covering these paths.

Tests were assessed by reading only. The reported 135 WP01 and 991 deploy-suite passes remain unverified. No files were edited; no network, SSH or Docker was used.

**REQUEST CHANGES**

## Orchestrator disposition
Findings 1–3 are resolved by design rather than by a harder pre-scan: verify the archive's size and sha256 against the pinned release.json BEFORE any tar parsing, so the parser only ever sees the exact pinned bytes. Remove the custom pre-scan. Finding 4: catch RecursionError (and MemoryError) in marker_read and map it to MARKER_UNREADABLE.
