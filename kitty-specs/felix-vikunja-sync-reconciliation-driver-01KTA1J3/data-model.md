# Data Model: Felix-Vikunja Sync Reconciliation Driver — Phase 1

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Date**: 2026-06-04

This document enumerates the entities the driver creates, reads, and writes. Each entity is described in terms of its role, fields, persistence, and relationships. Detailed on-disk layout is in `contracts/state-directory.md`; detailed event schema is in `contracts/conflict-event-schema.md`.

---

## Entity 1 — `ReconciliationCycle`

**Role**: One execution of the 6-phase pipeline (fetch → diff → classify → emit → update → complete) triggered by the systemd timer.

**Persistence**: Ephemeral (process state during the tick). State derived from this cycle is persisted into `PerTickHealthRecord`, `ConflictEvent` rows, `FreshnessPointer`, and `TaskCacheRecord` mutations.

**Fields** (in-memory only):

| Field | Type | Description |
|---|---|---|
| `tick_id` | string (ULID) | Cycle identifier, generated at start; surfaced into the health record and into every conflict event emitted this tick. |
| `started_at_utc` | ISO-8601 | Wall-clock at cycle start. |
| `cadence_seconds` | int | Resolved cadence from env var or config (default 300). |
| `layer_pointers_before` | dict[str → ISO-8601] | Snapshot of FreshnessPointer values at cycle start. |
| `layer_pointers_after` | dict[str → ISO-8601] | Pointer values to commit on successful completion. |
| `events_emitted` | dict[class → int] | Running count of conflict events emitted by class (`auto_resolved`, `unsafe_to_auto_resolve`). |
| `cycle_error` | string \| null | Last error encountered; non-null means the cycle did not complete successfully. |

**Relationships**:
- Reads from: `FreshnessPointer`, `TaskCacheRecord`
- Writes to: `ConflictEvent` (log), `PerTickHealthRecord`, `TaskCacheRecord` (cache updates), `FreshnessPointer` (only if cycle succeeds)

---

## Entity 2 — `FreshnessPointer`

**Role**: Per-layer record of the most recent Vikunja `updated` timestamp the driver has processed. Used as the `updated_since` parameter on the next delta fetch; advanced only on cycle success.

**Persistence**: Single JSON file at `/data/services/openclaw/state/sync/freshness.json` (overwrite-on-success).

**Schema**:

```json
{
  "schema_version": 1,
  "last_updated_utc": "2026-06-04T19:25:32Z",
  "layers": {
    "status_and_task": {
      "last_polled_utc": "2026-06-04T19:25:30Z"
    }
  }
}
```

