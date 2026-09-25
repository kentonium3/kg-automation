---
affected_files: []
cycle_number: 4
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:12:57Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:297 — Exposed header binding remains mutable — changing `led.header.binding.serving["n_ctx"]` allowed a run with n_ctx=1 beneath a persisted header declaring 262144 — keep authoritative binding private and expose immutable values or defensive copies.
[MAJOR] scripts/research/arms849/ledger.py:270 — Read APIs expose mutable authoritative rows — changing a returned `ok` row’s outcome allowed another attempt and a second persisted `ok`, violating I2 — return deep copies from rows, run_rows, grading_rows and calibration.
[MAJOR] scripts/research/arms849/ledger.py:421 — Summary counts discard failed attempts once a key succeeds — reproduced error→ok yielding `counts={}`, contrary to T014’s non-scored outcome counting — count recorded non-scored outcomes separately while preserving attempt-only exhausted-cell reporting.

Source: Codex read-only review, WP03 cycle 4, 2026-09-25. VERDICT: REJECT (cycle-3 five + minor confirmed fixed; three new — header.binding mutable through the public attribute; read APIs return live rows; counts drop non-scored rows once a key succeeds).
