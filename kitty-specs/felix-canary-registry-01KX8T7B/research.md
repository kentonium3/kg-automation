# Research: Felix component-health canary registry

Phase 0 decisions. Each: **Decision / Rationale / Alternatives considered.**
Revised 2026-07-11 after the post-plan Codex review (folded findings F1–F10).

## R1 — Runner structure: sibling scanner (not extend felix-trust-scan)

- **Decision**: Ship a new `scripts/canary/` package + its own `felix-canary` systemd timer, sharing
  `scripts/common/alert_bus/` for emission. It does NOT extend `felix-trust-scan`.
- **Rationale**: `felix-trust-scan` watches for *trust* drift (rogue crons, fabricated completions) —
  a different domain from *component health*. Two single-responsibility scanners sharing the emit
  substrate keeps each simple and independently evolvable. (Operator decision DM 01KX8TY1KRNXQ2Y7C6QKXYEYCR.)
- **Alternatives**: one "felix scanner" doing both — rejected: couples cadence + lifecycle of two
  unrelated concerns.

## R2 — Freshness representation: machine-readable `max_age_seconds`

- **Decision**: Add an optional `max_age_seconds` integer to each `health_check` in
  `service-inventory.json`. Freshness probes compare `now - <timestamp field>` against it. Entries that
  omit it get no freshness dimension (liveness only).
- **Rationale**: deterministic; no fragile regex over the prose `expected` clause. ADR-0006 §5
  anticipated this. (Operator decision DM 01KX8TY3N10EQT1V81Z8DJCMRZ.)
- **Alternatives**: parse the `expected` prose — rejected as brittle free-text parsing.

## R3 — Probe-method taxonomy (REVISED per Codex F1 — support the REAL inventory vocabulary in code)

The inventory does **not** use only 3 methods. A live audit of `service-inventory.json` found these
`health_check.method` values across active/running service-type entries:

| method | count (active/running) | example entries | probe strategy |
|--------|------------------------|-----------------|----------------|
| `http` | 3 | vikunja, transcribe-api, ollama | GET endpoint; healthy iff status == `expected` (int) within `timeout_seconds`; else failed |
| `shell` | 2 | restic-backup, security-monitor | run `endpoint`; healthy iff exit 0 (and expected marker if the check emits one); non-zero ⇒ failed |
| `systemd-status` | 3 | obsidian-sync, second-brain-sync, openclaw-gateway | run the `endpoint` (`systemctl [--user] status …`); healthy iff active/running; else failed |
| `tick-signal-file` / `signal-file` / `state-file` (**one freshness probe**) | ~8 | agent-prompt-sync, felix-core-digest, felix-heartbeat-gate, felix-habit-sweeper, felix-deployer, felix-doc-auditor(suspended), felix-health-check, felix-trust-scan | read the pointer JSON; healthy iff its success/exit/errors fields are good AND its authoritative timestamp is within `max_age_seconds`; older ⇒ `stale`; explicit error fields ⇒ `failed`; unreadable ⇒ `unknown` |
| `log-tail` / `journal` (**one log-scan probe**) | 3 | obsidian-sync-heartbeat, credential-health-check, credential-liveness-probe | run the `endpoint` (a `tail`/`journalctl [| grep]`); healthy iff the expected marker/event is present in the window; else stale/failed |
| `command` (`self-check-command` / `self-test`) | 3 | felix-calendar-helper, felix-timelog-helper, alert-bus | run the component's own self-check; healthy iff exit 0; else failed. (These are *libraries*; their `endpoint` names the self-check to run.) |
| `none` | 4 | inbox-processing, habit-checkin, escalation-daily (openclaw-crons); *(also all `python-module` / `cli-integration` code records, which are NON_SERVICE_TYPES and exempt)* | **no evaluable check ⇒ coverage gap** (FR-006) for the active/running openclaw-crons; the code-record types are exempt entirely |