**Layers in scope**: `status_and_task` (a single combined pointer covering both status and task layers, since both are surfaced by the same `GET /tasks/all?updated_since=<ts>` endpoint per RQ-1). The `project` layer is out of scope (#520).

**Relationships**:
- Read by: `fetch` phase (provides the `updated_since` query parameter)
- Written by: `complete` phase (commits the new pointer on success)
- On cycle failure: NOT advanced — next cycle re-polls from the same `updated_since`, ensuring no edits are silently missed.

---

## Entity 3 — `TaskCacheRecord`

**Role**: Felix's local view of one Vikunja task, addressed by integer `task.id`. The driver's authoritative "what Felix expected to see in Vikunja" reference for the diff phase. This is what UC-1/UC-2 collapse means: Felix's expected value, not Vikunja's `updated_by`, is the authorship signal.

**Persistence**: Single JSON file at `/data/services/openclaw/state/sync/task-cache.json` (overwrite-on-success at cycle end; updated only after emit succeeds for all events in the cycle).

**Schema**:

```json
{
  "schema_version": 1,
  "last_updated_utc": "2026-06-04T19:25:30Z",
  "tasks": {
    "14": {
      "vikunja_task_id": 14,
      "fields": {
        "title": "Wake at 5:00 AM",
        "done": false,
        "due_date": "0001-01-01T00:00:00Z",
        "project_id": 13,
        "repeat_after": 86400,
        "repeat_mode": 0,
        "labels": []
      },
      "vikunja_updated_at": "2026-06-04T18:32:18Z",
      "felix_last_observed_at": "2026-06-04T18:35:01Z"
    }
  }
}
```

**Field set**: A curated subset of Vikunja's task object (the fields Felix tracks for reconciliation). Defined as a constant in `scripts/sync/state.py`. The initial set: `title`, `done`, `due_date`, `project_id`, `repeat_after`, `repeat_mode`, `labels`. Field set can be extended as future capabilities require, without schema migration (new fields default to "unknown" → first observation populates them without firing a conflict).

**Relationships**:
- Read by: `diff` phase (compares against Vikunja's current value)
- Written by: `update` phase (replaces fields where Vikunja's value differs)
- The cache is the driver's primary "single source of truth for what Felix expects" — this is what makes the collapsed UC-1/UC-2 check meaningful.

**Privacy boundary**: Tasks whose `project_id` corresponds to a `02-Growth/_private/` Obsidian path are tracked only by integer ID, with `fields` set to an empty dict (no titles, due_dates, labels persisted). The driver's privacy filter is applied at the `update` phase and is config-driven (initial config: empty allowlist; populated in implement phase based on operator preference).

---

## Entity 4 — `ConflictEvent`

**Role**: One detected divergence between Felix's `TaskCacheRecord` value and Vikunja's current value, classified into `auto_resolved` or `unsafe_to_auto_resolve`.

**Persistence**: Append-only JSONL at `/data/services/openclaw/state/sync/conflict-events.jsonl`. Schema fully detailed in `contracts/conflict-event-schema.md`. 15 fields per the RQ-3 sketch, including a deterministic `event_id` for idempotent dedup.

**Key fields** (full schema in contracts):

- `event_id`: `sha256(layer | vikunja_entity_id | diff_field | ts_observed_utc | canonical(value))[:16]` — deterministic, idempotent.
- `schema_version`: 1 — load-bearing under #516 outcome (a).
- `tick_id`: links the event to its cycle.
- `class`: `auto_resolved` | `unsafe_to_auto_resolve`.
- `unsafe_reasons`: list of UC criteria that fired, drawn from `[uc1_uc2_divergence, uc3_downstream_behavior, uc4_manual_override]` (3 distinct codes since UC-1 and UC-2 are collapsed).
- `layer`: `status_and_task` (status/task collapsed; project not in scope).
- `vikunja_entity_id`: the integer `task.id`.
- `diff_field`: the field name that differed.
- `vikunja_value` / `felix_cached_value`: the two values that diverged.
- `router_route_set`: list of delivery routes attempted (initially `["whatsapp"]` for unsafe events, `[]` for auto-resolved) — load-bearing under #516 outcome (c).
- `delivery_status`: `delivered` | `suppressed_by_g1` | `suppressed_by_g2` | `suppressed_by_g3` | `not_unsafe` | `error`.

**Relationships**:
- Created by: `emit` phase
- Consumed by: guard phase (G-1 dedup reads recent events by `event_id` stem)
- Consumed by: operator (human review of divergence history via the JSONL file)
- Consumed by: future #516 framework when it lands (forward-compat anchored on `schema_version`, `event_id`, `router_route_set`)

---

## Entity 5 — `PerTickHealthRecord`

**Role**: The driver's self-report of the most recent cycle. The operator's primary "is the driver alive" signal.

**Persistence**: Single JSON file at `/data/services/openclaw/state/sync/last-tick.json` (overwrite-on-success). On cycle error, a separate append-only file `last-tick.errors.jsonl` accumulates failure records — preserving the success record while flagging the failure stream operator-side.

**Schema** (success):

```json
{
  "schema_version": 1,
  "tick_id": "01KTA1J3...",
  "started_at_utc": "2026-06-04T19:25:30Z",
  "completed_at_utc": "2026-06-04T19:25:30.347Z",
  "duration_ms": 347,
  "cadence_seconds": 300,
  "layer_pointers": {
    "status_and_task": {
      "before": "2026-06-04T19:20:30Z",
      "after": "2026-06-04T19:25:30Z"
    }
  },
  "events_emitted": {
    "auto_resolved": 0,
    "unsafe_to_auto_resolve": 0
  },
  "cycle_error": null,
  "vikunja_version_seen": "0.24.6"
}
```

**Schema** (failure, appended to `last-tick.errors.jsonl`):

```json
{
  "schema_version": 1,
  "tick_id": "01KTA1J3...",
  "started_at_utc": "2026-06-04T19:25:30Z",
  "failed_at_utc": "2026-06-04T19:25:33Z",
  "phase": "fetch | diff | classify | emit | update | complete",
  "cycle_error": "step 1 (Vikunja delta fetch) failed: HTTP 503 ...",
  "layer_pointers_unchanged": true
}
```

**Relationships**:
- Written by: `complete` phase (success) or any phase on error
- Read by: operator via `cat` (manual health check), future `felix status sync` command (out of scope for this mission)

---

## Entity 6 — `WhatsAppDeliveryRequest`

**Role**: One outbound WhatsApp message attempt for an unsafe-class conflict event.

**Persistence**: Ephemeral. The request is constructed at emit time and handed to `subprocess.run` (openclaw CLI). The result (exit code, stderr) populates the corresponding `ConflictEvent.delivery_status`.

**Fields** (in-memory only):

| Field | Type | Description |
|---|---|---|
| `agent` | string | Always `"main"` (matches `sync-heartbeat.py` precedent). |
| `recipient` | string | E.164 phone number; sourced from a constant `WHATSAPP_RECIPIENT` in the driver, mirroring `sync-heartbeat.py`. |
| `message` | string | The fully-formatted 3-line message: line 1 = class (e.g. `🟠 Vikunja edit (unsafe)`), line 2 = entity (task title + id), line 3 = diff summary (`field: old → new`). |
| `timeout_seconds` | int | Default 60. |
| `dry_run` | bool | If true, log the would-send payload and return success without invoking the CLI. Supports the implement-phase test plan. |

**Relationships**:
- Constructed by: `emit` phase, after guards have approved the event
- Consumed by: `scripts/sync/send_whatsapp.py` (the subprocess wrapper)
- Result feedback: populates `ConflictEvent.delivery_status` and `ConflictEvent.delivery_error` (if any)

---

## Entity 7 — `Guard`

**Role**: Pre-emit filter that suppresses or delays an unsafe-class event. Three guards apply in order: G-1, G-2, G-3.

**Persistence**: State for each guard is partially derived from `ConflictEvent` history (`G-1` dedup) and partially from `TaskCacheRecord.felix_last_observed_at` timestamps (`G-2` post-write suppression). `G-3` daily cap state lives in a small overwrite-on-update file: `/data/services/openclaw/state/sync/guard-state.json`.

**Schema** (`guard-state.json`):

```json
{
  "schema_version": 1,
  "g3_daily_cap": {
    "calendar_day_et": "2026-06-04",
    "unsafe_pings_sent_today": 0,
    "cap": 5
  }
}
```

**Per-guard semantics**:

- **G-1 (24-hour event-id stem dedup)**: Compute `event_id_stem = sha256(layer | vikunja_entity_id | diff_field)[:16]`. If any event with the same stem appears in `conflict-events.jsonl` within the last 24 hours AND was delivered (or was auto-resolved), suppress. Records the suppression in the new event's `delivery_status`.
- **G-2 (30-minute post-Felix-write suppression)**: If `TaskCacheRecord.fields[diff_field].felix_last_observed_at` is within 30 minutes of the current cycle's start, suppress. (Reasoning: Felix just wrote this; the operator's edit is overwhelmingly likely to be a deliberate response to Felix's write, not an independent divergence.)
- **G-3 (hard daily cap)**: If `unsafe_pings_sent_today >= cap` (default 5), suppress further unsafe-class WhatsApp deliveries for the rest of the calendar day (Eastern Time). The cap is sized so that 5 unsafe pings per day is a clearly-anomalous-day threshold that itself becomes a signal — the next cycle after a G-3 cap fires emits a special "daily cap reached" event with class `system_signal`.

**Relationships**:
- G-1 reads: `conflict-events.jsonl` (last 24h slice)
- G-2 reads: `TaskCacheRecord`
- G-3 reads/writes: `guard-state.json`

---

## Entity 8 — `ProjectCacheRecord` *(read-only this mission)*

**Role**: Lightweight cache of project metadata (title, id, is_archived). Read-only this mission — the driver fetches projects only as part of the initial bootstrap and again whenever a task's `project_id` references a project not in the cache. Full project-layer reconciliation (with deletion detection) is #520.

**Persistence**: Single JSON file at `/data/services/openclaw/state/sync/project-cache.json`.

**Schema**:

```json
{
  "schema_version": 1,
  "last_refreshed_utc": "2026-06-04T19:25:30Z",
  "projects": {
    "13": {
      "title": "Habits",
      "is_archived": false
    }
  }
}
```

**Relationships**:
- Read by: `diff` phase (cross-references task `project_id` for UC-3 evaluation)
- Refreshed when: a task references a project_id not in the cache (just-in-time fetch). NOT refreshed every cycle — project-layer drift detection is #520's concern.

---

## Entity relationship summary

```
┌─────────────────────────┐
│   ReconciliationCycle   │ (ephemeral, one per tick)
└───────────┬─────────────┘
            │ reads
            ▼
┌─────────────────────────┐  ┌──────────────────────┐
│   FreshnessPointer      │  │   TaskCacheRecord    │
│   (1 file, on-disk)     │  │   (1 file, on-disk)  │
└─────────────────────────┘  └─────┬────────────────┘
                                   │ informs
                                   ▼
                          ┌──────────────────────┐
                          │      Guard           │ ← reads guard-state.json
                          │   (in-memory logic)  │
                          └─────┬────────────────┘
                                │ approves
                                ▼
                          ┌──────────────────────┐
                          │   ConflictEvent      │
                          │   (JSONL append)     │
                          └─────┬────────────────┘
                                │ triggers
                                ▼
                          ┌──────────────────────────┐
                          │  WhatsAppDeliveryRequest │
                          │  (ephemeral, subprocess) │
                          └──────────────────────────┘

      ┌────────────────────────────┐
      │   PerTickHealthRecord      │ ← written by every cycle, success or fail
      │   (last-tick.json /         │
      │    last-tick.errors.jsonl) │
      └────────────────────────────┘

      ┌────────────────────────────┐
      │   ProjectCacheRecord       │ ← read-only this mission, just-in-time refresh
      │   (project-cache.json)     │
      └────────────────────────────┘
```

---

## Field-set evolution policy

The TaskCacheRecord field set is intentionally curated, not auto-derived. Adding a field to the curated set is a deliberate design choice (each field added expands the conflict surface). The implementation includes a single source of truth at `scripts/sync/state.py` (`TRACKED_TASK_FIELDS`) so future capability missions can extend it without searching the codebase. First observation of an existing task after a field-set expansion populates the new field without firing a conflict event (treated as "new information," not "divergence").
