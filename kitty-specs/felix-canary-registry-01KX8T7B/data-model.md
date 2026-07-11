# Data Model: Felix component-health canary registry

Revised 2026-07-11 after the post-plan Codex review (folds F3–F8).

## Entities

### CanaryTarget (derived, in-memory)
Produced by `registry.py` from one `service-inventory.json` entry.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `component_id` | str | inventory `name`/`id` | stable identity; used as the alert `source` and dedup key |
| `type` | str | inventory `type` | one of the SERVICE_TYPES |
| `status` | str | inventory `status` | ADR-0006 declared status |
| `alert_eligible` | bool | derived | `status ∈ {active, running}` |
| `health_check` | object\|None | inventory `health_check` | probe spec; None / `method: none` / unhandled method ⇒ coverage gap |
| `pointer_path` | str\|None | `health_check.state_path` **else** `health_check.endpoint` | **F4**: freshness pointer path lives in `state_path` for some entries (restic) and in `endpoint` for others (agent-prompt-sync); the loader resolves state_path-first-then-endpoint |

### health_check (schema delta — the only inventory schema change)
Existing fields (`method`, `endpoint`, `expected`, `timeout_seconds`, `state_path`, `note`) unchanged.
**Added:** one optional field.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `max_age_seconds` | int (>0) | optional | Freshness bound for freshness/log-scan checks. When present, the authoritative timestamp/most-recent-event must be within this many seconds of now, else `stale`. Omitted for pure liveness (http/systemd-status/command) checks. |

Validator (`validate_architecture_data.py`): if present, `max_age_seconds` MUST be a positive int;
warn (not block) when an alert-eligible freshness/log-scan `health_check` omits it (warn→strict, matching
the existing STATUS_ENUM/health-check pattern).

Method vocabulary handled (per research R3, in code — NOT normalized in the inventory):
`http` · `shell` · `systemd-status` · freshness pointer (`tick-signal-file`/`signal-file`/`state-file`) ·
log-scan (`log-tail`/`journal`) · command (`self-check-command`/`self-test`) · `none`/unhandled ⇒ gap.

### ProbeResult (in-memory)
Output of a probe evaluator in `probes.py`.

| Field | Type | Notes |
|-------|------|-------|
| `ok` | bool | probe's raw pass/fail |
| `stale` | bool | freshness/recency bound exceeded (freshness + log-scan probes only) |
| `evaluable` | bool | false ⇒ probe could not run conclusively → `unknown` |
| `evidence` | str | human-readable: status code, exit code, age, missing marker, or error |

### HealthResult (in-memory) — REVISED (F5, F6)
Output of `health.py`.

| Field | Type | Notes |
|-------|------|-------|
| `component_id` | str | |
| `outcome` | enum | `healthy` \| `stale` \| `failed` \| `degraded` \| `unknown` \| **`suppressed`** \| **`gap`** |
| `alert_eligible` | bool | from CanaryTarget (status gate) |
| `should_emit` | bool | see emission rule below (F5: now includes persistent `unknown` and `gap`) |
| `severity` | enum\|None | ERROR (failed/stale) \| WARN (degraded/gap/persistent-unknown) \| INFO (recovery) \| None (healthy/suppressed) |
| `evidence` | str | carried from ProbeResult |
| `evaluated_at` | str (ISO-8601 UTC) | |

**Suppression rule (F6, single rule):** if `alert_eligible` is false, the component is **not probed**;
`outcome = suppressed`, `should_emit = false`. Probing happens only for alert-eligible components.

**Emission rule (F5):** for an alert-eligible component, `should_emit` is true when
`outcome ∈ {stale, failed, degraded}` **OR** `outcome ∈ {unknown, gap}` **and** it has persisted past the
dedup window — subject to the dedup transition logic below. `healthy` emits only as a recovery INFO.

### DedupState (persisted — `/data/services/felix-canary/state/dedup.json`) — REVISED (F7)
Map `component_id` → `{ "last_outcome": str, "last_emitted_utc": ISO8601 }`. Atomic `.tmp`+`mv`.

