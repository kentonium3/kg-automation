---
affected_files: []
cycle_number: 8
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T03:56:34Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:157 — Gate digests lack 64-hex validation: creation and resume accept `gate_host_sha=None` and `gate_container_sha="g"*64` — required fields can contain no valid digest; all 82 tests pass using invalid placeholders — validate all three gate SHAs on creation and resume, use valid test fixtures, and test null, malformed, and wrong-length values.

Source: Codex read-only review, WP03 cycle 7, 2026-09-25. VERDICT: REJECT (the two fields present; their 64-hex validation absent — my earlier edit was a silent no-op and the tests used placeholders). Design-lead APPROVE at f775b72e carries to the fold.
