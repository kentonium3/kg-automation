# Feature Specification: Felix component-health canary registry

**Mission**: felix-canary-registry-01KX8T7B
**Status**: Draft
**Created**: 2026-07-11
**Source issue**: kentonium3/kg-automation#327 (Foundation 1 / Epic #516)
**Governing contract**: ADR-0006 — Felix component lifecycle status contract

## Summary

Felix components fail silently. Today when a scheduled job stops running, a service
dies, or a sync tick starts erroring, Kent finds out only through a downstream symptom —
a reminder that never went out, a backup that turns out to be days old — often long after
the fact. Yet nearly every Felix component already *declares* how its health can be
checked (`service-inventory.json` requires a `health_check` for every service-type entry),
and the delivery path for alerts already exists (the #701 unified alert bus). What is
missing is the thing in the middle: a deterministic watcher that evaluates those declared
health checks on a schedule and raises an alert when a live component is unhealthy.

This mission builds that watcher — the **canary registry**: a scheduled, deterministic
runner that reads each component's declared `health_check` directly from
`service-inventory.json`, computes the component's `health` per ADR-0006, gates alerting on
the component's declared `status` (only `active`/`running` alert; `suspended`-class states
are suppressed by construction), and emits `stale`/`failed` conditions to the #701 bus. The
restic backup ships as the first concrete canary.

## User Scenarios & Testing

### Primary scenario (happy path of detection)

- **Primary actor**: the canary runner (deterministic, scheduled), watching on Kent's behalf.
- **Trigger**: a scheduled tick of the runner (target cadence ≤ 15 minutes).
- **Flow**: the runner reads every service-type entry in `service-inventory.json`; for each
  one whose declared `status` is `active` or `running`, it evaluates the declared
  `health_check` and computes a `health` value. For a component computed `stale` or `failed`,
  it emits a structured alert to the #701 bus.
- **Success outcome**: when a monitored active component fails or goes stale, Kent receives
  an alert on his phone within one canary interval — minutes, not hours or days — naming the
  component, its computed health, and the evidence.

### Exception / branch scenarios

- **Suspended component goes stale**: a component whose declared `status` is
  `suspended`/`deprecated`/`planned`/`retired` is evaluated but never alerted. A suspended
  backup that hasn't run is *expected*, not an incident. No alert is produced.
- **Health check cannot be evaluated**: if a probe cannot run conclusively (endpoint
  unreachable in an inconclusive way, malformed pointer), the component's health is `unknown`.
  A `unknown` that **persists past the dedup window** on a live component is emitted as a
  warning — a component we cannot even evaluate is itself a signal — never silently dropped.
- **Continuing failure**: a component that stays failed across many ticks pages Kent once per
  dedup window, not on every tick.
- **Live component with no usable health check**: an `active`/`running` entry that lacks a
  declared or evaluable `health_check` is reported as a coverage gap, not silently skipped.
