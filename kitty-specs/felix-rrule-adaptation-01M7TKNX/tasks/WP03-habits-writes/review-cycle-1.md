---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T23:50:41Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP03
---

# WP03 review feedback — cycle 1

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Valid rule occurrences are rejected | scripts/habits/sweeper.py:668 | The unconditional EOD guard rejects a valid 08:00 ET occurrence without writing. The pinned server’s withDueDate also anchors repeat-from-completion rules at completion time, so an EOD anchor is not guaranteed. This blocks FR-004 and causes repeated tick errors. | Preserve the server’s occurrence time while converting to explicit-offset ET; replace the rejection test with successful non-EOD coverage.

2. MAJOR | Due-date regression tests omit required preservation fields | tests/habits/test_habits_rule_roundtrip.py:386 | Both sweeper and bulk tests use _dayspec(), which defaults to repeats_from_current_date=False and reminders=None, and assert only rule preservation. They cannot prove FR-020/T016. Probes confirmed both writers accept readbacks with reminders removed and the flag changed. | Seed these paths with the flag true and a reminder; assert flag and reminder-set preservation, allowing expected relative-reminder recomputation.

3. MINOR | Expected UNTIL exhaustion lacks caller coverage | tests/habits/test_habits_rule_roundtrip.py:304 | The UNTIL case covers only unknown exhaustion with repeat-from-completion enabled. No habits round-trip exercises successful preview-established UNTIL exhaustion, required by the client contract and data-model invariant 3. | Add an UNTIL-passed case asserting success, Done with rule retained, and series_ended in comment and state log.

Tests: habits 749 passed. Full suite was interrupted after several minutes without progress around 72%; no final result obtained. Worktree remained clean.

Checklist: dead code PASS; synthetic fixtures PASS; silent empty returns PASS; FR coverage FAIL; frozen surfaces PASS; locked decisions PASS; shared ownership N/A; documented raises PASS.

Judgment calls: agree with 1, 2, 3, 5, 6 and 7. Agree with rule_changed in 4; reject its unconditional non-EOD refusal.

VERDICT: REJECT
## Required
- Fix 1: keep the server's occurrence time, converted to explicit-offset ET; drop the unconditional EOD refusal (keep the explicit-offset check).
- Fix 2 and 3 as stated; relative reminders: compare presence + (relative_to, relative_period) only (server recomputes them on every save, see WP05 cycle-1 finding); absolute reminders strict.
