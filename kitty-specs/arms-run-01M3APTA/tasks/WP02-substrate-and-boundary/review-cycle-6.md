---
affected_files: []
cycle_number: 6
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T02:09:07Z'
reviewer_agent: claude
wp_id: WP02
---

[MAJOR] scripts/research/arms849/substrate.py:596 — `/runs` bypasses mount identity validation — binding the host checkout there exposes excluded material while the self-test checks forbidden paths only under `/work`; subsequent identity checks omit `/runs` entirely — verify all four bind sources against their intended directories and add a checkout-at-`/runs` negative test.
[MAJOR] tests/research/test_arms849_isolation.py:55 — Literal `None` still bypasses constant folding — reproduced `f"or{None!s:.0}acle"` evaluating to `oracle` while both source and folded-string scans pass because `None` also represents an unknown expression — use a distinct unknown sentinel and add this regression fixture.

Source: Codex read-only review, WP02 cycle 6, 2026-09-25. VERDICT: REJECT (cycle-5 three confirmed fixed; two new — /runs identity unchecked; None sentinel ambiguity in the scan).
