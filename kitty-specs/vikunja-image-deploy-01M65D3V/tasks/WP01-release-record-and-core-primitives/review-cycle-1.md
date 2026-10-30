---
affected_files: []
cycle_number: 1
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:01:23Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP01
---

# WP01 review cycle 1 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES

1. **HIGH — Output allowlist leaks private text.** `scripts/deploy/vikunja_release/core.py:141` accepts arbitrary summaries matching a character regex rather than fixed summaries. Read-only probes confirmed that `emit()` prints `password=hunter2`, the seeded task title, and the seeded user name unchanged. This violates R-16. Use explicit summary identifiers/templates and test each seeded string in the summary position.

2. **MEDIUM — Malformed markers escape the required refusal.** `scripts/deploy/vikunja_release/core.py:695–699` performs set membership before checking types. JSON such as `{"phase":[]}` or `{"phase":"started","outcome":{}}` raises `TypeError`, rather than `MARKER_UNREADABLE`. Validate types first and add malformed-type cases with valid-marker controls.

3. **MEDIUM — Marker writes can report success with unreadable content.** `scripts/deploy/vikunja_release/core.py:734` and `:761` ignore `os.write()`’s returned byte count. A short write followed by successful fsync can leave truncated JSON, including replacing the previous valid marker. Additionally, `:714` accepts payloads exceeding the reader’s 64 KiB limit; an in-memory probe accepted 70,042 bytes. Write the complete payload and enforce the read limit before mutation.

4. **MEDIUM — Tar metadata processing lacks resource bounds.** `scripts/deploy/vikunja_release/core.py:629–634` parses extension headers and collects all members before applying JSON-member limits. The independent review reproduced `RecursionError` using approximately 563 KiB of nested PAX headers; this also escapes the stable archive-error handlers. Bound metadata processing and test hostile archives against intact controls. The pinned archive SHA limits current exploitability.

5. **MEDIUM — Required positive controls are missing.** `tests/deploy/test_vikunja_release_core.py:367`, `:444`, and `:461` exercise refusals without successful same-fixture controls. Separate success tests do not meet the explicit per-refusal requirement. The summary-privacy test at `:254` also misses private strings that satisfy the permissive regex.

The specified R-13 identity checks are present; no `shell=True` or extraction-to-disk path was found.

The permitted pytest command failed **before collection** because the read-only environment has no usable writable temporary directory. Tests remain unverified. No files were edited; no network, SSH, or Docker was used.

**REQUEST CHANGES**
