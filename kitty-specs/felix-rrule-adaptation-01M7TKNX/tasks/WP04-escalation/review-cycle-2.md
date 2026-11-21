---
affected_files: []
cycle_number: 2
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-20T00:06:05Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP04
---

# WP04 review feedback — cycle 2

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Absolute reminder corruption passes preservation checks | scripts/escalation/record_completion.py:303 | Every absolute reminder becomes the identical signature ("absolute",). A probe rescheduled a task while replacing its reminder timestamp with the unset sentinel; the helper accepted success. This violates data-model invariant 2. | Compare absolute reminder instants on reschedule; validate legitimate movement separately for completion. Add corruption controls for changed and unset timestamps.

2. MINOR | Same-day recurring completions disappear | scripts/escalation/reconcile_completions.py:894 | Baselines and cached due dates are reduced to calendar dates. A probe advancing an hourly task from 15:00Z to 16:00Z emitted neither done nor rescheduled, missing FR-015. | Compare timezone-aware instants when an instant baseline exists; retain calendar-date fallback for legacy records and add a same-day advancement test.

VERDICT: REJECT
## Required (last cycle before arbiter)
- Fix 1: absolute reminders compared by instant on reschedule (strict); for completion, absolute reminders are allowed to move only as the server moves them — verify that server behaviour in d7e202228 (cite lines) and test both. Controls for changed and unset timestamps.
- Fix 2: compare timezone-aware instants when an instant baseline exists; calendar-date fallback for legacy records; same-day advancement test.
