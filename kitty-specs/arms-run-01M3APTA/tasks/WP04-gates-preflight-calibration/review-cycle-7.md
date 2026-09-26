---
affected_files: []
cycle_number: 7
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T04:00:56Z'
reviewer_agent: claude
wp_id: WP04
---

[MAJOR] scripts/research/arms849/gates.py:282 — Container hashing excludes `gate_host_sha` — substituting the cited host digest leaves `gate_container_sha` unchanged, breaking evidence binding — exclude only the record’s own digest field and test host-digest substitution.
[MAJOR] scripts/research/arms849/gates.py:326 — Freshness trusts the host record’s own `up_ts` — reproduced acceptance of yesterday’s record despite today’s `env.up_ts`; an earlier stack’s evidence remains replayable — require an independently supplied current-stack identity and timestamp, compare them, and test replay of an unchanged previous-stack record.
[MINOR] scripts/research/arms849/gates.py:415 — Host timestamps truncate fractional seconds while validation compares strings — legitimate same-second health completion can produce `ts < up_ts` and refuse a healthy run — preserve precision, compare parsed timezone-aware timestamps, and test fractional seconds and equivalent UTC encodings.

Source: Codex read-only review, WP04 cycle 6, 2026-09-25. VERDICT: REJECT (three new on the two-phase seam, all accepted).
