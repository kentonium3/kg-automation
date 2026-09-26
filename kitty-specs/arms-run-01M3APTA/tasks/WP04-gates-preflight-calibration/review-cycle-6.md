---
affected_files: []
cycle_number: 6
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T03:46:16Z'
reviewer_agent: claude
wp_id: WP04
---

[MAJOR] scripts/research/arms849/gates.py — design-lead ruling 20260925T033758187296Z4e2f3be79e (2026-09-25): the gate set runs in TWO PHASES because the D-8 runner has no docker socket. HOST phase (run by the harness's `run` entry immediately before launching the runner, after up + health): boundary, substrate_health, preflight_present_and_matching → signed gate-host.json {ts, up_ts, export_content_sha, export_source_commit, preflight_sha, results, gate_host_sha}. CONTAINER phase (before the header): preflight match recomputed inside, prompt/manifest digests, excluded material + scan, env_clean, tokenizer_equivalence vs llama:8080, substrate_health_inside (/props re-probe + verification of gate-host.json: sha recomputes, export/preflight equal, every host result passed, up_ts ≤ ts ≤ container start), code_hashes → signed gate-container.json. Tests: a stale host record (ts < up_ts) refused; a host record for another export refused.

Source: design-lead ruling after the WP04 live evidence run (8/9 gates from the host; env_clean fails on the host by construction). Contract corrected @9f693cfc.
