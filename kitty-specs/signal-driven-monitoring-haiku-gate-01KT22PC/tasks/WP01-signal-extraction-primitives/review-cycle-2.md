---
affected_files: []
cycle_number: 2
mission_slug: signal-driven-monitoring-haiku-gate-01KT22PC
reproduction_command:
reviewed_at: '2026-06-01T18:19:14Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: `scripts/openclaw/observation/signals/_engine.py` only extracts from `log_files[-1]`, so a glob such as `/tmp/openclaw/openclaw-*.log` can miss unread source data when more than one matching log file exists. This conflicts with FR-001's "extracts each defined signal from its source data exactly once per cycle" and WP01 T003's plural log-file/cursor requirement. Fix by iterating the resolved files in mtime order, applying the cursor only to the file it matches, reading later files from byte 0, and persisting the final cursor for the last file read. Add a regression test with two matching log files where the older file contains unread matches after the prior cursor and the newer file also contains matches.

**Issue 2**: `scripts/openclaw/observation/signals/_engine.py` redacts long strings only when their key is in each extractor's `REDACT_KEYS`. WP01 T004 requires credential material to be redacted by truncating any value field longer than 64 chars to `<redacted len=N>`, and this narrower key allowlist can leak long credential-like values under unlisted keys such as `value`, `auth`, or future OpenClaw fields. Fix the excerpt redaction to apply the 64-character truncation to value fields per the WP requirement, or otherwise expand and test the policy so arbitrary credential-bearing fields in OpenClaw excerpts cannot pass through. Add a test with a long credential-like value under an unlisted key.

Downstream note: WP02 and WP04 depend on WP01. After this WP is corrected and approved, those lanes should rebase before continuing work that consumes the signal primitives.
