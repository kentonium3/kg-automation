# Contract: PendingClarification record + all-day block plan

Not an HTTP API — these are the internal data contracts between the add-time
capture, the state store, and the deterministic sweep-finalize path.

## C1 — Extended PendingClarification (state file element)

```jsonc
{
  "note_filename": "Inbox 42.md",          // basename; existing
  "created_at": "2026-07-17T14:03:00Z",    // ISO-8601 Z; existing; drives 24h age-out
  "partial_payload": {
    "title": "Meet Rob",                   // existing
    "missing_fields": ["start_time"],      // NEW — eligibility signal (from validate)
    "start_date": "2026-07-23",            // NEW — resolved once at capture (validate)
    "start_natural": "Thursday"            // existing; NOT used to derive the date at sweep
  }
}
```

**Producer**: `felix-admin-capture` AGENTS.md Step 3c → `handle_clarification_state
add --partial-payload <json>`, where the JSON is `validate`'s incomplete-result
`fields_so_far` (now carrying `missing_fields` + `start_date`).

**Consumers**:
- `pending_filenames`/`_is_live` (read-time withhold) — unchanged; ignores the new keys.
- The sweep-finalize path — reads `missing_fields` + `start_date` for the eligibility gate.

**Compatibility**: absent `missing_fields` or `start_date` ⇒ **not eligible**
(legacy/in-flight records degrade to delete-and-release). No version bump; additive keys.

## C2 — All-day RoutingPlan handed to `_run_finalize`

```jsonc
{
  "blocks": [
    {
      "block_index": 0,
      "kind": "calendar",
      "content": "<note-derived string>",
      "payload": {
        "title": "Meet Rob",
        "start_date": "2026-07-23",
        "end_date": "2026-07-24"           // start_date + 1 day, exclusive (C-004)
      }
    }
  ]
}
```

**Consumer chain**: `_run_finalize` → `_adapt_calendar` → `route_calendar_event`
(all-day-aware, IC-02) → `calendar_helper create --payload-file <tmp>
--idempotency-key <source_inbox_path> --account personal`.

**Guarantees**:
- Exactly-once via `--idempotency-key` extended-property dedup + `_run_finalize`
  mark-note-once.
- Fail-closed: any failure leaves the note unprocessed and the pending record
  retained.

## C3 — Observability event (FR-007)

The finalize path emits a routing-log entry (or marker) for the age-out-create
that is **distinct** from:
- a normal answered/timed calendar create, and
- a plain sweep-delete of an ineligible aged-out record.

Exact event type/label is fixed at IC-04 implementation to match existing
`RoutingLogWriter` conventions; the contract is *separability* — an operator can
grep a count of "landed as all-day via unanswered-clarification fallback".
