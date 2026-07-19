# Research: Author felix-admin-tasker workspace

Phase 0 research. This is a behavior-preserving authoring refactor with a fully locked move-table (operator decisions taken before specify). No open NEEDS CLARIFICATION markers. The research below records the decisions and their rationale.

## Decision 1 — Scope posture: refactor + fix in-scope drift (not fold-improvements)

- **Decision**: Behavior-preserving ownership refactor of SOUL/USER/TOOLS to #587, plus one narrow stale-text correction (the TOOLS action-log format). No AGENTS behavior change; no fold-improvements.
- **Rationale**: The operator chose this posture explicitly. tasker already passes all four #587 invariants, so there is no fail to fix — the value is ownership discipline (Principle 2) + correcting a doc that is actively wrong. Fold-improvements (e.g. de-hardcoding the `Sent by felix-admin-tasker:sonnet` line) would touch AGENTS on a live executor and raise blast radius for no correctness gain in this mission.
- **Alternatives considered**: (a) Pure refactor only — rejected because it would knowingly ship the stale action-log format. (b) Refactor + fold-improvements (#583 pattern) — rejected by the operator for blast radius; the `:sonnet` inconsistency is noted for a future fold (C-004).

## Decision 2 — SOUL becomes voice-only (+ one-line stance)

- **Decision**: Remove SOUL's `## Purpose` (role) and the entire `## Behavioral principles` block; keep `## Voice — write as Kent` verbatim; reduce `## Privacy boundary` to a one-line stance.
- **Rationale**: #587 says SOUL owns voice/tone/stance and is explicitly NOT role/purpose or enforceable policy or operating mechanics. Every Behavioral-principles item is already owned by AGENTS (confirmation-while-Assisted in `## Operating Mode`; infer/clarify thresholds + one-question-at-a-time in the `enrich_task` workflow; batch-concise in `retroactive_enrichment`) or is a stance already stated in SOUL `## Voice` ("Confident but honest. Acknowledge uncertainty without apology" covers "propose confidently … hedge only when uncertain"). So removing the block drops no unique instruction. The full privacy policy + the mission-026/#152 changelog parenthetical violate SOUL's "no enforceable policy, no changelog" rule.
- **Alternatives considered**: Keep stance-flavored principles folded into Voice — rejected by the operator (SOUL → voice-only, matching #583/#584/#585/#582).

## Decision 3 — USER: remove duplicated enforceable privacy rule; correct scope text

- **Decision**: Remove `USER.md`'s `## Privacy boundary` (enforceable rule) entirely; trim the embedded role re-statement in `## Context`; de-duplicate the "concise/direct" voice line in `## Communication preferences`. Keep the person block, `## Identities`, the genuine Kent-context, and the genuine interaction preferences.
- **Rationale**: Invariant A's enforceable home is AGENTS (+ optional TOOLS env path); USER carrying it is duplication (a drift hazard the standard bans). The `## Context` role re-statement duplicates AGENTS/SOUL-purpose. The "Concise, direct. No pleasantries" line is a voice rule owned by SOUL `## Voice`. `## Identities` (personal/intentional/metalcasework) is genuine task-intelligence context the tasker needs to assign identity labels — a legitimate Principle-4 filtered view; kept.
- **Alternatives considered**: Keep USER's privacy copy as a "convenience" — rejected: duplication is exactly what #587 Principle 2 prohibits; the validator confirms the enforceable rule is present in AGENTS + TOOLS, so USER's copy is redundant.

## Decision 4 — TOOLS: correct the stale action-log format (FR-008)

- **Decision**: Replace the TOOLS `## Action log` line `Format: task-intelligence-YYYY-MM-DD.md` with the shape the canonical helper actually writes: `/home/kgale/second-brain/agents/logs/felix-admin-tasker/YYYY-MM-DD.jsonl` (per-agent subdirectory, `.jsonl`).
- **Rationale**: Source-verified. `scripts/openclaw/observation/log_action.py::_write_entry` writes `log_dir / agent_name / (YYYY-MM-DD + ".jsonl")`; `config.py` sets `DEFAULT_AGENT_LOGS_DIR = /home/kgale/second-brain/agents/logs` (#656). The current TOOLS text (`task-intelligence-*.md`) describes neither the directory shape nor the extension the helper produces — it is stale documentation. Correcting it is documentation-only and behavior-preserving (the helper writes JSONL regardless of the TOOLS text).
- **Alternatives considered**: Leave it and file a separate debt issue (the pure-refactor option) — rejected by the operator; the fix is inside a target file (TOOLS) and is a one-line correction.

## Decision 5 — TOOLS Restrictions: drop the behavioral confirmation rule

- **Decision**: Remove "NEVER create tasks without Kent's confirmation (while at Assisted level)" from TOOLS `## Restrictions`; keep the enforceable privacy path and "NEVER log API tokens or credentials".
- **Rationale**: The confirmation rule is a behavioral operating rule (#587: behavioral rules belong in SOUL/AGENTS, not TOOLS) already owned by AGENTS `## Operating Mode` ("every task creation requires Kent's explicit confirmation"). The privacy path is Invariant A's environment home (TOOLS-appropriate; validator relies on it). The token rule is a tool-use constraint (TOOLS-appropriate).
- **Alternatives considered**: none material.

## Decision 6 — AGENTS.md and IDENTITY.md are not edited

- **Decision**: Leave both byte-unchanged. FR-010 re-verifies by grep that AGENTS already owns every removed concern.
- **Rationale**: Reading AGENTS at design time confirmed it owns role (`## Authority`/`## Scope`), the confirmation rule (`## Operating Mode`), and enforceable privacy (`## Privacy — absolute rule`), and it does NOT reference SOUL as a privacy-enforcement home — so no truthfulness correction is warranted (unlike #585's FR-012 case). IDENTITY is out of the issue's explicit SOUL/USER/TOOLS scope (the #582 precedent of not touching non-target files). The `Sent by felix-admin-tasker:sonnet` vs `<model>` inconsistency lives in AGENTS and is deferred (C-004).
- **Alternatives considered**: Trim IDENTITY's Agent-card/Scope duplication — rejected by the operator (leave as-is).

## Decision 7 — Deploy & rebaseline posture

- **Decision**: Deploy via agent-prompt-sync on merge-to-main (no `deploys/queued/` manifest); rebaseline "not required".
- **Rationale**: The #636 boundary: agent prompt files deploy via the `scripts/openclaw/deploy/deploy_agent_prompts.py` pull pipeline, not felix-deployer manifests. Rebaseline is not required because `audited-surfaces.json` sets `rebaseline_required: false` for `openclaw-agent-prompts` (the #621 gap: `audit.sh` hashes only `openclaw.json`, not agent prompt files). Deploy dir is `/data/services/openclaw/tasker-agent/` (slug ≠ dir), to be re-verified via `find` at deploy time. tasker is a per-dispatch sub-agent (not the main DM lane), so no gateway restart is needed (C-007).
- **Alternatives considered**: none — this is the established pattern for all #167 authoring children.
