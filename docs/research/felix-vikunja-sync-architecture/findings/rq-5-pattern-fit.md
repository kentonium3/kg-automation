---
rq_id: "RQ-5"
title: "Existing-pattern fit assessment"
depends_on: []
wp: "WP01"
---

# RQ-5 — Existing-Pattern Fit Assessment

**Purpose**: For each existing Felix pattern, assess fit for the proposed bi-directional sync architecture. Verdict per pattern: `use as-is` / `extend` / `replace` / `not applicable`.

Sources: memory entries, code under `scripts/`, `docs/runbooks/doc-auditor-driver-ops.md`.

---

## Pattern 1 — Signal-driven monitoring pipeline (issues #59/#490)

**Canonical references**: memory `feedback_signal_driven_doc_audit`; code at `scripts/openclaw/observation/signals/`; `scripts/doc_audit/run.py`.

### Structural shape

The signal pipeline has five components:

1. **Signal extractor** (`scripts/openclaw/observation/signals/<name>.py`): reads a log source (file, API endpoint, structured output), applies a pattern match, emits a `SignalExtraction` dataclass with `{signal_id, count_cycle, count_rolling, excerpts, last_event_at_utc, new_cursor}`. observed (`scripts/openclaw/observation/signals/types.py`)

2. **Cursor / freshness pointer** (`LogCursor` dataclass: `{path, inode, byte_offset, mtime}`): records the exact position within a log file after each cycle. Next cycle reads from this position forward — incremental, not full re-read. observed (`scripts/openclaw/observation/signals/types.py` lines 18–29)

3. **Rolling-window state**: `count_rolling` aggregates counts across multiple cycles within a time window. Enables threshold evaluation ("N errors in 24h") without re-reading old log data.

4. **Tick driver** (`scripts/doc_audit/run.py`): per-cycle orchestrator that: (a) runs all extractors, (b) evaluates thresholds, (c) emits signals (GitHub issues, WhatsApp pings), (d) writes `last-tick.json` health signal. observed (`scripts/doc_audit/run.py` lines 7–50)

5. **`last-tick.json` health signal**: structured JSON written after every tick regardless of success/failure. Contains `{status, timestamp_utc, errors, next_tick_utc, ...}`. Operators use this to verify liveness. observed (`docs/runbooks/doc-auditor-driver-ops.md` lines 62–96)

### Mapping to sync architecture needs

| Sync need | Pattern component | Fit |
|---|---|---|
| Incremental delta detection (poll only changed tasks) | Cursor / freshness pointer → analogous to `updated_since` timestamp for Vikunja | Strong fit |
| Reconciliation cycle structure | Tick driver (fetch→diff→classify→emit→update→complete) | Strong fit (phases map directly) |
| Conflict-event emission | Signal emission to router (GitHub/WhatsApp) | Strong fit — same router infrastructure |
| State cache / freshness pointer | `last-tick.json` + `LogCursor` | Extend: replace log cursor with `{last_polled_utc, last_task_updated_ts}` per layer |
| Rolling-window rate-limiting (NFR-003) | `count_rolling` mechanism | Applicable to conflict-event WhatsApp ping rate limiting |

### Verdict: **extend**

The signal pipeline's structural shape — extractor emits a typed record, driver orchestrates per-cycle, health signal proves liveness — maps cleanly onto the sync architecture's reconciliation cycle. The main adaptation is replacing the log-file cursor with a Vikunja poll timestamp (last `updated_since` value per layer). The rolling-window state mechanism is directly applicable to the NFR-003 noise-floor constraint (rate-limit unsafe-class WhatsApp pings).

The key gap is that the signal pipeline is read-only (extract and classify); the sync architecture also needs a **write phase** (`update` in the reconciliation cycle). This is an extension, not a conflict.

documented (`feedback_signal_driven_doc_audit`, `scripts/openclaw/observation/signals/types.py`, `scripts/doc_audit/run.py`)

---

## Pattern 2 — felix-doc-auditor driver pattern

**Canonical references**: memory `reference_felix_doc_auditor_ops`; `scripts/doc_audit/run.py`; `docs/runbooks/doc-auditor-driver-ops.md`.

### Structural shape

The doc-auditor driver is the reference implementation of the "scripts-first, LLM for judgment" pattern:

