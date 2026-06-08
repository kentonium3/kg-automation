**Issue 1 (blocking): Capped completion counts do not emit the required anomaly event.**

`build_report()` caps current and prior completion counts at scheduled days, but no
`weekly_report_anomaly` action is emitted. This contradicts validation invariant 1
in `contracts/weekly_report_payload.md`, which requires the helper to log that
action whenever Vikunja returns more completion events than the scheduled count.
As written, duplicate or otherwise inconsistent completion history is silently
normalized, so operators lose the required audit signal.

Fix the helper so each capped current/prior count produces a redaction-safe
`weekly_report_anomaly` log action without changing the report JSON or exit code.
Add focused tests that run the production path and assert the anomaly action and
context; retain the existing cap assertions. Also assert that ordinary reports do
not emit anomaly actions.

Verification already completed: the current implementation passes 67 tests with
98.26% coverage using:

`python3 -m pytest tests/habits/test_query_active_habits_weekly.py --cov=scripts.habits.query_active_habits_weekly --cov-branch --cov-fail-under=90 -q`
