---
affected_files: []
cycle_number: 2
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-20T00:12:03Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP07
---

# WP07 review feedback — cycle 2

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Future preview changes recurrence phase | scripts/habits/query_active_habits_weekly.py:221 | Replacing the task’s due date with window_start minus one second changes interval-based schedules. Probe: DAILY/INTERVAL=2 anchored at 2026-05-02T23:59:59Z has four occurrences in June 1–8, but the helper returns three. The “server-faithful” fake hides this by using a fixed schedule independent of the supplied anchor. | Preserve the task’s recurrence anchor and context, or return None; test with an anchor-dependent fake.

2. MINOR | Falsy non-string reasons bypass validation | scripts/habits/query_active_habits_weekly.py:229 | `or ""` converts false, 0, [], and {} into an accepted empty reason. With 100 occurrences beyond the window, probes return 0 instead of None, contradicting the reported malformed-response handling. | Validate the raw reason’s type before applying a default; add falsy non-string cases.

Validation: 839 relevant tests passed. Full suite stalled near 72% and was interrupted; its result remains unverified. Worktree remains clean.

VERDICT: REJECT
## Orchestrator ruling (within FR-012)
Production weekly windows are always in the past, where preview cannot evaluate (cycle 1). The only remaining preview path (future windows) is unused in production and, per finding 1, changes recurrence phase. Remove preview from the weekly report entirely: count daily and weekly-by-day (interval 1, plain BYDAY, no COUNT/UNTIL) locally; every other rule -> None (unknown). Delete the now-dead preview plumbing (weekly_report_driver passing client.preview_occurrences, the now= future branch, reason handling) and its tests; keep the past-window and refusal tests that still apply. Finding 2 becomes moot with the preview path removed. Record the deviation from plan IC-05/O4 in add-history.
