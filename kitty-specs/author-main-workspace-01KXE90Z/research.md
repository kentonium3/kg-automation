# Research: Author main agent workspace

Phase 0 decisions. No open `[NEEDS CLARIFICATION]` markers — the design was
locked with the operator before mission creation (issue #583 + the design
session). Decisions below record the rationale for the plan.

## D1 — Deploy path is agent-prompt-sync, NOT a felix-deployer manifest

- **Decision**: On merge-to-main, `main`'s prompt files deploy via the
  agent-prompt-sync pull pipeline (`scripts/openclaw/deploy/deploy_agent_prompts.py`,
  systemd timer on office2). No `deploys/queued/<name>.yaml` manifest is authored.
- **Rationale**: Agent prompt files are outside the felix-deployer manifest
  boundary (#636); felix-deployer manifests are for crons/helpers/systemd/config.
  Established by the #584 pilot (its plan-phase finding corrected the same wrong
  assumption).
- **Alternatives considered**: `deploys/queued/` manifest — rejected (wrong
  pipeline; would never fire for prompt files).
- **Timing note**: the agent-prompt-sync tick that performs the `git pull` runs
  the *old* code loaded pre-pull; the *next* tick writes the changed prompt
  files. Verification waits one tick past the pull.

## D2 — Purpose "why" → USER.md, role → AGENTS.md; SOUL becomes voice-only

- **Decision**: The Felix mission/"why" (extraordinary-life / 10x-leverage) moves
  to `USER.md` as filtered Kent-context; a concise role/authority statement lives
  in `AGENTS.md`; `SOUL.md` keeps only Voice + a one-line privacy stance.
- **Rationale**: #587 Principle 2 — SOUL owns voice/stance only; USER owns the
  filtered view of Kent; AGENTS owns role & authority. The "why" is about Kent's
  goals → USER. Operator-confirmed.
- **Alternatives considered**: keep a trimmed Purpose in SOUL (operator rejected
  — chose standard-clean); full mission preamble in AGENTS (rejected — grows the
  frequently-changing file).

## D3 — GOVERNANCE.md left unchanged, acknowledged in the standard/roster

- **Decision**: Do not re-author `GOVERNANCE.md`; add a one-line note to the #587
  standard/roster that `main` carries an on-demand `GOVERNANCE.md` outside the
  five-file model and outside validator scope.
- **Rationale**: The file is clean (no SOUL/USER contamination), is read
  on-demand via `cat` (not a recognized OpenClaw bootstrap basename, so never
  session-injected), and mirrors the canonical change-risk taxonomy. Rewriting it
  adds scope for no benefit. Operator-confirmed.
- **Alternatives considered**: include it in the authoring pass — rejected (scope).

## D4 — Reuse the #587 validator; no new deterministic work

- **Decision**: Verification uses the existing
  `scripts/openclaw/agents/validate_workspace.py` (`--json`, exit 0/1/2). No new
  helper/library/skill is introduced.
- **Rationale**: The deterministic invariant check already exists from #587 and
  is the standard's canonical checker. Helper/library/skill decision (per
  helper-script-conventions §9): no new deterministic work → no new artifact.

## D5 — Rebaseline not required

- **Decision**: The merge commit records `Rebaseline: not required — agent prompt
  files are not hashed by audit.sh (#621)`.
- **Rationale**: Agent prompts are a nominal audited surface but `audit.sh` does
  not hash prompt files (#621 gap); #584 set this precedent for the same file
  class.

## D6 — Content-authoring collapses toward a single coherent WP

- **Decision**: Expect the tasks phase to author the five coupled files in one
  WP (the #584 pattern), with the standard-roster note and the post-merge smoke
  as attached scope, not separate lanes.
- **Rationale**: Content moves *between* SOUL/USER/AGENTS; splitting across lanes
  would create cross-lane conflicts on the same workspace. #584 collapsed to a
  single WP for exactly this reason.
- **Alternatives considered**: one WP per file — rejected (the moves span files;
  a per-file split fractures a single conservation operation).

## D7 — Output Discipline canonical source = felix-admin-capture

- **Decision**: Mirror the Output Discipline (Hard Rules) block from
  `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` into `main/AGENTS.md`
  (fixes Invariant B).
- **Rationale**: #587 names capture's block as canonical; the block is already
  mirrored across capture + habits. main is a user-facing-WhatsApp agent, so the
  block (not the annotation) is required.

## D8 — EA-orchestrator framing = current reality only

- **Decision**: The AGENTS role statement frames main as front-desk /
  EA-orchestrator based on what it does today (direct conversation + delegation
  to specialists); it introduces no speculative mail #165 behavior.
- **Rationale**: Authoring for unlanded features risks rework (cf. the calendar
  #635 RRULE caution). The framing sets up the mail work without pre-committing
  its shape.

## D9 — Identity line de-hardcode

- **Decision**: Replace the model-embedded message-identity line
  (`Sent by main:sonnet`) with a model-agnostic form.
- **Rationale**: The model name goes stale when main's model changes; the
  identity line should identify the agent, not the model. The exact string is a
  small authoring choice confirmed at review (proposed: `Sent by Felix`).
