# Specification: Harden Inbox Capture on Sonnet

**Mission**: harden-inbox-capture-01KWVGZM
**Type**: software-dev
**Status**: Draft
**Source**: kentonium3/kg-automation#662 (Phase 1), corrects #658

## Overview

Felix's OpenClaw agents invoke Python helper scripts (inbox capture, habits,
escalation, calendar, tasker) as `exec` tool calls. The inbox-capture agent
(`felix-admin-capture`) intermittently fails: it hallucinates that its helper
scripts "are not implemented / do not exist," refuses to run, and emits a false
`🛠️ … failed` / "system broken" alarm to Kent's phone.

Live behavioral probing of office2 (2026-07-06) identified the **real root cause**,
which is environmental, not a pure model hallucination:

- OpenClaw's `exec` tool runs commands in a **sanitized environment that strips
  `PYTHONPATH`**. The gateway *process* has `PYTHONPATH=/home/claude/kg-automation`
  (set via a verified systemd drop-in), but exec subshells do **not** inherit it.
- Every agent prompt currently invokes helpers via the form
  `cd "${PYTHONPATH:?PYTHONPATH unset}" && python3 -m scripts.<pkg>.<mod>` — the
  "canonical" form established fleet-wide by **#658**. Because exec strips
  `PYTHONPATH`, this `cd` fails with exit 127 (`PYTHONPATH unset`) on **every**
  cron run. The model then flails, and a weak model (haiku) concludes "scripts
  don't exist."
- The deployed workspace cwd (`/data/services/openclaw/inbox-agent`) does not
  contain the `scripts/` package (it lives in `/home/claude/kg-automation`), so a
  bare `python3 -m scripts.…` also fails with `ModuleNotFoundError`.
- The **only** invocation that works — proven 102× in the run trajectories — is the
  self-contained `cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod>`.
- The `🛠️ … failed` warning is **not a "show" tool** — it is OpenClaw humanizing
  the *last failing exec command*. Under `delivery.mode: "announce"` (verified on
  all four inbox crons), a run that ends in error surfaces that diagnostic to
  WhatsApp. There is no successful fallback (`fallbackUsed: false` in every run).

This is a **fleet-wide** defect: `#658`'s `${PYTHONPATH:?}` form is broken under
exec sanitization in **all six active agents** (capture, escalation, habits,
calendar, tasker, main) — confirmed by sibling crons already on sonnet
(escalation-daily, habits-weekly) hitting the same `🛠️ … failed` class. #658's
verification checked the gateway process env, not the exec subshell env — a blind
spot this mission corrects.

**Scope decision (Kent, 2026-07-06):** fix the invocation form fleet-wide in this
mission; keep the capture haiku→sonnet move. This is **Phase 1** of #662; the
richer multi-intent decomposition (original FR-5) is a separate follow-up.

## The governing principle: two layers, model in only one

- **Plumbing / mechanics — deterministic; the LLM must NEVER touch it.** Where
  files/packages live, how a helper is invoked, dedup, state, delivery transport.
  The invocation must be a self-contained, opaque command that resolves its own
  environment — *no dependence on an inherited env var, no path guessing.*
- **Comprehension / judgment / interaction — the LLM's actual job.** Read the
  note, decide routing, ask a clarifying question, confirm the outcome. Preserved
  and (via sonnet) strengthened.

The fleet invocation-form fix *is* the deterministic-layer correction; sonnet and
the prompt reword are the comprehension-layer reinforcements.

## User Scenarios & Testing

### Primary — a note is captured and routed reliably
1. A scheduled/on-demand capture run fires.
2. Step 1 runs `cd /home/claude/kg-automation && python3 -m scripts.inbox.prescan`
   — succeeds regardless of exec's stripped env.
3. The agent comprehends and routes the note; Kent gets one clean WhatsApp
   confirmation with no `🛠️ … failed` warning.

### Exception — empty inbox
1. A run fires with nothing to process.
2. The agent emits exactly `[felix-admin-capture]: IDLE` — no "not implemented,"
   no invented path, no false alarm.

