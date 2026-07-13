# Feature Specification: Author main agent workspace

**Mission**: author-main-workspace-01KXE90Z
**Source issue**: [#583](https://github.com/kentonium3/kg-automation/issues/583) (parent epic [#167](https://github.com/kentonium3/kg-automation/issues/167))
**Written against**: `docs/design/openclaw-workspace-authoring-standard.md` (#587)

## Overview

`main` is Felix's front-desk / orchestrator OpenClaw agent: it handles all direct
WhatsApp conversation and delegates domain work to specialist sub-agents
(capture, habits, escalation, tasker, calendar). Its workspace files are the
least intentionally-authored of the active agents — two files (`IDENTITY.md`,
`TOOLS.md`) are unmodified factory templates, `SOUL.md` is cross-contaminated
with role, user-context, and operational content, and both #587 shared
invariants (privacy boundary, Output Discipline) currently fail validation.

This mission re-authors `main`'s workspace as a coherent, self-contained set
against the #587 standard, and — because `main` is the agent the future mail /
EA capability (#165) will extend — folds in two approved behavior improvements
(EA-orchestrator role framing; tighter delegation reliability). It is not a pure
refactor: it changes authored behavior on the live front-desk agent, so
validation, review, and a post-deploy smoke test are load-bearing.

## Domain Language

- **Workspace file ownership** (per #587 Principle 2): `IDENTITY.md` = display
  card; `SOUL.md` = voice/stance only; `USER.md` = filtered view of Kent;
  `TOOLS.md` = environment/tool surface + enforceable privacy path; `AGENTS.md`
  = operating rules / SOP / role & authority + enforceable policy.
- **Invariant A (privacy)**: the enforceable `04-Growth/_private/` never-touch
  rule must live in `AGENTS.md` and/or `TOOLS.md`; `SOUL.md` may carry only a
  one-line stance.
- **Invariant B (Output Discipline)**: a user-facing-WhatsApp agent must carry
  the canonical Output Discipline block in `AGENTS.md`.
- **agent-prompt-sync**: the deploy pipeline that copies agent prompt files to
  office2 on merge-to-main (distinct from the felix-deployer manifest pipeline).
- **GOVERNANCE.md**: a `main`-only on-demand-read risk-tier reference; not one of
  the #587 five files and not a recognized OpenClaw bootstrap basename.

## User Scenarios & Testing

### Scenario 1 — Authoring passes validation (primary acceptance)
A maintainer authors `main`'s five standard workspace files to the #587
standard. Running the workspace validator reports `main` `ok: true` — both
Invariant A (privacy in an enforceable home) and Invariant B (Output Discipline
block present) pass.

### Scenario 2 — Direct conversation post-deploy (runtime happy path)
Kent sends a direct WhatsApp message to Felix. `main` replies in Kent's voice,
leads with its `Sent by main:...` identity line (unchanged by this mission), and
never reads, writes, references, or logs `04-Growth/_private/`.

### Scenario 3 — Delegation relay (runtime happy path)
Kent sends a message that belongs to a specialist (e.g. a habit completion, an
inbox-processing request, a calendar event). `main` forwards Kent's text
**verbatim** to the correct specialist and relays the specialist's result back —
without double-relaying cron-driven (announce-mode) output.

### Edge / exception cases
- **Privacy**: any prompt or content that would touch `04-Growth/_private/` is
  refused — the enforceable rule holds regardless of framing.
- **Ambiguous delegation**: `main` routes to exactly one specialist or asks;
  it does not handle a specialist's domain itself.
- **Repo ↔ office2 drift**: after deploy, the deployed copies must match the
  repo copies (md5 parity); a mismatch is a failed deploy, not a silent skip.

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | `SOUL.md` is authored to voice-only: retain the Voice content (principles, words-to-avoid, "words that are Kent"); remove role/purpose, the "Understanding Kent" block, the delegation table, and heartbeat guidance; reduce the privacy boundary to a one-line stance. | Approved |
| FR-002 | `USER.md` is authored as `main`'s filtered view of Kent: absorb the filtered "Understanding Kent" context and the Felix "why" (mission/purpose); resolve the overlap with SOUL Voice so Kent's *preferences* live in USER and the *agent voice* lives in SOUL. | Approved |
| FR-003 | `TOOLS.md` is authored from the factory scaffold to `main`'s real surface: office2 paths, SSH hosts, the `openclaw agent` delegation mechanics, `felix-file-issue.py`, the timelog helper invocation, relevant state files, and the enforceable `04-Growth/_private/` privacy path; authoritative lists are referenced by pointer, not inlined. | Approved |
| FR-004 | `IDENTITY.md` is authored with `main`'s identity (name = Felix, plus creature/vibe/emoji drawn from the voice); no factory placeholder text remains. | Approved |
| FR-005 | `AGENTS.md` receives a concise role/authority statement framing `main` as the front-desk / EA-orchestrator (current reality only, no speculative mail behavior). | Approved |
| FR-006 | `AGENTS.md` carries an **adapted** Output Discipline block (main-specific, reconciled with `HEARTBEAT_OK`; not a literal copy of capture's inbox-specific block) under the `output discipline` marker (fixes Invariant B). The enforceable `04-Growth/_private/` privacy rule lives in `TOOLS.md` (fixes Invariant A; keeps AGENTS under its byte cap). | Approved |
| FR-007 | Delegation is consolidated to a single owner (AGENTS routing matrix; drop the SOUL table) covering **all six specialist paths** (capture, habits, escalation, tasker, calendar, timelog) — escalation and tasker, currently only in the SOUL table, must survive. Delegation command **mechanics** (the `openclaw agent` bash, timelog block, issue-filing block) move to `TOOLS.md`; AGENTS keeps the rules. The verbatim-passthrough, cron-vs-ask, and #679 calendar-boundary rules are preserved and unambiguous. | Approved |
| FR-008 | Red lines are consolidated into a single enforceable owner (`AGENTS.md`), with only pure behavioral stance (if any) retained in SOUL. | Approved |
| FR-009 | The #587 standard / roster is updated with a one-line note that `main` carries an on-demand `GOVERNANCE.md` outside the five-file model and outside validator scope; GOVERNANCE.md content itself is unchanged. | Approved |
| FR-010 | After merge, the authored files deploy via agent-prompt-sync to `/data/services/openclaw/data/` and the deployed copies match the repo copies; the live `main` session is rotated (`rotate_main_session.py`) so it picks up the new prompt; a post-deploy evidence-based smoke test confirms a direct exchange (Scenario 2) and one delegation route (Scenario 3). | Approved |

> **Dropped (operator decision 2026-07-13):** the message-identity-line de-hardcode (formerly FR-008). The fleet-wide `Sent by <agent-id>:<model>` convention is referenced by the Output Discipline Hard Rule; changing it on `main` alone creates inconsistency for marginal value. The identity line (`Sent by main:sonnet`) is left **unchanged**; the message-identity section is authored as-is. A fleet-wide de-hardcode may be reconsidered separately.

## Non-Functional Requirements

| ID | Requirement | Measurable threshold | Status |
|----|-------------|----------------------|--------|
| NFR-001 | Shared invariants pass (main-scoped). | `python3 -m scripts.openclaw.agents.validate_workspace --json` reports the **`main`** entry `ok: true` (Invariant A and B). Acceptance reads main's object, not the process exit code — the full-fleet exit is independently RED due to `felix-admin-calendar` (out of scope, #635). | Approved |
| NFR-002 | No file-ownership duplication. | Each shared concern (privacy rule, voice, role, delegation, heartbeat) appears in exactly one owner file per the #587 ownership table; zero duplicated rules across files. | Approved |
| NFR-003 | Deploy parity. | 100% md5 match between repo and `/data/services/openclaw/data/` for every authored file after agent-prompt-sync runs. | Approved |
| NFR-004 | No runtime regression. | After session rotation, post-deploy smoke: direct exchange + one delegation route both succeed with log/session evidence; the `Sent by main:...` identity line still leads replies (unchanged); no `04-Growth/_private/` access. | Approved |
| NFR-005 | AGENTS byte cap. | `main/AGENTS.md` stays below the 12,000-byte hard cap (`scripts/openclaw/agents/tests/test_agents_md_size.py` green), with ≥ ~300 B headroom after authoring. | Approved |

## Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Deploy is via agent-prompt-sync on merge-to-main. **No `deploys/queued/<name>.yaml` manifest is authored** — agent prompt files are outside the felix-deployer manifest boundary (#636). | Approved |
| C-002 | `GOVERNANCE.md` content is left unchanged (acknowledged in the standard/roster only). | Approved |
| C-003 | The role framing reflects current reality only; no speculative mail #165 / EA behavior is introduced. | Approved |
| C-004 | Change is Tier 3 (agent prompts / logic-workflow). Rebaseline is **not required** — agent prompt files are not hashed by `audit.sh` (#621 gap); the merge commit records `Rebaseline: not required — <reason>`. | Approved |
| C-005 | The mission branches from `main` with the #587 standard + validator already present (avoids the #584 mid-mission dependency-merge git-state trap). Satisfied at create time. | Approved |
| C-006 | No new deterministic work is introduced; the existing `scripts/openclaw/agents/validate_workspace.py` checker (from #587) is reused as-is. No new helper/library/skill. | Approved |

## Success Criteria

- **SC-001**: The workspace validator reports the `main` entry `ok: true` for both shared invariants, and `main/AGENTS.md` is under the 12,000-byte cap.
- **SC-002**: All five standard files are intentionally authored — no factory-template or placeholder content remains in `IDENTITY.md` or `TOOLS.md`, and `SOUL.md` contains voice/stance only.
- **SC-003**: No instruction conflicts exist across `main`'s workspace files, and all six specialist routing paths plus the load-bearing delegation rules survive (validated during review).
- **SC-004**: After deploy and session rotation, repo and office2 copies match, and an evidence-based smoke test shows a direct exchange and one delegation route both working (identity line unchanged).
- **SC-005**: The privacy boundary (`04-Growth/_private/` never-touch) is preserved and lives in its enforceable home (`TOOLS.md`).

## Key Entities

- **main workspace** — `scripts/openclaw/agents/main/` : `IDENTITY.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `AGENTS.md` (the five standard files), plus the out-of-standard `GOVERNANCE.md` and helper `felix-file-issue.py`.
- **#587 standard** — `docs/design/openclaw-workspace-authoring-standard.md` (the contract) and `scripts/openclaw/agents/validate_workspace.py` (the checker).
- **Deployed copy** — the office2 agent-prompt-sync destination for `main`'s prompt files.

## Assumptions

- The agent-prompt-sync timer is live on office2 and fires on merge-to-main (confirmed by plan phase).
- `main` is a user-facing-WhatsApp agent, so Invariant B requires the Output Discipline block (not the "no user-facing WhatsApp" annotation).
- The pilot #584 (felix-admin-capture) is the canonical Output Discipline source to mirror.
- `GOVERNANCE.md`, being outside the recognized bootstrap basenames, is read on-demand and never session-injected; leaving it unchanged does not affect the session prompt surface.
