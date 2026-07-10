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

**Decision**: A **completion-assertion protocol**. When an agent reports a
delegated create/do request as complete, doctrine requires it to record a
structured **completion-assertion** naming the concrete artifact it claims to
have produced (artifact kind + identifier + the request it answers). A
deterministic **verifier** reads recent assertions and confirms each referenced
artifact actually exists in the owning system (e.g., the Vikunja task id is
present via the Vikunja API). An assertion whose artifact cannot be
corroborated → alert via the #701 bus.

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

**Honest limitation (primary design risk — flagged for post-plan Codex)**:
This detects fabrications for **artifact-producing** delegated requests where
the agent emits an assertion. A pure verbal fabrication with *no* artifact and
*no* assertion (e.g., "today's run is logged as complete" when nothing was even
claimed to be created) is only partially covered by detection — its primary
control is **doctrine** (FR-001). We mitigate by: (a) doctrine requiring an
assertion for any delegated create/do completion, so the *absence* of a
grounding assertion for such a request is itself a doctrine violation; and
(b) the cron-drift detector (D1) catching the infrastructure side
independently. We explicitly do **not** claim to detect every conceivable
verbal lie — that is the deferred full-F1 subsystem. This bounded design is the
operator-chosen scope.

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
- Prompt changes are an **audited surface** → rebaseline obligation on deploy
  (C-004). Prompts deploy via the agent-prompt-sync path; the detector deploys
  via a `deploys/queued/` manifest + systemd timer.

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

## Key risks carried into design

1. **Completion-fabrication coverage is partial** (D2 limitation) — doctrine is
   the primary control; detection covers the artifact-producing + infra classes.
   Post-plan Codex must scrutinize whether this bounded coverage is honestly
   scoped and whether the assertion protocol's compliance dependency is
   acceptable.
2. **Baseline maintenance burden** — the approved-cron baseline must be updated
   when legitimate crons change, or the detector produces false-positive alerts.
   Design must make baseline updates a cheap, obvious step.
3. **Prompt budget** — fleet-wide doctrine must fit within AGENTS.md budget.
