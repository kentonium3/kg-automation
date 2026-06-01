# Phase 1 — Data Model

**Mission**: `signal-driven-monitoring-haiku-gate-01KT22PC`
**Source**: [`spec.md`](./spec.md) §7 Key Entities, refined by [`research.md`](./research.md)

This document defines the canonical entities, their fields, validation rules, and persistence boundaries.

---

## E1 — Signal definition (config-time)

The declarative description of one named, machine-extracted observation.

| Field | Type | Required | Description |
|---|---|---|---|
| `signal_id` | str (snake_case) | ✓ | Unique identifier across all signal definitions. Used as state-file basename and dedup key. |
| `source_kind` | enum `{"openclaw_log", "agent_jsonl", "systemd_journal"}` | ✓ | What kind of source data the extractor reads. Initial mission uses only `openclaw_log`. |
| `source_path_pattern` | str (glob) | ✓ | Path or glob pointing at the source. E.g., `/tmp/openclaw/openclaw-{YYYY-MM-DD}.log`. |
| `match_pattern` | str (regex or substring) | ✓ | What to grep for. Stored verbatim; extractor decides whether to treat as regex or substring. |
| `cycle_threshold` | int | ✓ | Trip if count in the current 15-min cycle ≥ this value. |
| `rolling_window_minutes` | int | ✓ | Width of the rolling secondary window (default 60). |
| `rolling_threshold` | int | ✓ | Trip if count over the rolling window ≥ this value. |
| `dedup_strategy` | enum `{"open_issue_present", "time_since_last_filed"}` | ✓ | How to suppress duplicate filings. Mission uses `open_issue_present` exclusively. |
| `dedup_window_hours` | int | ✓ | For `time_since_last_filed` strategy; ignored when `open_issue_present`. Set to 24 by default. |
| `priority` | enum `{"P1", "P2"}` | ✓ | Issue priority for `felix-file-issue.py`. |
| `area_label` | str | ✓ | Area label (e.g., `felix-core`, `tooling`). |
| `tier_hypothesis` | enum `{"0","1","2","3","4","unknown"}` | ✓ | Tier hypothesis for the filed issue body. |
| `excerpt_lines` | int | ✓ | Number of representative log lines to include in the filed issue body (default 5). |
| `enabled` | bool | ✓ | Hard kill switch per signal. Default `true`. |

**Storage**: `scripts/openclaw/observation/signals/config.toml` (TOML, in-repo, deployed to office2 via existing deploy pattern).

**Validation rules**:
- `signal_id` unique across the file.
- `cycle_threshold ≥ 1`, `rolling_threshold ≥ cycle_threshold`.
- `match_pattern` non-empty.
- `source_path_pattern` resolves to at least one existing file at cycle start (warning if not — signal evaluation skipped that cycle).

---

## E2 — Signal state (runtime, persistent)

Per-signal counter state that survives cycle boundaries and process restarts. One file per signal.

| Field | Type | Required | Description |
|---|---|---|---|
| `signal_id` | str | ✓ | Matches the signal definition. |
| `cycle_id` | str (ULID) | ✓ | ID of the last cycle that updated this state. |
| `last_cycle_count` | int | ✓ | Event count observed in the last cycle. |
| `rolling_buckets` | list[`{cycle_id, started_at, count}`] | ✓ | Per-cycle counts within the rolling window (≤ `rolling_window_minutes/15` entries). |
| `last_event_at_utc` | str (ISO 8601) \| null | ✓ | Timestamp of the most recent matching event seen. Null if never observed. |
| `last_filed_issue_ref` | int \| null | ✓ | Issue number of the most recently filed (and not-yet-closed) issue. Null if none open. |
| `last_filed_at_utc` | str (ISO 8601) \| null | ✓ | When `last_filed_issue_ref` was filed. |
| `last_log_position` | dict `{path: str, byte_offset: int, mtime: float}` \| null | ✓ | Cursor for the source file — extractor resumes from here. Null on cold start. |

**Storage**: `/data/services/openclaw/felix-core-digest-signals/state/<signal_id>.json` (per-signal, atomic write via tmp+rename).

**Validation rules**:
- Cold-start recovery: if file missing or `last_log_position` is null, the next cycle re-scans the most recent N=4 cycles of source content (1 hour) before trusting state. Emits a one-time warning to the systemd journal.
- Clock-skew tolerance: `last_event_at_utc` may be in the past relative to `cycle_id`; this is normal (events lag the cycle that processes them).
- Rolling-buckets list eviction: drop entries with `started_at` older than `rolling_window_minutes` minutes ago at cycle start.

---

## E3 — Cycle record (runtime, transient → ledger)

The per-cycle execution record. One row per cycle in the ledger; the latest also surfaces in `last-tick.json`.

