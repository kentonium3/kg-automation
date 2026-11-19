---
affected_files: []
cycle_number: 1
mission_slug: arms-preconditions-01M3FVRY
reproduction_command:
reviewed_at: '2026-09-27T03:12:02Z'
reviewer_agent: codex-gpt-6-astra
wp_id: WP01
---

# WP01 review cycle 1 — REVISE

Reviewer: Codex (gpt-6-astra, OpenAI Codex CLI), read-only sandbox, cross-vendor. Implementer: Claude Opus 5.5 (python-pedro). Date: 2026-09-27.
Review prompt: property-based P1–P11 (wp01-review-prompt.md). Scope: ff67c8cb..c25bcd82.

## Findings
[MAJOR] scripts/research/arms849/ledger.py:625 — P1 VIOLATED: scored writes remain permitted after `premise_violated` — Probe: score G/C1/r1, record violation, then begin and score G/C1/r2; both rows survive replay — Reject subsequent scored rows in shared write/replay validation.
[MAJOR] scripts/research/arms849/ledger.py:821 — P1 VIOLATED: `grading_rows()` exposes premise-tainted rows as scored — Immediately and after replay, it returns the rows and `grading.seal_map()` consumes them — Make the scored accessor raise `LedgerUnusable`; retain raw rows for inspection.
[MINOR] tests/research/test_arms849_ledger.py:1706 — P3 retry semantics are ambiguous — The test explicitly permits immediate same-session retry after unreadable-at-send, while ledger-deltas item 1 says “refuses the cell” without defining retry timing — Clarify same-session and resumed-session retry rules, then test both.

## Orchestrator disposition
- MAJOR ×2: accepted, returned to the implementer for fix.
- MINOR (unreadable-at-send retry): the code's reading (attempt-level refusal, re-guarded at each send, MAX_ATTEMPTS terminal) kept; design-lead confirmation requested on the bus (20260927T031021976636Z714d1f6ce3); resumed-session retry test requested.

VERDICT: REVISE
