---
title: ADR-0006 — Felix component lifecycle status contract (declared status vs observed health)
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-07-11'
version: v1.0
audience: agents_and_humans
tags: [538, 516, 327, 545, 511]
---

# ADR-0006 — Felix component lifecycle status contract (declared status vs observed health)

**Status**: Approved
**Date**: 2026-07-11
**Deciders**: Kent Gale
**Closes**: kentonium3/kg-automation#538 (child of Epic #516 — Foundation 1: health & observability)
**Feeds**: #327 (universal error/alerting primitives — the canary registry consumes this contract), #701 (unified alert bus — the emission target)
**Reconciles**: #545 (felix-doc-auditor status/operational_status split), #511 (restic backup health-pointer freshness)

## Context

Felix has strong *local* observability patterns — per-component state files (`last-tick.json`,
`last-tick.errors.jsonl`, `last-backup.json`), schema versions, conflict ledgers — but no *common
contract* for what a component's status means or how different signals about the same component
are meant to agree. The result is that different surfaces tell different stories about one
component:

> `felix-doc-auditor.timer` is disabled on office2, the runbook says "suspended indefinitely,"
> but `service-inventory.json` said `status: active` and the last `last-tick.json` said
> `status=success` from weeks earlier.

That specific inconsistency was patched by #545 (adding `operational_status: suspended` plus a
`status-contradiction` validator rule), but the patch treated a symptom. The underlying gap is
that **one `status` field was being asked to carry two different kinds of fact at once**:

- what an operator *intends* for the component (is it supposed to be running?), and
- what a probe *observes* about the component right now (is it actually healthy?).

These are different axes. A component can be *intended active but observed failed* (a real
alert), or *intended suspended and observed stale* (entirely expected, must **not** alert). A
single flat enum that mixes `active`/`suspended`/`disabled` with `failed`/`stale`/`degraded`
cannot express that difference — and collapsing it is exactly what produced the #538 symptom.

