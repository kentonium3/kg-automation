# Contract: `scripts/habits/query_active_habits_weekly.py` — weekly habit-completion helper

**Mission**: `vikunja-client-and-habits-weekly-report-01KTKSFT` | **Spec FR**: FR-003/004/005/006/011/012/013 | **Data model**: [WeeklyHabitReport](../data-model.md#entity-weeklyhabitreport-new-json-output-of-the-helper)

## Purpose

Deterministic helper that queries Vikunja's `done_at` history for project-13 habits over a 7-day window (plus a prior 7-day baseline), classifies each habit, computes per-habit completion percentages, and emits a structured JSON report on stdout. Replaces the felix-admin-habits agent's previous LLM-improvised data path.

## Invocation

```bash
python3 scripts/habits/query_active_habits_weekly.py \
    [--window-end YYYY-MM-DD] \
    [--window-days N] \
    [--include-baseline]
```

| Flag | Default | Notes |
|---|---|---|
| `--window-end` | Today (UTC) | The end of the current window (exclusive). If specified, must be ISO date `YYYY-MM-DD`. |
| `--window-days` | 7 | The length of each window in days. Both current and prior windows use the same length. |
| `--include-baseline` | True (omit flag = include) | If passed as `--no-include-baseline`, the prior window is omitted (baseline fields show `null`). |

Deployed-path invocation pattern (felix-admin-habits' AGENTS.md will reference this):
```bash
python3 /home/claude/kg-automation/scripts/habits/query_active_habits_weekly.py
```

## Output schema (stdout JSON)

Schema as defined in [data-model.md](../data-model.md#entity-weeklyhabitreport-new-json-output-of-the-helper). Reproduced for contract clarity:

```json
{
  "window_start_iso": "2026-06-01T00:00:00Z",
  "window_end_iso": "2026-06-08T00:00:00Z",
  "prior_window_start_iso": "2026-05-25T00:00:00Z",
  "prior_window_end_iso": "2026-06-01T00:00:00Z",
  "habits": [
    {
      "habit_title": "<verbatim Vikunja task title>",
      "habit_kind": "daily" | "weekday-in-title" | "other",
      "scheduled_days_current": <int>,
      "completed_events_current": <int>,
      "percent_current": <float, [0, 100]>,
      "scheduled_days_prior": <int>,
      "completed_events_prior": <int>,
      "percent_prior": <float, [0, 100]>
    }
  ],
  "overall_percent_current": <float, [0, 100]>,
  "overall_percent_prior": <float, [0, 100]>
}
```

Habit rows are sorted: kind=`daily` rows first (alphabetical by title), then kind=`weekday-in-title` rows (sorted by weekday Mon→Sun, then title). `kind=other` rows are filtered out entirely.

## Algorithm

1. Parse CLI args; compute `window_start = window_end - window_days`, and (if baseline) `prior_window_end = window_start`, `prior_window_start = prior_window_end - window_days`.
2. Instantiate `VikunjaClient`.
3. Query `client.get("/projects/13/tasks", params={"filter": "done=true", "per_page": "200", "page": "<n>"})` paginating until empty/partial. Collect all done tasks.
4. For each task, parse `done_at`; classify via `classify_habit(task)`.
5. Filter to tasks whose `done_at` falls in `[window_start, window_end)` OR `[prior_window_start, prior_window_end)`.
6. Aggregate by `habit_title`: count current-window events, count prior-window events.
7. For each habit, compute `scheduled_days_for_window(kind, title, window_start, window_end)` (and the prior).
8. Compute percentages: `100.0 * completed / scheduled` (0.0 if scheduled == 0).
9. Compute overall: `100.0 * sum(completed_events_current) / sum(scheduled_days_current)`.
10. Also query for ACTIVE (not yet completed) habits to ensure we include habits with 0 completions but real scheduled days. Strategy: `GET /projects/13/tasks?filter=done=false&per_page=200`; classify each; add 0-completion rows for habits not already in the report.
11. Write the report JSON to stdout. Exit 0.

## Exit codes

| Exit | Meaning |
|---|---|
| 0 | Success. JSON report on stdout. |
| 2 | Usage error (bad `--window-end`, bad `--window-days`). Message on stderr. |
| 3 | Vikunja API failure (VikunjaError raised by the client). Diagnostic message on stderr. Caller (the agent) catches this exit-class and surfaces to WhatsApp. |
| 4 | Internal error (assertion, unexpected exception). Should not happen; treat as bug. |

## log_action calls

Per FR-013:

- On successful exit: invoke `log_action.py --action weekly_report_generated --category routine --context '{"window_start_iso":"...","window_end_iso":"...","habit_count":N,"overall_percent_current":X.X}'`.
- On VikunjaError exit (exit 3): invoke `log_action.py --action weekly_report_failed --category error --context '{"error_class":"VikunjaXxxError","error_detail":"...","path":"/projects/13/tasks"}'`.

The agent rendering step (in felix-admin-habits' AGENTS.md) is responsible for `weekly_report_sent` log_action AFTER the WhatsApp turn-summary is composed.

## Test fixtures (FR-012)

| Fixture | Scenario | Expected output |
|---|---|---|
| `weekly_normal_data` | Full week of varied completions | Per-habit percentages match the fixture's known done_at events. |
| `weekly_cardiac_non_habit_present` | Project 13 includes "Upload cardiac lab history" (repeat_after=0, no weekday in title) | Cardiac row NOT in report; habit_kind would be "other" if classified. |
| `weekly_baseline_nonzero` | Prior week had real completions | percent_prior values are non-zero (regression test for the 2026-06-08 bug). |
| `weekly_weekday_in_title_completed_on_match` | "Strength training — Wednesday" done on Wed in window | percent_current = 100. |
| `weekly_weekday_in_title_skipped` | Same habit NOT done | percent_current = 0; row included. |
| `weekly_partial_pagination` | More than 200 done tasks → multiple pages | Helper iterates pages and aggregates correctly. |
| `weekly_vikunja_unreachable` | Mocked client raises VikunjaTimeoutError | Helper exits 3; stderr message redacted-safe. |
| `weekly_bad_filter_syntax` | Mocked client raises VikunjaBadRequestError | Helper exits 3; stderr message references the path. |

## Plan-phase open items

- Confirm exact Vikunja filter syntax for `done_at` date-range (per research.md R-002 / OP-001). The contract uses `filter=done=true` as the baseline; the date-range refinement is implementation-time.
- Confirm habit-row sort order (alphabetical-within-kind vs. cron-tick-time priority).
- Confirm `--include-baseline=false` semantics for the `_prior` fields (null vs. -1 vs. omitted).
