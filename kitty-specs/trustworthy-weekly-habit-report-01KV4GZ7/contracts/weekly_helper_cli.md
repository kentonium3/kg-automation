# Contract: `scripts/habits/query_active_habits_weekly.py` (Weekly Helper CLI)

**Entry point**: `python3 -m scripts.habits.query_active_habits_weekly [args]`
**Purpose**: Generate the WeeklyHabitReport JSON document (with rendered text) for the prior 7-day window. Single source of truth for the felix-admin-habits weekly tick.

## CLI surface

```
usage: query_active_habits_weekly.py [-h]
                                      [--as-of AS_OF]
                                      [--output {json,text}]

Generate the weekly habit report. Reads canonical habits-history.jsonl;
does NOT query Vikunja done_at for completion history.

optional arguments:
  --as-of AS_OF       Reference datetime (ISO 8601, tz-aware) for the
                      report window. Defaults to current wall clock.
                      Window = [as_of - 7 days @ 00:00 ET, as_of @ 00:00 ET).
                      Tests use this for deterministic golden-week fixture.
  --output            'json' (default) emits WeeklyHabitReport. 'text' emits
                      just the rendered_text field.
```

## Inputs

| Source | Read via | Purpose |
| --- | --- | --- |
| `habits-history.jsonl` | `scripts.habits.history` (IC-01 wrapper) | Completion records for the window |
| Vikunja project 13 task list | `scripts.common.vikunja_client.VikunjaClient.get_tasks(...)` | Habit titles, classification (current-state ONLY; not done_at) |
| `--as-of` arg | argparse | Reference datetime for windowing |

The Vikunja query is current-state only (which habits exist, their titles, their `repeat_after` for classification). It does NOT read `done_at`. This is allowlisted in the IC-03 architectural test as a current-state usage.

## Output: WeeklyHabitReport JSON (extended)

```json
{
  "report_date": "2026-06-15",
  "window_start": "2026-06-08",
  "window_end": "2026-06-14",
  "per_habit": [
    {
      "title": "Get steps in today",
      "classification": "daily",
      "current_pct": 0.57,
      "prior_pct": 0.71,
      "trend": "down"
    },
    {
      "title": "Strength training — Monday",
      "classification": "day-specific",
      "current_pct": 1.0,
      "prior_pct": 0.0,
      "trend": "up"
    }
  ],
  "overall": {
    "current_pct": 0.43,
    "prior_pct": 0.38,
    "trend": "up"
  },
  "rendered_text": "*This week* (Jun 8–14):\n\nGet steps in today — 57% (was 71%) ↓\n..."
}
```

### Field rules

- `report_date`: the Monday on which the report is generated, in ET.
- `window_start`: prior Monday (inclusive), ET.
- `window_end`: prior Sunday (inclusive), ET.
- `per_habit[]`: one entry per active habit in Vikunja project 13.
- `per_habit[].current_pct`: 0.0–1.0 float from IC-01 wrapper.
- `per_habit[].prior_pct`: 0.0–1.0 float for the window preceding `window_start`.
- `per_habit[].trend`: `"up"` if current > prior, `"down"` if current < prior, `"flat"` otherwise.
- `overall.*`: arithmetic mean of `per_habit[].current_pct` (and prior).
- `rendered_text`: pure function of all other fields. NFR-004 determinism.

### Rendered text format (matches existing production message)

```
*This week* ({short_window}):

{title} — {pct}% (was {prior_pct}%) {arrow}
...

*Overall: {overall_pct}%* (was {prior_overall_pct}%) {overall_arrow}
```

Where:
- `{short_window}` is e.g. `"Jun 8–14"` — 7 days, NOT 8 (FR-006). Use `"%b %-d"` for the start (or `"%b %d"` with leading zero strip) and `"%-d"` for the end if same month, else `"%b %-d"`.
- `{pct}` is `round(current_pct * 100)`.
- `{arrow}` is `↑` for up, `↓` for down, `` (empty) for flat.

## Failure surface

| Failure | Exit code | stderr | Agent behavior (per AGENTS.md) |
| --- | --- | --- | --- |
| `habits-history.jsonl` unreadable | 1 | error class + path | Render `Weekly report unavailable: <class> <path>` to WhatsApp; halt tick |
| Vikunja unavailable for habit list | 1 | error class | Same |
| Schema validation failure on a JSONL record | 1 | record locator | Same |
| Internal contract violation (e.g. classification not in {daily, day-specific, week-bounded}) | 2 | which contract | Same |

## Determinism contract

- Same `habits-history.jsonl` byte content + same Vikunja tasks response + same `--as-of` → byte-identical JSON output AND byte-identical `rendered_text` (NFR-001 + NFR-004).
- Test approach: stub Vikunja with fixture JSON; use golden `habits-history.jsonl` fixture; assert byte equality of `--output json` and `--output text`.

## What changed vs the prior contract

- Data source for completion history flipped from Vikunja `done_at` to `habits-history.jsonl` (FR-002).
- `rendered_text` added as optional top-level field (FR-005, FR-007 backward-compat).
- Window label corrected: 7 days, not 8 (FR-006).
- `--as-of` flag added for testability and DST-safe windowing.
- VikunjaClient import retained for current-state title/classification only — allowlisted in IC-03.
