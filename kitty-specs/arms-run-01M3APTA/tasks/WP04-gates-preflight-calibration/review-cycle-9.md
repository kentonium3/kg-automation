---
affected_files: []
cycle_number: 9
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T19:24:40Z'
reviewer_agent: claude
wp_id: WP04
---

[MAJOR] scripts/research/arms849/litscan.py:96 — `str("or")+"acle"`, `"or acle".split()[0]+"or acle".split()[1]`, and `bytes([111,114,97,99,108,101]).decode()` each produce the forbidden word but the real gate returns `True, '13 modules scanned (12 registered present), no hit'` — why: literal-only constructions still bypass the required isolation scan — fix: evaluate supported pure literal calls in the bounded child and refuse unsupported literal-call constructions instead of silently treating them as opaque; add gate-level regressions.

Notes (non-blocking, Codex): suite 88 passed / 36 failed in the sandbox — the failures are sandbox-denied socket creation in `_closed_port()` (not a defect); the checkout-write guard tests now pass read-only. Direct probes confirmed the exclusion-list and inventory refusals, unknown-node rejection in-process and through the child, and fail-closed behaviour on exceptions, memory exhaustion and SIGKILL. All 12 REQUIRED_MODULES match the package; extra modules are scanned; deleting a registered one fails the gate; no stale excluded_prefixes= callers. No forbidden word in package source.

Source: Codex read-only review (gpt-6-astra), WP04 cycle 9 on lane-d @ff6d2f84, 2026-09-25; design-lead delta read APPROVE (20260925T192325166318Za199054831). VERDICT: REJECT.
