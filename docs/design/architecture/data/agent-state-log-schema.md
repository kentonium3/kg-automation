---
title: Agent State Log Schema
doc_type: reference
status: approved
audience: agents_and_humans
level: reference
owners: [kent]
last_validated: 2026-05-19
---

# Agent State Log Schema

## Purpose

The canonical JSONL state-log schema shared by every Vikunja-touching Felix
agent, per [ADR-0002 Q5-C](../adr/0002-felix-vikunja-task-model.md). One
append-only JSONL file per domain under `/data/services/openclaw/state/`
records the discrete state transitions Kent and Felix care about for habits,
escalation, and enrichment. Producers write through the
[`scripts.common.state_log`](../../../../scripts/common/state_log.py) library
(or its `python3 -m` CLI); consumers either call `read()` or use line-oriented
shell tools (`jq`, `grep`) directly against the files.

This doc is the public contract — the dataclass and `DOMAIN_STATES` constant
in code are the source of truth, and this document mirrors them.

## File layout

```
/data/services/openclaw/state/                  # 0775 claude:secondbrain
├── habits-history.jsonl                        # 0664 claude:secondbrain
├── escalation-history.jsonl                    # 0664 claude:secondbrain
└── enrichment-history.jsonl                    # 0664 claude:secondbrain
```

- One JSON object per line, terminated by `\n` (LF). UTF-8, no BOM.
- Append-only in normal operation; the library never rewrites or truncates.
- Lines are independently parseable — `jq -c .`, `grep`, `head`, `tail`, and
  `wc -l` all work.
- The last line may or may not end with `\n` if a process was killed
  mid-append; tools must handle both cases.

## Record schema

| Field | Type | Required | Constraints | Rejection example |
|---|---|---|---|---|
| `domain` | string | yes | Member of `DOMAIN_STATES.keys()`; matches the file name | `"habit"` (typo) |
| `task_id` | integer | yes | Positive integer (Vikunja task ID) | `"14"` (string), `0`, `-5` |
| `title` | string | yes | Non-empty after strip; denormalized for human readability | `""`, `"   "` |
| `date` | string | yes | ISO-8601 `YYYY-MM-DD`; parses via `datetime.date.fromisoformat()` | `"2026/05/19"`, `"05-19-2026"` |
| `state` | string | yes | Member of `DOMAIN_STATES[record["domain"]]` | `"complet"`, `"Complete"` |
| `source` | string | yes | Non-empty writer identity: `"whatsapp"`, `"vikunja-ui"`, `"cron"`, `"manual"`, ... | `""` |
| `timestamp` | string | yes | ISO-8601 datetime parsable by `datetime.datetime.fromisoformat()`; MUST include a timezone offset | `"2026-05-19T11:00:00"` (no TZ) |
| `note` | string or null | no | If present, must be `str` or explicitly `None`; default `null` | `123` (int), `[]` (list) |

Validation error messages quote the offending field name and value so
consumers can immediately fix.

Adding a new optional field is non-breaking. Renaming or removing a required
field is breaking and requires a coordinated migration plus a one-off file
rewrite.

## Per-domain state enums

The library enforces these enums at `append()` time via
`DOMAIN_STATES: dict[str, frozenset[str]]`.

### habits

| State | Meaning |
|---|---|
| `complete` | Task done for this date (auto-advance triggered in Vikunja, comment mirror written, JSONL recorded). |
| `incomplete` | Task explicitly NOT done for this date (Kent declined / negative WhatsApp reply / missed window). Captured so downstream analytics distinguish "skipped intentionally" from "didn't surface". |
| `skipped` | Task intentionally skipped by Kent for this date (holiday, illness, travel — non-failure). |

### escalation

| State | Meaning |
|---|---|
| `triggered` | Task surfaced for escalation review. |
| `level-1` | First escalation outreach sent (WhatsApp ping to Kent). |
| `level-2` | Second escalation (e.g., next-day reminder). |
| `resolved` | Kent took action; escalation closed cleanly. |
| `dismissed` | Kent dismissed the escalation without taking action; closed without resolution. |

### enrichment

| State | Meaning |
|---|---|
| `pending` | Tasker queued the task for enrichment but has not started. |
| `enriched` | Enrichment completed successfully (frontmatter updated, Vikunja comment mirror written). |
| `deferred` | Tasker chose to defer (e.g., not enough context yet); will retry later. |
| `failed` | Enrichment failed and will not be auto-retried (manual operator action needed). |

Adding a new state value to an existing enum is non-breaking IF consumers
handle unknown states gracefully (display as-is, do not crash). Adding a new
domain is non-breaking — a new file appears under `/data/services/openclaw/state/`,
existing files are untouched.

## Idempotency contract

The dedup unique key per domain file is the tuple `(task_id, date, state)`.
Re-appending a record whose tuple already matches an existing line in the
same domain file is a silent no-op — no exception, no write. A task can have
multiple records for the same date if the state differs (for example,
`incomplete` then later `complete` for the same date), but `complete` then
`complete` again on retry is deduped.

Operators repairing files manually MUST preserve this invariant. Running
`sort -u` is NOT safe because it does not understand the JSON structure; use
the library or a JSON-aware deduper.

## Example records

```json
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-19","state":"complete","source":"whatsapp","note":null,"timestamp":"2026-05-19T11:05:11+00:00"}
```

```json
{"domain":"habits","task_id":17,"title":"Strength training","date":"2026-05-19","state":"skipped","source":"whatsapp","note":"travel — no gym access","timestamp":"2026-05-19T11:05:22+00:00"}
```

```json
{"domain":"escalation","task_id":42,"title":"Avetta certificate renewal","date":"2026-05-19","state":"level-2","source":"cron","note":null,"timestamp":"2026-05-19T13:00:01+00:00"}
```

```json
{"domain":"enrichment","task_id":71,"title":"Tuesday trivia at Tru West","date":"2026-05-19","state":"enriched","source":"cron","note":"recurring weekly added to calendar","timestamp":"2026-05-19T11:01:34+00:00"}
```

Backfill from Vikunja UI — `date` is the day the habit was for, `timestamp`
is when the reconciler caught it:

```json
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-18","state":"complete","source":"vikunja-ui","note":null,"timestamp":"2026-05-19T11:00:03+00:00"}
```

## Library reference

- Python module: `scripts/common/state_log.py`
- Schema constants and validator: `scripts/common/state_log_schema.py`
- Python API contract: [`contracts/api.md`](../../../../kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/api.md)
- CLI contract: [`contracts/cli.md`](../../../../kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/cli.md)
- JSONL on-disk format contract: [`contracts/jsonl.md`](../../../../kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/jsonl.md)
- Mission spec & plan: [`spec.md`](../../../../kitty-specs/shared-jsonl-state-log-library-01KS0E9A/spec.md), [`plan.md`](../../../../kitty-specs/shared-jsonl-state-log-library-01KS0E9A/plan.md)
- Design intent: [ADR-0002 — Felix ↔ Vikunja task model](../adr/0002-felix-vikunja-task-model.md)

## Reading via shell tools

```bash
# All records as parsed objects (one per line)
jq -c . < habits-history.jsonl

# Records for task 14
jq -c 'select(.task_id == 14)' < habits-history.jsonl

# Just the dates
jq -r '.date' < habits-history.jsonl | sort -u

# Records where state is "skipped"
jq -c 'select(.state == "skipped")' < habits-history.jsonl

# Count records per state
jq -r '.state' < habits-history.jsonl | sort | uniq -c
```

These work stably across the library's v0 lifecycle because the library
guarantees the JSON shape on disk.
