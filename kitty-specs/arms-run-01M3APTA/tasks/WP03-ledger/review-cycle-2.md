---
affected_files: []
cycle_number: 2
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:30:13Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:294 — Required scored telemetry remains optional — rows lacking `cache_write_tokens`, `prefill_s`, `generation_s`, and `generation_tok_s` are accepted despite D-13’s explicit refusal requirement; cycle-1’s fix is incomplete — validate every required measurement and test each omission.
[MAJOR] scripts/research/arms849/ledger.py:334 — Calibration payload can overwrite `record` — reproduced two successful `write_calibration({"record":"event", ...})` calls while `calibration()` remained `None`, bypassing exactly-once enforcement — reject reserved fields and construct authoritative fields last.
[MAJOR] scripts/research/arms849/ledger.py:236 — Closed ledgers can still append without holding the lock — reproduced an old handle writing after another opener acquired ownership, violating NFR-007 — reject every append after closure and test competing ownership.
[MAJOR] scripts/research/arms849/ledger.py:365 — Summaries omit cells containing only interrupted attempts — three starts produce terminal `error` but `summarise()` returns `{}`, hiding the exhausted cell and its attempts — include attempt-only cells and account for terminal failures without run rows.
[MAJOR] scripts/research/arms849/ledger.py:438 — Lock initialization remains outside exception cleanup — failure in `os.ftruncate` or `os.write` leaks the acquired descriptor and prevents subsequent opens; cycle-1’s cleanup fix is incomplete — protect initialization with the same cleanup handler and test injected failures.

Source: Codex read-only review, WP03 cycle 2, 2026-09-25. VERDICT: REJECT (cycle-1 ten confirmed fixed; five new).