- **Decision (Codex F1, operator-confirmed "support-as-is in code")**: The runner supports the real
  method vocabulary above via a **method→probe dispatch**, with two name-unifications handled *in code*
  (NOT by editing the inventory): the three freshness-pointer names (`tick-signal-file`/`signal-file`/
  `state-file`) map to one **freshness probe**, and `log-tail`/`journal` map to one **log-scan probe**;
  `self-check-command`/`self-test` map to one **command probe**. `none` on an active/running entry is a
  coverage gap. Unknown/unhandled method strings ⇒ coverage-gap (surfaced, never silently skipped).
- **Rationale**: no inventory churn, no bulk-edit gate; the runner is robust to what is *actually*
  declared; the code owns the small amount of vocabulary heterogeneity. (Operator decision on probe
  scope, 2026-07-11.)
- **Alternatives**: normalize the inventory vocabulary (rejected — bulk-edit scope/risk); a core subset
  + defer the rest (rejected — leaves ~6 active components uncovered on day one for little saving, since
  each probe is small).
- **Follow-up noted (not this mission)**: the method-vocabulary inconsistency in the inventory is real
  coherence debt; a later normalization pass could collapse the variant names. Recorded, not done here.

## R4 — Health computation + status gate (ADR-0006) — REVISED per Codex F6 (single suppression rule)

- **Decision**: The runner determines `alert_eligible = status ∈ {active, running}` **first**. For a
  **suppressed** status (`suspended`/`deprecated`/`planned`/`retired`) the runner does **NOT probe** the
  component — it records a `suppressed` outcome in the per-component ledger and moves on (no wasted probe,
  no spurious error on an intentionally-off component). For an alert-eligible component it probes and maps
  the `ProbeResult` to `health ∈ {healthy, stale, failed, degraded, unknown}`.
- **Rationale**: resolves the spec-vs-research inconsistency Codex F6 flagged into ONE rule: *gate before
  probe*. It honors ADR-0006 (status gates health-alerting) and avoids probing components deliberately
  turned off. `should_emit` can therefore only be true for alert-eligible components (INV-A).
- **Alternatives**: probe-then-suppress (rejected — wastes probes and can log confusing "failed" health
  on a component that is *supposed* to be down).

## R5 — Dedup design — REVISED per Codex F7 (mandatory reset on transition/recovery)

- **Decision**: A dedup-state file keyed by `component_id` stores `{ last_health, last_emitted_utc }`.
  On each tick for an alert-eligible component:
  - If the computed `health` **differs** from `last_health` (any transition, including recovery to
    `healthy`) → **always emit** (recovery emits an INFO "recovered" notice) and update the key. The
    reset is **mandatory**, not optional — this closes the `failed → healthy → failed` gap (F7).
  - If `health` is unchanged **and** bad and `now - last_emitted_utc < dedup_window` (default **6 h**,
    configurable) → suppress emission, still record the outcome in the per-component ledger.
  - If `health` is unchanged, bad, and the window elapsed → re-emit (re-remind) and update.
- **Rationale**: keying by `component_id` (with `last_health`) rather than by `(component_id, health)`
  makes a health *change* unconditionally emit, so no actionable transition is ever swallowed.
- **Alternatives**: `(component_id, health)` key with optional recovery (the pre-review design) —
  rejected: F7 showed it can suppress a genuine re-failure.

## R6 — Severity mapping — REVISED per Codex F3 (real alert-bus vocabulary)

- **Decision**: Use the real `alert_bus` `Severity` enum (`info|warn|error|critical`):
  `failed` → **ERROR**; `stale` → **ERROR**; `degraded` → **WARN**; coverage-gap → **WARN**; persistent
  `unknown` (F5) → **WARN**; recovery notice → **INFO**.
- **Rationale**: matches `scripts/common/alert_bus/model.py` exactly (`Severity.WARN`, not the string
  "warning"). Stale on a live component is a real "should have run, didn't" incident ⇒ ERROR.
- **Alternatives**: stale → WARN — rejected (under-alerts the target failure class).

## R7 — Cadence

- **Decision**: 15-minute `systemd --user` timer, matching `felix-trust-scan`. Satisfies NFR-001.
- **Rationale**: reuse the proven cadence + pattern; 15 min is well inside the ≤30 s pass budget.
- **Alternatives**: 5 min (needless noise/cost) · hourly (violates NFR-001).

