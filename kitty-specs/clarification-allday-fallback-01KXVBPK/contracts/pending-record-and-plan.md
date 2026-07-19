# Contract: PendingClarification record + all-day block plan

Not an HTTP API — these are the internal data contracts between the add-time
capture, the state store, and the deterministic sweep-finalize path.

## C1 — Extended PendingClarification (state file element)

```jsonc
{
  "note_filename": "Inbox 42.md",          // basename; existing
  "created_at": "2026-07-17T14:03:00Z",    // ISO-8601 Z; existing; drives 8h age-out
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
- Exactly-once (sequential) via `--idempotency-key` extended-property dedup +
  `_run_finalize` mark-note-once. The note path AND `--idempotency-key` are derived
  from **one canonical absolute inbox path** reconstructed from `note_filename`, so
  basename/path-form records never mint two keys (MED-2, INV-7).
- Fail-closed **before mark**: a failure that does not reach mark leaves the note
  unprocessed and the record retained (FR-008).
- **Reconcile after mark**: if create+mark succeeded but record-removal failed, the
  next sweep detects the already-processed note / existing routing-log key and
  removes the stale record **without re-creating** (FR-009, INV-6).
- Concurrency out of scope: serial `felix-admin-capture` tick (NFR-004 narrowed).

## C3 — Observability event (FR-007)

The finalize path emits a **concrete durable marker** for the age-out-create that
is separable from a normal answered/timed calendar create and from a plain
sweep-delete. Per Codex MED-1, a normal calendar routing-log row is only
`kind="calendar"` + destination, so separability needs an explicit marker:
**preferred = a distinct routing-log `kind`/event `calendar_all_day_fallback`** (or
an explicit boolean field on the entry), consistent with `RoutingLogWriter`
conventions. The contract is that an operator can grep an **exact count** of
appointments that landed as all-day via the unanswered-clarification fallback
(SC-004). Final field/kind name fixed at IC-04 against the real schema.
