---
affected_files: []
cycle_number: 9
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T04:02:55Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:570 — New-ledger creation bypasses SHA validation for directly constructed bindings — reproduced `open_ledger()` persisting `gate_host_sha=None`, creating a ledger that cannot subsequently resume — validate all three incoming digests before writing any header and test direct-constructor inputs.

Source: Codex read-only review, WP03 cycle 8, 2026-09-25. VERDICT: REJECT (one: open_ledger bypasses sha validation for a directly constructed Binding).
