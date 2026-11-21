---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-19T23:45:42Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP04
---

# WP04 review feedback — cycle 1

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | First recurring completion is mislabelled | scripts/escalation/reconcile_completions.py:882 | Without a prior reschedule_to, an actual UI completion falls through to rescheduled, violating FR-015. The probe reproduced this; the new test explicitly accepts it. | Persist a due-date baseline independently of reschedules and test completion before any reschedule.

2. MAJOR | Historical done records suppress later completions | scripts/escalation/reconcile_completions.py:1151 | After a synthetic done and a newer level_sent, _is_subscribed returns true, but _has_terminal_record still blocks recurring completion detection because it searches the entire history. The probe reproduced no emitted event after re-subscription. | Scope terminal checks and due-date baselines to the current subscription/occurrence; add a multi-cycle regression.

3. MAJOR | Preservation regressions accept lost companion fields | tests/escalation/test_escalation_rule_roundtrip.py:190 | Both happy-path tests still pass when fake responses remove reminders and reset repeats_from_current_date to false. They therefore do not prove FR-020 preservation. The contract-required COUNT=2→1 and UNTIL-ended helper cases are also absent. | Assert companion-field preservation, distinguish legitimate reminder movement from removal, add corruption controls, and cover both finite-series transitions.

VERDICT: REJECT
## Required
- Fix all three. For 1+2: a due-date baseline independent of reschedules (e.g. record the task's due_date on each escalation level_sent record and use the newest one within the current subscription), and scope terminal checks to the current subscription/occurrence. Keep the JSONL backward-compatible (old records without the new field fall back to today's behaviour). Multi-cycle regression required.
- For 3: assert companion-field preservation (repeats_from_current_date=true + a reminder) with corruption controls, plus COUNT=2->1 and UNTIL-ended helper cases.
