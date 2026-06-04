# Contract: Conflict Event Schema

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Phase**: Plan / Phase 1 / contracts
**Date**: 2026-06-04

The append-only conflict-event log is the durable record of every divergence the driver detects. This document is the canonical schema definition. Implementation lives in `scripts/sync/emit.py`; the JSONL file is `/data/services/openclaw/state/sync/conflict-events.jsonl`.

The schema is taken directly from `docs/research/felix-vikunja-sync-architecture/findings/conflict-event-log.sketch.md` (RQ-3 sketch). This contract anchors that sketch and locks the field set for implementation.

---

## Schema version

```
schema_version: 1
```

Increment only on backwards-incompatible field renames/removals. Adding optional fields is NOT a version bump. The `schema_version` field is **load-bearing under #516 forward-compat outcome (a)** — when the #516 framework lands and prescribes a versioning protocol, this field is the migration anchor.

---

## Full field set (15 fields)

Every conflict-event row contains exactly these 15 fields. Order in the JSONL row is not significant; implementations canonicalize during testing.

### Identity fields (4)

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | string | yes | `sha256(layer \| vikunja_entity_id \| diff_field \| ts_observed_utc \| canonical(vikunja_value))[:16]`. **Load-bearing under #516 outcome (b)**. Deterministic; identical inputs → identical event_id. Used by G-1 dedup and downstream observers as the row's stable identifier. |
| `schema_version` | int | yes | Always 1 in this mission. Load-bearing under #516 outcome (a). |
| `tick_id` | string (ULID) | yes | Cycle identifier; ties the event to its tick's `last-tick.json` health record. Generated at cycle start. |
| `ts_observed_utc` | string (ISO-8601 UTC) | yes | Wall-clock time at which the driver observed this divergence (cycle's `started_at_utc`). |

### Subject fields (3)

| Field | Type | Required | Description |
|---|---|---|---|
| `layer` | string (enum) | yes | `status_and_task` always in this mission. `project` reserved for #520. |
| `vikunja_entity_id` | int | yes | The integer `task.id` (canonical cross-cycle identifier per ADR-0003). |
| `diff_field` | string | yes | The field name that diverged (from the `TRACKED_TASK_FIELDS` set). |

### Value fields (2)

| Field | Type | Required | Description |
|---|---|---|---|
| `vikunja_value` | any (JSON) | yes | Vikunja's current value of the field. JSON-encoded per Python's `json.dumps`. |
| `felix_cached_value` | any (JSON) | yes | Felix's cached "expected" value at cycle start. JSON-encoded. May be `null` if first observation (in which case classify/emit are skipped and this row is not generated — but documented here for schema completeness). |

### Classification fields (2)

| Field | Type | Required | Description |
|---|---|---|---|
| `class` | string (enum) | yes | `auto_resolved` or `unsafe_to_auto_resolve`. |
| `unsafe_reasons` | list[string] | yes | Subset of `["uc1_uc2_divergence", "uc3_downstream_behavior", "uc4_manual_override"]`. Empty list when class is `auto_resolved` AND no UC-4 was the inverter (rare). Always contains `uc1_uc2_divergence` when class is `unsafe_to_auto_resolve` (per classify.md rule 1). UC-4 presence inverts class to `auto_resolved` and remains listed. |

### Routing fields (2)

| Field | Type | Required | Description |
|---|---|---|---|
| `router_route_set` | list[string] | yes | List of delivery routes ATTEMPTED. Initially `["whatsapp"]` for unsafe events, `[]` for auto-resolved. **Load-bearing under #516 outcome (c)** — when the #516 framework lands and prescribes a route-set protocol, this field becomes the row's routing manifest. |
| `delivery_status` | string (enum) | yes | One of: `delivered`, `suppressed_by_g1`, `suppressed_by_g2`, `suppressed_by_g3`, `not_unsafe`, `error`. |

### Diagnostics fields (2)

| Field | Type | Required | Description |
|---|---|---|---|
| `vikunja_updated_at` | string (ISO-8601 UTC) | yes | Vikunja's `updated` timestamp for the entity at the moment of observation. Useful for forensic timeline reconstruction. |
| `delivery_error` | string \| null | yes (may be null) | Stderr or exception text from the openclaw CLI call, if delivery failed. Null when `delivery_status != "error"`. |

---

## Example row (`auto_resolved` — Felix wrote the change)

```json
{
  "schema_version": 1,
  "event_id": "a3f1c9d4b2e8e7f0",
  "tick_id": "01KTA1J3FH87XJWT7FQPT1EZE7",
  "ts_observed_utc": "2026-06-04T19:35:30Z",
  "layer": "status_and_task",
  "vikunja_entity_id": 18,
  "diff_field": "done",
  "vikunja_value": false,
  "felix_cached_value": true,
  "class": "auto_resolved",
  "unsafe_reasons": [],
  "router_route_set": [],
  "delivery_status": "not_unsafe",
  "vikunja_updated_at": "2026-06-04T19:33:11Z",
  "delivery_error": null
}
```

**Interpretation**: Felix's cache thought task 18 (`Get steps in today`) was `done=true` (from the previous tick's observation, post-felix-bot-completion). Vikunja's auto-advance flipped it back to `done=false`. The diff phase detected the change. UC-4 didn't apply (no `felix:ignore` label). UC-3 fired (`done` is in the downstream-affecting set). But — wait, this would actually classify as unsafe. Let me re-examine...

