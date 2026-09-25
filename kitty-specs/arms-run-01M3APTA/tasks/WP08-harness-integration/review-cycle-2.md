---
affected_files: []
cycle_number: 2
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T22:25:35Z'
reviewer_agent: claude
wp_id: WP08
---

[MAJOR] scripts/research/run_849_harness.py:1007 — If GTT rises from 30 to 58 GiB or becomes unreadable during tokenization, the probe still sends the completion request; both probes reproduced `sent=True` — why: M2’s pre-send protection permits a known unsafe request — fix: recheck sampler readability, breach flag and peak immediately before `complete()`, refusing without sending.
[MINOR] scripts/research/run_849_harness.py:693 — Registration accepts a custom direct BaseException subclass as its refusal, but raising it escapes the worker wrapper; the probe left one attempt, zero run rows and no terminal outcome — why: an accepted refusal class violates W8-1’s first-attempt terminal behavior — fix: recognize the registered refusal before propagating non-Exception exceptions, while preserving interruption behavior.
[MINOR] scripts/research/run_849_harness.py:995 — An initial 58 GiB or unreadable sample returns without `gtt_breached` and `gtt_window_valid` — why: the persisted secondary gate event omits M2’s required telemetry flags — fix: include both flags on pre-send refusals.
[MINOR] scripts/research/run_849_harness.py — (design lead, bus 20260925T222320935007Z871e1c44e6, rider 1) a fresh path with failing gates creates no ledger/header but must still write gate-host.json / gate-container.json naming the failing gate + detail, and the CLI must exit non-zero with a DISTINCT status.
[MINOR] scripts/research/run_849_harness.py — (design lead, same, rider 3) the ceiling is breached STRICTLY above 57.5 GiB (NFR-004: 62.5 budget, ≥ 5 GiB headroom ⇒ exactly 57.5 is compliant); the harness pre-send guard and post-window breach must both import sampler.py's single ceiling constant, and the reading that triggered a refusal is recorded. (Codex's c2 note called at-equality "the requested conservative rule"; the design lead's derivation from the registered text governs.)

Artifact note (design lead): W8-1's STRING HALF — non-refusal errors are recorded with the module-qualified class name so the ledger's `ArmRefusal:` prefix rule cannot confer terminality on an unrelated same-named class; the contract sentence about the prefix stays as it is. Design-lead delta read @c1d0d7d9: APPROVE. Source: Codex read-only review (gpt-6-astra), WP08 cycle 2 on lane-h @c1d0d7d9, 2026-09-25 — 121 passed, four mutations went red as expected. VERDICT: REJECT.
