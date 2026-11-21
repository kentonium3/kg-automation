---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T22:47:04Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP02
---

# WP02 review feedback — cycle 1

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Committed rule-clear can escape recovery | scripts/common/vikunja_client.py:873 | If the clear PATCH commits but returns an invalid task body or truncated response, end_series propagates VikunjaServerError or IncompleteRead without re-reading or reporting partial progress. Both black-box probes left done=false and repeat=None after only GET, PATCH. This violates T008’s recovery contract. | Re-read after response-validation and transport failures; resume from verified state or raise SeriesEndIncomplete. Add tests where the write commits before its response fails.

Tests: 151 focused tests passed. Full suite interrupted after several minutes without output around 72%; no failures had been reported.

Judgment calls 1–7: agree, subject to finding 1’s additional recovery case.

Checklist: dead code N/A (foundation; consumers assigned to later WPs); synthetic fixtures PASS; silent returns PASS; FR coverage PASS; frozen surfaces PASS; locked decisions PASS; ownership PASS; production fragility FAIL (finding 1).

VERDICT: REJECT
## Required
- Fix finding 1 and add the failure-injection test the reviewer describes (commit-then-fail for WP02; partial-append-then-retry for WP06).
- Orchestrator note: the reviewer's full-suite run stalls ~71% inside the Codex sandbox (sandbox limitation); re-run make test yourself and record it.
