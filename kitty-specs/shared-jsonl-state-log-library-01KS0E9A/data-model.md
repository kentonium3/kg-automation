# Data Model

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Phase**: 1 (design)

This document defines the on-disk and in-memory data model for the JSONL state log.

---

## In-memory record (Python)

```python
from dataclasses import dataclass
from typing import Optional, Literal

# Type alias — used by validators
Domain = Literal["habits", "escalation", "enrichment"]

@dataclass(frozen=True, slots=True)
class StateLogRecord:
    domain: Domain          # one of the three known domains
    task_id: int            # Vikunja task ID; positive integer
    title: str              # denormalized for human-readable history; non-empty
    date: str               # ISO-8601 date — YYYY-MM-DD; the day this record is FOR
    state: str              # one of the per-domain enum (see below); validated at append
    source: str             # writer identity: "whatsapp", "vikunja-ui", "cron", "manual", ...
    timestamp: str          # ISO-8601 datetime with UTC offset — when WRITTEN
    note: Optional[str] = None  # freeform per-record annotation; default null
```

The dataclass is `frozen=True` to keep records immutable post-construction. `slots=True` keeps memory low when reading large files into memory.

---

## Per-domain state enums

Enforced by `state_log_schema.DOMAIN_STATES` at `append` time:

```python
DOMAIN_STATES: dict[str, frozenset[str]] = {
    "habits": frozenset({"complete", "incomplete", "skipped"}),
    "escalation": frozenset({"triggered", "level-1", "level-2", "resolved", "dismissed"}),
    "enrichment": frozenset({"pending", "enriched", "deferred", "failed"}),
}
```

### Semantics

#### habits

- `complete` — task done for this date (auto-advance triggered in Vikunja, comment mirror written, JSONL recorded)
- `incomplete` — task NOT done for this date (Kent declined / negative WhatsApp reply / missed window). Explicit negative is recorded so downstream analytics can distinguish "skipped intentionally" from "didn't surface".
- `skipped` — task was intentionally skipped by Kent for this date (holiday, illness, travel — non-failure)

#### escalation

- `triggered` — task surfaced for escalation review
- `level-1` — first escalation outreach sent (WhatsApp ping to Kent)
- `level-2` — second escalation (e.g., next-day reminder)
- `resolved` — Kent took action; escalation closed cleanly
- `dismissed` — Kent dismissed the escalation without taking action; closed without resolution

#### enrichment

- `pending` — tasker queued the task for enrichment but hasn't started
- `enriched` — enrichment completed successfully (frontmatter updated, Vikunja comment mirror written)
- `deferred` — tasker chose to defer (e.g., not enough context yet); will retry later
- `failed` — enrichment failed and won't be auto-retried (manual operator action needed)

---

## Required fields

```python
REQUIRED_FIELDS: tuple[str, ...] = (
    "domain", "task_id", "title", "date", "state", "source", "timestamp",
)
# `note` is optional
```

A record missing any of these MUST raise `ValueError` at append time, before any I/O.

---

## Field type contracts

| Field | Type | Constraints | Rejection example |
|---|---|---|---|
| `domain` | `str` | One of `DOMAIN_STATES.keys()` | `"habit"` (typo) |
| `task_id` | `int` | Positive integer | `"14"` (string), `0`, `-5` |
| `title` | `str` | Non-empty after strip | `""`, `"   "` |
| `date` | `str` | Matches `^\d{4}-\d{2}-\d{2}$` and parses via `datetime.date.fromisoformat()` | `"2026/05/19"`, `"05-19-2026"` |
| `state` | `str` | Member of `DOMAIN_STATES[record["domain"]]` | `"complet"`, `"Complete"` |
| `source` | `str` | Non-empty | `""` |
| `timestamp` | `str` | ISO-8601 datetime parsable by `datetime.datetime.fromisoformat()`, MUST contain a timezone offset | `"2026-05-19T11:00:00"` (no TZ), `"now"` |
| `note` | `str` or `None` (optional) | If present, must be `str` or explicitly `None` | `123` (int), `[]` (list) |

Validation error messages MUST quote the offending field name and the rejected value so consumers can immediately fix.

---

## On-disk file layout

### Filesystem location

```
/data/services/openclaw/state/                  # 0775 claude:secondbrain
├── habits-history.jsonl                        # 0664 claude:secondbrain
├── escalation-history.jsonl                    # 0664 claude:secondbrain
└── enrichment-history.jsonl                    # 0664 claude:secondbrain
```

### Line format

One JSON object per line, terminated by `\n`. No leading/trailing whitespace. UTF-8 encoded. Each line is independently parseable — concatenating two lines does NOT produce a valid JSON object (this is a feature: it means line boundaries are byte-aligned).

### Append order

Records are appended in arrival order. The file is read top-to-bottom by `read()`. There is no in-file sorting by date or timestamp — consumers that need a specific order MUST sort the result themselves.

### Idempotency key

The unique key per domain is `(task_id, date, state)`. Re-appending a record whose `(task_id, date, state)` tuple matches an existing line in the SAME domain file is a no-op (no write, no error). This means a task can have multiple records for the same date if the state differs (e.g., `incomplete` then later `complete` for the same date — but `complete` then `complete` again on retry is deduped).

---

## Example records

### Habits — completion

```json
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-19","state":"complete","source":"whatsapp","note":null,"timestamp":"2026-05-19T11:05:11+00:00"}
```

### Habits — skipped (travel day)

```json
{"domain":"habits","task_id":17,"title":"Strength training","date":"2026-05-19","state":"skipped","source":"whatsapp","note":"travel — no gym access","timestamp":"2026-05-19T11:05:22+00:00"}
```

### Escalation — second-day escalation

```json
{"domain":"escalation","task_id":42,"title":"Avetta certificate renewal","date":"2026-05-19","state":"level-2","source":"cron","note":null,"timestamp":"2026-05-19T13:00:01+00:00"}
```

### Enrichment — successful enrich

```json
{"domain":"enrichment","task_id":71,"title":"Tuesday trivia at Tru West","date":"2026-05-19","state":"enriched","source":"cron","note":"recurring weekly added to calendar","timestamp":"2026-05-19T11:01:34+00:00"}
```

### Backfill from Vikunja UI

```json
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-18","state":"complete","source":"vikunja-ui","note":null,"timestamp":"2026-05-19T11:00:03+00:00"}
```

Note: `date` is 2026-05-18 (the day the habit was for), `timestamp` is 2026-05-19 (when the reconciler caught it).

---

## Forward compatibility

Unknown fields in a record are silently ignored on read but are NOT preserved on write (the writer's known schema wins). Consumers MUST NOT depend on round-tripping unknown fields.

Adding a new domain or extending a domain enum is a library-level change (new constant in `DOMAIN_STATES`); existing records with old vocabulary are NOT migrated automatically. If a state value is removed, future reads of old records still surface them (they parse fine — the enum check is on `append`, not on `read`).
