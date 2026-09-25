---
affected_files: []
cycle_number: 3
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:43:04Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] scripts/research/arms849/substrate.py:285 — Health validates only the rope mode, ignoring required YaRN parameters — mocked `--rope-scale 99 --yarn-orig-ctx 4096` still returns `llama_ok=True` — validate scale `2` and original context `262144` from inspected arguments.
[MAJOR] tests/research/test_arms849_isolation.py:39 — `f"or{'ac' + 'le'}"` still bypasses the isolation scan — interpolation handles only literal constants, ignoring otherwise-supported constant concatenation — recursively evaluate supported expressions before conversion/formatting and add a regression fixture.
[MAJOR] scripts/research/arms849/compose/runner.Dockerfile:5 — Runner base image remains an unpinned tag — rebuilding after teardown can silently change the execution environment despite the digest-pinning requirement — pin the Python base by digest and record its identity.

Source: Codex read-only review, WP02 cycle 3, 2026-09-25. VERDICT: REJECT (cycle-2 three confirmed fixed; three new). Also folding: jinja2 into light deps (rubric 939d9b29), #974 cite, runner network-list assertion (design lead 01:00Z).
