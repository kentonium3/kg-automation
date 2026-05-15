# Contract: `scripts/habits/query_active_habits.py`

**FR**: FR-002 (Active habit query + filter helper)
**Invocation tier**: Helper
**Run frequency**: Once per `habits-morning-checkin` cron invocation

---

## Purpose

Query the Vikunja "Habits" project, parse each task's frequency descriptor from its description field, apply the project's frequency-table rules (Daily, Daily (evening), Mon-Sat, Mon/Wed/Fri, etc.), exclude paused/done tasks, and return the subset scheduled for the input day.

Exists because the current agent prompt encodes a markdown frequency table that the LLM has to read and apply at runtime — high-criticality (wrong filter yields wrong habits in WhatsApp), high hallucination risk (table-parsing in-prompt).

---

## CLI

```
python3 scripts/habits/query_active_habits.py --day <Mon|Tue|Wed|Thu|Fri|Sat|Sun>
                                              [--vikunja-token-path <path>]
                                              [--vikunja-base-url <url>]
```

| Flag | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `--day` | string | YES | — | One of `Mon`,`Tue`,`Wed`,`Thu`,`Fri`,`Sat`,`Sun`. Typically from `compute_today.py` output. |
| `--vikunja-token-path` | path | No | `/data/services/openclaw/secrets/vikunja-api` | Override for testing. |
| `--vikunja-base-url` | URL | No | `https://office2.tail0f5f56.ts.net/api/v1` | Override for testing. |

---

## Output

### stdout (JSON object, then SUMMARY line)

```json
{
  "habits": [
    {"id": 123, "title": "Meditate 45 min", "description": "Daily", "due_date": "2026-05-15T23:59:59-04:00"},
    {"id": 124, "title": "Strength training 45 min", "description": "Mon/Wed/Fri", "due_date": null}
  ],
  "total_in_project": 12,
  "scheduled_today": 2
}
```

```
SUMMARY: total=12 scheduled=2 paused=3 done=5 unrecognized_freq=2
```

**Field contract:**
- `habits`: ordered list of habits scheduled for the input day, excluding paused/done. Each item has `id`, `title`, `description`, `due_date` (current value; may be null or stale; `set_due_dates.py` updates it).
- `total_in_project`: total count of tasks in the Habits project (for SUMMARY/observability)
- `scheduled_today`: count of habits in the returned list

Order of habits: sorted by `id` ascending (deterministic for downstream tests).

### stderr

Used for warnings on unrecognized frequency descriptors (one warn line per habit skipped):

```
WARN: task 145 "Some habit" has unrecognized frequency 'Twice weekly'; skipped
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (any number of habits returned, including zero) |
| 1 | Operational error (Vikunja unreachable, auth failed, project not found) |
| 2 | Usage error (invalid `--day` value, malformed flags) |

---

## Side effects

Read-only. No Vikunja state mutations. Idempotent by definition.

---

## Frequency descriptor lexicon

Per [`data-model.md`](../data-model.md#habit) — canonical table from current AGENTS.md preserved verbatim:

| Pattern (case-insensitive) | Scheduled days |
|---|---|
| `Daily` | All 7 |
| `Daily (evening)` | All 7 |
| `Mon-Sat` or `Mon–Sat` (en-dash variant) | Mon, Tue, Wed, Thu, Fri, Sat |
| `Mon/Wed/Fri` | Mon, Wed, Fri |
| Anything else | Skip with stderr WARN |

Pattern matching is by exact substring after stripping leading/trailing whitespace and `(PAUSED)` markers. Future frequency additions extend this lexicon explicitly.

---

## Test coverage (NFR-005)

Tests at `tests/habits/test_query_active_habits.py`:

| Test | Scenario |
|---|---|
| `test_daily_all_seven_days` | Mock Vikunja: 1 task w/ "Daily"; verify it's in result for every input day |
| `test_mon_sat_excludes_sunday` | Mock Vikunja: 1 task w/ "Mon-Sat"; verify excluded on Sunday |
| `test_mon_wed_fri_only_three_days` | Mock: 1 task w/ "Mon/Wed/Fri"; verify in/out on each day |
| `test_paused_excluded` | Mock: 1 task w/ `(PAUSED)` in description; never in result |
| `test_done_excluded` | Mock: 1 task w/ `done: true`; never in result |
| `test_unrecognized_freq_skipped_with_warning` | Mock: 1 task w/ "Twice weekly"; not in result, stderr has WARN |
| `test_empty_project` | Mock: 0 tasks in project; exit 0, `habits: []` |
| `test_vikunja_unreachable` | Mock: connection error; exit 1, error to stderr |
| `test_invalid_day_arg` | `--day Funday`; exit 2 |
