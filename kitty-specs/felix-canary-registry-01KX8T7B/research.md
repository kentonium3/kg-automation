# Research: Felix component-health canary registry

Phase 0 decisions. Each: **Decision / Rationale / Alternatives considered.**

## R1 — Runner structure: sibling scanner (not extend felix-trust-scan)

- **Decision**: Ship a new `scripts/canary/` package + its own `felix-canary` systemd timer, sharing
  `scripts/common/alert_bus/` for emission. It does NOT extend `felix-trust-scan`.
- **Rationale**: `felix-trust-scan` watches for *trust* drift (rogue crons, fabricated completions) —
  a different domain from *component health*. Two single-responsibility scanners sharing the emit
  substrate keeps each simple and independently evolvable; the alert bus (#701) is the intended shared
  seam, not the scanner. (Operator decision DM 01KX8TY1KRNXQ2Y7C6QKXYEYCR.)
- **Alternatives**: one "felix scanner" doing both — rejected: couples cadence + lifecycle of two
  unrelated concerns, and grows a god-runner.

## R2 — Freshness representation: machine-readable `max_age_seconds`

- **Decision**: Add an optional `max_age_seconds` integer to each `health_check` in
  `service-inventory.json`. Freshness probes compare `now - <timestamp field>` against it. For entries
  that omit it (e.g. pure http/shell liveness), freshness does not apply.
- **Rationale**: deterministic; no fragile regex over the prose `expected` clause (e.g. "within 28
  hours"). The validator can enforce presence for freshness-type checks. ADR-0006 §5 explicitly
  anticipated formalizing this in the canary-registry mission. (Operator decision DM
  01KX8TY3N10EQT1V81Z8DJCMRZ.)
- **Alternatives**: parse the `expected` prose — rejected as brittle free-text parsing (INV against the
  determinism principle).

## R3 — Probe-method taxonomy (evaluate only what the inventory already declares)

- **Decision**: Support exactly the `health_check.method` values already in `service-inventory.json`:
  - `http` — GET `endpoint`; healthy iff status == `expected` (int) within `timeout_seconds`; else failed.
  - `shell` — run `endpoint` command; healthy iff exit 0 (and, where declared, the expected line/marker); else failed.
  - `tick-signal-file` / freshness pointer (`last-tick.json`, `last-backup.json`) — read the state file;
    healthy iff the success/exit/errors fields are good AND the authoritative timestamp is within
    `max_age_seconds`; older ⇒ `stale`; explicit error fields ⇒ `failed`; unreadable/malformed ⇒ `unknown`.
- **Rationale**: derive-from-inventory (C-001) means the probe set is bounded by what components actually
  declare. New methods are added only when a component declares one.
- **Alternatives**: a generic pluggable probe DSL — rejected as over-engineering (#10) for ~3 methods.

## R4 — Health computation + status gate (ADR-0006, verbatim)

- **Decision**: `health.py` maps a `ProbeResult` to a `HealthResult ∈ {healthy, stale, failed, degraded,
  unknown}`. The runner computes health for a component **only when** its declared `status ∈
  {active, running}`; `{suspended, deprecated, planned, retired}` are short-circuited to "suppressed"
  (evaluated-not-emitted). `degraded` is honored only if a component self-reports it (optional).
- **Rationale**: this IS the ADR-0006 contract (C-003); the gate is what makes suspension safe (FR-003).
- **Alternatives**: none — contract-bound.

## R5 — Dedup design

- **Decision**: A dedup-state file keyed by `(component_id, health)` stores the last-emitted timestamp.
  On a repeat of the same `(component_id, health)` within `dedup_window` (default **6 h**, configurable),
  suppress emission but still record the evaluation in the tick ledger. A *transition* (health changes,
  or recovery to healthy) resets the key and is always emitted.
- **Rationale**: prevents per-tick re-paging of a continuing failure (FR-005) while never hiding a state
  change. Mirrors the alert-bus dedup intent; 6 h balances "don't nag" vs "re-remind if still broken".
- **Alternatives**: bus-side dedup only — rejected: the bus dedups identical alerts but the canary should
  own the resend cadence for a *continuing* condition; per-key state is explicit and testable.

## R6 — Severity mapping

- **Decision**: `failed` → **error**; `stale` → **error** (a live component overdue is actionable);
  `degraded` → **warning**; coverage-gap (active/running with no usable `health_check`, FR-006) →
  **warning**; persistent `unknown` on a live component → **warning**. Severities are the alert-bus
  severity vocabulary; routing is the bus's job (INV-003).
- **Rationale**: stale on a live component is a real "it should have run and didn't" incident, so error,
  not warning. Gaps/unknowns are lower-urgency hygiene signals.
- **Alternatives**: stale → warning — rejected: under-alerts the exact silent-failure class this mission
  targets.

## R7 — Cadence

- **Decision**: 15-minute `systemd --user` timer, matching `felix-trust-scan`. Satisfies NFR-001
  (≤15-min detection).
- **Rationale**: reuse the proven trust-scan cadence + pattern; 15 min is well inside NFR-002's ≤30 s
  pass budget for ~30 components.
- **Alternatives**: faster (5 min) — unnecessary for these failure modes and more noise/cost; slower
  (hourly) — violates NFR-001.

## R8 — Self-observability boundary (SC-006, honest scope vs the deferred #269)

- **Decision**: Two layers, and an explicit honest boundary:
  1. **Crash detection (in scope):** the `felix-canary.service` unit declares `OnFailure=` → an
     alert-bus shim unit that emits an **out-of-band** error alert if the runner process fails. This is
     genuinely independent of the runner's own logic (systemd fires it).
  2. **Self-registration (in scope):** the runner is registered in `service-inventory.json` (status
     `active`, a `tick-signal-file` `health_check` on its own `last-tick.json`), so it is a first-class
     canary — any watcher can see it, and once the runner is up it confirms its own liveness each pass.
  3. **Total-silence detection (BOUNDARY — partially deferred):** the case where the *timer never fires
     at all* (so neither the runner nor its `OnFailure` runs) cannot be caught by anything the runner
     owns. Full out-of-band "Felix is silently dead" coverage is **#269 (deferred by the operator)**.
     Interim mitigation available without #269: `felix-trust-scan` (the independent sibling timer) can
     assert the canary runner's `last-tick.json` freshness as one of its checks — a cheap mutual-watch.
- **Rationale**: SC-006 is met for crash + up-but-wrong; the residual (dead timer) is #269's charter.
  Rather than hand-wave SC-006 as fully met, the plan states the boundary and offers the mutual-watch as
  the in-scope approximation. **This is the item most worth adversarial review at the post-plan gate.**
- **Alternatives**: build a mini-#269 here — rejected (scope creep into a deferred issue); claim SC-006
  fully met — rejected (dishonest per INV-001/INV-006).

## R9 — Coverage-gap + unknown handling (INV-002, no silent fallback)

- **Decision**: `registry.py` yields, alongside the CanaryTargets, a **coverage-gap set**: active/running
  service-type entries with a missing/empty/unparseable `health_check`. The runner emits these as
  warning-severity signals (deduped) and records them in the tick ledger. `unknown` health (probe could
  not run conclusively) is likewise recorded; a component that stays `unknown` across the dedup window is
  emitted as a warning.
- **Rationale**: the silent-failure class includes "we thought we were watching it but weren't." Surfacing
  gaps/unknowns is the point (FR-006).
- **Alternatives**: skip un-checkable components silently — rejected (that IS the bug).
