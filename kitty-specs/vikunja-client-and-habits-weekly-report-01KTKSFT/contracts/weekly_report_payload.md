# Contract: WeeklyHabitReport JSON payload

**Mission**: `vikunja-client-and-habits-weekly-report-01KTKSFT` | **Spec FR**: FR-003/004/005 | **Data model**: [WeeklyHabitReport](../data-model.md#entity-weeklyhabitreport-new-json-output-of-the-helper)

## Purpose

Defines the exact JSON payload the new helper emits and the agent consumes. This is the contract boundary between the deterministic helper (per Directive 6) and the stochastic rendering surface (the agent).

## Schema (JSON)

```json
{
  "window_start_iso": "string (ISO 8601 datetime, UTC)",
  "window_end_iso": "string (ISO 8601 datetime, UTC)",
  "prior_window_start_iso": "string | null",
  "prior_window_end_iso": "string | null",
  "habits": [
    {
      "habit_title": "string",
      "habit_kind": "daily | weekday-in-title | other",
      "scheduled_days_current": "integer ≥ 0",
      "completed_events_current": "integer ≥ 0",
      "percent_current": "float, [0, 100]",
      "scheduled_days_prior": "integer ≥ 0 | null",
      "completed_events_prior": "integer ≥ 0 | null",
      "percent_prior": "float | null"
    }
  ],
  "overall_percent_current": "float, [0, 100]",
  "overall_percent_prior": "float | null"
}
```

## Field semantics

- **`window_start_iso` / `window_end_iso`**: half-open interval `[start, end)`. The current 7-day window the report covers.
- **`prior_window_start_iso` / `prior_window_end_iso`**: half-open interval `[start, end)` for the prior 7 days. NULL if baseline was opted out via `--no-include-baseline`.
- **`habits`**: array of habit rows. Sorted: `daily` rows first (alphabetical by title), then `weekday-in-title` rows (sorted by weekday Mon→Sun, then title). `other`-classified rows are NEVER present in this array — they're filtered upstream by FR-006.
- **`habit_title`**: verbatim Vikunja task title. NOT sanitized; NOT shortened.
- **`habit_kind`**: classification per FR-004 / data-model HabitClassifier.
- **`scheduled_days_current`**: number of scheduled days within the current window per habit_kind rules (7 for daily, 1 per matched weekday for weekday-in-title).
- **`completed_events_current`**: count of `done_at` events for this habit within the current window.
- **`percent_current`**: `100.0 * completed_events_current / scheduled_days_current` (0.0 if scheduled is 0).
- **`scheduled_days_prior`, `completed_events_prior`, `percent_prior`**: same semantics for the prior window. NULL if baseline opted out.
- **`overall_percent_current`**: `100.0 * sum(completed_events_current) / sum(scheduled_days_current)` over all reported habits.
- **`overall_percent_prior`**: same for prior window. NULL if baseline opted out.

## Render contract (agent side)

The agent renders the payload to a WhatsApp turn-summary with this exact shape:

```
Sent by felix-admin-habits:sonnet

Weekly habits — {window_start_short} to {window_end_short} vs {prior_start_short} to {prior_end_short}:

{habit_title:padded}    {bar_current}  {percent_current}% (was {percent_prior}%) {trend_arrow}
...

Overall: {overall_percent_current}% (was {overall_percent_prior}%) {trend_arrow}
```

Where:
- `{window_*_short}` are formatted as `Jun 01` etc. (Month-abbr + day).
- `{bar_current}` is a 6-character ASCII bar: `██████` at 100%, `█░░░░░` at ~17%, `░░░░░░` at 0%. Plan-phase decides the exact threshold mapping.
- `{trend_arrow}`: `↑` if current > prior, `↓` if current < prior, `→` if equal. Skipped (NULL) if `percent_prior` is null.
- Padding aligns the bars; precise padding decided in plan-phase contract or implementation.

## Failure render

If the helper exits non-zero (per the helper contract's exit-code table), the agent emits:

```
Sent by felix-admin-habits:sonnet

Weekly report unavailable: <one-line error class + stripped path, e.g., "VikunjaTimeoutError: /projects/13/tasks">
```

NO preamble. NO internal monologue. NO retry within the turn.

## Validation invariants

1. Every habit row satisfies `0 ≤ completed_events_current ≤ scheduled_days_current` IF the data is consistent. If Vikunja returns more completion events than the scheduled count (e.g., a habit completed twice in one day), the helper caps at `scheduled_days_current` AND logs a `weekly_report_anomaly` action (plan-phase decides exact semantics).
2. Percentages are floats; rendered with 0 decimal places in the WhatsApp turn-summary (e.g., `100%`, `83%`, NOT `100.0%`, `83.3%`).
3. The JSON is valid (parseable) at all times — the helper does not emit partial JSON on internal error; it exits non-zero with stderr message instead.

## Plan-phase open items

- Bar-character threshold mapping (e.g., is 50% three bars or four?).
- Trend arrow rendering when `percent_prior` is null (current option: omit).
- Whether to round percentages at the helper layer (floats in JSON, ints rendered) or at the agent layer.
