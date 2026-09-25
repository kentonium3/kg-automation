---
affected_files: []
cycle_number: 14
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T20:59:07Z'
reviewer_agent: claude
wp_id: WP04
---

[MAJOR] scripts/research/arms849/litscan.py:304 — `"".join(({"or","acle"}.__iter__,)[0]())` returns the label under PYTHONHASHSEED=0 and "acleor" under seed 3; the scanner catches only seed 0 because retrieving the bound method through Subscript loses its receiver's taint — why: the literal-only scan remains seed-dependent — fix: carry bound-receiver taint through callable values and check it before invocation; add both-seed regression coverage.

Notes (Codex): all 14 requested constructions agree across both seeds; generators opaque; the len-index expression returns "acle"; the conditional refuses; both expected caught constructions caught; the fold checks operands before compiled execution; allowlist and shadowing pre-pass unchanged; real package "12 modules scanned (12 registered present), no hit". 120 passed / 168 sandbox PermissionErrors (environment).

Scope: inside the D-8 closure rule (a value path that skipped the consumer check) — folded. Source: Codex read-only review (gpt-6-astra), WP04 cycle 14 on lane-d @1e203918, 2026-09-25. VERDICT: REJECT.
