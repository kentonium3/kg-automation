# Feature Specification: Deterministic Monitoring Checks

**Mission**: deterministic-monitoring-checks-01KX1XNW
**Type**: software-dev
**Source**: kentonium3/kg-automation#676 (Foundation 1, Sprint 0 — Felix Bedrock Stabilization epic #673)
**Target branch**: feat/deterministic-monitoring-checks
**Status**: Draft

## Overview

Felix's own observability spends money by routing deterministic work through LLMs.
Two paths are the offenders:

1. **Heartbeat-gate** — a systemd user timer fires every 30 minutes and, for each
   tick, calls Claude Haiku (`scripts/openclaw/heartbeat_gate/gate.py:decide`) to
   choose one of three routes (`HEARTBEAT_OK`, `LOG_AND_SKIP`, `ESCALATE_TO_SONNET`).
   The inputs the model is given (`novelty_markers`, `heartbeat_md_state`, `errors`,
   `issues_filed`) are **already computed deterministically** in `context.py`, and
   the routing prompt itself specifies the decision as exact boolean conditions.
   The model call is therefore avoidable cost (~48 calls/day, ~$7/mo).
2. **Health-check** — two openclaw crons (`health-check-morning`, `health-check-evening`)
   run a bash check twice daily, but do so **through the Sonnet `main` agent**,
   incurring mostly cache-write cost (~$12/mo) for work that was never stochastic.

