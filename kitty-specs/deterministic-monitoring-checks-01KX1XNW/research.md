# Research: Deterministic Monitoring Checks

**Mission**: deterministic-monitoring-checks-01KX1XNW
**Date**: 2026-07-08
**Method**: local code read + live office2 probe (DIR-015) + design-time INV-006 validation against the historical ledger.

## R0 — Design-time INV-006 validation (the headline finding)

**Decision**: The deterministic escalation rule is proven correct against the full
historical gate-decision ledger *before* implementation.

**Evidence**: Replayed the deterministic rule over all **1748** ledger records
(`/data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl`, 2026-06-01 →
2026-07-08):

| Metric | Result |
|---|---|
| Total ticks | 1748 |
| Historical `ESCALATE_TO_SONNET` | 42 |
| Historical non-escalate (`HEARTBEAT_OK` 1390 + `LOG_AND_SKIP` 316) | 1706 |
| **Missed escalations** (rule fails to escalate a historical escalate) | **0** |
| **Over-escalations** (rule escalates a historical non-escalate) | **0 (0.00%)** |

**Rationale**: The rule `escalate ⟺ novelty_markers non-empty OR heartbeat_md_state
== "has_tasks" OR errors non-empty` reproduces the historical Haiku decision
**exactly** — zero divergence in either direction. This confirms the Haiku model
added **no judgment value** to the escalation decision; the routing prompt already
specified it as pure boolean logic and the model merely executed that logic at
per-call cost. NFR-006 (100% fidelity, ≤5% over-escalation) is not just achievable
but already **met at 100% / 0.00%** on real data.

**Alternatives considered**: (a) a looser threshold rule tuned to reduce
over-escalation — unnecessary, over-escalation is already 0; (b) deriving new
thresholds from signal history — rejected, the existing conditions are exact.

**Consequence**: A ledger-replay validation harness (see R6) is shipped as the
INV-006 forcing function and as a regression guard.

## R1 — The escalation rule (semantics to reproduce)

**Decision**: `gate.decide` is replaced by a pure, stdlib-only function
`decide_deterministic(context) -> GateDecision` implementing the routing prompt's
three-outcome contract:

- `ESCALATE_TO_SONNET` ⟺ `novelty_markers` non-empty **OR** `heartbeat_md_state ==
  "has_tasks"` **OR** `errors` non-empty.
- Otherwise **non-escalate**, sub-labeled deterministically:
  - `LOG_AND_SKIP` when there is below-threshold-but-notable activity — i.e.
    `issues_filed` non-empty, or any evaluated signal has non-zero cycle activity
    while still `below` threshold.
  - `HEARTBEAT_OK` otherwise (fully quiet).

**Rationale**: Escalation is the only cost-bearing decision (it wakes Sonnet); it is
validated at 100%/0% (R0). The `LOG_AND_SKIP`↔`HEARTBEAT_OK` split does not affect
whether Sonnet runs — both are no-Sonnet — so it is preserved best-effort for ledger
readability, not validated against history (the ledger record does not persist
`issues_filed`/per-signal counts, only the escalation-relevant fields).

**Token fields**: always `0` on the deterministic path (NFR-001).

## R2 — Reason-text construction (deterministic)

**Decision**: On escalation the `reason` is built from a deterministic template that
cites the concrete trigger(s), e.g.:
`"Escalating: novelty markers {ids}; heartbeat contract has tasks; tick errors: {types}."`
(only the clauses that apply), truncated to ≤500 chars to match the existing
`GateDecision.reason` contract and the `openclaw system event` body.

**Rationale**: Preserves the actionable context `main` currently receives (FR-004)
without any generative call. The historical Haiku `reason` strings were already
factual citations of the same triggers.

## R3 — Heartbeat-gate wiring (FR-008 refinement)

**Finding (live)**: the systemd `ExecStart` is
`.../venv/bin/python /home/claude/kg-automation/scripts/openclaw/heartbeat_gate/run.py`
— it passes **no** `--prompt`/`--api-key` today; `run.py` uses the in-code defaults.

**Decision**:
- The change is **internal**: `run_tick` step 2 calls the new
  `decide_deterministic(context)` instead of `gate.decide(context, api_key_path=…,
  prompt_path=…)`. No `ExecStart` edit is required for argument removal.
