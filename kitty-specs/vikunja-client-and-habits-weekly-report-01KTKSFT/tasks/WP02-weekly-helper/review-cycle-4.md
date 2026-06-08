---
affected_files: []
cycle_number: 4
mission_slug: vikunja-client-and-habits-weekly-report-01KTKSFT
reproduction_command:
reviewed_at: '2026-06-08T17:00:29Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue 1 (blocking, small fix)**: `scripts/habits/query_active_habits_weekly.py:363` emits `weekly_report_anomaly` with `category="warning"`, but `scripts/openclaw/observation/log_action.py` accepts only `routine`, `flagged`, `error`, and `security`. A real invocation exits 1 with `Invalid category 'warning'`, so no JSONL anomaly event is written and weekly_report_payload invariant 1 remains unmet. Change the anomaly category to `flagged`, update the category assertions in `tests/habits/test_query_active_habits_weekly.py`, and add an integration-level assertion that exercises the real category validation rather than only mocking `_emit_log_action`.

Focused verification note: direct `pytest`/coverage execution was unavailable in the reviewer shell because `pytest` and `uv` are not installed or on PATH. The real `log_action.py --category warning` subprocess rejection was reproduced independently.