This mission replaces both LLM-mediated paths with deterministic execution — no LLM
in the monitoring hot path — while preserving cadence, the escalation-to-Sonnet
path, the ledger, and the fail-safe. It is the Sprint-0 quick win that applies
Foundation 1's deterministic-canary principle ahead of the full F1 build (#516). It
is deliberately narrow: collection/assertion only — no canary registry, no single
alert stream (Sprint 1 / #516), no dashboards (#137).

## Domain Language

| Term | Canonical meaning | Avoid |
|---|---|---|
| Heartbeat-gate | The 30-min systemd tick that decides whether to wake the reasoning agent | "heartbeat cron" (it is a systemd timer, not an openclaw cron) |
| Gate decision | The route chosen for one tick: `HEARTBEAT_OK` / `LOG_AND_SKIP` / `ESCALATE_TO_SONNET` | "gate result" |
| Novelty markers | Deterministically-derived list of `signal_id`s whose `threshold_status != "below"` | "signals" (broader) |
| Escalation | Waking the Sonnet `main` agent via `openclaw system event --mode now` | "alert" |
| Fail-safe | On any step-1/step-2 failure, escalate anyway with `fallback_invoked=true` | "fallback" (ambiguous) |
| Health-check | The twice-daily bash system check, currently routed through `main` | "health cron" |
| Historical gate-decision ledger | The existing `gate-ledger.jsonl` tick records used to validate the new rule | "logs" |

## User Scenarios & Testing

**Primary actor**: the Felix operator (Kent) / the Felix system monitoring itself.

### Scenario 1 — Quiet tick (the common case)
- **Trigger**: heartbeat timer fires; the latest signal-extraction tick shows all
  signals below threshold, an empty heartbeat contract, no errors, no issues filed.
- **Expected outcome**: the deterministic rule classifies the tick as no-escalation;
  the ledger records the decision with **zero token counts**; **no Anthropic API call
  is made** and no Sonnet session is created.

### Scenario 2 — Escalation tick
- **Trigger**: a tick where at least one of `novelty_markers` is non-empty,
  `heartbeat_md_state == "has_tasks"`, or `errors` is non-empty.
- **Expected outcome**: the deterministic rule yields `ESCALATE_TO_SONNET`; the
  orchestrator wakes `main` via `openclaw system event --mode now` with a
  deterministically-constructed reason that cites the specific trigger(s); the tick
  is recorded in the ledger.

### Scenario 3 — Fail-safe tick
- **Trigger**: context-load (step 1) or the decision (step 2) raises (e.g. corrupt
  `last-tick.json`, missing input).
- **Expected outcome**: the tick still escalates to Sonnet with `fallback_invoked=true`
  recorded in the ledger — observation is never silently dropped.

### Scenario 4 — Health-check run
- **Trigger**: the twice-daily health-check schedule fires.
- **Expected outcome**: the existing bash check runs and emits its result directly
  via a non-agent execution path; **no `main` (Sonnet) session is created** for it
  (`openclaw cron runs` shows none); cadence is unchanged (2×/day).

### Scenario 5 — Rule validation before done (INV-006)
- **Trigger**: acceptance of the new escalation rule.
- **Expected outcome**: the rule is replayed against the historical gate-decision
  ledger and reproduces **every** historical Haiku escalation (zero missed
  escalations), with over-escalation bounded to a small documented threshold.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The heartbeat-gate escalation decision MUST be computed by a deterministic rule over the already-computed `GateContext` fields (`novelty_markers`, `heartbeat_md_state`, `errors`, `issues_filed`), with **no Anthropic/LLM call in the tick hot path**. | Draft |
| FR-002 | The deterministic rule MUST yield `ESCALATE_TO_SONNET` when — and only when — the routing prompt's escalation conditions hold: `novelty_markers` non-empty **OR** `heartbeat_md_state == "has_tasks"` **OR** `errors` non-empty. | Draft |
| FR-003 | The deterministic rule MUST classify a fully-quiet tick (`novelty_markers == []` AND `heartbeat_md_state == "empty"` AND `errors == []` AND `issues_filed == []`) as **no-escalation**, invoking no downstream Sonnet session. | Draft |
| FR-004 | On escalation, the gate decision `reason` MUST be constructed deterministically, citing the specific trigger(s) (signal IDs, contract-task presence, and/or error type) so `main` still receives actionable context in the `openclaw system event` body. | Draft |
| FR-005 | The escalation path (step 3) MUST be preserved unchanged: when the rule escalates, the orchestrator still wakes `main` via `openclaw system event --mode now`. | Draft |
| FR-006 | The ledger write (step 4) MUST be preserved: every tick still writes a tick record; the token-cost fields (`input_tokens`, `cache_hit_tokens`, `output_tokens`) MUST record `0` on the deterministic path. | Draft |
| FR-007 | The fail-safe MUST be preserved AND extended to the deterministic decision: any failure in step 1 (context-load) or step 2 (decision) MUST result in `ESCALATE_TO_SONNET` with `fallback_invoked=true` and exit 0. The deterministic decision MUST be **total** over every `GateContext` `load_context` can produce (never raising on malformed-but-loaded data), and/or step 2's exception handling MUST be broadened, so such failures route through the fail-safe and NOT the emergency exit-1 path. | Draft |
| FR-008 | The heartbeat-gate MUST fully remove the now-unused LLM arguments and Anthropic dependency from the tick path (`--api-key` / `--prompt` from `run.py`'s parser and the `anthropic` call sites), with **no vestigial no-op flags**, and MUST update all affected tests and docs accordingly; the installed systemd `ExecStart` MUST be smoke-verified after the change. | Draft |
| FR-009 | The health-check MUST run via a **standalone non-agent systemd user timer** that executes the existing bash check via `subprocess` (not `exec`) and emits its result directly, **creating no Sonnet `main` session**. A missing/non-executable check script and an alert-delivery (ntfy) failure MUST each be surfaced (alerted and/or logged where the operator will see it), not silently swallowed. | Draft |
| FR-010 | The health-check's existing assertions MUST be reused unchanged (only the execution path changes), and its cadence MUST remain 2×/day. | Draft |
| FR-011 | The deterministic escalation rule MUST be validated against the historical gate-decision ledger before the mission is declared done (INV-006): every historical tick Haiku escalated MUST also escalate under the deterministic rule (zero missed escalations); over-escalation relative to history MUST be ≤5%. The ledger replay validates the **escalate-vs-not boolean only** (the ledger lacks `issues_filed`/per-signal counts); the `LOG_AND_SKIP`↔`HEARTBEAT_OK` sub-label split MUST be validated separately via synthetic `GateContext` fixtures. | Draft |
| FR-012 | Architecture documentation MUST be synchronized: `data/service-inventory.json` (+ markdown view) reflects the health-check execution path moving off `main` and the heartbeat-gate LLM-model dependency being removed; `AGENT-REGISTRY.md` is reviewed for `main`'s scheduled-workload change (DIR-014). | Draft |
| FR-013 | The change MUST be deployable to office2 through a `deploys/queued/<name>.yaml` manifest covering both the systemd unit/script change and the openclaw cron reconfiguration (DIR-004). | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | No LLM call in the heartbeat tick hot path. | Ledger token counts (`input_tokens` + `cache_hit_tokens` + `output_tokens`) = **0** on every deterministic-path tick; **0** Haiku requests attributable to the gate in Anthropic spend. | Draft |
| NFR-002 | Health-check creates no reasoning-agent session. | **0** `main` (Sonnet) sessions created per health-check run, verified via `openclaw cron runs`. | Draft |
| NFR-003 | Measured spend reduction. | Anthropic spend attributable to heartbeat-gate + health-check trends toward ~$0, targeting **~$15–20/mo** saved, observed within **7 days** of deploy. | Draft |
| NFR-004 | No added tick latency. | The deterministic gate decision step completes in **< 1 s** wall-clock (vs. the prior network round-trip to Haiku). | Draft |
| NFR-005 | Reduced dependency surface in the hot path. | The tick decision path imports **no third-party package** (no `anthropic` SDK) — Python standard library only. | Draft |
| NFR-006 | Escalation fidelity vs history. | **100%** of historical Haiku `ESCALATE_TO_SONNET` ticks also escalate under the deterministic rule; over-escalation rate ≤ **5%** of historical non-escalation ticks (documented if any). | Draft |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Tier 3 (Standard) change per the change-risk taxonomy; no Tier 0–2 surface touched. | Draft |
| C-002 | All cron operations go through the `openclaw cron` CLI; system crontab is never used (DIR-007). | Draft |
| C-003 | Rebaseline obligation (#557): touches audited surfaces (systemd user units + deploy scripts, and openclaw config via cron reconfiguration); the merge commit MUST record `Rebaseline: completed at <ts>` (automated via felix-deployer if pipeline-applied, else manual per `docs/runbooks/security-baseline-ops.md`). | Draft |
| C-004 | Steps 1, 3, and 4 of the heartbeat orchestrator (context-load, escalate, ledger), the fail-safe, and both cadences (30-min heartbeat; 2×/day health-check) MUST remain behaviorally unchanged. | Draft |
| C-005 | Out of scope: canary registry / single alert stream (Sprint 1 / #516) and reporting dashboards (#137). No new assertions beyond the existing health-check. | Draft |
| C-006 | office2 is python3-only; any module import uses the `python3 -m scripts.<pkg>.<mod>` invocation form. | Draft |

## Success Criteria

| ID | Criterion (measurable, outcome-focused) |
|---|---|
| SC-001 | No LLM call occurs in the heartbeat tick hot path — verified via the ledger (zero token counts) and Anthropic spend (no gate-attributable Haiku requests). |
| SC-002 | The health-check runs without waking the reasoning agent — zero `main` sessions per run. |
| SC-003 | Escalation and the fail-safe still fire under their trigger conditions — an escalation-triggering tick wakes `main`; a forced step-1/2 failure escalates with `fallback_invoked=true`. |
| SC-004 | Measured monthly monitoring spend drops toward the ~$15–20/mo target within 7 days of deploy. |
| SC-005 | The deterministic escalation rule reproduces 100% of historical Haiku escalations with over-escalation ≤ 5% (INV-006 validation recorded). |
| SC-006 | Architecture docs are synchronized and the rebaseline is recorded in the merge commit. |

## Key Entities

- **GateContext** (`context.py`) — per-tick deterministic inputs: `novelty_markers`,
  `heartbeat_md_state`, `errors`, `issues_filed`, `signals_evaluated`. Unchanged; it
  is the sole input to the new rule.
- **GateDecision** (`gate.py`) — the typed decision (`outcome`, `reason`, token
  fields). The deterministic rule produces this struct with zeroed token fields.
- **Gate ledger record** (`gate-ledger.jsonl`) — per-tick record written by step 4;
  the historical corpus used for INV-006 validation.
- **Health-check runner** — the existing bash check plus its new non-agent execution
  wrapper (systemd timer or non-agent cron).
- **Deploy manifest** (`deploys/queued/<name>.yaml`) — the office2 deploy vehicle.

## Assumptions

- The routing prompt's boolean conditions (quoted in FR-002/FR-003) are the
  authoritative decision semantics to reproduce; `LOG_AND_SKIP` and `HEARTBEAT_OK`
  are both non-escalation and interchangeable for cost purposes, so the rule need
  only decide escalate vs. not-escalate (it may still emit a `LOG_AND_SKIP` label
  where the historical ledger shows non-empty-but-below activity, but this does not
  affect whether Sonnet is invoked).
- The historical `gate-ledger.jsonl` on office2 contains enough ticks (running since
  ~2026-06-01, ~48/day) to validate the rule. **Risk**: escalation samples may be
  sparse; if too few real escalations exist to be meaningful, validation is
  supplemented with synthetic ticks constructed to exercise each escalation
  condition. To be resolved in plan/research against the real ledger.
- The health-check bash script's assertions are correct as-is and need no change —
  only the execution path (off `main`) is in scope.
- The Anthropic API key file may still be needed by the fail-safe/other paths; FR-008
  removes it only from the deterministic decision path, not globally, pending plan
  confirmation.

## Dependencies

- `scripts/openclaw/heartbeat_gate/` module (context/gate/escalator/ledger/run) —
  the deterministic rule replaces `gate.decide`'s body / call site.
- systemd user unit `felix-heartbeat-gate.{service,timer}` on office2.
- openclaw cron subsystem (for the health-check reconfiguration).
- felix-deployer manifest pipeline (`deploys/queued/`), `scripts/deploy/lib/`.
- Architecture data store `docs/design/architecture/data/` (service-inventory) and
  `docs/constitution/AGENT-REGISTRY.md`.

## Out of Scope

- Canary registry and single alert stream (Sprint 1 / #516).
- Reporting dashboards / consumers (#137).
- Any change to the health-check's assertions themselves.
- Any change to the deterministic signal-extraction pipeline
  (`scripts/openclaw/observation/`), which already runs deterministically.
- Broader fleetwide model-selection work (#671).