| Field | Type | Required | Description |
|---|---|---|---|
| `cycle_id` | str (ULID) | ✓ | Unique cycle identifier. |
| `started_at_utc` | str (ISO 8601) | ✓ | Cycle start timestamp. |
| `duration_ms` | int | ✓ | Wall-clock duration of the cycle. |
| `signals_evaluated` | list[`{signal_id, count, threshold_status}`] | ✓ | Per-signal evaluation summary. `threshold_status ∈ {"below", "tripped_cycle", "tripped_rolling", "tripped_both"}` |
| `issues_filed` | list[`{signal_id, issue_number, issue_url}`] | ✓ | Issues filed this cycle (empty if none). |
| `issues_skipped_dedup` | list[`{signal_id, existing_issue_ref}`] | ✓ | Tripped signals where filing was suppressed by an existing open issue. |
| `errors` | list[`{signal_id, error_type, error_message}`] | ✓ | Per-signal errors. Empty list = clean cycle. |
| `exit_status` | enum `{"success", "partial", "failure"}` | ✓ | `success` = all signals OK, `partial` = some errors but cycle ran, `failure` = cycle aborted before completion. |

**Storage**:
- Latest cycle → `/data/services/openclaw/felix-core-digest-signals/last-tick.json` (overwritten each cycle, atomic).
- All cycles → `/data/services/openclaw/felix-core-digest-signals/signals-ledger.jsonl` (append-only, one row per cycle, JSON Lines).

**Health-check contract**: `last-tick.json` must show `started_at_utc` within the last ~30 minutes; staleness beyond 2 hours triggers operator attention (matches `felix-doc-auditor` convention).

---

## E4 — Heartbeat gate decision (runtime, transient → ledger)

The per-heartbeat-tick gate decision record.

| Field | Type | Required | Description |
|---|---|---|---|
| `tick_id` | str (ULID) | ✓ | Unique tick identifier. |
| `started_at_utc` | str (ISO 8601) | ✓ | Tick start timestamp. |
| `gate_latency_ms` | int | ✓ | Time spent at the gate (Haiku call + decision logic). |
| `digest_snapshot_at_utc` | str (ISO 8601) | ✓ | Timestamp of the felix-core-digest output the gate read. |
| `heartbeat_md_state` | enum `{"empty", "has_tasks"}` | ✓ | What the gate observed in the heartbeat contract file. |
| `novelty_markers_seen` | list[str] | ✓ | Signal IDs from the digest that the gate flagged as novel/notable for this tick. |
| `outcome` | enum `{"HEARTBEAT_OK", "LOG_AND_SKIP", "ESCALATE_TO_SONNET"}` | ✓ | The gate's routing decision. |
| `reason` | str (≤500 chars) | ✓ | One-paragraph reason. For `HEARTBEAT_OK`, may be empty. For `ESCALATE_TO_SONNET`, required. |
| `escalated_event_id` | str \| null | ✓ | If outcome is ESCALATE, the openclaw event id returned by `openclaw system event`. |
| `gate_input_tokens` | int | ✓ | Tokens billed to Haiku for this tick (0 on fallback). |
| `gate_cache_hit_tokens` | int | ✓ | Cache-hit tokens (billed at 10%). |
| `gate_output_tokens` | int | ✓ | Output tokens from Haiku. |
| `fallback_invoked` | bool | ✓ | True if the gate failed and the heartbeat fell back to expensive-tier per FR-011. |
| `errors` | list[`{error_type, error_message}`] | ✓ | Per-tick errors. |

**Storage**:
- Latest tick → `/data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json` (overwritten each tick, atomic).
- All ticks → `/data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl` (append-only JSON Lines).

---

## Relationships

```
Signal definition (E1, config)
   └─→ defines what to extract
            │
            ▼
Signal state (E2, persistent)
   └─→ accumulates counts across cycles
            │
            ▼
Cycle record (E3, per-tick)
   └─→ summarizes one extraction pass + any filings
            │
            ▼
GitHub issue (external)
   └─→ referenced by Signal state.last_filed_issue_ref
            │
            ▼
[Independent loop] Heartbeat gate decision (E4)
   └─→ reads E3's last-tick.json + heartbeat contract file
   └─→ routes to expensive-tier via `openclaw system event --mode now` on escalate
```

The signal-extraction loop (E1→E2→E3→GitHub) and the gate loop (E4 reading E3 output) are loosely coupled via file artifacts. Either can be deployed and tested independently.

---

## State transitions

### Signal state lifecycle

```
[no state file]
     │
     │ cycle 1: cold-start re-scan
     ▼
[populated, last_filed_issue_ref=null]
     │
     │ threshold crossed AND no open matching issue
     ▼
[populated, last_filed_issue_ref=<issue#>]
     │
     │ (a) issue closed by operator/automation:
     │     next cycle that trips → file new issue
     │ (b) issue still open, signal trips again:
     │     no new filing; cycle record notes "skipped_dedup"
```

Crucially: when `last_filed_issue_ref` becomes "closed" upstream (operator action), the next threshold trip files a new issue. State transition is detected by querying issue state via `gh issue view --json state` at filing-decision time.

### Heartbeat gate decision lifecycle

Stateless per tick — no transitions between ticks. The gate's only "memory" across ticks is the structured ledger (read-only from the gate's perspective).

---

## Why these entities and not others

- **No "Heartbeat" entity**: the heartbeat is OpenClaw infrastructure; we wrap it but don't own the schedule model. `E4` captures one *gate decision*, which is the only state we author per tick.
- **No "Signal source" entity in data model**: source-kind is a field on the Signal definition. Distinct source-kind extractors are code modules under `signals/`, not data records.
- **No "Filed issue" entity**: GitHub owns the canonical issue record. We reference it by number/url from `E2.last_filed_issue_ref` and `E3.issues_filed[]`.
