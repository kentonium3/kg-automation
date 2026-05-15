# Contract: `scripts/habits/compute_today.py`

**FR**: FR-001 (TZ-aware date / day helper)
**Invocation tier**: Helper (per [conventions § 9](../../../docs/design/helper-script-conventions.md))
**Run frequency**: Once per `habits-morning-checkin` cron invocation (currently daily; future weekly)

---

## Purpose

Compute today's day-of-week, date, current Eastern Time UTC offset, and end-of-day-ET ISO timestamp. Output is consumed by subsequent helpers (`query_active_habits.py` takes `--day`; `set_due_dates.py` takes `--iso-eod-et`).

This helper exists because the agent's prompt currently encodes the rule "use `TZ=America/New_York`, never UTC; recognize that 8 PM ET has already rolled over in UTC" — a high-criticality block (wrong day yields wrong habits in Kent's WhatsApp) that's hallucination-prone in-prompt.

---

## CLI

```
python3 scripts/habits/compute_today.py [--now-utc <ISO-8601>]
```

| Flag | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `--now-utc` | ISO-8601 string | No | current UTC time | Override for testing (allows fixed-time test cases for DST/EST transitions, after-8-PM-ET edge cases) |

No structured input (no stdin, no `@file` references). All input via flags.

---

## Output

### stdout (single JSON line, then SUMMARY line)

```json
{"day": "Wed", "date": "2026-05-15", "et_offset": "-04:00", "iso_eod_et": "2026-05-15T23:59:59-04:00"}
```

```
SUMMARY: day=Wed date=2026-05-15 et_offset=-04:00
```

**Field contract:**
- `day`: three-letter day abbreviation; one of `Mon|Tue|Wed|Thu|Fri|Sat|Sun`
- `date`: `YYYY-MM-DD` in Eastern time
- `et_offset`: `-04:00` (EDT) or `-05:00` (EST). Computed from `zoneinfo.ZoneInfo("America/New_York")` applied to `now_utc`
- `iso_eod_et`: `YYYY-MM-DDT23:59:59<ET_OFFSET>` — **MUST NOT** end with `Z` (per #112 regression-prevention)

### stderr

Used only for warnings/errors. Empty under happy path.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Operational error (zoneinfo data unavailable on host; rare) |
| 2 | Usage error (malformed `--now-utc` value) |

---

## Side effects

None. Pure computation. Idempotent by definition.

---

## Test coverage (NFR-005)

Tests at `tests/habits/test_compute_today.py`:

| Test | Scenario | Why |
|---|---|---|
| `test_typical_weekday` | `--now-utc 2026-05-15T11:00:00Z` (7 AM ET) | Happy path |
| `test_after_8pm_et` | `--now-utc 2026-05-16T01:00:00Z` (9 PM ET prev day) | Verifies date doesn't roll over with UTC (issue #112 class) |
| `test_dst_transition` | `--now-utc 2026-03-09T07:00:00Z` (DST starts in US) | Verifies offset flips `-05:00` → `-04:00` |
| `test_est_transition` | `--now-utc 2026-11-02T07:00:00Z` (DST ends in US) | Verifies offset flips `-04:00` → `-05:00` |
| `test_iso_eod_no_z_suffix` | Any input | Asserts output `iso_eod_et` does not end with `Z` |
| `test_malformed_now_utc` | `--now-utc not-a-date` | Verifies exit code 2 |