- Outcome **changed** vs `last_outcome` (any transition, incl. → `healthy`) ⇒ **always emit** (recovery →
  INFO "recovered"); update the key. Mandatory reset — closes `failed → healthy → failed` (F7).
- Outcome **unchanged** and bad and within `dedup_window` (default 6 h) ⇒ suppress emission, still ledger it.
- Outcome unchanged, bad, window elapsed ⇒ re-emit; update.

### ComponentLedger (persisted — `/data/services/felix-canary/ledger/<date>.jsonl`) — NEW (F8)
Append-only, date-partitioned. One line per component per tick: `{component_id, outcome, evidence,
emitted (bool), suppressed_dedup (bool), evaluated_at}`. Records **every** outcome including
healthy/suppressed/gap/deduped — satisfies FR-008 (the aggregate tick-signal + alert-bus ledger do not).
Best-effort; a ledger write failure never aborts the pass (INV-D).

### TickSignal (persisted — `/data/services/felix-canary/state/last-tick.json`)
The runner's own health-pointer (makes the runner a canary of itself, FR-010). Atomic write.

| Field | Type | Notes |
|-------|------|-------|
| `status` | str | `success` \| `error` |
| `completed_at_utc` | str | freshness anchor for the runner's own `health_check` (15-min → `max_age_seconds` ~2100) |
| `components_evaluated` | int | |
| `emitted` | int | · `suppressed_dedup` int · `coverage_gaps` int · `suppressed_status` int |
| `errors` | list | per-component probe errors (does not abort the pass, NFR-004) |
| `duration_ms` | int | pass timing (NFR-002 witness) |

### Alert (reuse #701 — CORRECTED per F3)
The runner emits via `scripts/common/alert_bus.emit(Alert(...))`. The real `Alert` dataclass:

| Field | Type | Canary usage |
|-------|------|--------------|
| `source` | str | `felix-canary` (or `felix-canary:<component_id>`) — carries stable signal identity (F3) |
| `severity` | `Severity` | `Severity.ERROR` / `WARN` / `INFO` (enum — NOT the string "warning") (F3) |
| `title` | str | e.g. `"<component_id> health: <outcome>"` |
| `description` | str | the message + evidence text (F3: `description`, there is no `message` field) |
| `action` | str\|None | optional remediation hint |
| `details` | dict[str,str] | `{component_id, outcome, evidence, ...}` (bus redaction rules apply) |

`emit(alert) -> AlertResult`; the #706 ledger records every emit attempt + result (INV-C).

## State set & transitions (health)

```
alert_eligible? ── no ─────────────────────────► suppressed  (NOT probed; ledgered; never emitted)   [F6]
       │ yes
       ▼
probe evaluable? ── no ──► unknown ──(persists past window)──► emit WARN                              [F5]
       │ yes
       ├─ ok & fresh (or no freshness bound) ─► healthy ──(was bad)──► emit INFO "recovered"          [F7]
       ├─ ok & stale (freshness bound exceeded) ─► stale ─► emit ERROR
       ├─ not ok ─────────────────────────────► failed ─► emit ERROR
       └─ self-reported partial ───────────────► degraded ─► emit WARN

coverage gap (method none/missing/unhandled on an active/running entry) ─► gap ─► emit WARN           [F5]
```

## Invariants

- **INV-A (status gate, F6):** a suppressed-status component is never probed and never emits. `should_emit`
  ⟹ `alert_eligible`. (ADR-0006 §4; FR-003; SC-002.)
- **INV-B (no silent drop):** every inventory service-type entry yields a ledger line — a HealthResult,
  a `suppressed`, or a `gap`. Nothing is skipped silently. (FR-006; INV-002.)
- **INV-C (durable alert record):** every emitted alert is in the #706 ledger even on delivery failure. (NFR-005.)
- **INV-D (fail-open pass):** a probe or ledger-write raising on one component records `unknown`/an error
  and the pass continues. (NFR-004.)
- **INV-E (determinism):** no LLM call anywhere. (NFR-003.)
- **INV-F (transition never swallowed, F7):** any change in `outcome` emits, regardless of dedup window.