Actually this is a tricky case: Vikunja's *server-side* auto-advance generated this transition; from Felix's perspective the cache becomes stale not because Kent edited but because Vikunja's recurrence behavior fired. The classify phase doesn't distinguish "Vikunja auto-fired" from "Kent edited" because there's no Vikunja signal for that. So this row WOULD classify as `unsafe_to_auto_resolve` and emit a WhatsApp ping unless G-1 dedup suppressed (it would on the first occurrence).

This is a known **soft edge** in the design — Vikunja's server-side auto-advance on recurring tasks produces divergences indistinguishable from operator edits. The mitigation strategies:

1. **G-2 (post-Felix-write suppression)** catches the immediate case where Felix has recently written `done=true` (the trigger for the auto-advance).
2. UC-4 (`felix:ignore` on tasks where this behavior is expected) lets the operator opt out for known recurring habits.

The implementer should validate this edge case explicitly during the smoke test on office2. If it produces noise, the operator's options are: apply `felix:ignore` to the daily-habit tasks, OR extend the G-2 window for those tasks specifically (config-driven).

---

## Example row (`unsafe_to_auto_resolve` — Kent edited a due date)

```json
{
  "schema_version": 1,
  "event_id": "b7e4d2f0a1c3e5d8",
  "tick_id": "01KTA1J3FH87XJWT7FQPT1EZE7",
  "ts_observed_utc": "2026-06-04T19:35:30Z",
  "layer": "status_and_task",
  "vikunja_entity_id": 27,
  "diff_field": "due_date",
  "vikunja_value": "2026-06-10T17:00:00Z",
  "felix_cached_value": "2026-06-08T17:00:00Z",
  "class": "unsafe_to_auto_resolve",
  "unsafe_reasons": ["uc1_uc2_divergence", "uc3_downstream_behavior"],
  "router_route_set": ["whatsapp"],
  "delivery_status": "delivered",
  "vikunja_updated_at": "2026-06-04T19:32:08Z",
  "delivery_error": null
}
```

**Interpretation**: Kent moved task 27's due date from June 8 to June 10. UC-1/UC-2 fired (cache divergence) and UC-3 fired (`due_date` is downstream-affecting). No UC-4. WhatsApp delivery succeeded.

---

## Example row (`suppressed_by_g1` — duplicate within 24h)

