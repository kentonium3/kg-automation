---
affected_files: []
cycle_number: 6
mission_slug: documentation-developer-portal-01KSJ75K
reproduction_command:
reviewed_at: '2026-05-26T13:48:25Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: `write_block()` does not preserve content outside the marker pair byte-for-byte when the portal uses CRLF line endings.

Contract row: T004 requires `--write` to "Preserve every line outside the markers byte-for-byte." The current implementation reads `docs/DEVELOPER_PORTAL.md` as text and immediately applies `.replace('\r\n', '\n')` before splicing and writing the whole file back. That converts line endings in the preamble and suffix outside the generated block from CRLF to LF.

How to reproduce:

1. Create a synthetic `docs/DEVELOPER_PORTAL.md` with CRLF line endings before and after the marker block.
2. Make the marker block stale.
3. Run `write_block(repo_root)` or `python tooling/scripts/build_runbook_filter.py --write`.
4. Compare bytes before and after the marker span; the outside bytes are rewritten.

Fix: Keep the original portal text/bytes for splicing in `--write`. Normalize line endings only for comparisons, not for the text used to preserve the prefix/suffix. Add a regression test that asserts CRLF bytes outside the marker-bounded region are unchanged after `--write`.

Downstream note: WP02 depends on WP01 and should rebase after this fix lands.
