---
affected_files: []
cycle_number: 7
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T03:46:36Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py — design-lead ruling 20260925T033758187296Z4e2f3be79e (2026-09-25): the ledger header binds preflight_sha, gate_host_sha AND gate_container_sha; Binding gains the two new required fields, compared on every resume like every other field; a header missing any of the three is refused (test c).

Source: two-phase gate ruling; data-model.md §LedgerHeader corrected @9f693cfc.