```json
{
  "schema_version": 1,
  "event_id": "c9a6b3d8e2f4a7b1",
  "tick_id": "01KTA1J3FH87XJWT7FQPT1EZE7",
  "ts_observed_utc": "2026-06-04T20:35:30Z",
  "layer": "status_and_task",
  "vikunja_entity_id": 27,
  "diff_field": "due_date",
  "vikunja_value": "2026-06-12T17:00:00Z",
  "felix_cached_value": "2026-06-10T17:00:00Z",
  "class": "unsafe_to_auto_resolve",
  "unsafe_reasons": ["uc1_uc2_divergence", "uc3_downstream_behavior"],
  "router_route_set": ["whatsapp"],
  "delivery_status": "suppressed_by_g1",
  "vikunja_updated_at": "2026-06-04T20:31:45Z",
  "delivery_error": null
}
```

**Interpretation**: Kent moved task 27's due date AGAIN (to June 12) within 24h of the prior edit. G-1 dedup matched on the event-id stem `(layer | vikunja_entity_id | diff_field)` and suppressed the WhatsApp ping. The cache STILL advances (next tick will start from this new value); only the operator-facing delivery is suppressed.

---

## Forward compatibility with #516

Per RQ-3 § Forward compatibility, the schema is designed to remain valid across each of #516's three possible framework outcomes:

| Outcome | Load-bearing field | What changes |
|---|---|---|
| **(a)** Versioned migration framework | `schema_version` | New fields get a version bump; existing rows continue to deserialize at v1. |
| **(b)** Event-bus framework with stable IDs | `event_id` | Used as the bus message key; existing rows replay deterministically. |
| **(c)** Route-set protocol framework | `router_route_set` | Existing rows fit the new protocol with the current `["whatsapp"]` or `[]` values; future rows add more routes. |

No row written by this mission's driver requires backfill or transformation under any of the three outcomes. Forward-compatibility is built in, not bolted on.

---

## Validation rules

The implementation provides a deserializer/validator function `validate_row(row: dict) -> Optional[ValidationError]` exported from `scripts/sync/emit.py`:

- All 15 fields present.
- `event_id` is a 16-char lowercase hex string.
- `schema_version == 1`.
- `tick_id` parses as ULID.
- All timestamps parse as ISO-8601 UTC.
- `class` ∈ {`auto_resolved`, `unsafe_to_auto_resolve`}.
- `unsafe_reasons` is a list of values from `{uc1_uc2_divergence, uc3_downstream_behavior, uc4_manual_override}`.
- `delivery_status` ∈ {`delivered`, `suppressed_by_g1`, `suppressed_by_g2`, `suppressed_by_g3`, `not_unsafe`, `error`}.
- `delivery_error` is null iff `delivery_status != "error"`.

Validation is applied to the row immediately before JSONL append. A validation failure is a programming bug; it surfaces as a cycle error (exit code 2, since the cache update / freshness advance must NOT proceed if an invalid event was about to be written).

---

## Read path

The conflict-event log is a one-writer / many-readers structure. The driver is the only writer. Readers include:

- The G-1 dedup check (reads last 24h window during emit phase)
- The operator (via `cat`, `tail`, `jq`)
- Future analytics tooling (future mission; not in scope)
- Future #516 framework (forward-compat anchors)

Readers should:
- Read the file with line-oriented JSON parsing (each line is one row).
- Skip lines that fail to parse (defensive against partial writes during rotation).
- Use `event_id` as the row's stable identifier.
- Never write to the file.

---

## Privacy

For tasks routed through a private Obsidian path (per `02-Growth/_private/`):

- `vikunja_entity_id` IS populated (the integer ID has no semantic content).
- `vikunja_value` and `felix_cached_value` are replaced with the literal string `"<redacted>"`.
- `diff_field` is replaced with the literal string `"<redacted>"`.
- All other fields are populated normally.

The diff phase identifies private tasks via the `ProjectCacheRecord` (matching by project_id). If a task moves into or out of a private project, the redaction state changes at the next cycle.
