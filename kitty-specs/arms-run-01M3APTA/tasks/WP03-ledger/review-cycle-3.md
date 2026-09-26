---
affected_files: []
cycle_number: 3
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:41:53Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:365 — Summaries omit cells containing only interrupted attempts — three starts produce terminal `error` but `summarise()` returns `{}`, hiding the exhausted cell and its attempts — include attempt-only cells and account for terminal failures without run rows.
[MAJOR] scripts/research/arms849/ledger.py:438 — Lock initialization remains outside exception cleanup — failure in `os.ftruncate` or `os.write` leaks the acquired descriptor and prevents subsequent opens; cycle-1’s cleanup fix is incomplete — protect initialization with the same cleanup handler and test injected failures.
[MAJOR] scripts/research/arms849/ledger.py:56 — Required telemetry remains optional: `elapsed_s` on all rows, four `*_loaded` counts on scored rows, and `peak_gtt_gib` on error rows — accepted rows violate data-model.md; tests derive their omission list from the incomplete implementation — enforce these fields and test an independent contract-derived list.
[MAJOR] scripts/research/arms849/ledger.py:329 — `finish_reason="length"` neither requires nor sets `truncated=true` — grading_rows returns truncated answers without the required grading flag — derive and persist `truncated` from finish_reason, rejecting contradictory payload values.
[MAJOR] scripts/research/arms849/ledger.py:315 — R’s `r_g_ratio` is checked only for presence, so null is accepted — D-10 explicitly forbids null and requires a ratio or an unavailable reason — validate the value and test null and malformed unavailable states.
[MAJOR] scripts/research/arms849/ledger.py:495 — New ledgers retain the caller’s mutable Binding dictionaries — changing `binding.serving` changes the append comparison target while the persisted header stays unchanged, permitting mismatched serving rows — snapshot the binding and protect its authoritative values from mutation.
[MINOR] scripts/research/arms849/ledger.py:500 — Recovery modifies the tail before checking binding equality — a mismatched opener repairs the file, then refuses without logging recovery; a subsequent valid opener cannot recover that evidence — validate the header binding before repairing the tail and recording its event.

Source: Codex read-only review, WP03 cycle 3, 2026-09-25. VERDICT: REJECT (cycle-2 five confirmed fixed; five new + one minor).
