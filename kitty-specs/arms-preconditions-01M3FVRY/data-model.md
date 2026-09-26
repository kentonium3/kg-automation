# Data Model — 849 Arms Run Pre-Run Preconditions

The baseline is arms-run-01M3APTA's `data-model.md` and contracts. This file lists only the deltas.

## Run row (ledger `run` record)

| Field | Change | Rule |
|---|---|---|
| `outcome` | **adds** `sampler_unreadable_at_send` | The GTT read failed at `before_send`, after the attempt began. Could-not-check. Terminal for the attempt, never averaged, not scored. Refuses the cell and does NOT stop the session. Distinct from `exceeds_memory_ceiling` and from the pre-attempt `sampler_unreadable` event. |
| `outcome` | **adds** `exceeds_memory_ceiling` | Terminal for the attempt. Never averaged. Not a scored outcome. Carries `memory_ceiling: {measured_gib: float, ceiling_gib: float, stage: "before_send"}`. Distinct from `error`, from `exceeds_model_context`, and from an unreadable sampler (which is `sampler_unreadable`, an event, and no attempt). |
| `falkordb_rss_peak_mib` | **REMOVED** from G rows (retired; must not appear anywhere) | Per-cell G rows carry NO graph-store memory column (D-7a). |

### memory_support

| Key | Type | Rule |
|---|---|---|
| `window_start` | str | canonical UTC isoformat |
| `window_end` | str | canonical UTC isoformat, ≥ `window_start` |
| `in_window_readings` | int | ≥ 0 (excluding the held reading) |
| `held_ts` | str or null | canonical UTC. When present it is STRICTLY before `window_start` and at most `GAP_INTERVALS × interval_s` before it |
| `peak_source` | `"held"` \| `"in_window"` | `"held"` ⇒ `held_ts` present. `"in_window"` ⇒ `in_window_readings ≥ 1`. `in_window_readings == 0` ⇒ `"held"`. A tie ⇒ `"in_window"`. |
| `interval_s` | float | the series' **recorded** real interval: finite and > 0 |
| `last_ts` | str | canonical UTC: the latest reading used; ≤ `window_end` and at most `STALE_INTERVALS × interval_s` before it |

Exactly these keys. There is no other key and no coercion (a bool is not an int).

## attempt_start record

| Field | Change | Rule |
|---|---|---|
| `session_id` | **new**, required | Non-empty str. Replay requires that the most recent `session_gates` event above this row has the same `session_id`, `passed: true`, and `skipped: false`. Skipped is allowed only under a `SKIP_GATES_SHA` header. |

## Event records

| Kind | Change | Detail |
|---|---|---|
| `premise_violated` | **new** | `{arm: str, reason: "tripwire" \| "cross_group_leak", message: str, at_key: RunKey dict}`. Its presence makes the ledger **unusable as a primary, for export, and for `Ledger.summarise()`** (correction C). Rows stay untouched. |
| `memory_ceiling` | unchanged | The pre-cell ceiling refusal stays as it is. |
| `graph_store_memory` | **new**, one per question | `{question, falkordb_cgroup_peak_mib, memory_support}`. The container's cgroup high-water mark over [that question's build start .. its last graph query]. NOT attributable to the question (§5 @`a00abc03`). Validated on write and replay. |
| `graph_store_footprint` | **new**, one per run | `{baseline_mib, all_resident_mib}`: the container before the first build, and the peak with every question's graph resident. The marginal per-graph figure is derivable from them. |

## Arm registration (in-memory, not persisted)

| Field | Rule |
|---|---|
| `refusal` | The unified `ArmRefusal`, the same class for all three arms. Terminality by identity. |
| `answer` \| `bind` | Exactly one, as today. R also exposes `calibration_inputs(views, cache)`. |
| `build_graph`, `drop_graph` | G only. Synchronous wrappers over the persistent loop. |
| `close()` | **new, optional**. G shuts down its loop and driver. The Session calls it on stop. |

## Memory series file (`RUNS_DIR/falkordb-cgroup.jsonl`)

- **Header**: `{series: "arms849-falkordb-cgroup/1", started, container, container_id, interval_s}`. The format id changes with the measure; `interval_s` is the real interval.
- **Records**: `{ts, cgroup_mib, container_id}`. `ts` is canonical UTC only (C12).
- **A failed read writes no line**, so the hole surfaces as a gap.

## State transitions

```mermaid
stateDiagram-v2
    [*] --> attempt_started: begin_attempt (session gates passed; attempt carries session_id)
    attempt_started --> ok: arm answered, samplers readable
    attempt_started --> exceeds_model_context: D over native limit
    attempt_started --> exceeds_memory_ceiling: before_send breach (nothing sent)
    attempt_started --> error: ArmRefusal (terminal) or other failure (retryable)
    attempt_started --> halted: PremiseViolated (run stops; ledger unusable as primary)
    ok --> [*]
    exceeds_model_context --> [*]
    exceeds_memory_ceiling --> [*]
    error --> attempt_started: retryable and attempts remain
    error --> [*]
    halted --> [*]
```
