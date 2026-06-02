# Phase 1 — Data Model

**Mission**: `habit-day-specific-scheduling-01KT48Y6`
**Source**: [`spec.md`](./spec.md) §7 Key Entities + [`research.md`](./research.md)

This document defines the canonical entities, their fields, validation rules, and persistence boundaries for this mission.

---

## E1 — Habit schedule entry (config-time)

A declarative entry binding one Vikunja task to its scheduling metadata.

| Field | Type | Required | Description |
|---|---|---|---|
| `task_id` | int | ✓ | Vikunja task identifier (the same id used by `set_due_dates.py` and the existing helpers). |
| `title` | str | ✓ | Display title (mirrors Vikunja's title for human readability in the YAML). |
| `designated_weekdays` | list[enum `{"Mon","Tue","Wed","Thu","Fri","Sat","Sun"}`] | ✗ | If set, habit is **day-specific** and appears in the morning check-in only on the listed weekdays. If absent or empty list, habit is **daily** (every day). |
| `repeat_after_seconds` | int | ✓ (per existing schedule shape) | Vikunja-native repeat interval (existing field; unchanged by this mission). |
| (other existing fields) | various | per existing schedule | Mission #282's existing schedule fields preserved. |

**Storage**: `scripts/habits/migrations/phase3-schedule.yaml` (existing file, extended in place).

**Validation rules**:
- `designated_weekdays` if present must be a list of valid three-letter ISO weekday abbreviations. Duplicates are silently deduped; unknown values are a load-time error.
- A habit with `designated_weekdays` set should have `repeat_after_seconds` = 604800 (7 days) for single-day cycles or a multiple of 86400 for multi-day cycles. (Cross-validation warning, not a hard error.)

---

## E2 — Morning check-in artifact (existing, lightly extended)

The per-date artifact written by `morning_checkin_list.py` capturing what was delivered to Kent's WhatsApp.

| Field | Type | Required | Description |
|---|---|---|---|
| `checkin_date_et` | str (YYYY-MM-DD) | ✓ | The ET date the check-in was delivered. |
| `delivered_at_utc` | str (ISO 8601 with `Z`) | ✓ | UTC timestamp of delivery. |
| `habits_listed[]` | list of `{task_id, title, designated_weekdays?}` | ✓ | The habits included in the delivered message. **Extension**: `designated_weekdays` is recorded on each entry so the sweeper can recall what was day-specific. |
| (other existing fields) | various | per existing helper | Existing morning-checkin shape preserved. |

**Storage**: `/data/services/openclaw/state/habits/morning-checkin-<date>.json` (existing path).

**Validation rules (new for this mission)**:
- Every entry's `task_id` exists in the active schedule at the time of delivery.
- Day-specific habits in `habits_listed[]` MUST have their designated weekday include the check-in's ET weekday (FR-002 enforced at delivery time).

---

## E3 — `habits-history.jsonl` event (existing, new event_type added)

Append-only event log; each line is one event.

| Field | Type | Required | Description |
|---|---|---|---|
| `event_type` | str | ✓ | Existing values (`completed`, `skipped`, etc.) plus new `auto_skipped`. |
| `task_id` | int | ✓ | The habit's Vikunja task id. |
| `original_checkin_date_et` | str (YYYY-MM-DD) | ✓ for `auto_skipped` | The date of the morning-checkin artifact the habit appeared in. |
| `original_designated_weekday` | str (three-letter ISO) | ✓ for `auto_skipped` when habit was day-specific | The designated weekday on `original_checkin_date_et`. Null/absent if daily. |
| `tick_id` | str (ULID) | ✓ for `auto_skipped` | The sweeper tick that generated the event (for traceability). |
| `recorded_at_utc` | str (ISO 8601 with `Z`) | ✓ | When the event was appended. |
| (other existing fields) | various | per existing readers | Existing JSONL schema preserved. |

**Storage**: `/data/services/openclaw/state/habits-history.jsonl` (existing path, append-only).

**Backwards-compatibility**: existing readers MUST tolerate the new `event_type` value (either by filtering on known types or by treating `auto_skipped` as a no-op). Plan-phase research item: verify the existing reader (likely `exclude_completed_v2.py`) handles unknown event types gracefully. If not, that reader gains an explicit `auto_skipped` case (treated identically to `skipped` for exclude-completed purposes).

---

## E4 — Sweeper tick record (new)

The structured per-tick artifact written by the sweeper.

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | int | ✓ | 1 today. |
| `tick_id` | str (ULID) | ✓ | Unique per tick. |
| `started_at_utc` | str (ISO 8601 with `Z`) | ✓ | Sweeper start. |
| `duration_ms` | int | ✓ | Wall-clock total. |
| `dry_run` | bool | ✓ | True when `--dry-run` flag passed; false in normal production. |
| `expired_checkin_dates_evaluated[]` | list[str] (YYYY-MM-DD) | ✓ | Which morning-checkin dates the sweeper considered "older than 48 hours, candidates for auto-skip." |
| `habits_evaluated[]` | list of `{task_id, original_checkin_date_et, status}` | ✓ | All habits the sweeper saw, with their resolution status. `status ∈ {"completed_in_window", "skipped_in_window", "already_auto_skipped", "auto_skipped_this_tick", "deferred_outside_48hr"}`. |
| `habits_auto_skipped[]` | list of `{task_id, original_checkin_date_et, original_designated_weekday, new_due_date_et}` | ✓ | The subset of habits this tick newly marked `auto_skipped`. `new_due_date_et` populated only for day-specific (the advanced Vikunja due_date). |
| `errors[]` | list of `{task_id, error_type, error_message}` | ✓ | Per-habit errors. Empty list = clean tick. |
| `exit_status` | enum `{"success", "partial", "failure"}` | ✓ | `partial` when some habits errored but the tick ran to completion. `failure` for cycle-aborting errors. |

**Storage**: `/data/services/openclaw/state/habits/sweeper-tick-<date>.json` (newest tick per date; if a tick re-runs same date, it overwrites). Append-only ledger at `/data/services/openclaw/state/habits/sweeper-ledger.jsonl` (one JSON line per tick).

---

## E5 — Reconciliation record (new, from FR-010 `--reconcile-schedule` flag on `set_due_dates.py`)

When the operator runs `set_due_dates.py --reconcile-schedule`, a record is written.

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | int | ✓ | 1. |
| `reconciled_at_utc` | str (ISO 8601 with `Z`) | ✓ | When the operator ran the command. |
| `operator` | str | ✓ | The active gh identity at run time (sanity for audit; not enforcement). |
| `schedule_file_sha256` | str | ✓ | Hash of the schedule.yaml at reconciliation time. |
| `habits_reconciled[]` | list of `{task_id, old_designated_weekdays, new_designated_weekdays, old_due_date, new_due_date}` | ✓ | What changed. |
| `errors[]` | list of `{task_id, error_type, error_message}` | ✓ | |

**Storage**: `/data/services/openclaw/state/habits/reconcile-<datetime>.json` (one file per reconciliation run; `<datetime>` is the UTC ISO datetime with seconds, e.g., `reconcile-2026-06-02T18-45-00Z.json`).

---

## Relationships

```
Habit schedule entry (E1, config-time)
   └─→ defines day-of-week metadata for each Vikunja habit
            │
            ▼
Morning check-in artifact (E2, per-date)
   └─→ records what was delivered, including which entries were day-specific
            │
            ▼ (48hr later)
Sweeper tick record (E4, per-tick)
   └─→ reads expired check-in artifacts + reply state, decides who to auto-skip
            │
            ▼
habits-history.jsonl event (E3, append-only)
   └─→ auto_skipped events recorded; existing reader excludes them from future check-ins
            │
            ▼
Reconciliation record (E5, on-operator-action)
   └─→ recorded when operator changes schedule mid-week
```

---

## State transitions

### Habit response state (per check-in occurrence)

```
[checkin appearance]
     │
     │ Kent replies within 48hr:
     ├─→ [resolved: completed] (habits-history: completed event)
     ├─→ [resolved: skipped]   (habits-history: skipped event)
     │
     │ Kent doesn't reply within 48hr:
     └─→ sweeper tick 48hr after delivery → [resolved: auto_skipped]
              │ (habits-history: auto_skipped event)
              │ if day-specific: Vikunja due_date advanced to next designated weekday
              │ if daily: no due_date change (existing Vikunja repeat handles next day)
```

### Sweeper idempotency

Re-running the sweeper for the same `(task_id, original_checkin_date_et)` MUST be a no-op (FR-005). Detection: scan habits-history.jsonl for an existing `auto_skipped` event matching the pair; if present, skip.

---

## Why these entities and not others

- **No "Reply correlation" entity in the data model**: how the parser correlates an inbound reply to a specific check-in artifact is captured in `parse_morning_reply.py`'s test surface, not as persisted state. The 48hr window is a runtime check at parse time.
- **No "Schedule change event" entity**: schedule changes are git-versioned (the YAML file is checked in). The reconciliation record (E5) captures the operator's reconciliation action; the schedule's history lives in git.
