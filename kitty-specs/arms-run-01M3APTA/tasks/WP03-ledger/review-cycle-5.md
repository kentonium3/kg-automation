---
affected_files: []
cycle_number: 5
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:18:32Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:327 — Telemetry validation still accepts missing measurements disguised as values: reproduced G `ok` with `falkordb_rss_peak_mib=None`, error with `peak_gtt_gib=None`, and scored `prefill_s=NaN` — persisted rows violate the measurement contract — require finite, non-negative numeric measurements, validate error text, and test null/non-finite inputs.
[MINOR] scripts/research/arms849/ledger.py:452 — Summary omits `cache_write_tokens` — T014 requires sums of the cache split, but this required measurement disappears — expose its sum over `ok` rows and test exclusion of non-scored rows.

Source: Codex read-only review, WP03 cycle 5, 2026-09-25. VERDICT: REJECT (cycle-4 three confirmed fixed; one MAJOR + one MINOR new — None/NaN/inf accepted as measurements; cache_write_tokens missing from Summary).