- `run.py`'s `--api-key` / `--prompt` CLI flags become unused by the tick path;
  remove them from the parser (and the now-dead Anthropic call sites in `gate.py`
  or reduce `gate.py` to the deterministic function), so the tick path imports **no
  `anthropic`** (NFR-005).
- The Anthropic key **file** and the venv's `anthropic` package are left in place
  (no other consumer confirmed to break; removing them is optional cleanup outside
  this mission's blast radius, DIR-024).

**Rationale**: Minimal blast radius; ExecStart untouched means the systemd unit
change is limited to whatever the deploy manifest re-asserts (Description text may be
updated to drop "Haiku-tier").

## R4 — Health-check current behavior (live)

**Finding (live)**: two openclaw crons, `health-check-morning` (`0 11 * * *`) and
`health-check-evening` (`0 23 * * *`), both `agentId: main`, `sessionTarget:
isolated`, payload:

> "Run the health check script: exec bash `/home/claude/helper-scripts/health-check.sh`
> — if output is ALL_HEALTHY reply HEARTBEAT_OK only. If FAILURES_DETECTED, send the
> full output to Kent via WhatsApp."

`delivery.mode: none` (healthy runs deliver nothing); `failureAlert.after: 2 →
+16179300916`. So today: the **Sonnet main agent** is spun up twice daily merely to
`bash health-check.sh` and conditionally forward output — pure agent overhead for a
deterministic check.

## R5 — Health-check replacement (Kent's decision: systemd user timer)

**Decision** (decision_id 01KX1XY2CN2RHA6675BXDRG84Y):
- A new **systemd user timer** `felix-health-check.timer` → `.service` fires at the
  same two times (`11:00` and `23:00`), matching the `felix-core-digest` /
  `credential-health-check` reference posture (both are enabled systemd user timers
  on office2 — confirmed live).
- The service runs a thin wrapper that runs (via `subprocess`, **not** `exec` — see
  R9/Codex #1) the **existing** `/home/claude/helper-scripts/health-check.sh` unchanged
  (FR-010) and inspects its output: `ALL_HEALTHY` → silent (a health-signal file is
  stamped for observability); `FAILURES_DETECTED`/`UNKNOWN`/`SCRIPT_MISSING` → push the
  full (bounded) output as an alert.
- The two `health-check-*` openclaw crons are **removed** via the `openclaw cron`
  CLI (DIR-007), eliminating the `main` session (NFR-002).

**Delivery decision — ntfy (flag for review)**: failure alerts go via **ntfy**, the
canonical non-agent push substrate on office2 (security-monitor / credential-health
precedent, [[reference_ntfy_notification_pattern]]), rather than WhatsApp. Rationale:
WhatsApp delivery is an agent/openclaw-messaging capability; re-invoking it from a
non-agent timer would reintroduce the coupling we are removing. **Channel change to
surface to Kent**: failure notifications move WhatsApp → ntfy. The healthy case is
unchanged (already silent: `delivery.mode: none`). *If Kent prefers WhatsApp for
health failures, the wrapper can shell a non-agent `openclaw` send instead — folded
if requested.*

**Scope note (DIR-024 / no-vestiges)**: `health-check.sh` currently lives only in
`/home/claude/helper-scripts/` (unversioned, not in the repo). This mission **reuses
it in place** per FR-010/C-005 and does **not** vendor it into the repo; that
version-control gap is pre-existing minor debt noted for a future issue, not this
mission's scope.

## R6 — Validation harness (INV-006 forcing function)

**Decision**: ship `scripts/openclaw/heartbeat_gate/validate_ledger.py` (or a pytest)
that replays `decide_deterministic` over a gate-ledger.jsonl and asserts **0 missed
escalations** and reports the over-escalation rate. Runnable against the live ledger
(`python3 -m scripts.openclaw.heartbeat_gate.validate_ledger --ledger <path>`) and
wired into the test suite with a committed fixture sample so it guards regressions.

**Rationale**: Makes INV-006 a mechanical gate (verify-before-done), not a manual
claim; reuses the exact replay that produced R0.

## R7 — Deploy + rebaseline

**Decision**:
- One `deploys/queued/<name>.yaml` manifest (DIR-004) installs the new
  `felix-health-check.{service,timer}` unit files and the wrapper, and — because
  openclaw cron removal is not a file-copy — either the manifest's script performs
  the `openclaw cron` removal through the vetted lib, or the removal is an explicit
  documented step in `quickstart.md` executed via `openclaw cron` CLI. (Plan/tasks to
  choose; the manifest script path is preferred for auditability.)
- **Rebaseline required** (#557): touches systemd user units + deploy scripts, and
  openclaw config (cron removal). Merge commit records `Rebaseline: completed at
  <ts>` (felix-deployer automated if pipeline-applied for the unit files; the cron
  removal is an openclaw-config change — confirm whether it rides the pipeline or is
  out-of-band manual per `docs/runbooks/security-baseline-ops.md`).

**Open sub-question for tasks**: does `openclaw cron remove` fit the felix-deployer
happy path, or is it an out-of-band manual step (like prior openclaw.json edits)?
Resolve during tasks against the deploy lib.

## R8 — Architecture docs (DIR-014)

**Decision**: update `docs/design/architecture/data/service-inventory.json` (+ md
view) — health-check execution path moves off `main` to a systemd timer; heartbeat-
gate loses its Haiku/model dependency. Review `docs/constitution/AGENT-REGISTRY.md`
for `main`'s scheduled-workload reduction (two fewer scheduled sessions/day).

## R9 — Post-plan Codex review folds (2026-07-08)

Codex (`spec-kitty-review` profile) reviewed spec+plan+research+data-model+contracts
against the live code. 9 findings, all accepted and folded:

**New precedent discovered** (reuse, don't reinvent): `scripts/office2/
credential-health-check.{service,timer}` + `scripts/office2/deploy/
credential-health-check.sh` = the systemd-timer deterministic-check pattern to mirror;
`scripts/office2/security-monitor/audit.sh:243-255` = the canonical ntfy send. The
health-check wrapper/units land under `scripts/office2/` accordingly.

| # | Severity | Finding | Fold |
|---|---|---|---|
| 1 | HIGH | Wrapper `exec` can't classify; missing-script/ntfy-failure could be silent | `subprocess` not `exec`; missing-script + ntfy-failure both alert/log; deploy preflight — health-check contract + FR-009 |
| 2 | HIGH | Step-2 fail-safe only catches 2 exc types; a deterministic impl error → exit-1 emergency path, violating FR-007 | `decide_deterministic` must be **total** and/or broaden step-2 `except`; malformed-context test — escalation contract + FR-007 |
| 3 | HIGH | Plan over-claims the 1748-tick replay proves all 3 labels | Replay validates **escalate boolean only**; label split via synthetic fixtures — escalation contract + FR-011 |
| 4 | MED | Replay can't validate full `GateDecision` (ledger lacks issues_filed/counts) | Split: live replay = escalation; synthetic fixtures = 3-label — IC-02 |
| 5 | MED | WhatsApp→ntfy is a user-visible regression w/o acceptance parity | Operator-visible delivery-parity acceptance (push received, full output, all-alert-cases, ntfy-failure logged) — contract + quickstart |
| 6 | MED | Deploy sequencing leaves double-run/no-run windows | Strict order: install→smoke→enable→verify→remove crons→confirm — quickstart + IC-04 |
| 7 | MED | Removing `--api-key`/`--prompt` may break tests | Full removal (no vestiges), update ALL tests, smoke installed ExecStart — FR-008 |
| 8 | LOW | Escalation reason parity (cite triggers, no action framing) | reason test: contains trigger IDs, excludes recommendation language — escalation contract |
| 9 | LOW | Health-check status precedence ambiguous | `FAILURES_DETECTED` wins; test both-token/stderr-only/non-zero+healthy/truncation — health-check contract |

**Open operator decision surfaced (Codex #5)**: failure alerts move **WhatsApp → ntfy**.
Proceeding with ntfy (canonical non-agent substrate; healthy case already silent) but
flagged to Kent; a fold to a non-agent WhatsApp send is available if he prefers.
