---
title: "Conflict-Event Log — Schema Sketch"
rq_id: "RQ-3 (T007 + T008)"
wp: "WP02"
depends_on: ["RQ-1", "RQ-2", "RQ-5"]
tags: [507, 516]
---

# Conflict-Event Log — Schema Sketch

**Purpose**: Define the conflict-event log shape required by FR-010. This is a
**sketch** (research output) — the implementation mission that follows will
confirm field types, file path, and library integration. Nothing here is
final code.

**Upstream derivation**: Extended from `habits-history.jsonl` ledger pattern
(RQ-5 Pattern 4 `extend` verdict; `data-model.md` § Conflict Event dimensions).
The `scripts/common/state_log.py` `append()` function can write these records
without modification if passed the full dict.

---

## 1. Schema Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | string | yes | Idempotency anchor — see § 2 for derivation rule |
| `schema_version` | int | yes | Forward-compat anchor; initial value `1` |
| `ts_observed_utc` | ISO-8601 | yes | When Felix first detected the divergence (start of `diff` phase) |
| `ts_emitted_utc` | ISO-8601 | yes | When Felix wrote this record to the log (end of `emit` phase) |
| `layer` | string | yes | `status` / `task` / `project` — which sync layer |
| `vikunja_entity_id` | int | yes | Vikunja `id` (globally unique, immutable) — primary cross-cycle key |
| `vikunja_entity_kind` | string | yes | `task` / `project` |
| `vikunja_identifier` | string | no | Human-readable Vikunja `identifier` (e.g., `#14`) — for WhatsApp ping display only |
| `diff_field` | string | yes | The specific Vikunja field that diverged |
| `felix_state_snapshot` | object | yes | Felix's cached view for this field at conflict time (compact) |
| `vikunja_state_snapshot` | object | yes | Vikunja's actual value at conflict time (compact) |
| `diff_summary` | string | yes | One-line human-readable diff — used verbatim by WhatsApp router |
| `conflict_class` | string | yes | `auto_resolved` or `unsafe_to_auto_resolve` (extensible) |
| `unsafe_criteria_fired` | list[string] | no | Which UC-# criteria fired (populated only when `conflict_class=unsafe_to_auto_resolve`) |
| `resolution_decision` | string | yes | `accepted_vikunja` (steady-state, C-002) / `escalated` (future: UC-4 override) |
| `router_route_set` | list[string] | yes | Routers that received this event; `["log"]` or `["log", "whatsapp"]` |
| `correlation_id` | string | no | Links event to a Felix mission, operator WhatsApp action, or upstream event |

### Snapshot sub-object shape (`felix_state_snapshot` and `vikunja_state_snapshot`)

These are compact objects capturing only the relevant field at conflict time, not
full task payloads (to keep log size bounded).

```json
{
  "field_name": "due_date",
  "field_value": "2026-06-04T23:59:00Z",
  "ts_last_write_utc": "2026-06-04T06:01:12Z",
  "last_writer": "felix-bot"
}
```

For `vikunja_state_snapshot`, `last_writer` is inferred from `created_by.username`
where available; `ts_last_write_utc` is the task's `updated` field.

---

## 2. `event_id` Derivation Rule

The `event_id` must be **deterministic** so that replays of the same conflict
produce the same ID (idempotency anchor; `data-model.md` § Conflict Event note).

**Derivation**:
```
event_id = sha256(
  layer
  + "|" + str(vikunja_entity_id)
  + "|" + diff_field
  + "|" + ts_observed_utc   # ISO-8601, second-precision, UTC
  + "|" + canonical(vikunja_state_snapshot.field_value)
)[:16]  # truncated to 16 hex chars; collision probability negligible at Felix scale
```

**Idempotency guarantee**: If the sync driver is restarted mid-cycle and re-processes
the same Vikunja state for the same entity at the same observed timestamp, it produces
the same `event_id`. Log consumers (WhatsApp router, downstream signal extractors) can
use `event_id` as a dedup key to suppress double-delivery.

**Semantic distinguishability**: Two conflicts on the same entity and field but at
different `ts_observed_utc` values produce different `event_id` values. Two conflicts
on the same entity but different fields produce different `event_id` values. This
satisfies the requirement that "semantically different = different IDs."

**Caveat**: `ts_observed_utc` must be recorded at second precision (not sub-second)
to ensure determinism across replay. The implementation must enforce this.

---

## 3. Worked Examples per `conflict_class`

### Example A — `auto_resolved`

**Scenario**: Reconciliation cycle detects `done_at` field discrepancy. Felix's
JSONL cache says the task was completed on 2026-06-03; Vikunja also shows
`done=true` but with `done_at=0001-01-01T00:00:00Z` (zero sentinel — Vikunja did
not record the time). This is a benign data-model inconsistency, not an operator
edit, and no downstream behavior change results.

