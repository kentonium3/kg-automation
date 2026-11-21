---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T22:05:45Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP01
---

# WP01 review feedback — cycle 1

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5).
Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | UNTIL rule loss is accepted as a normal end | scripts/common/vikunja_rule.py:362 | With preview-confirmed exhaustion, both a stripped rule and a replacement yearly rule produce “series_ended”. This suppresses detection of destructive writes; WP01 specifies UNTIL ending with its rule kept. | Require same_rule(before.repeat, after.repeat) for UNTIL endings; test stripped and replaced rules.

2. MAJOR | Default WKST compares unequal to server output | scripts/common/vikunja_rule.py:124 | Parsing FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;WKST=MO produces a rule that compares unequal to the server’s equivalent response. Server d7e202228 omits default Monday. WP08 consequently reports successful creation as failure, and WP07 reports false schedule drift. | Canonicalise omitted, empty, and explicit Monday WKST identically; retain differences for other weekdays.

3. MINOR | Reminder fixture contradicts server readback | tests/common/vikunja_v2_factory.py:134 | with_reminder(make_task()) returns an unset reminder timestamp despite a populated due date. The server computes 2026-11-20T03:59:59Z for these defaults. This weakens the shared fixture’s ability to test reminder movement realistically. | Compute the reminder from its referenced date; use the unset timestamp only when that date is absent.

4. MINOR | Floating UNTIL is silently assigned UTC | scripts/common/vikunja_rule.py:231 | The parser turns floating or date-only UNTIL into valid UTC text, changing its meaning. Server d7e202228 explicitly rejects these forms and requires YYYYMMDDTHHMMSSZ. | Reject unsupported UNTIL forms with ValueError instead of inventing a timezone.

Judgment calls: 1 and 3 flagged above; 2, 4, 5, and 6 accepted.

Checklist: dead code PASS under WP01’s explicit planned-caller allowance; synthetic-fixture tests PASS for scoped helper behavior; documented empty returns PASS; scoped FR coverage PASS; frozen surfaces PASS.

Verification: 66 focused tests passed. Full suite started but stalled around 71%; interrupted after several minutes without progress, exit 130. Full-suite success remains unverified.

VERDICT: REJECT
## Required for re-review
- Fix findings 1 and 2 (MAJOR). Also fix 3 and 4 (MINOR) — both are cheap and make later WPs more accurate.
- For #2, cite the d7e202228 server code you relied on for the default-WKST behaviour.
- Orchestrator note: the reviewer's full-suite run stalled at ~71% inside the Codex sandbox (known sandbox asyncio limitation); the implementer's own full-suite run (9203 passed) stands as the full-suite evidence. Re-run make test after the fixes and record the result.