1. **Systemd user timer** triggers the Python driver on a schedule (hourly). Deterministic entry point.
2. **Python driver** (`scripts/doc_audit/run.py`): collects signals, invokes LLM only for classification/judgment, writes structured output to JSONL activity log + `last-tick.json`.
3. **`last-tick.json`** at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json`: machine-readable health signal. Shape: `{status, timestamp_utc, errors, next_tick_utc, judgment: {token_usage, ...}}`. observed (`docs/runbooks/doc-auditor-driver-ops.md` lines 62–96)
4. **Activity log** (JSONL): append-only log of every audit action with timestamp and outcome. Separate from `last-tick.json`.
5. **Router outputs**: GitHub issue filing (deterministic) + WhatsApp ping (for failures meeting threshold). Both are conditional on signal classification.

### Mapping to sync architecture needs

| Sync need | Pattern component | Fit |
|---|---|---|
| Systemd-timer trigger | Hourly systemd user timer | Strong fit — same trigger model for ~5-min polling |
| Freshness pointer | `last-tick.json` `timestamp_utc` field | Directly reusable: sync driver writes `last_sync_utc` instead of `last-tick` |
| Router for conflict events | WhatsApp router (conditional on classification) | Strong fit — same "log always, WhatsApp only for threshold class" pattern |
| Conflict-event JSONL log | Activity log shape | Extend: activity log → conflict-event log with sync-specific fields |
| Health monitoring | `last-tick.json` | Directly reusable |

### Verdict: **extend**

The doc-auditor driver is the closest existing pattern to the sync architecture's operational shape. It establishes: systemd-timer trigger → Python driver → JSONL output → conditional router → health signal. The sync architecture uses the same skeleton with different signal extraction (Vikunja API instead of log files), different classification (conflict class instead of audit signal), and an additional write phase.

The JSONL activity log shape may need a new schema (conflict-event vs audit-action), but the append-only semantics and file-path convention (`/data/services/openclaw/state/<domain>-history.jsonl`) are already established by ADR-0002 Q3.

documented (`reference_felix_doc_auditor_ops`, `docs/runbooks/doc-auditor-driver-ops.md`)

---

## Pattern 3 — schedule_loader.py + reconciliation flag

**Canonical references**: code at `scripts/habits/schedule_loader.py`; `scripts/habits/reconcile_completions.py`; `scripts/habits/set_due_dates.py --reconcile-schedule`.

### Structural shape

`schedule_loader.py` is a **pure-read config loader** with no API calls:

1. Reads a YAML file (`habits/migrations/phase3-schedule.yaml`) defining habit task IDs, titles, and schedule patterns.
2. Returns typed `ScheduleEntry` dataclasses.
3. `is_active_today(entry, weekday)` returns bool — deterministic.
4. No Vikunja API calls. No state file. No freshness pointer.

`reconcile_completions.py` uses the schedule loader's output as the authoritative list of habit task IDs, then calls `GET /projects/<id>/tasks` to fetch current Vikunja state and performs diff against JSONL history.

The reconciliation pattern it implements:
- `done=true` in Vikunja but no JSONL entry for `done_at` date → backfill with `source: vikunja-ui`
- JSONL has entry but Vikunja shows `done=false` → JSONL wins for history; Vikunja wins for current state

observed (`scripts/habits/reconcile_completions.py` lines 261–400, `scripts/habits/schedule_loader.py` lines 1–50)

### Mapping to sync architecture needs

| Sync need | Pattern component | Fit |
|---|---|---|
| Entity enumeration | Schedule loader provides canonical task ID list | Partial fit — works for habits; sync architecture needs a dynamic entity list (any project, not just habits) |
| State comparison (diff) | `reconcile_completions.py` diff logic | Strong fit — same pattern (Vikunja state vs local JSONL) |
| Backfill on Kent UI write | `source: vikunja-ui` backfill record | Directly applicable — same semantics for conflict detection |
| Per-cycle freshness | No explicit freshness pointer in schedule_loader itself | Gap — sync architecture needs last-polled timestamp; `reconcile_completions.py` does not write one |

### Verdict: **extend**

The reconciliation diff logic in `reconcile_completions.py` is a concrete, working implementation of "compare Vikunja state to local JSONL and backfill discrepancies." It is the direct ancestor of the sync architecture's `diff` + `classify` + `update` phases. The main gaps are: (a) no freshness pointer written after each reconciliation tick, and (b) the entity list is static (loaded from YAML) rather than dynamic (discovered from Vikunja projects).

`schedule_loader.py` itself (pure config loader) is not reusable for the sync architecture directly, but its design pattern (YAML-driven config → typed dataclass) is the correct approach for the sync architecture's layer/entity configuration.

observed (`scripts/habits/reconcile_completions.py`, `scripts/habits/schedule_loader.py`)

---

## Pattern 4 — habits-history.jsonl ledger format

**Canonical references**: live JSONL at `/data/services/openclaw/state/habits-history.jsonl`; `scripts/common/state_log.py`; ADR-0002 Q3.

### Structural shape

The habits JSONL ledger shape (from live sample):
```jsonl
{"domain": "habits", "task_id": 14, "title": "Wake at 5:00 AM", "date": "2026-03-31", "state": "complete", "source": "historical-backfill", "note": "test entry", "timestamp": "2026-04-01T03:17:15Z"}
```

Key structural properties: observed (`/data/services/openclaw/state/habits-history.jsonl` Probes on 2026-06-03)

- **Append-only**: records are never deleted or updated in place.
- **Domain-tagged**: `domain` field allows shared reader library to serve multiple agents.
- **`task_id`**: integer, the Vikunja `id` (not `identifier`). Consistent with stable-identifier verdict in RQ-1.
- **`date`** vs **`timestamp`**: `date` is the day the event is *for*; `timestamp` is when it was recorded. This distinction enables retroactive logging without timestamp confusion.
- **`source`**: `historical-backfill`, `vikunja-ui`, `whatsapp` — provenance tracking.
- **`state`**: domain-specific state token (`complete`, `rescheduled`, `will-not-do` for habits; `level_sent`, `snoozed`, `done`, `rescheduled` for escalation; `proposed`, `confirmed`, `skipped`, `declined` for enrichment). observed (`/data/services/openclaw/state/escalation/project-9-escalation-history.jsonl`, `/data/services/openclaw/state/enrichment/enrichment-history.jsonl`)

The shared library `scripts/common/state_log.py` provides `append(domain, record)` and `read(domain, **filters)`. observed (`scripts/common/state_log.py` exists in codebase — not read in detail)

### Mapping to sync architecture needs

| Sync need | Pattern component | Fit |
|---|---|---|
| Conflict-event log (append-only) | JSONL append-only semantics | Strong fit — same durability model |
| Provenance tracking (`source` field) | `source` field | Directly reusable — `source: vikunja-ui` is already a value |
| Event idempotency key | `task_id + date + state` combination in habits | Partial fit — sync needs a more explicit `event_id` field for idempotent delivery to routers |
| Cross-domain reader | `scripts/common/state_log.py` shared library | Directly reusable for the sync conflict-event log |
| `date` vs `timestamp` semantics | Two-timestamp pattern | Applicable — conflict events need both `ts_observed_utc` and `ts_emitted_utc` |
| Schema versioning | Not present in current JSONL schema | Gap — `data-model.md` § Conflict Event requires `schema_version` for forward-compat with #516 |

### Verdict: **extend**

The habits-history.jsonl pattern is the direct ancestor of the conflict-event log. The format, append semantics, shared library, and provenance tracking are all reusable. The primary extensions needed for a conflict-event log are: (a) an explicit `event_id` idempotency key (currently implicit from `task_id+date+state`), (b) `felix_state_snapshot` and `vikunja_state_snapshot` diff fields, (c) `conflict_class` and `resolution_decision` routing fields, (d) `router_route_set` (which routers received this event), (e) `schema_version` for #516 forward-compat. The `scripts/common/state_log.py` `append()` function can write these extended records without modification if called with the full dict.

observed (`/data/services/openclaw/state/habits-history.jsonl`, `scripts/common/state_log.py`, `data-model.md` §Conflict Event)

---

## Summary Matrix

| Pattern | Verdict | Primary fit | Key gap |
|---|---|---|---|
| Signal-driven monitoring pipeline | **extend** | Cursor/freshness pointer, rolling-window rate-limiting, tick driver structure | Add write phase to reconciliation cycle |
| felix-doc-auditor driver | **extend** | Systemd-timer trigger, `last-tick.json` health signal, conditional router | Adapt signal extraction from log-file to Vikunja API; adapt activity log schema to conflict-event schema |
| schedule_loader + reconciliation flag | **extend** | Diff logic (Vikunja vs JSONL), backfill pattern, `source: vikunja-ui` semantics | Dynamic entity enumeration; freshness pointer write |
| habits-history.jsonl ledger | **extend** | Append-only semantics, provenance, shared library | `event_id`, diff snapshots, `conflict_class`, `schema_version` for #516 compat |

**No pattern requires replacement.** All four patterns are extend-verdict, not not-applicable or replace. This is a strong signal that the sync architecture can be built on existing infrastructure rather than introducing new primitives.

---

## Deferred to implementation

- **`scripts/common/state_log.py` schema extension**: the exact field additions to support conflict events (adding `event_id`, `conflict_class`, `felix_state_snapshot`, etc.) is an implementation decision. The extend verdict means the library API needs a new record type, not a rewrite.
- **Systemd timer cadence for sync**: 5-minute polling cadence requires a systemd user timer (or modification to the existing habits timer). Timer unit creation is Tier 3 (standard change) and belongs in an implementation mission.
- **Rolling-window threshold for WhatsApp pings (NFR-003)**: the count_rolling mechanism from the signal pipeline is applicable, but the threshold value ("≤1/day unsafe-class pings") is an implementation-time calibration decision, not a research finding.
- **`state_log.py` concurrency safety**: multiple agents currently append to separate per-domain JSONL files. A shared sync conflict-event log would be written by a single sync driver, so concurrency is not an issue. But if multi-agent writes are ever needed, `state_log.py`'s `append()` concurrency model needs review.
