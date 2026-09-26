---
affected_files: []
cycle_number: 4
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:53:08Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] tests/research/test_arms849_substrate.py:44 — Static tests invoke Docker through `_runner_cmd` here and at line 186 — authorized suite produced 2 failures, 29 passes, 2 skips; tests attempt image builds and require host mount directories — mock lifecycle side effects and supply temporary mount sources.
[MAJOR] scripts/research/arms849/compose/runner.Dockerfile:15 — Runner still omits `jinja2`; only host setup includes it — runner dependencies do not supply it transitively, so tokenizer chat templating fails despite successful setup/self-test — install `jinja2` in the runner and verify chat templating there.
[MAJOR] tests/research/test_arms849_isolation.py:39 — Constant numeric formatting bypasses isolation scanning — `X = f"{111:c}racle"` evaluates to the forbidden string but passes both source and folded-string checks; reproduced without Docker — preserve numeric constants during recursive evaluation and add this regression fixture.

Source: Codex read-only review, WP02 cycle 4, 2026-09-25. VERDICT: REJECT (cycle-3 three confirmed fixed; three new — static tests reach docker via _runner_cmd; runner image lacks jinja2; numeric-constant format spec escapes the scan).
