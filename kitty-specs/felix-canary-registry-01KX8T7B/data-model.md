# Data Model: Felix component-health canary registry

## Entities

### CanaryTarget (derived, in-memory)
Produced by `registry.py` from one `service-inventory.json` entry.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `component_id` | str | inventory `name`/`id` | stable identity used in alerts + dedup keys |
| `type` | str | inventory `type` | one of the SERVICE_TYPES |
| `status` | str | inventory `status` | ADR-0006 declared status |
| `alert_eligible` | bool | derived | `status ∈ {active, running}` |
| `health_check` | object\|None | inventory `health_check` | probe spec (below); None ⇒ coverage gap |

### health_check (schema delta — the only inventory schema change)
Existing fields (`method`, `endpoint`, `expected`, `timeout_seconds`, `state_path`, `note`) are unchanged.
**Added:** one optional field.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `max_age_seconds` | int (>0) | optional | Freshness bound for freshness/tick-file checks. When present, the authoritative timestamp must be within this many seconds of now, else `stale`. Omitted for pure liveness (http/shell) checks. |

Validator (`validate_architecture_data.py`) rule: if present, `max_age_seconds` must be a positive int;
for `method` values that are freshness-based (tick-signal-file / freshness pointer) on an alert-eligible
entry, `max_age_seconds` SHOULD be present (warn-only, consistent with the existing warn→strict pattern).

### ProbeResult (in-memory)
Output of a probe evaluator in `probes.py`.

| Field | Type | Notes |
|-------|------|-------|
| `ok` | bool | probe's raw pass/fail |
| `stale` | bool | freshness bound exceeded (freshness probes only) |
| `evaluable` | bool | false ⇒ probe could not run conclusively → `unknown` |
| `evidence` | str | human-readable: status code, exit code, age, or error |

### HealthResult (in-memory)
Output of `health.py` — the ADR-0006 observed-health value + emission decision.

| Field | Type | Notes |
|-------|------|-------|
| `component_id` | str | |
| `health` | enum | `healthy` \| `stale` \| `failed` \| `degraded` \| `unknown` |
| `alert_eligible` | bool | from CanaryTarget (status gate) |
| `should_emit` | bool | `alert_eligible AND health ∈ {stale, failed, degraded}` (subject to dedup) |
| `severity` | enum\|None | error (failed/stale) \| warning (degraded/gap/persistent-unknown) |
| `evidence` | str | carried from ProbeResult |
| `evaluated_at` | str (ISO-8601 UTC) | |

### DedupState (persisted — `/data/services/felix-canary/state/dedup.json`)
Map `"<component_id>::<health>"` → `{ "last_emitted_utc": ISO8601 }`. Atomic `.tmp`+`mv` write.
A health transition or recovery removes/resets the component's keys.

### TickSignal (persisted — `/data/services/felix-canary/state/last-tick.json`)
The runner's own health-pointer (makes the runner a canary of itself, FR-010). Atomic write.

| Field | Type | Notes |
|-------|------|-------|
| `status` | str | `success` \| `error` |
| `completed_at_utc` | str | freshness anchor for the runner's own `health_check` |
| `components_evaluated` | int | |
| `emitted` | int | alerts emitted this pass |
| `suppressed_dedup` | int | |
| `coverage_gaps` | int | |
| `errors` | list | per-component probe errors (does not abort the pass, NFR-004) |
| `duration_ms` | int | pass timing (NFR-002 witness) |

Alerts themselves reuse the **#701 Alert** model + **#706 ledger** — no new alert schema.

## State set & transitions (health)

```
             ┌──────────── probe evaluable? ── no ──► unknown
             │
active/      │   ok & fresh ──► healthy
running ─────┤   ok & !fresh ─► stale        (freshness probes)
(gated)      │   !ok ─────────► failed
             │   self-reported partial ─► degraded
             │
suspended/deprecated/planned/retired ─► SUPPRESSED (evaluated, never emitted)
```

Emission (subject to dedup): `stale`/`failed` → error; `degraded` → warning; `healthy` → none.
Transition to `healthy` from a previously-emitted bad state → optional recovery notice (emit, resets dedup).

## Invariants

- **INV-A (status gate):** `should_emit` can be true only if `status ∈ {active, running}`. A suspended
  component NEVER emits, regardless of computed health. (ADR-0006 §4; FR-003; SC-002.)
- **INV-B (no silent drop):** every CanaryTarget produces either a HealthResult or a coverage-gap record;
  nothing is skipped silently. (FR-006; INV-002.)
- **INV-C (durable record):** every emitted alert is written to the #706 ledger even if bus delivery
  fails. (NFR-005.)
- **INV-D (fail-open pass):** a probe raising on one component records `unknown` + an `errors[]` entry and
  the pass continues. (NFR-004.)
- **INV-E (determinism):** no LLM call anywhere in registry/probes/health/dedup/run. (NFR-003.)
