# Research: Felix Truthful Reporting Guardrails

**Mission**: felix-truthful-reporting-01KX6MN5
**Phase**: 0 (Outline & Research)
**Date**: 2026-07-10

This document resolves the open design questions from `spec.md` before Phase-1
design. The dominant unknown is **how a completion/infrastructure claim can be
grounded against independent system state** (FR-004/FR-005) without trusting the
agent's own narration — the mission's primary design risk.

---

## D1 — How do we detect "unrequested infrastructure was created"?

**Decision**: A deterministic **cron-drift detector**. Enumerate the live
OpenClaw cron set (`openclaw cron list --json`) and compare it to a versioned
**approved-cron baseline** committed in the repo. Any live cron absent from the
baseline (or any baseline cron missing) is a drift → emit an alert via the #701
unified alert bus.

**Rationale**:
- Live-probed `openclaw cron list --json` on office2 (2026-07-10) returns clean
  structured records: `id`, `name`, `enabled`, `agentId`, `createdAtMs`,
  `schedule`. Enumeration is deterministic and cheap.
- The 7 current legitimate crons are all owned by `felix-admin-*` agents
  (inbox-5pm/10pm/7am/noon, habits-morning-checkin, habits-weekly-report,
  escalation-daily). The incident's rogue `workspace_auth_spike daily run`
  cron was **not** one of them — a baseline diff would have flagged it
  immediately, with **zero dependence on what any agent claimed**.
- This grounds against independent system state (the actual scheduler), exactly
  as the spec's edge-case note requires. It is the load-bearing, reliable half
  of detection and directly kills the incident's most dangerous defect
  (autonomous standing-infrastructure creation).

**Alternatives considered**:
- *Parse the agent's outbound WhatsApp claim and correlate.* Rejected —
  outbound messages are not logged anywhere discoverable on office2 (probed
  `~/.local/share/openclaw`, `~/.config/openclaw`, agent log dirs); free-text
  NLP correlation is fragile and out of bounded scope.
- *Hard capability guardrail (remove/approval-gate cron creation).* Rejected —
  Kent's Q2 decision is doctrine + prompt only; hard containment is F0/#704
  (deferred).

**Baseline maintenance**: the approved-cron baseline is a small committed
artifact. Adding/removing a legitimate cron updates the baseline in the same
change (a documented, reviewable step). Drift = "reality diverged from the
approved set," which is precisely the signal we want.

---

## D2 — How do we detect a fabricated *completion* claim?

