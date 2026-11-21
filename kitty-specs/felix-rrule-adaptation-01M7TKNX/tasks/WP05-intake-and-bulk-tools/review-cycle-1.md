---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T23:41:46Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP05
---

# WP05 review feedback — cycle 1

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Valid reminder recomputation makes intake report failure | scripts/vikunja/migrate_tasks.py:786 | Production recomputes relative reminders on every save in the saver’s timezone, including project-only moves. Reproduced with due_date=2027-03-15T00:00Z and relative_period=-86400: a reminder previously saved in UTC legitimately shifts from 00:00Z to 01:00Z under Kent’s ET timezone. The move persists with its rule intact, but intake returns failed. This invalidates judgment call 2. | Account for server-driven relative-reminder recomputation on every save while checking reminder presence and relative settings; retain strict absolute-reminder checks. Add a DST regression.

2. MINOR | Round-trip fixtures omit required true-flag coverage | tests/intake/test_apply_reply_rule_roundtrip.py:212 | Intake and date-migration regression fixtures default repeats_from_current_date to false; the intake move also has no reminders. These tests cannot establish the contract’s required preservation of a true flag plus reminders for each write path. | Exercise each path with repeats_from_current_date=true and a reminder, then add matching controls that remove the reminder or flip the flag.

VERDICT: REJECT
## Required
- Fix 1: for RELATIVE reminders compare presence + (relative_to, relative_period) only, on every write (not just due-date writes); keep absolute reminders strict. Cite the server code (d7e202228 updateRelativeReminderDates) in history. Add a DST regression.
- Fix 2: run each write path's round-trip with repeats_from_current_date=true and a reminder, with flip/remove controls.