## R8 — Self-observability boundary (SC-006) — REVISED per Codex F2 (SC reworded to the honest boundary)

- **Decision**: Two layers, with the success criterion reworded to match what is actually delivered:
  1. **Crash detection (in scope):** `felix-canary.service` declares `OnFailure=` → an alert-bus shim
     unit that emits an out-of-band ERROR if a *run* fails. (systemd fires it, independent of runner logic.)
  2. **Self-registration (in scope):** the runner is registered in the inventory (`tick-signal-file`
     freshness on its own `last-tick.json`) so that the deferred out-of-band watchdog (#269) — or any
     future independent watcher — can detect a dead timer.
  3. **Dead-timer + total-silence (BOUNDARY — deferred):** a timer that never fires (so neither the run
     nor its `OnFailure` executes), and whole-host silence, cannot be caught by anything the runner owns.
     This is **#269's charter** (deferred by the operator).
- **SC-006 reword (F2)**: crash → out-of-band `OnFailure` alert (delivered); dead-timer/silence →
  self-registered so #269 detects it (deferred). The SC no longer claims the runner detects its own dead
  timer.
- **Rationale**: honest per INV-001/INV-006 — don't claim coverage we don't build.
- **Mutual-watch via `felix-trust-scan` — REJECTED**: having trust-scan assert the canary's freshness
  would make the *trust* scanner do *health* watching, violating R1's single-responsibility separation
  (the whole reason they're sibling scanners). Circular self-watch (a dead runner evaluating its own
  registration) is likewise impossible. Dead-timer detection genuinely belongs to #269, not here.
- **Alternatives**: build a mini-#269 (rejected — scope creep); claim full out-of-band coverage (rejected
  — dishonest, F2).

## R9 — Coverage-gap + unknown handling — REVISED per Codex F5 (unknown IS emit-capable)

- **Decision**: `registry.py` yields CanaryTargets plus a **coverage-gap set** (active/running entries
  with `method: none`, a missing/empty `health_check`, or an unhandled method string). The runner emits
  gaps as WARN (deduped). For `unknown` **health** (a probe that couldn't run conclusively): recorded
  every tick, and — per F5 — **emitted as WARN once it persists past the dedup window** (a live component
  we *can't even evaluate* is itself a signal). This required adding `unknown`/gap to the emission set,
  which the pre-review model omitted.
- **Rationale**: the silent-failure class includes "we thought we were watching it but weren't" and "the
  probe itself is broken." Both must surface (FR-006; INV-002 no-silent-fallback).
- **Alternatives**: skip un-checkable components silently — rejected (that IS the bug).

## R10 — Per-component evaluation ledger (Codex F8, new)

- **Decision**: Every tick writes a per-component outcome to a durable date-partitioned JSONL ledger
  (`/data/services/felix-canary/ledger/<date>.jsonl`): `{component_id, health|suppressed|gap, evidence,
  emitted, suppressed_dedup, evaluated_at}`. This is distinct from (a) the aggregate `last-tick.json`
  (counts/timing) and (b) the #706 alert-bus ledger (alerts only). FR-008 asks for *per-component*
  outcomes including healthy/suppressed/deduped — neither existing surface records those.
- **Rationale**: FR-008 + observability; lets us answer "was X evaluated last tick and what did it say?"
  offline. Append-only, best-effort (never breaks the pass — INV-D).
- **Alternatives**: rely on the alert-bus ledger (rejected — it only holds alerts, not healthy/suppressed
  outcomes, so FR-008 would be unmet — F8).

## R11 — Restic scope correction (Codex F10)

- **Decision**: `scripts/office2/restic-backup.sh` **already** writes `last-backup.json` and the backup is
  **already registered** in the inventory with a working `shell` freshness check (hardcoded 28 h). IC-05
  shrinks to: add `max_age_seconds: 100800` to the restic `health_check` so the *new freshness probe* (not
  the embedded jq) drives it uniformly, and confirm the pointer's `snapshot_timestamp_utc` semantics match
  the freshness probe. No new pointer/writer work.
- **Rationale**: don't rebuild what exists; normalize it into the registry's uniform freshness path.
- **Alternatives**: build a parallel pointer (rejected — duplication, F10).
