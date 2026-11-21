---
affected_files: []
cycle_number: 3
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T23:18:46Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP02
---

# WP02 review feedback — cycle 3 (third rejection → arbiter)

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19.

1. MAJOR | Malformed recovery readback falsely confirms series end | scripts/common/vikunja_client.py:945 | The shape check only calls has_rule(), which treats repeat=[], false, 0, or "" as absent. Black-box reproduction: GET a done repeating task → rule-clear PATCH times out → GET returns done=true, repeat=[], and non-empty repeats_rrule → end_series returns success. This leaves the recovery class incompletely closed and violates invariant 4. | Explicitly validate recurrence types and consistency before interpreting state; map malformed readbacks into the existing recovery handling. Add regression cases at every readback position.

Tests: 266 client tests passed. Full suite stalled at 71% for several minutes and was interrupted; completion is unverified.
Checklist: dead code N/A (staged foundation); synthetic fixtures PASS; silent empty returns PASS; FR coverage PASS; frozen surfaces PASS; locked decisions FAIL (invariant 4); shared ownership N/A; production fragility PASS.
Judgment calls: agree with broad v2 exception mapping and ignoring malformed write-response task shapes when a separate read verifies the outcome.
VERDICT: REJECT