---
affected_files: []
cycle_number: 2
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:22:42Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] scripts/research/arms849/substrate.py:492 — Boundary self-test accepts arbitrary nested mounts — mounting the host checkout at `/runs/leak` exposes excluded material without failing any mount or denied-path check; `/dev-leak` also bypasses the system-prefix check — allow exact mount destinations and explicitly enumerated system mounts; add both negative cases.
[MAJOR] scripts/research/arms849/substrate.py:328 — Standalone health still accepts incorrect configuration — reproduced `health().llama_ok=True` with `n_ctx=4096` and rope `"unknown"` because the CLI supplies neither expectation — require the intended serving configuration in every health call and fail closed when it cannot be verified.
[MAJOR] tests/research/test_arms849_isolation.py:39 — Static isolation scan still misses resolvable f-strings — reproduced `f"or{'acle'!s}"` escaping both checks despite evaluating to a forbidden string — evaluate constant conversions and format specifications, with regression fixtures.

Source: Codex read-only review, WP02 cycle 2, 2026-09-25. VERDICT: REJECT (cycle-1 six confirmed fixed; three new).