### Exception — a helper genuinely fails
1. A helper exits non-zero (a real error, not a missing-env artifact).
2. The agent reports the actual stderr and does not speculate about "missing
   infrastructure."

### Interactivity — calendar clarification (non-regression)
1. A calendar note omits a time.
2. The agent asks Kent over WhatsApp; his reply resolves and routes it.

### Fleet non-regression
1. Escalation, habits, calendar, tasker, and main runs invoke their helpers with
   the self-contained form and complete without the `🛠️ … failed` class.

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Every active agent prompt (capture, escalation, habits, calendar, tasker, main; both `AGENTS.md` and any `AGENTS.md.tmpl`) MUST invoke helpers via the exec-sanitization-immune self-contained form `cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod>` (and the analogous `cd /home/claude/kg-automation && python3 scripts/<path>.py`). No invocation may depend on an inherited `PYTHONPATH`. | Approved |
| FR-002 | `env_assumptions.py` MUST be inverted to reflect the corrected canonical form: the self-contained checkout-`cd` invocation is compliant, and a bare/ unanchored `python3 -m scripts.…` remains a violation; the `${PYTHONPATH:?}` anchor is no longer the required compliant form. The Test-CI fleet guard, `validate_workspace.check_runtime_env_assumptions`, and all associated tests MUST agree with the new policy. Every prompt that is runtime-reliable passes the checker; no reliable prompt is flagged. | Approved |
| FR-003 | The capture prompt MUST be reworded so the model cannot read a "helpers live at `<path>`" claim and negate it. `AGENTS.md:74` ("Helpers under `scripts/inbox/` do the deterministic work…") is removed/reworded; helpers are referenced only as opaque invocations. On a helper non-zero exit the agent reports actual stderr, never "missing infrastructure." | Approved |
| FR-004 | `felix-admin-capture` MUST run on `anthropic/claude-sonnet-4-6` (already registered on office2) instead of `anthropic/claude-haiku-4-5`, changed in `openclaw.json`. The capture prompt's identity line `Sent by felix-admin-capture:haiku` MUST become `:sonnet` (all occurrences). | Approved |
| FR-005 | The conversational clarification loop MUST be preserved: a calendar note missing a required detail still triggers a WhatsApp clarifying question, and Kent's reply resolves and routes it. No regression. | Approved |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Cost + spend observability MUST be assessed for the sonnet move. office2 has **no** on-box $ spend tracking (cost fields zeroed; `model-usage` skill disabled); token volume is observable per run. | A rough per-run cost estimate (sonnet vs haiku, noting the ~252k-token flailing runs haiku produces on failure) and the observability gap are recorded in research before merge. | Approved |
| NFR-002 | Hallucination-free behavior MUST be demonstrable on an empty inbox. | 5 consecutive triggered capture runs over an empty inbox each emit exactly `[felix-admin-capture]: IDLE` with zero "not deployed/implemented" or invented-path output. | Approved |
| NFR-003 | Delivery robustness MUST be demonstrable. | 5 consecutive successful capture runs deliver their summary with no `🛠️ … failed` warning (i.e. runs no longer end in error). | Approved |

## Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | The LLM must never guess/infer/assert helper paths, package location, or existence; invocations are opaque and self-contained. | Approved |
| C-002 | The `openclaw.json` model change is an **out-of-band** edit on office2 (openclaw.json is not in the felix-deployer prompt-sync pipeline; it lives only at `/home/claude/.openclaw/openclaw.json`). It touches a **monitored** audited surface → **manual** security-baseline rebaseline required (the out-of-band exception, not the deployer happy path). | Approved |
| C-003 | Agent prompt files (`AGENTS.md`) deploy via the agent-prompt-sync pipeline and are an **unmonitored** audited surface (`audit.sh` does not hash them) → no rebaseline for the prompt changes. | Approved |
| C-004 | The 14 `scripts/inbox/` helpers (and other agents' helpers) are reused unchanged; this mission changes invocation form, the env-assumption checker, model config, and prompt wording — not helper behavior. | Approved |
| C-005 | Risk tier: Tier 3 (agent prompt/config + checker logic) + Tier 4 (arch docs). openclaw.json + prompts are audited surfaces. | Approved |
| C-006 | Architecture docs MUST be updated in-mission: `data/service-inventory.json` (+ md) capture `model` haiku→sonnet; `docs/constitution/AGENT-REGISTRY.md`; the #658 canonical-form correction noted where #658 is documented. | Approved |
| C-007 | The fleet invocation-form swap is a **bulk edit** (same string across many prompt files) → an `occurrence_map.yaml` classifying occurrences is produced during plan; `implement` will refuse the first WP without it. | Approved |
| C-008 | This mission **corrects #658**: it supersedes #658's `${PYTHONPATH:?}` canonical-form policy fleet-wide. The correction and its rationale (exec sanitizes env; gateway-env check was a blind spot) are recorded so the reversal is auditable. | Approved |

## Success Criteria

- **SC-001**: Every active agent `AGENTS.md`/`.tmpl` uses the self-contained form; `python3 -m scripts.openclaw.agents.env_assumptions` reports **ok** across the fleet.
- **SC-002**: `openclaw cron runs --id <inbox job>` shows `model: claude-sonnet-4-6` for capture runs after deploy.
- **SC-003**: A capture run over a real inbox note routes it correctly (journal/someday/task/calendar) with **no** "not implemented / not deployed" hallucination and no exit-127/ModuleNotFoundError.
- **SC-004**: 5 consecutive empty-inbox capture runs emit exactly `[felix-admin-capture]: IDLE` (satisfies NFR-002).
- **SC-005**: 5 consecutive successful capture runs deliver their WhatsApp summary with no `🛠️ … failed` warning (satisfies NFR-003).
- **SC-006**: A calendar note missing a time still triggers the clarification question and Kent's reply routes it (FR-005 non-regression).
- **SC-007**: The merge records `Rebaseline: completed at <ts>` (manual, for the openclaw.json model change); `service-inventory.json` (+ md) and `AGENT-REGISTRY.md` reflect the new model.
- **SC-008**: Test-CI green — the inverted `env_assumptions.py` + updated tests pass, and no reliable prompt is flagged.

## Key Entities

- **Active agent workspaces (×6)** — capture, escalation, habits, calendar, tasker, main; each `scripts/openclaw/agents/<slug>/AGENTS.md` (+ some `.tmpl`) carrying the invocation form (FR-001). felix-doc-auditor is suspended (excluded).
- **`env_assumptions.py`** — the #658 env-assumption checker; its canonical-form policy is inverted (FR-002). Shared by the Test-CI guard and `validate_workspace`.
- **`openclaw.json`** (office2 only) — carries the per-agent `model`; monitored audited surface (FR-004, C-002).
- **`scripts/inbox/` + other agents' helpers** — deterministic plumbing, reused unchanged (C-004), invoked self-contained.

## Assumptions

- `anthropic/claude-sonnet-4-6` is already registered in `openclaw.json` `models.providers.anthropic.models[]` (verified) — FR-004 is a one-field flip, no provider edit.
- OpenClaw's exec tool offers no config knob to stop sanitizing `PYTHONPATH` (not found in the minified dist) — a prompt-level self-contained invocation is the fix, not a systemd/env change.
- The office2 repo checkout is stably at `/home/claude/kg-automation` (deploy invariant); hardcoding it in prompts is acceptable (the `${PYTHONPATH:-/home/claude/kg-automation}` fallback variant was considered; see research).

## Out of Scope

- **FR-5 / Phase 2** of #662 — richer LLM-driven multi-intent decomposition. Separate follow-up.
- **Fleetwide model-selection framework** — only capture moves to sonnet here; the framework is deferred.
- **Non-capture model changes** — only the invocation form (not the model) changes for escalation/habits/calendar/tasker/main.
- **The helpers, routing destinations, vault layout, and future email/research intents** — unchanged.