```jsonl
{
  "event_id": "a3f8c2d1e4b56789",
  "schema_version": 1,
  "ts_observed_utc": "2026-06-04T06:05:33Z",
  "ts_emitted_utc": "2026-06-04T06:05:34Z",
  "layer": "task",
  "vikunja_entity_id": 14,
  "vikunja_entity_kind": "task",
  "vikunja_identifier": "#7",
  "diff_field": "done_at",
  "felix_state_snapshot": {
    "field_name": "done_at",
    "field_value": "2026-06-03T22:41:00Z",
    "ts_last_write_utc": "2026-06-03T22:41:00Z",
    "last_writer": "felix-bot"
  },
  "vikunja_state_snapshot": {
    "field_name": "done_at",
    "field_value": "0001-01-01T00:00:00Z",
    "ts_last_write_utc": "2026-06-03T22:41:02Z",
    "last_writer": "felix-bot"
  },
  "diff_summary": "done_at: Felix=2026-06-03T22:41:00Z vs Vikunja=zero-sentinel (0001-01-01)",
  "conflict_class": "auto_resolved",
  "unsafe_criteria_fired": [],
  "resolution_decision": "accepted_vikunja",
  "router_route_set": ["log"]
}
```

---

### Example B — `unsafe_to_auto_resolve`

**Scenario**: Kent manually changed `due_date` for task #7 (id:14) in Vikunja UI
after the morning cron ran. Reconciliation detects the divergence; UC-1 fires
(`kent_edit_after_felix_write`) because Vikunja's `updated` timestamp is newer
than Felix's last write timestamp. UC-3 also fires (`downstream_behavior_depends`)
because `due_date` is a load-bearing field. WhatsApp ping is routed.

```jsonl
{
  "event_id": "b9e7a1f3c2d40512",
  "schema_version": 1,
  "ts_observed_utc": "2026-06-04T11:03:17Z",
  "ts_emitted_utc": "2026-06-04T11:03:18Z",
  "layer": "task",
  "vikunja_entity_id": 14,
  "vikunja_entity_kind": "task",
  "vikunja_identifier": "#7",
  "diff_field": "due_date",
  "felix_state_snapshot": {
    "field_name": "due_date",
    "field_value": "2026-06-04T23:59:00Z",
    "ts_last_write_utc": "2026-06-04T06:01:12Z",
    "last_writer": "felix-bot"
  },
  "vikunja_state_snapshot": {
    "field_name": "due_date",
    "field_value": "2026-06-10T23:59:00Z",
    "ts_last_write_utc": "2026-06-04T10:47:22Z",
    "last_writer": "kent"
  },
  "diff_summary": "due_date: Felix=2026-06-04 → Vikunja=2026-06-10 (kent_edit_after_felix_write)",
  "conflict_class": "unsafe_to_auto_resolve",
  "unsafe_criteria_fired": ["kent_edit_after_felix_write", "downstream_behavior_depends"],
  "resolution_decision": "accepted_vikunja",
  "router_route_set": ["log", "whatsapp"]
}
```

---

## 4. Persistence Options

### Option A — JSONL (recommended)

- **Shape**: append-only `.jsonl` file, one JSON object per line.
- **Location**: `/data/services/openclaw/state/sync-conflict-history.jsonl`
  (consistent with `habits-history.jsonl`, `escalation-history.jsonl`, etc.;
  per ADR-0002 Q3 pattern).
- **Reader library**: `scripts/common/state_log.py` `append()` function is
  directly usable — it accepts an arbitrary dict and appends to the domain's
  JSONL file.
- **Trade-offs**:
  - Pro: consistent with all existing Felix patterns (RQ-5 Pattern 4 `extend`
    verdict); no new infrastructure; append-only = durable by default.
  - Pro: human-readable; greppable for debugging.
  - Con: no indexed lookup by `event_id` or `vikunja_entity_id`; to query "all
    conflicts for task 14 in the last 7 days" requires a full file scan. At
    Felix's scale (~10–50 tasks, ≤1 conflict/day), this is not a performance
    concern.
  - Con: no atomic transactions; if the sync driver crashes after writing the log
    entry but before writing the freshness pointer, the next cycle may re-process
    the same state and emit a duplicate event. Guard: `event_id` dedup at the
    router layer (WhatsApp router checks for duplicate `event_id` before sending).

### Option B — SQLite

- **Trade-offs**:
  - Pro: indexed queries; atomic writes; easy "count conflicts by day" queries.
  - Con: not consistent with existing Felix state-log patterns; adds a new
    infrastructure primitive; requires schema migration tooling.
  - Con: overkill at current Felix scale.
  - Verdict: consider if conflict volume grows (>1000 events/day); not for initial
    implementation.

