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

## D7 — Output Discipline: ADAPT capture's block, do not literal-mirror (post-plan Codex F3)

- **Decision**: Author a lean, main-specific Output Discipline block under the
  `## Output discipline` heading (the validator marker) following the fleet
  3-Hard-Rules shape (as installed on habits/escalation/tasker), reconciled with
  main's `HEARTBEAT_OK` no-op behavior. Do **not** copy capture's block verbatim.
- **Rationale**: Codex correctly flagged that capture's block is inbox-cron /
  `[felix-admin-capture]: IDLE` specific — literal-mirroring would import
  nonsensical inbox semantics and "main relays your output" language into main,
  conflicting with main's direct-conversation + `HEARTBEAT_OK` role. The
  validator (`OUTPUT_DISCIPLINE_TOKEN = "output discipline"`) only requires the
  marker + a real block, so a concise adapted block passes and saves bytes (see
  D10). main is user-facing WhatsApp, so the block (not the annotation) is required.
- **Alternatives considered**: literal mirror — rejected (behavior-risky, F3).

## D8 — EA-orchestrator framing = current reality only

- **Decision**: The AGENTS role statement frames main as front-desk /
  EA-orchestrator based on what it does today (direct conversation + delegation
  to specialists); it introduces no speculative mail #165 behavior.
- **Rationale**: Authoring for unlanded features risks rework (cf. the calendar
  #635 RRULE caution). The framing sets up the mail work without pre-committing
  its shape.

## D9 — Identity line de-hardcode: **DROPPED** (operator decision 2026-07-13)

- **Decision**: Do **not** de-hardcode the message-identity line. `Sent by main:sonnet`
  is left unchanged; the message-identity section is authored as-is. FR-008 removed
  from scope; folded improvements are now two (EA-orchestrator framing + delegation
  reliability).
- **Why dropped**: Codex F8 established that the whole fleet uses
  `Sent by <agent-id>:<model>` and the Output Discipline Hard Rule #2 references
  that exact format — so `Sent by Felix` was out, and the only safe form was
  `Sent by main:<model>` (drop the stale model token, keep the shape). But that is
  a *fleet-wide* convention; changing it on `main` alone creates inconsistency for
  marginal value (avoiding a stale model name). Kent's call: drop it here; a
  fleet-wide de-hardcode can be considered separately if it ever matters.

## D10 — AGENTS↔TOOLS byte-budget rebalance (post-plan Codex F4)

- **Decision**: Keep `main/AGENTS.md` under the hard 12,000-byte cap by moving the
  enforceable privacy rule and all delegation/timelog/issue-filing **mechanics**
  to `TOOLS.md`, keeping only **rules** + a lean Output Discipline block in
  AGENTS, and dropping the `## Make It Yours` filler.
- **Rationale**: Codex F4 (verified) — `test_agents_md_size.py` enforces
  `size < 12000`; main is at 11,592 B (~408 B headroom) and the mission adds a
  role statement, Output Discipline block, and escalation/tasker routing. Invariant
  A accepts the privacy rule in TOOLS; Invariant B only needs the marker in AGENTS.
  So mechanics→TOOLS + privacy→TOOLS buys the room while satisfying both invariants.
- **Alternatives**: cram everything into AGENTS + compress prose only — rejected
  (insufficient; risks dropping load-bearing rules to save bytes).

## D11 — Validator acceptance is main-scoped (post-plan Codex F6)

- **Decision**: Acceptance reads the `main` object's `ok: true` from the validator
  JSON, not the process exit code.
- **Rationale**: `validate_workspace` validates all active workspaces and the
  process is currently RED because `felix-admin-calendar` also fails
  `output_discipline` — that belongs to the #635 mission, out of scope here. A
  process-exit gate would wrongly block on an unrelated failure.

## D12 — Rotate the live main session before smoke (post-plan Codex F5)

- **Decision**: After deploy (and after any rollback), run
  `scripts/openclaw/helpers/rotate_main_session.py` before the smoke test.
- **Rationale**: Codex F5 (verified helper exists) — prompt-sync copies the files
  but an active `main` session caches its prompt at session-init (known
  systemPromptReport staleness), so smoke would test the old prompt. Rotation
  forces a fresh session that loads the new prompt.
