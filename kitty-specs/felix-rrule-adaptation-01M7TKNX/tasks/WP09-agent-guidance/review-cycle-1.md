---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-20T19:10:25Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP09
---

# WP09 review cycle 1: REJECT (reviewer: Codex gpt-6.1-sol, 2026-11-20)

1. MAJOR | Preview drops the first due date and miscounts bounded series | scripts/vikunja/preview_rule.py:199 | Production server d7e202228 returns the anchor in due_date; occurrences contains only subsequent dates. A production-shaped COUNT=1 response prints “no upcoming occurrences” and “series ends after 0 occurrences”; COUNT=2 claims one occurrence. The test fixture incorrectly supplies two subsequent dates for COUNT=2. | Preserve and render due_date, distinguish it from subsequent occurrences, correct exhaustion wording, and test production-shaped COUNT=1/2 responses.

2. MINOR | Invalid count escapes the CLI error contract | scripts/vikunja/preview_rule.py:141 | --count 101 passes local validation, then VikunjaClient raises an uncaught ValueError. No JSON summary is emitted. Argument-parser errors also omit the promised summary. | Validate count within 1..100 and route input failures through the exit-2 JSON error path.

3. MINOR | Malformed preview responses report success | scripts/vikunja/preview_rule.py:199 | A mocked HTTP 200 body of {} produces “no upcoming occurrences”, ok:true, and exit 0. Missing or wrongly typed occurrences silently becomes an empty list; invalid timestamps likewise pass through as successful dates. | Validate response fields and timestamps; return exit 3 with an error summary for malformed responses.

Validation: focused tests passed, 95/95. Full suite stalled around 71% without reported failures and was interrupted; full-suite validation remains incomplete.

Scope limitation: the two changed SKILL.md files were not read, honoring your explicit prohibition; their semantic acceptance criteria remain unverified.

Size check: new AGENTS.md guidance falls before the documented 14,000-byte budget. No WP09-specific truncation finding.

Checklist, inspected scope: dead code PASS; synthetic-fixture PASS; silent-empty FAIL; FR coverage FAIL; frozen surface PASS; locked decision PASS; shared-file ownership PASS; production fragility FAIL.

VERDICT: REJECT
Fix all three findings, the MINORs included. If the SKILL.md text describes the preview output, make it match the corrected behaviour (the anchor due date is shown first).
