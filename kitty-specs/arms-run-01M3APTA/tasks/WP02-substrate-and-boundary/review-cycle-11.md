---
affected_files: []
cycle_number: 11
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:38:18Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] tests/research/test_arms849_isolation.py:33 — `X = "%s%s" % (*("or", "acle"),)` evaluates to `oracle` but passes both scans — `_PURE_NODES` omits `ast.Starred`, misclassifying literal-only unpacking as opaque — support literal unpacking in the resource-limited evaluator and add a regression fixture.

Source: Codex read-only review, WP02 cycle 11, 2026-09-25. VERDICT: REJECT (cycle-10 confirmed fixed; one new — ast.Starred omitted from the pure-node allowlist). Disposition: classify EVERY ast.expr subclass pure-or-opaque with a grammar-enumerating test, so the class of "forgotten node" cannot recur.