**Decision (revised after post-plan Codex finding 2)**: A completion-assertion
**action ledger**, populated **deterministically by the artifact-creation
helpers** — not by free-form agent compliance. When a supported artifact is
created (starting with the Vikunja task helper `scripts/vikunja/create_task.py`,
#686), the helper auto-emits a structured **completion-assertion** on success
(artifact kind + id list, grounded in the creation result). A deterministic
**verifier** reads recent assertions and confirms each referenced artifact
actually exists in the owning system. An assertion whose artifact cannot be
corroborated → alert via the #701 bus.

**Why auto-emit, not agent-emitted**: the original design had the agent choose
to emit the assertion — but the same agent that fabricates a completion would
simply omit the record (Codex: "audit decoration"). Anchoring emission in the
creation helper makes the ledger a reliable ground-truth record of what was
actually created, independent of the agent's narration. Doctrine still asks an
agent to record a manual assertion when it bypasses a wrapped helper, but the
success path no longer depends on compliance.

**What this detects vs. does not (honest framing — Codex finding 1)**:
- **Cron drift (D1)** is the load-bearing, agent-independent "reported-vs-actual"
  detector and needs no cooperation.
- The assertion verifier catches an assertion referencing a **missing** artifact
  (helper-bug or a narrow fabricate-and-log pattern) and provides the auditable
  FR-004 ledger.
- **Blind spot (explicit non-goal):** a pure verbal completion lie that creates
  no artifact and emits no assertion ("today's run is logged as complete") is
  **not** detectable in v1 — its only control is doctrine (FR-001). Detecting it
  needs an outbound-message/request log, which does not exist today. SC-003 is
  scoped to the two detectable classes accordingly.

**Rationale**:
- Grounds the claim against **independent system state** (the artifact's owning
  system), not the agent's narration — a fabricating agent cannot conjure a
  Vikunja task id that the API will confirm.
- The structured assertion IS the "structured request↔outcome record" from
  Kent's bounded-detection choice. Verification is fully deterministic.
- Reuses existing substrates: agents already write per-agent JSONL action logs
  (`/home/.../second-brain/agents/logs/<agent>/<date>.jsonl` via
  `log_action.py`); the assertion record fits the same shape. Alerts reuse the
  #701 bus + are durably captured by the #706 ledger.

**Alternatives considered**:
- *LLM-judge that re-reads the conversation and rules on truthfulness.*
  Rejected for v1 — reintroduces a stochastic component into the trust
  substrate (self-defeating), higher cost, and depends on a message log that
  doesn't exist.
- *Require every agent turn to emit an assertion.* Rejected — too heavy;
  bounded to delegated create/do completions (FR-006 class a).

---

## D3 — Where does the doctrine live, and how is it applied fleet-wide?

**Decision**: Extend the existing **Felix Output-discipline pattern** (already
mirrored in several agent `AGENTS.md` files) with a **truthful-reporting +
mechanism-fidelity** block, applied to all fleet agent prompts under
`scripts/openclaw/agents/<agent>/AGENTS.md`. Add a **no-unrequested-
infrastructure** block to `main`'s prompt specifically. Keep a single canonical
source for the shared doctrine text to avoid drift across agents.

**Rationale**:
- `main/AGENTS.md` (220 lines) already carries absolute-rule blocks ("Verbatim
  pass-through (ABSOLUTE)", "Red Lines") — the truthfulness rule belongs in the
  same register.
- Fleet-wide application matches Kent's Q3 decision (doctrine fleet-wide,
  infra guardrail main-only) and the #661/#662 comprehension-class lineage.

**Constraints**:
- AGENTS.md effective prompt budget (~12k rawChars; ~26% inflation noted in
  prior deploy gotchas). Doctrine additions must be terse; run fleet-guard
  prompt tests after editing (NFR-003).
- Prompt changes are a **listed audited surface but UNMONITORED** — per gap
  #621 (recorded in `audited-surfaces.json`, verified 2026-07-10), `audit.sh`
  does not hash deployed `AGENTS.md`, so **no baseline is written and no
  rebaseline is required or possible** for prompt edits (Codex finding 9). The
  detector code (`scripts/trust/`, `scripts/deploy/`) is likewise not a hashed
  baseline. Net: this mission is **Rebaseline: not required**. Prompts deploy via
  the agent-prompt-sync path; the detector deploys via a `deploys/queued/`
  manifest + systemd timer.

---

## D4 — How does the detector run and deploy?

**Decision**: A helper/library under `scripts/` (per the helper/library/skill
conventions), invoked by a **systemd user timer** on office2 (the
felix-health-check pattern), on a cadence ≤ 15 min (NFR-002). It emits via the
#701 alert bus. Deploy through a `deploys/queued/<name>.yaml` manifest consumed
by felix-deployer, with an entrypoint that installs + `daemon-reload`s the timer
(the #701 lesson: repo unit files do nothing until the entrypoint installs them).

**Rationale**: matches established Felix deterministic-monitoring patterns
(#676 felix-health-check timer; #701 deploy entrypoint discipline). Fail-safe
per NFR-001/#706 — a detector failure degrades to no-alert, never breaks agents.

**Cadence note**: the cron-drift detector and assertion-verifier are both
poll-based scanners; a single timer can drive both scans to keep the surface
small.

---

## Consolidated decisions

| Ref | Decision | Requirement(s) |
|-----|----------|----------------|
| D1 | Deterministic cron-drift detector vs approved baseline; alert via #701 | FR-003 (detection), FR-004, FR-005, FR-006(b) |
| D2 | Completion-assertion protocol + deterministic artifact verifier; alert via #701 | FR-001 (detection), FR-004, FR-005, FR-006(a) |
| D3 | Extend Output-discipline pattern fleet-wide; no-unrequested-infra block in main | FR-001, FR-002, FR-003 (prevention) |
| D4 | Helper + systemd timer, deploy via manifest, fail-safe, reuse #701/#706 | NFR-001, NFR-002, C-002, C-004 |

## Key risks carried into design (post-Codex status)

1. **Completion-fabrication coverage is partial — now honestly scoped.**
   Detection covers cron drift (agent-independent) + missing-artifact
   assertions; the pure-verbal-lie residual is doctrine-only and declared an
   explicit blind spot (spec FR-006, SC-003). Auto-emit from creation helpers
   removes the compliance dependency on the success path. **Resolved** per Codex
   findings 1–3.
2. **Baseline maintenance race/false-positives** — a legitimate cron created
   before its baseline lands on office2 would transiently alert. **Mitigation
   (Codex finding 5):** the approved-cron baseline must deploy before or with the
   cron; finding fingerprints include the baseline version/hash; a baseline
   change clears/re-evaluates seen-findings. See data-model State & idempotency.
3. **Alert cadence/resolution (Codex finding 6)** — seen-findings must not hide
   persistent drift forever: first-seen alerts immediately, re-alerts every 24h
   while unresolved, and a low-priority resolved event fires when drift clears.
4. **Cron identity semantics (Codex finding 4)** — match key `(name, agent_id)`,
   diff on `schedule.expr` + `tz` + `enabled`; finding kinds cover present /
   missing / schedule-mismatch / enabled-mismatch. See data-model.
5. **Fail-safe exit-code discipline (Codex finding 8)** — timer mode always
   exits 0 (`ok:false` in JSON on fault) to avoid systemd failure loops;
   explicit preflight/CLI mode may exit 2. Deploy self-test uses preflight mode.
6. **Deploy prompt-sync race (Codex finding 10)** — the deploy entrypoint must
   trigger `agent-prompt-sync.service` and verify deployed prompt content before
   the regression DM test, rather than waiting for the 5-min timer.
7. **Prompt budget** — fleet-wide doctrine must fit within AGENTS.md budget
   (~12k rawChars); run fleet-guard tests after editing.
