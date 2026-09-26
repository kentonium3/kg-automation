---
affected_files: []
cycle_number: 2
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T03:06:29Z'
reviewer_agent: claude
wp_id: WP04
---

[BLOCKER] scripts/research/arms849/preflight.py:46 — Cycle 1’s nonexistent checker remains registered — invocation still returns `ModuleNotFoundError`, preventing real preflight success — derive the actual checker name from exclusion data and test all four real imports.
[BLOCKER] scripts/research/arms849/gates.py:127 — Cycle 1’s empty-results bypass remains — directly verified that a re-signed record with `gates=[]` and matching fingerprints passes without checker evidence — require exactly four expected outcomes, each with strictly successful boolean and exit-code values.
[MAJOR] scripts/research/arms849/gates.py:171 — Static scanning covers only top-level Python files — modules in subdirectories evade the required package-wide exclusion scan — scan recursively and add an injected nested-module failure test.
[MAJOR] scripts/research/arms849/sampler.py:107 — Context exit returns before outstanding reads finish — its three-second join is shorter than the ten-second RSS timeout, allowing a numeric peak to be persisted before a late failure invalidates it — settle outstanding reads or invalidate unfinished windows and prevent subsequent mutation.

Source: Codex read-only review, WP04 cycle 2, 2026-09-25. VERDICT: REJECT (cycle-1 seven confirmed fixed; four new incl. two BLOCKERs: the fourth checker module name was mangled by my rename — derived from the data file now; the preflight gate accepted an empty gates list).
