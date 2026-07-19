# Feature Specification: Author felix-admin-tasker workspace

**Mission**: author-tasker-workspace-01KXXEVB
**Source issue**: #586 (child of epic #167)
**Mission type**: software-dev
**Status**: Draft

## Intent Summary

- **Primary actor**: the maintainer authoring OpenClaw agent workspaces (Kent / Felix operator).
- **Trigger**: `felix-admin-tasker`'s workspace files, while passing all four #587 shared invariants, are cross-contaminated at the content-ownership level and carry stale text — SOUL carries a `## Purpose` role block, a `## Behavioral principles` operating block, and the full enforceable privacy rule (with a changelog parenthetical); USER duplicates the enforceable privacy rule and re-states the agent's role inside `## Context`; TOOLS documents an action-log format that no longer matches the canonical logging helper and carries a behavioral operating rule that AGENTS already owns.
- **Desired outcome**: each workspace content block lives in its #587-canonical owner file; `SOUL.md` is voice-only plus a one-line privacy stance; `USER.md` is a filtered person-view whose scope text is accurate and which carries no enforceable rule; `TOOLS.md` documents the real environment surface with a correct action-log format and no behavioral rules — with **no change to the agent's runtime behavior** (behavior-preserving clean-separation refactor plus one stale-text correction).
- **Invariant that must hold**: `validate_workspace.py` continues to report `felix-admin-tasker` `ok: true` (enforceable privacy rule stays in AGENTS + TOOLS; Output Discipline block stays in AGENTS).
- **Boundary / scope**: behavior-preserving refactor plus one stale-text correction (the TOOLS action-log format). No feature/behavior additions. `AGENTS.md` and `IDENTITY.md` are not edited (AGENTS already owns every concern being removed from SOUL/USER/TOOLS; the known `Sent by felix-admin-tasker:sonnet` vs `<model>` inconsistency inside AGENTS is noted but out of scope — a future fold, not this mission).

## User Scenarios & Testing

### Primary scenario (happy path)

1. The maintainer re-homes tasker's content: SOUL's `## Purpose` role block → already owned by AGENTS (`## Authority`/`## Scope`), so the SOUL copy is removed; SOUL's `## Behavioral principles` block → every item is an operating rule already owned by AGENTS (confirmation-while-Assisted in `## Operating Mode`; infer/clarify thresholds and one-question-at-a-time in the `enrich_task` workflow) or a stance already stated in SOUL `## Voice` (confidence/honesty), so the block is removed; SOUL's full `## Privacy boundary` → reduced to a one-line behavioral stance (enforceable copy already in AGENTS + TOOLS), dropping the policy body and the mission-026/#152 changelog parenthetical.
2. The maintainer corrects USER: the `## Privacy boundary` enforceable rule is removed from `USER.md` (its canonical homes are AGENTS + TOOLS); the `## Context` block's embedded role re-statement ("Your job is to take raw or incomplete task descriptions and structure them…") is trimmed while the genuine Kent-context (solo entrepreneur, task-source landscape) is kept; the `## Communication preferences` "Concise, direct. No pleasantries or filler" line (a voice rule already in SOUL `## Voice`) is trimmed while the genuine interaction preferences (proposals over open-ended questions, yes/no confirmations, batch when multiple) are kept as USER-owned Kent preferences.
3. The maintainer cleans TOOLS: the `## Action log` description is corrected from the stale `Format: task-intelligence-YYYY-MM-DD.md` to the shape the canonical helper actually writes — `/home/kgale/second-brain/agents/logs/felix-admin-tasker/YYYY-MM-DD.jsonl` (per-agent subdirectory, `.jsonl`, via `log_action.py`); the `## Restrictions` behavioral rule "NEVER create tasks without Kent's confirmation (while at Assisted level)" is removed (owned by AGENTS `## Operating Mode`), while the enforceable privacy path and "NEVER log API tokens or credentials" are retained.
4. `validate_workspace.py` still reports tasker `ok: true`; a content-conservation check confirms nothing substantive was dropped (only re-homed, reduced to a stance whose enforceable copy lives elsewhere, or a deliberate stale-text removal).
5. The change merges to `main` (via the `feat/author-tasker-workspace` → `main` merge); agent-prompt-sync deploys the updated tasker files to office2; repo ↔ office2 md5 parity is verified at the correct destination directory.
6. A live smoke test confirms tasker's task-proposal / structuring behavior and Output Discipline are unchanged.

### Exception / edge cases

