---
affected_files: []
cycle_number: 7
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:16:45Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] tests/research/test_arms849_isolation.py:38 — Constant folding still permits forbidden strings: reproduced `f"{+111:c}racle"`, `f"or{1 / 2!s:.0}acle"`, and `"%s%s" % ("or", "acle")` evaluating to `oracle` while both scans pass — unary plus, division, and tuple operands escape evaluation, undermining FR-013’s static gate — support these constant expressions and add regression fixtures.

Source: Codex read-only review, WP02 cycle 7, 2026-09-25. VERDICT: REJECT (cycle-6 two confirmed fixed; one new — the hand-written constant evaluator misses unary plus, division and %-formatting with tuples). Disposition: replace the bespoke evaluator with Python’s own evaluation of pure-literal subtrees.