- **The runner itself dies**: a *crashing* run fires an out-of-band alert via the service unit's
  `OnFailure=` hook (systemd, independent of runner logic). A *dead timer* or whole-host silence cannot be
  caught by anything the runner owns; the runner is self-registered in the inventory so the deferred
  out-of-band watchdog (#269) will detect it. Full dead-timer/silence detection is out of scope here (#269).

### Rules that must always hold

- A component is only alerted on when its declared `status` is `active` or `running`
  (ADR-0006 status-gates-health). This invariant is what makes suspension safe.
- An alert is never lost silently: every computed alert is recorded to the durable local
  ledger even if bus delivery fails.
- The runner never has an LLM in its evaluation path.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | On each scheduled tick, the runner MUST evaluate every `service-inventory.json` entry whose type denotes a runtime service (has runtime health), computing exactly one `health` value per component from its declared `health_check`. | Accepted |
| FR-002 | The runner MUST support the real `health_check.method` vocabulary present in `service-inventory.json` today: `http`, `shell`, `systemd-status`, freshness-pointer (`tick-signal-file`/`signal-file`/`state-file`, reading the pointer path from `state_path` or `endpoint`), log-scan (`log-tail`/`journal`), and command (`self-check-command`/`self-test`). Variant names are unified in the probe layer (no inventory rewrite). An entry with `method: none`, a missing/empty `health_check`, or an unhandled method is a coverage gap (FR-006), not a silently-skipped component. | Accepted |
| FR-003 | The runner MUST gate on declared `status` per ADR-0006: components with `status` in {`active`,`running`} are alert-eligible and probed; components with `status` in {`suspended`,`deprecated`,`planned`,`retired`} MUST be suppressed — **not probed**, recorded as `suppressed`, never emitted (gate-before-probe). | Accepted |
| FR-004 | For an alert-eligible component computed as `stale` or `failed`, the runner MUST emit a structured alert to the #701 unified alert bus containing the component identity, the computed `health`, and the failing evidence. A `degraded` result MUST emit at a lower severity. | Accepted |
| FR-005 | The runner MUST deduplicate repeated alerts for the same component + health condition within a configurable window, so a continuing failure does not re-page on every tick. | Accepted |
| FR-006 | An alert-eligible component with a missing or unusable `health_check` MUST be surfaced as a distinct coverage-gap signal, never silently skipped. | Accepted |
| FR-007 | The restic backup — which **already** writes a `last-backup.json` pointer and is registered with a freshness `health_check` (#511 shipped) — MUST be normalized to the registry's uniform freshness path (add `max_age_seconds: 100800`) so it is the first component the runner evaluates end-to-end via the shared freshness probe. | Accepted |
| FR-008 | The runner MUST record each tick's per-component evaluation outcome (component, computed health, evidence, timestamp) to a durable local state/ledger, consistent with existing tick-signal patterns, supporting both observability and dedup. | Accepted |
| FR-009 | The runner MUST perform all health evaluation and alert decisions deterministically, with no LLM invocation in its execution path. | Accepted |
| FR-010 | The runner MUST itself be a registered Felix component (declared `status` + `health_check` + tick signal), so that a stalled or failed runner is itself detectable. | Accepted |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Detection latency for a failed/stale alert-eligible component. | ≤ one canary interval + one delivery attempt; canary interval ≤ 15 minutes (so time-to-detect ≤ ~15 min, versus hours-to-days today). | Accepted |
| NFR-002 | A full evaluation pass over all registered components completes well within the tick interval. | ≤ 30 seconds per full pass. | Accepted |
| NFR-003 | LLM cost of the runner. | 0 tokens per tick (fully deterministic). | Accepted |
| NFR-004 | Robustness of a pass. | A probe error on one component MUST NOT abort the pass; that component records `unknown` and evaluation continues. 0 whole-pass aborts from a single-component probe failure. | Accepted |
| NFR-005 | Durability of alert records. | 100% of computed alerts are written to the local ledger even when bus delivery fails (consistent with the #706 alert-bus ledger). | Accepted |

## Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Canaries MUST derive from `service-inventory.json`'s existing `health_check` fields; no separate `canaries.json` registry is introduced (single source of truth). | Accepted |
| C-002 | Alert emission MUST go through the existing #701 shared emit library (`scripts/common/alert_bus/`); no new delivery path is created. | Accepted |
| C-003 | Health/status vocabulary and the status-gates-health rule MUST follow ADR-0006 exactly. | Accepted |
| C-004 | The runner MUST deploy to office2 via a `deploys/queued/<name>.yaml` manifest as a systemd user timer; the deploy MUST rebaseline the affected audited surfaces (systemd unit is an audited surface). | Accepted |
| C-005 | The runner MUST NOT modify the behavior of the components it watches; it only reads their `health_check` declarations and state files. (The sole component-side change is the restic backup script gaining its health-pointer write, per FR-007.) | Accepted |

## Success Criteria

- **SC-001**: When a monitored `active`/`running` component fails or goes stale, Kent receives an alert within 15 minutes — versus the current hours-to-days.
- **SC-002**: A `suspended` component that goes stale produces zero alerts.
- **SC-003**: Every `active`/`running` component that declares a `health_check` is evaluated on every cycle (no silent coverage gaps); any live component lacking a usable `health_check` is reported.
- **SC-004**: A component that stays failed pages Kent once per dedup window, not on every cycle.
- **SC-005**: The restic backup's staleness is detectable through its health-pointer — deliberately aging the pointer produces a `stale`/`failed` alert (the #511 dogfood, end-to-end).
- **SC-006**: If the canary runner **crashes**, an out-of-band alert fires (systemd `OnFailure`), and the runner is registered in the inventory so the deferred out-of-band watchdog (#269) can detect a dead timer / total silence. (Full dead-timer & whole-host-silence detection is out of scope here, tracked by #269.)

## Key Entities

- **Component** — a `service-inventory.json` entry: identity, type, declared `status`, `health_check`.
- **Canary evaluation result** — component identity, computed `health` (`healthy`/`stale`/`failed`/`degraded`/`unknown`), failing evidence, timestamp.
- **Alert** — the #701 bus record: severity, signal id, message, evidence.
- **Tick-signal / health-pointer file** — the per-component freshness/state file the runner reads (and, for the backup, the file FR-007 introduces).

## Assumptions

- ADR-0006 (the lifecycle status contract) is authoritative and already committed on main.
- The #701 unified alert bus and its shared emit library are deployed and available (shipped), and the #706 ledger convention applies.
- `service-inventory.json` `health_check` declarations are the intended source of truth for what "healthy" means per component; the runner's coverage-gap reporting (FR-006) helps keep them honest.
- The `felix-trust-scan` deterministic-scanner pattern (systemd user timer, ~15-minute cadence, `scripts/trust/`) is a suitable structural template and cadence reference. Whether the canary runner extends `felix-trust-scan` or runs as a sibling sharing the emit library is a design decision deferred to `/spec-kitty.plan`.
- Whether the per-component freshness threshold is formalized as a machine-readable field on `health_check` or parsed from the existing prose `expected` clause is a design decision deferred to `/spec-kitty.plan`.

## Out of Scope

- Reworking the #701 alert bus or its delivery channels (reused as-is).
- A separate declarative canary file (`canaries.json`) — explicitly rejected in favor of deriving from the inventory (C-001).
- Retrofitting missing `health_check` declarations onto every component in one pass — the runner *reports* coverage gaps (FR-006); closing them beyond the backup (FR-007) is follow-up work.
- Any LLM-based interpretation or triage of failures (Foundation 1 keeps the hot path deterministic).
