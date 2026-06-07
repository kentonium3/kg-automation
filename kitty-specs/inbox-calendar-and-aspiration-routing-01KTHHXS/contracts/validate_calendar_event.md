# Contract: `validate_calendar_event.py` helper

**Mission**: `inbox-calendar-and-aspiration-routing-01KTHHXS`
**Spec FR**: FR-003, FR-004, FR-006 | **Data model**: [`data-model.md` — ExtractedCalendarBlock](../data-model.md#entity-extractedcalendarblock-transient-in-capture) → [CalendarEventPayload](../data-model.md#entity-calendareventpayload-transient-capture--felix-main)

## Purpose

Deterministically validate that an `ExtractedCalendarBlock` carries all fields required to create a Google Calendar event, and produce either (a) a ready-to-invoke `gog calendar create` argument list, or (b) a structured `missing_fields` array enumerating what's absent.

Implements Felix Constitution Directive 6 (scripts vs LLM split): the LLM's job is field extraction from natural language; this helper's job is deterministic validation, datetime parsing, RRULE conversion, and gog-arg assembly.

## Invocation

```bash
python3 scripts/calendar/validate_calendar_event.py < /tmp/block.json
```

or

```bash
echo "<extracted block JSON>" | python3 scripts/calendar/validate_calendar_event.py
```

Reads JSON from stdin. Emits JSON to stdout. Returns exit code 0 on successful processing (regardless of `complete: true|false`), non-zero on malformed input or internal error.

## Input schema (stdin JSON)

```json
{
  "title": "<string, required>",
  "start_natural": "<string, required>",
  "end_natural": "<string|null>",
  "duration_natural": "<string|null>",
  "location": "<string|null>",
  "recurrence_natural": "<string|null>",
  "attendees": ["<string>", ...] | null,
  "source_inbox_path": "<string, required>",
  "source_block_index": "<int, required>",
  "tick_iso": "<string, ISO 8601, required>"
}
```

`tick_iso` is the capture-tick "now" timestamp injected by the caller so that relative phrases ("tomorrow", "next Tuesday") resolve against the cron tick's reference time, not the helper's wall clock. Helper purity.

## Output schema (stdout JSON)

### Complete event

```json
{
  "complete": true,
  "missing_fields": [],
  "calendar_event_payload": {
    "action": "create_calendar_event",
    "calendar_id": "primary",
    "account": "kent@intentional.biz",
    "summary": "<title>",
    "start_rfc3339": "<RFC 3339 string with TZ>",
    "end_rfc3339": "<RFC 3339 string with TZ>",
    "start_timezone": "America/New_York",
    "location": "<verbatim location or null>",
    "description": "Source: <inbox basename>",
    "rrule": "<RRULE string or null>",
    "attendees": ["<email>", ...] | null,
    "source_inbox_path": "<absolute path>"
  }
}
```

### Incomplete event

```json
{
  "complete": false,
  "missing_fields": ["start_datetime", "end_or_duration", "recurrence_pattern"],
  "fields_so_far": { ... echo of parseable input fields ... }
}
```

Recognized missing-field tokens:
- `"start_datetime"` — when start_natural is absent or unparseable
- `"end_or_duration"` — when both end_natural and duration_natural are absent or unparseable
- `"recurrence_pattern"` — when recurrence_natural is present but doesn't match any supported pattern (per R-007); absent otherwise (no recurrence is valid)
- `"title"` — when title is absent

## Recurrence patterns supported

Per R-007:

| Natural-language shape | RRULE output |
|---|---|
| "every Tuesday" / "weekly on Tuesday" / "Tuesdays" | `RRULE:FREQ=WEEKLY;BYDAY=TU` |
| "every Tuesday and Thursday" | `RRULE:FREQ=WEEKLY;BYDAY=TU,TH` |
| "every other week" / "biweekly on Tuesday" | `RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=TU` |
| "monthly on the 15th" / "every month on the 15th" | `RRULE:FREQ=MONTHLY;BYMONTHDAY=15` |
| "first Monday of the month" | `RRULE:FREQ=MONTHLY;BYDAY=1MO` |
| "last Friday of the month" | `RRULE:FREQ=MONTHLY;BYDAY=-1FR` |
| "second Tuesday and fourth Thursday of the month" | `RRULE:FREQ=MONTHLY;BYDAY=2TU,4TH` |

Anything outside this set → `missing_fields: ["recurrence_pattern"]`.

## Datetime parsing

- Standard library `datetime`. No external dependency.
- Recognized natural-language anchors: "today", "tomorrow", "next [weekday]", "this [weekday]", explicit ISO ("2026-06-08"), American format ("June 8, 2026" / "6/8/2026"), shorthand ("Tue 6/8").
- Recognized time formats: 12h ("2pm", "2:30 PM", "noon", "midnight"), 24h ("14:00").
- Timezone: assumes `America/New_York` (Kent's tz; documented in service-inventory.json under the host record).
- All output start/end as RFC 3339 with explicit offset.

## Failure handling

- Malformed input JSON → exit 2, stderr: `INVALID_INPUT_JSON: <detail>`
- Missing required field in input (title/start_natural/source_inbox_path/source_block_index/tick_iso) → exit 3, stderr: `MISSING_INPUT_FIELD: <field>`
- Internal exception (should not happen) → exit 4, stderr: `INTERNAL_ERROR: <traceback>`
- Normal `complete: true|false` outputs → exit 0

## Idempotency + purity

- Pure function: same input → same output.
- No filesystem reads or writes beyond stdin/stdout.
- No network calls.
- No env-var reads (uses caller-provided `tick_iso`, not wall-clock `now()`).
- No subprocess calls (no `gog` invocation; output is the arg list, caller invokes gog).

## Test fixtures (Phase 1 design)

The validator's tests in `tests/calendar/test_validate_calendar_event.py` exercise:

- `tests/calendar/fixtures/complete_oneoff.json` — one-shot event with explicit start + end
- `tests/calendar/fixtures/complete_oneoff_duration.json` — one-shot event with duration instead of end
- `tests/calendar/fixtures/complete_weekly.json` — weekly recurrence (trivia night case)
- `tests/calendar/fixtures/complete_biweekly.json` — biweekly recurrence
- `tests/calendar/fixtures/complete_monthly_by_dayofmonth.json` — monthly on the 15th
- `tests/calendar/fixtures/complete_byweekday_of_month.json` — first Monday of the month
- `tests/calendar/fixtures/incomplete_no_start.json` — missing start_natural
- `tests/calendar/fixtures/incomplete_no_end.json` — missing both end and duration
- `tests/calendar/fixtures/incomplete_recurrence_unrecognized.json` — exotic pattern like "every other Tuesday in February"
- `tests/calendar/fixtures/edge_dst_transition.json` — event crossing DST boundary
- `tests/calendar/fixtures/edge_relative_anchor_resolution.json` — "next Tuesday" resolution against tick_iso

Coverage target: ≥90% line, ≥85% branch on `scripts/calendar/validate_calendar_event.py`.
