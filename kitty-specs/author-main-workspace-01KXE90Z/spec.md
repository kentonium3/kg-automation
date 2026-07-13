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
EA capability (#165) will extend — folds in three approved behavior
improvements. It is not a pure refactor: it changes authored behavior on the
live front-desk agent, so validation, review, and a post-deploy smoke test are
load-bearing.

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
leads with a **model-agnostic** identity line (no hard-coded model name), and
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
| FR-006 | `AGENTS.md` carries the canonical Output Discipline block (fixes Invariant B) and the enforceable `04-Growth/_private/` privacy rule (fixes Invariant A). | Approved |
| FR-007 | Delegation guidance is consolidated to a single owner (drop the SOUL duplicate) and the verbatim-passthrough and cron-vs-ask relay rules (the #263/#285 duplicate-message class) are made unambiguous. | Approved |
| FR-008 | The message-identity line is de-hardcoded so it no longer embeds a specific model name (e.g. `Sent by main:sonnet` → a model-agnostic form). | Approved |
| FR-009 | Red lines are consolidated into a single enforceable owner (`AGENTS.md`), with only pure behavioral stance (if any) retained in SOUL. | Approved |
| FR-010 | The #587 standard / roster is updated with a one-line note that `main` carries an on-demand `GOVERNANCE.md` outside the five-file model and outside validator scope; GOVERNANCE.md content itself is unchanged. | Approved |
| FR-011 | After merge, the authored files deploy via agent-prompt-sync and the deployed office2 copies match the repo copies; a post-deploy smoke test confirms a direct exchange (Scenario 2) and one delegation route (Scenario 3). | Approved |

## Non-Functional Requirements

| ID | Requirement | Measurable threshold | Status |
|----|-------------|----------------------|--------|
| NFR-001 | Shared invariants pass. | `python3 -m scripts.openclaw.agents.validate_workspace --json` reports `main` `ok: true` (Invariant A and B both pass). | Approved |
| NFR-002 | No file-ownership duplication. | Each shared concern (privacy rule, voice, role, delegation, heartbeat) appears in exactly one owner file per the #587 ownership table; zero duplicated rules across files. | Approved |
| NFR-003 | Deploy parity. | 100% md5 match between repo and office2 for every authored file after agent-prompt-sync runs. | Approved |
| NFR-004 | No runtime regression. | Post-deploy smoke: direct exchange + one delegation route both succeed; identity line is model-agnostic; no `04-Growth/_private/` access. | Approved |

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

- **SC-001**: The workspace validator reports `main` `ok: true` for both shared invariants.
- **SC-002**: All five standard files are intentionally authored — no factory-template or placeholder content remains in `IDENTITY.md` or `TOOLS.md`, and `SOUL.md` contains voice/stance only.
- **SC-003**: No instruction conflicts exist across `main`'s workspace files (validated during review).
- **SC-004**: After deploy, repo and office2 copies match, and a live smoke test shows a direct exchange and one delegation route both working with the model-agnostic identity line.
- **SC-005**: The privacy boundary (`04-Growth/_private/` never-touch) is preserved and lives in its enforceable home.

## Key Entities

- **main workspace** — `scripts/openclaw/agents/main/` : `IDENTITY.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `AGENTS.md` (the five standard files), plus the out-of-standard `GOVERNANCE.md` and helper `felix-file-issue.py`.
- **#587 standard** — `docs/design/openclaw-workspace-authoring-standard.md` (the contract) and `scripts/openclaw/agents/validate_workspace.py` (the checker).
- **Deployed copy** — the office2 agent-prompt-sync destination for `main`'s prompt files.

## Assumptions

- The agent-prompt-sync timer is live on office2 and fires on merge-to-main (confirmed by plan phase).
- `main` is a user-facing-WhatsApp agent, so Invariant B requires the Output Discipline block (not the "no user-facing WhatsApp" annotation).
- The pilot #584 (felix-admin-capture) is the canonical Output Discipline source to mirror.
- `GOVERNANCE.md`, being outside the recognized bootstrap basenames, is read on-demand and never session-injected; leaving it unchanged does not affect the session prompt surface.
