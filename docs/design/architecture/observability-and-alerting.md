---
title: Observability & Alerting — the Deterministic-Scanner Pattern
doc_type: design
status: active
level: concept
audience: agents_and_humans
owners: [kgale]
created: 2026-07-11
last_updated: '2026-07-11'
last_validated: '2026-07-11'
version: v1.0
updated_by: '#327 (felix-canary-registry-01KX8T7B) — captures the reusable observability pattern established by #701 (bus) + #683 (trust-scan) + #327 (canary)'
tags: [327, 683, 701, 706, 516, 269, 707]
---

# Observability & Alerting — the Deterministic-Scanner Pattern

This is the **pattern** Felix follows to observe its own components and surface
failures — not a runbook for any one scanner. A future mission that adds a new
alert producer or health scanner should FOLLOW this document rather than
reverse-engineering it from the two exemplars.

The pattern has shipped **twice** — `felix-trust-scan` (#683, trust/cron-drift)
and `felix-canary` (#327, component health) — as sibling scanners sharing one
alert substrate (`scripts/common/alert_bus/`, #701). This doc names the shared
shape, the invariants it guarantees, and the checklist for adding a third.

> **Where the pieces live.** The alert bus is
> [`scripts/common/alert_bus/`](<../../../scripts/common/alert_bus/>) (how-to:
> [alerting.md](<../../runbooks/alerting.md>)). The canary is
> [`scripts/canary/`](<../../../scripts/canary/>) (ops:
> [canary-registry-ops.md](<../../runbooks/canary-registry-ops.md>)). The
> trust-scan is [`scripts/trust/`](<../../../scripts/trust/>) (ops:
> [trust-reporting-detector.md](<../../runbooks/trust-reporting-detector.md>)).
> The status contract they all obey is
> [ADR-0006](<./adr/0006-felix-component-lifecycle-status-contract.md>). The
> canonical data-flow record is [data-flows.md](<./data-flows.md>).

## 1. The pattern in one line

> An **inventory-declared** health signal → a **deterministic scanner** (systemd
> `--user` timer, ~15-min, **zero LLM**) → **ADR-0006** health computation
> (status gates health) → the **single #701 alert bus** → a **durable per-component
> ledger + tick-signal** that a later agent or watchdog can query.

Every stage is deliberate, and each maps to an invariant in §4:

1. **Declared, not hard-coded.** What to watch is declared *in data*
   (`service-inventory.json`'s `health_check`, or a baseline file for
   trust-scan), never as a special-cased list in code. A component becomes
   monitored the instant it declares a check; nothing else registers it.
2. **Deterministic.** The scanner is a systemd `--user` oneshot on a timer.
   It runs pure Python — no model call is ever in the tick path (0 tokens/tick).
   Determinism is *the point*: model-asserted health is exactly the fabrication
   class Felix does not trust (DEC-002, INV-001).
3. **Status gates health.** ADR-0006 splits the two axes a single `status` field
   used to conflate — declared *lifecycle* (`active`/`running`/`suspended`/…) vs
   observed *health* (`healthy`/`stale`/`failed`/`unknown`). Only
   `active`/`running` components are probed; suspending a component silences its
   alarm *by construction*, with no per-scanner muting logic.
4. **One alert stream.** Every emitting outcome goes through the **one** #701
   `felix-alert` bus (`scripts.common.alert_bus.emit`). No scanner hand-rolls its
   own ntfy/curl path. This is coherence invariant **INV-003**.
5. **Durable + queryable.** Every tick writes a structured, append-only JSONL
   **ledger** (per-component) plus a **tick-signal** pointer (the scanner's own
   health) — so state survives ntfy being down and is machine-queryable after
   the fact, not just a fleeting push.

## 2. Two exemplars, contrasted

The pattern's most important design choice is that these are **siblings, not one
scanner** — a decision recorded in
[decisions.jsonl](<../coherence/decisions.jsonl>) as **DEC-007** (mirroring
research R1 and operator decision DM-01KX8TY1KRNXQ2Y7C6QKXYEYCR).

| | `felix-trust-scan` (#683) | `felix-canary` (#327) |
|---|---|---|
| **Domain** | Trust drift — rogue/unapproved crons, fabricated completion assertions | Component health — is each declared service up / fresh? |
| **Declared by** | The approved-cron baseline + completion-assertion log | `service-inventory.json` `health_check` per service-type entry |
| **Package** | `scripts/trust/` | `scripts/canary/` |
| **Unit** | `felix-trust-scan.{service,timer}` (15-min) | `felix-canary.{service,timer}` (15-min) + `felix-canary-onfailure.service` |
| **Detection** | cron-drift detector + assertion verifier | ADR-0006 probe → health outcome |
| **State** | `seen-findings.json` (fingerprint → first/last/last-alerted; 24h re-alert) | `dedup.json` (component_id → last_outcome/last_emitted; 6h re-remind) |
| **Ledger** | (emits + seen-state; findings are the record) | per-component `ledger/<date>.jsonl` — one line every component every tick |
| **Shared** | **`scripts/common/alert_bus.emit` (#701)** | **`scripts/common/alert_bus.emit` (#701)** |

**Why siblings, not one scanner (DEC-007):** trust and health are different
domains with different cadences, lifecycles, and evolution paths. Folding
health-watching into the trust scanner would couple two unrelated concerns into
one unit. Two single-responsibility scanners that share only the emit substrate
stay simple and independently evolvable — and a third (a future scanner for some
new signal class) is a *new sibling*, not a new branch inside an existing one.
The shared thing is the **alert bus**, never the scanner.

## 3. Deploy discipline (the pattern's ops half)

A scanner is not done when the code passes tests; it is done when it runs on
office2 and its first real tick is *proven* to have written state. The pattern's
deploy half:

- **Manifest, not ad-hoc.** The deploy flows through a `deploys/queued/<NNNN>-*.yaml`
  manifest consumed by `felix-deployer` (canary = `0017-felix-canary-registry.yaml`,
  entrypoint `scripts/deploy/deploy-felix-canary.py`). No hand-run install.
- **systemd `--user` timer + `OnFailure=` shim.** The `.service` is a
  `Type=oneshot` running `python3 -m scripts.<pkg>.run --once`; the `.timer` sets
  the ~15-min cadence (`OnUnitActiveSec=15min`, `OnBootSec=5min`,
  `Persistent=true`). The canary adds a crash detector trust-scan lacked:
  `OnFailure=felix-canary-onfailure.service` fires an **out-of-band** ERROR via
  `scripts/common/alert_bus.sh` when the runner itself exits non-zero —
  independent of the runner's own emit logic, so a runner that crashed before it
  could report is still surfaced (SC-006).
- **Verify-before-enable.** The deploy entrypoint runs the **real unit once**
  *before* enabling the timer, and asserts the tick wrote a fresh tick-signal
  **and** a ledger line — proving state writes under systemd, which a `--dry-run`
  cannot. Only then does it `enable --now` the timer. This is the #703/#711
  lesson: a fresh deploy must never page on an unverified false-positive, and a
  mocked test cannot prove the real interpreter/venv/permissions path works
  (behavioral-verification, DEC-006).
- **Rebaseline.** systemd units under `scripts/office2/` are a hashed **audited
  surface** (`audited-surfaces.json`), so the deploy is a rebaseline event —
  `felix-deployer` auto-rebaselines on the happy path because the change has a
  repo-file signal.

## 4. Invariants the pattern guarantees

These are stated as candidate directives — a scanner that violates one is
mis-built. (This section is the doctrine-migration seed; see §7.)

- **INV — status gates health (ADR-0006).** Health is computed *only* for
  `status ∈ {active, running}`. Gate-before-probe: a non-alert-eligible component
  is never probed (its injected effects are never touched) and is recorded
  `suppressed`. Suspending a component is the *single* suppression mechanism — no
  code allowlists, no per-ID muting.
- **INV — no silent drop.** A live component the scanner *cannot* evaluate is a
  signal, never a skip. A `health_check` that is missing, `method: none`, or an
  unhandled method becomes a **coverage gap** (`gap`) and is surfaced; a probe
  that can't interpret its pointer is an honest `unknown`, never a false
  `healthy`. "We thought we were watching it but weren't" must be visible.
- **INV — determinism (0 tokens).** No LLM in the tick path. The evaluation
  modules are pure with respect to injected effects (network / subprocess /
  filesystem passed as callables); the runner supplies the real effects.
  Model-asserted state is never trusted as fact (DEC-002 / INV-001).
- **INV — fail-open pass.** One component's fault never aborts the pass: a probe
  that raises is caught into an `unknown` ledger line + an `errors[]` entry and
  evaluation continues. A ledger-write fault is best-effort. A non-zero **process**
  exit is reserved for a *runner-level* fault (inventory unreadable, state dir
  unwritable) — that, and only that, feeds `OnFailure=`.
- **INV — durable ledger even on delivery failure.** `emit()` records the alert +
  its delivery outcome to the durable ledger (#706) **even when ntfy delivery
  failed** — a failed POST is still a recorded fault. The ledger write is
  best-effort and never changes delivery semantics or raises.
- **INV — single canonical alert stream (INV-003).** All alerts flow through the
  one #701 `felix-alert` bus, routed by audience (operator/must-always → ntfy
  deterministic backstop; user-facing → WhatsApp best-effort). No component
  invents its own notification path.
- **INV — dedup timing.** A **transition always emits** (dedup keyed on
  `component_id` + `last_outcome`), so `failed → healthy → failed` produces all
  three alerts incl. the recovery **INFO** — a re-failure is never swallowed by a
  stale suppression window. `failed`/`stale` page immediately then re-page once
  per window (canary 6h; trust-scan 24h). `unknown`/`gap` are **recorded but not
  paged on first sight** — they page only once they *persist past the window*, so
  a single-tick blip doesn't wake anyone but a *persistent* un-evaluable live
  component does.

## 5. Dual observability surface (a key property)

The pattern deliberately produces **two** observability surfaces from one tick,
and they are for different consumers:

- **ntfy push = human / real-time.** The #701 bus POSTs to one canonical ntfy
  thread. This is the operator's phone buzzing *now*. It is push, ephemeral, and
  best-effort — the right shape for "a human needs to know something changed."
- **Durable JSONL ledgers = agent-queryable / after-the-fact.** Two append-only,
  date-partitioned JSONL stores are the structured record:
  - the **#706 bus ledger** (`/data/services/alert-bus/ledger/<date>.jsonl`) — every
    alert every producer emitted, with its delivery outcome; and
  - the **per-component canary ledger** (`/data/services/felix-canary/ledger/<date>.jsonl`)
    — every component's outcome every tick, including the healthy/suppressed/gap
    lines that never page.
  Plus the **tick-signal** (`state/last-tick.json`) — the scanner's own health
  pointer, itself a canary citizen.

This split matters: the push is for a human in the moment; the ledgers are the
**substrate a future responder or watchdog builds on** — an agent can query "what
was this component's health over the last day?" or "did we ever alert on X?"
without having been subscribed at the time. This is exactly what the deferred
out-of-band dead-timer watchdog (#269) and the alert-responder RFC (#707) stand
on: they don't re-observe, they *read the ledger*.

## 6. Adding a new scanner / alert producer — the checklist

Follow these steps; each maps to an invariant above.

1. **Declare the signal in data, not code.** For a component-health check, add a
   `health_check` to its `service-inventory.json` entry (freshness → `state-file`
   / `tick-signal-file` / `signal-file` + `state_path` + `max_age_seconds`;
   liveness → `http`/`shell`/`systemd-status` + `endpoint`). For a new *domain*
   scanner, declare its watch-list in its own data file (as trust-scan does with
   its baseline). Never special-case an ID in code.
2. **Share the alert bus.** Emit via `scripts.common.alert_bus.emit(Alert(...))`
   only. Do not write a new ntfy/curl path (INV-003). Pick a `source` of
   `<scanner>:<subject>` and a severity from `info`/`warn`/`error`/`critical`.
3. **systemd `--user` timer + `OnFailure=` + verify-before-enable.** Model the
   `.service`/`.timer` on the canary's; add an `OnFailure=` shim so a runner
   crash is caught out-of-band; make the deploy entrypoint run the real unit once
   and assert state was written *before* enabling the timer.
4. **Write a durable ledger.** Every tick appends a per-subject JSONL line
   (including the non-paging outcomes) and overwrites a tick-signal pointer. Make
   both writes atomic (temp file + `os.replace`) and best-effort (a ledger fault
   never aborts the pass).
5. **Register in the inventory for self-observability.** Add the scanner itself to
   `service-inventory.json` with a freshness `health_check` on its own
   tick-signal, so the *other* scanner (and the #269 watchdog) can watch *it*.
   A scanner that can't be watched is a blind spot.
6. **Report coverage gaps honestly.** If your scanner can't evaluate something it
   *should*, surface that as a first-class `gap`/`unknown` outcome — never a
   silent skip (no-silent-drop).

## 7. Doctrine-migration-ready pattern statement

The following is a **self-contained pattern statement** intended to be liftable
into a spec-kitty charter/doctrine tactic later, with the §4 invariants as
candidate directives. It restates the pattern with no dependency on the two
exemplars:

> **The Deterministic-Scanner pattern.** Felix observes its own state with
> single-responsibility scanners. Each scanner (a) reads *what to watch* from a
> declared data surface, never a hard-coded list; (b) runs as a periodic
> deterministic process (systemd `--user` timer, no LLM in the tick path);
> (c) gates observation on a declared *lifecycle status* so that intentionally-off
> components are silent by construction; (d) emits every actionable finding
> through the **one** canonical alert bus, routed by audience; and (e) writes a
> durable, append-only, per-subject ledger plus a self-health tick-signal every
> tick — even when delivery fails. Scanners are **siblings that share the bus, not
> the scanner**: a new signal domain is a new scanner, never a branch inside an
> existing one. A finding the scanner *cannot* evaluate is itself surfaced (no
> silent drop); a transition always alerts (including recovery); an
> un-actionable-yet condition pages only once it persists past the dedup window.
> The push channel serves the human in real time; the ledger serves later agents
> and watchdogs as the queryable substrate of record.

**Candidate directives** (the §4 invariants, phrased for a directive layer):
status-gates-health · no-silent-drop · deterministic-tick (0 tokens) ·
fail-open-pass · durable-ledger-on-delivery-failure · single-canonical-alert-stream ·
transition-always-emits-with-persistence-gated-unknowns.

## Cross-references

- **Status contract**: [ADR-0006](<./adr/0006-felix-component-lifecycle-status-contract.md>) — status gates health (the load-bearing computation rule).
- **Alert bus**: [alerting.md](<../../runbooks/alerting.md>) — the #701 `felix-alert` bus how-to + schema; ledger is #706.
- **Canary exemplar**: [canary-registry-ops.md](<../../runbooks/canary-registry-ops.md>) — `felix-canary` ops (#327).
- **Trust-scan exemplar**: [trust-reporting-detector.md](<../../runbooks/trust-reporting-detector.md>) — `felix-trust-scan` ops (#683).
- **Sibling decision**: [decisions.jsonl](<../coherence/decisions.jsonl>) `DEC-007` (siblings, shared bus) — and `DEC-002` (no model-asserted state) / `DEC-006` (behavioral verification).
- **Coherence invariant**: [doctrine.md](<../coherence/doctrine.md>) `INV-003` (one canonical alert stream) / `INV-001` (no fabrication) / `INV-002` (no silent fallback).
- **Engineering principles**: [engineering-principles.md](<../engineering-principles.md>) #8 (suspension as an operational state — the backing for status-gates-health).
- **Data flows**: [data-flows.md](<./data-flows.md>) — the `felix-canary`, `felix-trust-scan`, and `#701-alert-bus-emit` flow entries.
- **Program context**: Foundation 1 / Epic #516 (health & observability); deferred out-of-band watchdog #269; alert-responder RFC #707.