### Option C — Event appended inline to existing domain JSONL files

- **Trade-offs**:
  - Pro: zero new files; conflict events co-located with domain state.
  - Con: mixes conflict-event schema with domain-state schema; reader library would
    need type disambiguation; makes the conflict log harder to query independently.
  - Verdict: not recommended; separation of concerns argues for a dedicated log.

**Recommendation**: **Option A (JSONL)** with the path
`/data/services/openclaw/state/sync-conflict-history.jsonl`. The `state_log.py`
shared library handles append; `event_id` dedup is the guard for at-most-once
WhatsApp delivery.

---

## 5. Forward Compatibility with #516

Issue #516 scopes the Felix-wide observability and status-emission framework
(evidence-log row to be added by WP02; source `issue-516` already in
source-register.csv). Its three possible framework outcomes are analyzed below
for compatibility with this log shape.

Cross-reference: `findings/rq-3-conflict-policy.md` § 6 links back to this section.

### Outcome (a) — Yes, build a framework: sender contract + router primitives

Under outcome (a), #516 produces a **sender contract**: a required emission interface
that every Felix component must satisfy when producing an event. The conflict-event
log shape is forward-compatible because the `schema_version` field (introduced here
as the load-bearing forward-compat anchor) is exactly the versioned-contract hook
the sender-contract framework would require. If #516's sender contract mandates a
standard set of envelope fields (`event_id`, `ts_emitted_utc`, `schema_version`,
`router_route_set`), the conflict-event schema already provides all four. Adopting
the sender contract reduces to: (a) ensure the existing fields comply with any
envelope naming conventions the framework specifies, and (b) bump `schema_version`
to the framework's minimum. No backfill is required for existing log entries — the
JSONL format's append-only semantics mean old entries simply lack the new envelope
fields; readers can filter by `schema_version >= N`. The key load-bearing field is
`schema_version`: it is the upgrade path. Without it, every historic event would
need re-processing to determine its schema.

### Outcome (b) — Yes, principle only: constitutional directive, no framework

Under outcome (b), #516 produces a **constitutional directive** — a statement like
"every Felix component that emits state-change events MUST write to an append-only
JSONL ledger with at minimum `{event_id, ts_emitted_utc, source_component}`" — but
no shared library or standardized schema. The conflict-event log shape is
forward-compatible because it already satisfies any plausible observability
directive: it has `event_id` (idempotency), `ts_emitted_utc` (temporal anchor),
and a clearly identified `source_component` implied by the log's path
(`sync-conflict-history.jsonl`). The implementation mission does not need to wait
for the directive to be ratified before building the conflict-event log; if the
directive's wording turns out to require an additional field, `schema_version`
provides the hook to introduce it without breaking existing readers. The load-bearing
field for outcome (b) is `event_id`: it satisfies the most common directive
requirement (every event must be uniquely identifiable for dedup and replay).

### Outcome (c) — No: preserve inventory only, no framework or directive

Under outcome (c), #516 closes without a framework or directive — the Felix-wide
observability gap is acknowledged but deferred. The conflict-event log shape is
fully forward-compatible because it depends on no #516 output. The log is a
self-contained artifact: it uses the existing `state_log.py` append library, the
existing JSONL conventions, and the conflict-class taxonomy defined by this
research. It operates independently of any cross-component observability framework.
The load-bearing field for outcome (c) is `router_route_set`: it is the only
cross-cutting concern (the WhatsApp router needs to know which events to act on),
and its presence in the log means a future framework can index into it without
schema redesign. If #516 is ever reopened, the conflict-event log's `router_route_set`
values become the canonical inventory of which events currently cross component
boundaries — providing the "preserved inventory" that outcome (c) envisions.

---

## Limitations

- **Snapshot compactness**: The `felix_state_snapshot` and `vikunja_state_snapshot`
  objects are defined here as field-scoped (one field per event). If the implementation
  discovers that multi-field conflicts are common (e.g., both `done` and `due_date`
  diverge simultaneously), the schema may need a `diff_fields` array and per-field
  snapshot objects. `schema_version` provides the evolution path.

- **`last_writer` inference**: Detecting whether `last_writer` is `kent` or
  `felix-bot` requires comparing Vikunja's `updated` timestamp against Felix's
  `ts_last_write_utc` in the cache. This requires Felix to maintain a per-field
  write timestamp in its state cache — a new requirement not present in the current
  JSONL schema. Implementation must add this to the cache.

- **JSONL file growth**: At ≤1 conflict/day, annual volume is ≤365 events (~40KB).
  No rotation needed at Felix's scale. Revisit if conflict rate grows post-deployment.
