---
affected_files: []
cycle_number: 2
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T00:58:17Z'
reviewer_agent: claude
wp_id: WP01
---

[MAJOR] scripts/research/arms849/serving.py:276 — Cached tokens are subtracted twice: llama.cpp’s `prompt_n` already excludes cache hits ([source](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp)) — `prompt_n=1, cache_n=236` produces uncached/write counts of −235 and cache_fraction=236 — correct the conflicting D-13 contract, use total=prompt_n+cache_n and uncached=prompt_n, and add a regression fixture verified against the pinned server.

Source: Codex read-only review (gpt-6-astra), cycle 2, 2026-09-25 00:56Z. VERDICT: REJECT. Fixed in lane-a @4029e012; D-13 contract corrected @8dc8c798.
