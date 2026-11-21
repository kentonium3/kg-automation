---
affected_files: []
cycle_number: 2
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T23:01:53Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP02
---

# WP02 review feedback — cycle 2

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Invalid UTF-8 bypasses uncertain-write recovery | scripts/common/vikunja_client.py:1035 | json.loads(bytes) can raise UnicodeDecodeError, but only JSONDecodeError is mapped. Black-box probes reproduced committed writes escaping without recovery: step 1 left repeat=None and done=False after GET/PATCH; step 2 escaped after completion. A malformed recovery read likewise bypasses SeriesEndIncomplete("unknown"). | Map v2 decoding failures to VikunjaServerError while preserving v1 behavior. Add invalid-UTF-8 cases at both writes and recovery reads.

Tests: 192 client tests passed. Full suite interrupted after stalling around 71%; no failures reported before interruption.

Judgment calls: agree with transport wrapping and definite-4xx handling; uncertain-write coverage remains incomplete.

Checklist: dead code N/A (foundation; consumers assigned to later WPs); synthetic fixtures PASS; silent returns PASS; FR coverage PASS; frozen surfaces PASS; locked decisions PASS; ownership PASS; production fragility FAIL (finding 1).

VERDICT: REJECT
## Required
- Fix finding 1: on v2 paths, map every response-decoding failure (UnicodeDecodeError, JSONDecodeError, any ValueError from decoding) to VikunjaServerError(status=None); v1 behaviour unchanged. Add invalid-UTF-8 cases at both end_series writes and at the recovery read.
- Audit the whole v2 response path once more for any other exception type that can escape the uncertain-write classification (e.g. LookupError on a bad charset, OSError subclasses during read) so cycle 3 closes the class, not the instance.