This contract is the prerequisite for the rest of Foundation 1 (#516): the canary registry
(#327) needs an unambiguous answer to "should I be health-checking this component, and what does
a failure of this component mean?" before it can decide what to emit to the alert bus (#701).

The state space here is grounded in what `service-inventory.json` **actually uses today**
(`active`, `running`, `suspended`) plus the values already reserved in the validator's
`STATUS_ENUM` stub (`planned`, `deprecated`, `retired`) — no speculative states are introduced.

## Decisions

### 1. Two axes: declared **lifecycle status** vs observed **health**

A Felix component has two orthogonal state axes. Conflating them is the defect this ADR closes.

| Axis | Field | Who sets it | Nature |
| --- | --- | --- | --- |
| **Lifecycle status** | `status` in `service-inventory.json` | operator / deploy | a declared registry fact — an *intention* |
| **Health** | *computed at runtime*, never stored as `status` | a canary, from `health_check` | an *observation* |

`status` answers "what is this component supposed to be doing?" `health` answers "what is it
actually doing right now?" A component's alert-worthiness is a **function of both**, defined in
Decision 4.

### 2. Lifecycle status enum (declared)

`status` MUST be one of the following. This set is identical to the existing
`STATUS_ENUM` in `tooling/scripts/validate_architecture_data.py` — this ADR makes that stub
authoritative rather than changing its values.

| `status` | Meaning | Health-checked? | Alerts on bad health? |
| --- | --- | --- | --- |
| `active` | Deployed and intended to be operating. The default live state. | yes | **yes** |
| `running` | The `active` variant for long-lived **process** entities (containers, daemons, servers) where "is the process up?" is the primary liveness question. Semantically active for alerting. | yes | **yes** |
| `suspended` | Deliberately halted by an operator, expected to resume. Requires `suspension_metadata`. | no (see D4) | **no** — a suspended component going stale is *expected* |
| `deprecated` | Superseded, on a path to removal, may still exist. | no | no |
| `planned` | Declared but not yet deployed. | no | no |
| `retired` | Decommissioned/removed. Retained as historical record. | no | no |

**Alerting-live statuses** = `{active, running}`. **Alerting-suppressed statuses** =
`{suspended, deprecated, planned, retired}`.

`suspended` as a first-class status directly implements **Engineering Principle #8 — suspension
as a real operational state**: suspension is not "broken," it is a declared intention that
*suppresses* the health alarm rather than firing it.

### 3. Health value set (observed, computed — not stored as `status`)

A canary evaluates a component's `health_check` and produces exactly one `health` value. These
are **never** written into the `status` field; they are the runtime read.

| `health` | Meaning | Typical detection |
| --- | --- | --- |
| `healthy` | Probe passed within its freshness bound. | http 2xx; `last-tick.json` `status=success`, `errors=[]`, fresh; `restic_exit_code ∈ {0,3}` and fresh |
| `stale` | The freshness signal is older than its threshold — a scheduled job hasn't ticked, or a pointer is too old to trust. The *last* result may have been success. | `completed_at_utc` / `snapshot_timestamp_utc` older than the component's staleness threshold |
| `failed` | The probe returned an explicit failure. | non-zero exit; `errors` non-empty; http non-2xx; `restic_exit_code ∉ {0,3}` |
| `degraded` | **Optional, self-reported.** Operating but below normal (partial function). Components MAY report it; it is never required. | component writes a partial-function marker |
| `unknown` | No `health_check` declared, or the probe could not run conclusively. For a service-type entity, a persistent `unknown` is itself a gap to fix. | missing `health_check`; endpoint unreachable inconclusively |

`stale` and `failed` are kept distinct on purpose: "hasn't run in too long" and "ran and errored"
are different operational conditions with potentially different responses.

### 4. Consumption rule (the load-bearing part): status gates health, health drives emission

This is the contract the #327 canary registry implements against the #701 bus:

1. A canary computes `health` **only** for entities whose `status ∈ {active, running}`. For
   `{suspended, deprecated, planned, retired}` the canary does not evaluate health, or evaluates
   it but never emits — a suspended job being `stale` is expected, not an incident.
2. For an alerting-live entity: `health ∈ {stale, failed}` → **emit to the #701 alert bus**
   (severity per component); `health = degraded` → emit at lower severity; `health = healthy` →
   no emission.
3. Transitioning a component to `suspended`/`deprecated`/`retired` therefore **silences its
   health alarm by construction** — no per-canary muting logic, no alert-suppression flags. This
   is what makes suspension safe and cheap to use.

### 5. Freshness threshold is per-component, not a global constant

Whether a component is `stale` depends on its own cadence. The staleness threshold is declared
**per component**, derived from its expected cadence plus slack (e.g. restic's 24h cadence → a
28h threshold; a 30-min tick timer → a ~2h threshold). Today this threshold lives in prose in the
`health_check.expected` clause. The contract requires only that the threshold be *stated* per
component; formalizing it into a machine-readable `max_age_seconds` field is left to the #327
canary registry so this ADR does not pre-commit a schema the registry hasn't validated.

Process entities (`running`) have no meaningful freshness axis — their health is a binary
liveness probe (`healthy` / `failed`), and `stale` does not apply.

### 6. Health expectations by entity type

The contract maps cleanly onto the validator's existing type partition
(`SERVICE_TYPES` vs `NON_SERVICE_TYPES`):

| Entity class | Example types | Health mechanism | health_check required? |
| --- | --- | --- | --- |
| **Process service** | `docker-compose`, `systemd_user_timer` (daemon), npm server | liveness probe (http / process up) → `healthy`/`failed` | yes |
| **Scheduled one-shot** | `cron`, `systemd-timer`, `openclaw-cron` | tick-signal freshness (`last-tick.json` / `last-backup.json` pattern): success within cadence → `healthy`; too old → `stale`; errored → `failed` | yes |
| **Code record** | `python-module`, `library`, `cli-integration` | **none** — no runtime process; carries a declared `status` only (`active`/`deprecated`/`retired`) | no (exempt, matches `NON_SERVICE_TYPES`) |

### 7. `status` is the single authoritative declared-lifecycle field; `operational_status` is superseded

With `suspended` a first-class `status` value, the separate `operational_status` field (added by
#545 as a pre-contract patch) is redundant: declared lifecycle lives in `status` alone. The
validator's `status-contradiction` rule (`operational_status == "suspended"` vs
`status ∈ {active, running}`) is **retained as a transitional safety net** while any residual
`operational_status` fields exist, but new and updated entries express suspension via
`status: suspended` + `suspension_metadata`, not `operational_status`. Removing the residual
`operational_status` fields is opportunistic cleanup, not a blocking migration.

### 8. `suspension_metadata` is the canonical shape for a suspended component

When `status = suspended`, the entry SHOULD carry a `suspension_metadata` object (the shape
already shipped for felix-doc-auditor via #545):

```json
"suspension_metadata": {
  "since": "2026-05-26",
  "reason": "API cap exhaustion (May 2026)",
  "unblock_signal": "#137 cost-control epic",
  "layers": ["systemd timer disabled", "config flag enabled=false", "GitHub Actions disabled_manually"]
}
```

This makes a suspension self-documenting: *why*, *since when*, *what unblocks it*, and *what was
actually turned off* — so a suspended component is never mistaken for a silently-broken one.

## Alternatives Considered

| Alternative | Why rejected |
| --- | --- |
| **Single flat `status` enum** mixing `active`/`suspended`/`disabled` with `failed`/`stale`/`degraded` (the issue's literal framing) | Re-admits the exact contradiction class #545 just fixed: one field cannot say "intended off" and "observed broken" simultaneously. This is the defect, not the fix. |
| Keep `operational_status` as a co-equal second field | Two declared-state fields invite drift between them; the contradiction check exists *because* they can disagree. Collapsing declared lifecycle into one field (`status`) removes the drift surface. |
| Store computed `health` back into `service-inventory.json` | The inventory is a *declared* registry (git-tracked, operator-authored); writing observed runtime state into it conflates source-of-truth and makes the file a mutable runtime surface. Health is computed on read by the canary, emitted to the bus, and (optionally) journaled — not persisted as inventory truth. |
| Add `degraded` as a required health value | Most components have no partial-function notion; requiring it would force meaningless self-reports. Optional + self-reported keeps it honest. |
| Keep `disabled` as a status (per the issue's list) | Not used anywhere in the inventory; `suspended` is the canonical halt term already in use. Adding `disabled` would create a needless "suspended vs disabled" ambiguity. |
| A global staleness constant | Components have wildly different cadences (30-min tick vs 24h backup); one constant is either too tight (false stale) or too loose (misses real staleness). Per-component threshold is the only correct choice. |
| Full framework/schema now (machine-readable `max_age_seconds`, health-state persistence) | Over-engineers ahead of the consumer. The canary registry (#327) is where those schema commitments get validated against real use; this ADR defines the *contract*, not its serialization. (Roadmap principle #10 — guard against over-engineering.) |

## Consequences

- **For the canary registry (#327)**: it reads `status` to decide *whether* to health-check an
  entity, reads `health_check` to *compute* `health`, and emits to the #701 bus per Decision 4.
  Suspension handling is free — no muting logic.
- **For `service-inventory.json` authors**: set `status` to the declared intention only; never
  encode "it's broken right now" there. When suspending, use `status: suspended` +
  `suspension_metadata`. Every `SERVICE_TYPE` entry must declare a `health_check` with a stated
  freshness threshold; `NON_SERVICE_TYPE` records need only a `status`.
- **For the validator** (`tooling/scripts/validate_architecture_data.py`): `STATUS_ENUM` is now
  *defined by this ADR* rather than a stub — its comment is updated to cite ADR-0006; the values
  are unchanged. The `status-contradiction` rule is retained transitionally (Decision 7).
- **For the coherence doctrine** (`docs/design/coherence/`): this contract operationalizes
  INV-003 (one canonical alert stream + audience routing) for the *what-to-emit* decision, and
  is the concrete backing for Engineering Principle #8 (suspension as an operational state).
- **For EA Calendar/Email work** (#164/#165, #699/#703 helpers): new deployed helpers register
  with a `status` + a freshness-based `health_check`, and become canary-registry citizens for
  free once #327 lands.
- **Not in scope**: implementing the canary registry, retrofitting existing components' health
  probes, or the machine-readable freshness field — all belong to #327.

## References

- [`docs/design/architecture/data/service-inventory.json`](../data/service-inventory.json) — the declared registry this contract governs
- [`tooling/scripts/validate_architecture_data.py`](../../../../tooling/scripts/validate_architecture_data.py) — `STATUS_ENUM` (now defined by this ADR), `check_status`, `check_health`, `SERVICE_TYPES`/`NON_SERVICE_TYPES`
- [`docs/design/engineering-principles.md`](../../engineering-principles.md) — Principle #8 (suspension as an operational state)
- [`docs/design/coherence/doctrine.md`](../../coherence/doctrine.md) — INV-003 (one canonical alert stream)
- kentonium3/kg-automation#538 — this ADR's tracking issue (closes via this ADR)
- kentonium3/kg-automation#516 — Foundation 1 epic (health & observability)
- kentonium3/kg-automation#327 — universal error/alerting primitives (the canary registry that consumes this contract)
- kentonium3/kg-automation#701 — unified alert bus (the emission target; shipped)
- kentonium3/kg-automation#545 — felix-doc-auditor status/operational_status reconciliation (the symptom this contract resolves at the root)
- kentonium3/kg-automation#511 — restic backup health-pointer (the freshness pattern generalized here)

## Decision changes

(Future amendments record here.)