- **Invariant regression**: if reducing SOUL's privacy block or removing USER's copy accidentally removes the enforceable rule from its home(s), Invariant A would fail — the validator must still pass, so the enforceable copy in AGENTS + TOOLS must remain intact.
- **Silent content drop**: a moved/removed block whose content survives in neither the source nor the intended destination is a conservation failure — the conservation check must catch it.
- **Scope creep**: `AGENTS.md` and `IDENTITY.md` are not edited. The diff must stay within the NFR-002 file set (tasker SOUL/USER/TOOLS + mission artifacts).
- **Stale-text-correction safety (FR-008)**: correcting the TOOLS action-log format is documentation-only — `log_action.py` already writes to `<log_dir>/<agent>/YYYY-MM-DD.jsonl` regardless of what TOOLS says, so the correction makes the doc match reality and changes no runtime behavior.
- **Behavioral-rule removal safety (FR-003 / FR-009)**: removing the "never create without confirmation" rule from SOUL and TOOLS must not weaken the guarantee — the authoritative copy in AGENTS `## Operating Mode` must remain, so the agent still requires confirmation. Removing all copies would be a regression.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | `SOUL.md` retains only voice content: the `## Voice — write as Kent` section (principles, words/phrases to avoid, words/phrases that are Kent) is kept verbatim. | Draft |
| FR-002 | `SOUL.md` `## Purpose` operational role block is removed. The operational role remains owned by `AGENTS.md` (`## Authority`/`## Scope`); no role text remains in SOUL. | Draft |
| FR-003 | `SOUL.md` `## Behavioral principles` block is removed. Every item is already owned elsewhere: "never create a task without Kent's confirmation while at Assisted level" → AGENTS `## Operating Mode`; "minimize questions / infer what you can, ask what you must" and "one question at a time when clarifying" → AGENTS `enrich_task` Steps 1 & 3 (confidence thresholds; one focused question); "respect Kent's time — batch proposals concise" → AGENTS `retroactive_enrichment` batch shape; "propose confidently … hedge only when genuinely uncertain" → the confidence/honesty stance already in SOUL `## Voice`. No behavioral-principles text remains in SOUL. | Draft |
| FR-004 | `SOUL.md` `## Privacy boundary` is reduced to a one-line behavioral stance (e.g. "I work only where I'm invited"); the enforceable rule text, the filesystem path, and the mission-026/#152 changelog parenthetical are removed from `SOUL.md`. The enforceable copy remains present in `AGENTS.md` and `TOOLS.md`. | Draft |
| FR-005 | `USER.md` `## Privacy boundary` (the duplicated enforceable rule + path + changelog parenthetical) is removed entirely. The enforceable copy remains present in `AGENTS.md` and `TOOLS.md`; `USER.md` carries no enforceable privacy rule. | Draft |
| FR-006 | `USER.md` `## Context` is corrected: the embedded role re-statement ("Your job is to take raw or incomplete task descriptions and structure them into fully enriched Vikunja entries…") is trimmed; the genuine Kent-context (solo entrepreneur managing multiple business/personal initiatives; tasks arrive from Obsidian inbox, direct Vikunja creation, and agent actions) is retained. The `## Identities` block (personal / intentional / metalcasework) is retained unchanged as task-intelligence context. | Draft |
| FR-007 | `USER.md` `## Communication preferences` is de-duplicated against SOUL `## Voice`: the "Concise, direct. No pleasantries or filler" voice rule is trimmed (owned by SOUL Voice); the genuine Kent interaction preferences (prefers proposals over open-ended questions; yes/no confirmations preferred; batch proposals when multiple tasks need structuring) are retained as USER-owned. | Draft |
| FR-008 | `TOOLS.md` `## Action log` is corrected to match the canonical logging helper: the stale `Format: task-intelligence-YYYY-MM-DD.md` line is replaced with the actual shape written by `scripts/openclaw/observation/log_action.py` — a per-agent subdirectory file `/home/kgale/second-brain/agents/logs/felix-admin-tasker/YYYY-MM-DD.jsonl` (JSONL, not a `task-intelligence-*.md` file). The Directive-3 logging-fields requirement is preserved in substance. | Draft |
| FR-009 | `TOOLS.md` `## Restrictions` behavioral rule "NEVER create tasks without Kent's confirmation (while at Assisted level)" is removed (owned by AGENTS `## Operating Mode`). The enforceable privacy path ("NEVER read, write, or reference `…/04-Growth/_private/`") and "NEVER log API tokens or credentials" are retained (both TOOLS-appropriate — the privacy env path is Invariant A's environment home; the token rule is a tool-use constraint). | Draft |
| FR-010 | `AGENTS.md` and `IDENTITY.md` are not edited. Before finalizing, verify by grep that every concern removed from SOUL/USER/TOOLS already exists in `AGENTS.md` (role in `## Authority`/`## Scope`; confirmation-while-Assisted in `## Operating Mode`; enforceable privacy in `## Privacy — absolute rule`). Expected result: no AGENTS edit is required (no-op receiver, per #582). AGENTS does not reference SOUL as a privacy-enforcement home, so no truthfulness correction is warranted. | Draft |
| FR-011 | The updated tasker workspace files deploy to office2 via agent-prompt-sync on merge to `main` (no `deploys/queued/` manifest); repo ↔ office2 md5 parity is verified post-deploy at the confirmed destination directory `/data/services/openclaw/tasker-agent/` (per `service-inventory.json`; agent slug ≠ deploy dir). | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|----|-------------|---------------------|--------|
| NFR-001 | Invariant preservation | A tasker-SCOPED assertion (parse `validate_workspace.py --json`, assert the `felix-admin-tasker` object has `ok: true`) passes. Whole-fleet exit code is NOT used (calendar/#635 fails Invariant B, out of scope). | Draft |
| NFR-002 | Scope discipline | The mission diff touches only tasker `SOUL.md` / `USER.md` / `TOOLS.md` plus mission artifacts — no `AGENTS.md`, no `IDENTITY.md`, no other agent, no unrelated file. | Draft |
| NFR-003 | Content conservation | A row-by-row conservation checklist (derived from the data-model move-table) passes: every "keep"/"move" block is present in its destination; the enforceable privacy token is present in BOTH `AGENTS.md` and `TOOLS.md` AND absent from `SOUL.md` AND absent from `USER.md`; the confirmation-while-Assisted rule is present in `AGENTS.md` AND absent from `SOUL.md` AND absent from `TOOLS.md`; the role statement is present in `AGENTS.md` AND absent from `SOUL.md` AND absent from `USER.md`; **the TOOLS `## Action log` block still enumerates the Directive-3 required fields (agent name, action type, target, outcome, timestamp, autonomy level) after the FR-008 format correction — the correction changes only the filename/path shape, not the required-fields substance** (post-plan review, Codex MEDIUM / renata #2); every "delete" is a deliberate stale-text removal. | Draft |
| NFR-004 | Behavior preservation | Two-part: **(a) scope-creep guard** — `AGENTS.md` and `IDENTITY.md` are byte-identical before and after (prompt behavior for the executor's workflow, Output Discipline, exec-host rule, and confirmation rule is therefore unchanged); **(b) prompt-behavior guard** — the post-deploy live smoke is the actual prompt-mediated behavior check (a task proposal / structuring turn with clean Output Discipline: identity line first, no inter-tool narration, no preamble). | Draft |
| NFR-005 | Deploy parity | Every deployed tasker file's md5 on office2 matches the repo copy at the merged commit. | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Written against the #587 authoring standard (`docs/design/openclaw-workspace-authoring-standard.md`, on main). Mission branches from current `main` so the standard + validator are in-lane (avoids the #584 mid-mission dependency-merge trap). | Active |
| C-002 | Agent prompt files deploy via agent-prompt-sync on merge-to-main; no `deploys/queued/` manifest is authored (the #636 boundary). | Active |
| C-003 | Rebaseline is expected "not required" — agent prompt files are not hashed by `audit.sh` (#621 gap). The merge commit records the rebaseline decision. **Note (post-plan review, Codex LOW):** the `openclaw-agent-prompts` entry in `audited-surfaces.json` lists file patterns `AGENTS.md`/`SOUL.md`/`IDENTITY.md`/`USER.md`/`GOVERNANCE.md` but omits `TOOLS.md`, even though agent-prompt-sync deploys `TOOLS.md` and this mission edits it. This does not change the posture (the surface is `rebaseline_required: false` regardless, and `TOOLS.md` touches no security-monitor baseline), but the pattern omission is pre-existing drift — tracked as follow-up **#808**, NOT fixed in this mission (NFR-002 scopes the diff to tasker SOUL/USER/TOOLS). | Active |
| C-004 | Behavior-preserving refactor + one narrow stale-text correction (FR-008 action-log format) only — NO feature/behavior additions. The `Sent by felix-admin-tasker:sonnet` (AGENTS line ~25) vs `<model>` placeholder (AGENTS Hard-rule #2) inconsistency is noted but NOT fixed here (it lives in AGENTS, out of the SOUL/USER/TOOLS scope; a future fold, cf. the #583 main de-hardcoding). | Active |
| C-005 | The `_private` privacy path is already canonical across tasker's files (validator `privacy_path_canonical: ok`); the retained copies (AGENTS, TOOLS) are left byte-unchanged. | Active |
| C-006 | Post-merge acceptance criteria (deploy parity, live smoke) are operator-owned and documented in the mission quickstart — they are excluded from the acceptance matrix (the gate rejects post-merge "pending" rows). | Active |
| C-007 | tasker is a per-dispatch sub-agent (primary path is delegation from felix-admin-capture), not the main WhatsApp DM lane — no session rotation or `openclaw gateway restart` is required at deploy (unlike the #583 main SOP). | Active |
| C-008 | Single-branch topology (mission created without `--pr-bound` off a pre-cut `feat/author-tasker-workspace` branch; `coordination_branch: null`, `topology: single_branch`) to avoid the #2533 coordination-split fault; the feature branch merges to `main` at the end. | Active |

## Success Criteria

1. All three edited workspace files (SOUL/USER/TOOLS) are re-homed to #587 ownership; SOUL is voice + one-line privacy stance only; USER carries no enforceable rule and its scope text is accurate; TOOLS carries a correct action-log format and no behavioral operating rule.
2. `validate_workspace.py` reports tasker `ok: true` (all four invariants pass).
3. A content-conservation check confirms no substantive instruction was silently dropped (enforceable privacy survives in AGENTS + TOOLS; the confirmation rule survives in AGENTS).
4. The change is deployed to office2 via agent-prompt-sync with repo ↔ office2 parity confirmed at `/data/services/openclaw/tasker-agent/`.
5. A live smoke test confirms tasker's task-proposal / structuring behavior and Output Discipline are unchanged.
6. `AGENTS.md` and `IDENTITY.md` are byte-unchanged (NFR-002 / NFR-004a).

## Key Entities

- **felix-admin-tasker workspace** — the five OpenClaw bootstrap files at `scripts/openclaw/agents/felix-admin-tasker/` (SOUL / USER / TOOLS / IDENTITY / AGENTS.md). SOUL, USER, TOOLS are edited; IDENTITY and AGENTS are not.
- **#587 ownership model** — the concern→file mapping: SOUL = voice/stance; USER = filtered person-view; TOOLS = environment/setup; AGENTS = operating rules/role; IDENTITY = identity card.
- **log_action.py** — the deterministic Directive-3 logging helper (`scripts/openclaw/observation/log_action.py` + `config.py`) that writes `<DEFAULT_AGENT_LOGS_DIR>/<agent_name>/YYYY-MM-DD.jsonl` (`DEFAULT_AGENT_LOGS_DIR = /home/kgale/second-brain/agents/logs`, #656). It is the authority the TOOLS action-log description must match — the reason the current `task-intelligence-*.md` format line is stale (FR-008).
- **agent-prompt-sync** — the office2 pull pipeline (`scripts/openclaw/deploy/deploy_agent_prompts.py`, #567/#136/#636) that deploys agent prompt files on merge-to-main.

## Assumptions

- The agent-prompt-sync timer is live on office2 and will deploy the tasker files on the next tick after merge (no manifest required).
- tasker currently passes all four #587 invariants (verified at design time via `validate_workspace.py` — `privacy_boundary`, `privacy_path_canonical`, `output_discipline`, `runtime_env_assumptions` all `ok`).
- `AGENTS.md` already owns every concern removed from SOUL/USER/TOOLS (role in `## Authority`/`## Scope`; confirmation-while-Assisted in `## Operating Mode`; enforceable privacy in `## Privacy — absolute rule`) — confirmed by reading AGENTS at design time; FR-010 re-verifies by grep, so AGENTS is expected to remain byte-unchanged.
- tasker's TOOLS resolves Vikunja projects/labels by name at runtime (per AGENTS "resolve … project ID by name — never hardcode") and inlines no volatile Vikunja IDs — so, unlike #582 habits, there is no ID de-inlining work in this mission.
- "ADD (managed)" in USER notes is retained as a neutral person-fact (the #583 main precedent). tasker's SOUL Voice already attributes the "structured and chunked" style to Kent's ADD; per Kent's locked decision the whole `## Behavioral principles` block is removed but the Voice section (including its style rules) is kept verbatim.
- The action-log format correction (FR-008) is documentation-only and behavior-preserving: `log_action.py` writes the JSONL shape regardless of the TOOLS text.
