# Data Model: All-Day Fallback for Unanswered Clarifications

Phase 1 output. Entities, the extended record schema, the all-day block/payload
shapes, and the eligibility/state transitions.

## Entity: PendingClarification (extended)

Stored as a JSON array element in
`/data/services/openclaw/state/pending-calendar-clarifications.json`.

| Field | Type | Existing? | Meaning |
|---|---|---|---|
| `note_filename` | str (basename) | existing | The inbox note awaiting an answer |
| `partial_payload` | object | existing | What's known about the appointment |
| `created_at` | ISO-8601 `Z` | existing | When the clarification was recorded (drives 24h age-out) |

### `partial_payload` — extended keys (add-time)

| Key | Type | New? | Meaning / source |
|---|---|---|---|
| `title` | str | existing | Event title (from `validate` `fields_so_far`) |
| `missing_fields` | list[str] | **new** | The eligibility signal — e.g. `["start_time"]` (from `validate` output). Absent ⇒ **not eligible**. |
| `start_date` | str `YYYY-MM-DD` | **new** | The **resolved** date, computed once at capture time by `validate` (`start_dt.date().isoformat()`). Absent ⇒ **not eligible**. |
| `start_natural` | str | existing | NL string ("Thursday") — retained for context but **NOT** used to derive the date at sweep time (week-drift). |

**Backward-compatibility (C-002)**: records written before this feature carry
neither `missing_fields` nor `start_date`. The eligibility gate treats their
absence as **not eligible**, so a legacy in-flight record follows today's
delete-and-release path. No migration; no crash.

## Eligibility predicate (deterministic)

A **aged-out** record (`created_at` ≥ 24h old) is **fallback-eligible** iff:

```
timing-only gap:
      title present
  AND partial_payload.start_date is a well-formed YYYY-MM-DD
  AND "start_time" in partial_payload.missing_fields
  AND partial_payload.missing_fields is a subset of {"start_time", "end_or_duration"}
```

- **Corrected per Codex HIGH-1/HIGH-2**: an exact `== ["start_time"]` test is
  wrong — the canonical "Meet Rob Thursday" (no duration) yields
  `["start_time","end_or_duration"]` and would be wrongly excluded. A missing
  `end_or_duration` is acceptable for an all-day event, so the gate accepts it.
- Missing **title**, or any **non-timing** field in `missing_fields`, or an
  absent/malformed `start_date` → **not eligible** (fail-closed).
- Pin the exact `missing_fields` vocabulary against `validate`'s real output at
  IC-01/IC-03.

Ineligible aged-out records → **delete-and-release** (unchanged).

## Derived: all-day calendar block plan

The sweep-finalize path builds a single-block `RoutingPlan` for `_run_finalize`:

```json
{
  "blocks": [
    {
      "block_index": 0,
      "kind": "calendar",
      "content": "<note-derived content string>",
      "payload": {
        "title": "<partial_payload.title>",
        "start_date": "<partial_payload.start_date>",
        "end_date": "<start_date + 1 day, exclusive>"
      }
    }
  ]
}
```

- `end_date = start_date + 1 day` (Google exclusive-end convention, C-004).
- This payload flows: `_run_finalize` → `_adapt_calendar` →
  `route_calendar_event` (all-day-aware after IC-02) → `calendar_helper create
  --payload-file … --idempotency-key <source_inbox_path> --account personal`.

## State transitions

```
                         ┌─ answered in <24h ─────────────► timed event (existing path, unchanged)
pending record created ──┤
   (add-time: reason +   └─ unanswered ≥24h (sweep-finalize):
    start_date persisted)        │
                                 ├─ eligible ─► build all-day plan ─► _run_finalize
                                 │                 │
                                 │                 ├─ success ─► note marked processed
                                 │                 │             + event created + logged
                                 │                 │             ─► remove pending record
                                 │                 └─ failure ─► RETAIN record, note unprocessed
                                 │                               (fail-closed; next tick retries;
                                 │                                idempotency-key ⇒ no double-create)
                                 └─ ineligible ─► delete-and-release (existing GC; note re-scanned)
```

## Invariants

- **INV-1 (exactly-once)**: across N≥2 sweep runs over the same eligible record,
  exactly one calendar event exists (idempotency-key dedup + mark-once). [NFR-004, SC-003]
- **INV-2 (boundary)**: a record whose `missing_fields` is anything other than the
  start-time signal, or that lacks a resolved `start_date`, is never converted to
  an all-day event. [FR-005, SC-002]
- **INV-3 (no silent loss)**: a failure *before* the transaction reaches mark never
  drops the record or marks the note processed; it retries (FR-008). A failure
  *after* mark (record-removal only) leaves the note processed — reconciled by
  INV-6, never re-created.
- **INV-4 (determinism)**: the eligibility decision and payload construction use no
  LLM/agent and no NL re-parsing. [NFR-001, R2]
- **INV-5 (date fidelity)**: the all-day event's date equals the date resolved at
  capture time, independent of when the sweep runs. [R2 week-drift]
- **INV-6 (reconciliation)**: on retry of a record whose note is already processed /
  whose routing-log key already exists, the sweep-finalize removes the stale record
  **without re-creating** the event. [FR-009, Codex HIGH-3]
- **INV-7 (canonical key)**: the note argument and `--idempotency-key` are derived
  from **one** canonical absolute inbox path per record, so basename- vs path-form
  never mint two different idempotency keys. [MED-2]
