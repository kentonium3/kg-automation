---
affected_files: []
cycle_number: 3
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T22:38:28Z'
reviewer_agent: claude
wp_id: WP08
---

[MAJOR] scripts/research/run_849_harness.py:1080 — Real ServingFacade.complete calls serving.complete, which tokenizes again after the GTT guard; changing GTT to 58 GiB or unreadable during that second count still reaches HTTP POST — why: the pre-send safety check uses stale evidence and violates NFR-004 — fix: execute the guard after the final tokenization and serialization, immediately before transport; test through the real facade.
[MAJOR] scripts/research/run_849_harness.py:1200 — live_config validates preflight.json before entering gate-failure handling; a mismatched preflight hash returns 1 without gate-container.json, and a resumed ledger receives no session_gates failure event; a missing preflight raises uncaught FileNotFoundError — why: preflight_present_and_matching failures bypass rider 1’s durable evidence and distinct exit status — fix: route preflight-loading failures through the appropriate phase failure recorder and resumed-session event path, returning 3.

Design-lead delta read @8bfc0ed3: APPROVE (bus 20260925T223514053706Zf68055805c; W8-3 carried to C9). The first MAJOR requires a pre-send hook inside serving.complete (approved WP01 module) — routed to the design lead before any fold. Source: Codex read-only review (gpt-6-astra), WP08 cycle 3 on lane-h @8bfc0ed3, 2026-09-25; 127 passed. VERDICT: REJECT.
