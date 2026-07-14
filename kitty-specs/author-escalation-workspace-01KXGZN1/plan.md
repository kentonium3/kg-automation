# Implementation Plan: Author felix-admin-escalation workspace

**Branch**: `feat/author-escalation-workspace` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/author-escalation-workspace-01KXGZN1/spec.md`

## Summary

Re-home the `felix-admin-escalation` OpenClaw workspace content to its #587-canonical owner files (SOUL = voice/stance only; USER = filtered person-view; TOOLS = environment/setup; AGENTS = operating rules/role — unchanged) and absorb the #724 Goals(11) cleanup, with **no runtime-behavior change**. Both #587 invariants already pass and must stay passing. Approach: hand-authored markdown edits to three workspace files plus one dormant Python setup script, verified by the existing `validate_workspace.py` and a content-conservation grep/diff, then deployed to office2 via agent-prompt-sync on merge-to-main and smoke-tested.

## Technical Context

**Language/Version**: Markdown (agent prompt files) + Python 3.12 (the dormant `setup_vikunja.py` edit; office2 is python3-only)
**Primary Dependencies**: `scripts/openclaw/agents/validate_workspace.py` (the #587 invariant checker, reused as-is); agent-prompt-sync (`deploy_agent_prompts.py`, #567/#136/#636)
**Storage**: N/A (no data model; the "state" is file content in the agent workspace directory)
**Testing**: `python3 -m scripts.openclaw.agents.validate_workspace --json` (both escalation invariants must report `ok: true`); the openclaw agent test suite (`pytest scripts/openclaw/agents/tests tests/openclaw`); a content-conservation grep/diff of moved blocks; post-deploy repo↔office2 md5 parity + live smoke
**Target Platform**: office2 (Ubuntu 24.04, agents run as the `claude` user); deploy dest `/data/services/openclaw/data/` (per #583 — the agent-prompt-sync destination)
**Project Type**: single (repo-resident agent prompt authoring)
**Performance Goals**: N/A (authoring; no runtime perf surface)
**Constraints**: pure refactor — zero behavior change; diff scoped to escalation SOUL/USER/TOOLS.md + `scripts/vikunja/setup_vikunja.py` (+ mission artifacts); no `deploys/queued/` manifest; rebaseline expected "not required" (#621)
**Scale/Scope**: 3 workspace files edited (SOUL/USER/TOOLS), 2 files unchanged (AGENTS/IDENTITY), 1 dormant script edited; single agent (`felix-admin-escalation`)

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_001 (Architectural Integrity / separation of concerns)**: ✅ directly served — this mission *is* a separation-of-concerns refactor moving each content block to its canonical owner file per the #587 ownership model.
- **DIRECTIVE_003 (Decision Documentation)**: ✅ the scope decisions (pure refactor; AGENTS size left; `_private` path deferred to #732) are recorded in spec Constraints and this plan.
- **DIRECTIVE_010 (Specification Fidelity)**: ✅ implementation maps 1:1 to FR-001…FR-009; any deviation gets documented.
- **Engineering Principles (helper/library/skill, active-surface hygiene, migration-no-vestiges)**: ✅ no new helper is introduced (existing validator reused); the refactor removes vestigial content (Goals(11), duplicated privacy rule in SOUL) rather than adding parity layers — consistent with the migration-no-vestiges principle.
- **Change-risk tier**: Tier 3 (agent prompt logic/workflow) — no pre-flight checklist; dry-run validation via the validator. Rebaseline: expected "not required" (agent prompts not hashed by `audit.sh`, #621).

**Result**: No violations. No entries in Complexity Tracking.

## Project Structure

### Documentation (this mission)

```
kitty-specs/author-escalation-workspace-01KXGZN1/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (content-conservation model)
├── quickstart.md        # Phase 1 output (author → validate → merge → deploy → smoke runbook)
├── checklists/          # spec quality checklist
└── tasks/               # WP files (created by /spec-kitty.tasks — NOT here)
```

No `contracts/` directory: this is a content-authoring mission with **no API surface**. A `contracts/README.md` noting that will be added at tasks/accept time (the accept gate expects the directory to exist — #584 precedent).

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-escalation/
├── SOUL.md      # EDITED — voice/stance only (trim role, privacy→stance, ADD-justification)
├── USER.md      # EDITED — filtered person-view (remove Date handling)
├── TOOLS.md     # EDITED — receive Date handling; remove Goals(11) from filter + table
├── AGENTS.md    # UNCHANGED — already owns role/authority + both invariants
└── IDENTITY.md  # UNCHANGED — already authored

scripts/vikunja/
└── setup_vikunja.py   # EDITED — remove dormant "Goals" saved-filter block (project = 11)

scripts/openclaw/agents/
└── validate_workspace.py  # REUSED (not edited) — invariant checker
```

**Structure Decision**: single-project repo-resident authoring; the only edited surfaces are the three escalation workspace markdown files and the one dormant Python script. The validator is reused, not modified.

## Complexity Tracking

*No Charter Check violations — table intentionally empty.*

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` decides WP decomposition.

### IC-01 — Re-home escalation workspace content to #587 owners

- **Purpose**: Move each content block to its canonical file so SOUL is voice/stance-only, USER is a filtered person-view, and TOOLS holds operational date-handling — without dropping any substantive instruction or breaking either invariant.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-008; NFR-001, NFR-003
- **Affected surfaces**: `scripts/openclaw/agents/felix-admin-escalation/{SOUL,USER,TOOLS}.md`
- **Sequencing/depends-on**: none (self-contained single-agent authoring)
- **Risks**: (1) reducing SOUL's privacy block must NOT remove the enforceable rule from its AGENTS/TOOLS home (Invariant A regression); (2) the date-handling block must land in TOOLS verbatim-in-substance (conservation); (3) staying within scope — do not touch AGENTS.md content, IDENTITY.md, the `_private` path, or other agents.

### IC-02 — Absorb #724 Goals(11) cleanup

- **Purpose**: Remove residual references to the deleted Goals Vikunja project (11) from escalation's TOOLS.md query + exclusion table and from the dormant `setup_vikunja.py` saved-filter definitions.
- **Relevant requirements**: FR-006, FR-007
- **Affected surfaces**: `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md`, `scripts/vikunja/setup_vikunja.py`
- **Sequencing/depends-on**: IC-01 (TOOLS.md is edited by both; same file/WP is fine)
- **Risks**: the `project_id NOT IN (11, 13)` → `NOT IN (13)` change must keep the Habits(13) exclusion intact; the dormant-script edit must not disturb its other saved-filter definitions.

### IC-03 — Validate, deploy, and smoke-test

- **Purpose**: Prove both invariants still pass, no content was dropped, and the deployed agent behaves unchanged.
- **Relevant requirements**: FR-009; NFR-001, NFR-002, NFR-004, NFR-005
- **Affected surfaces**: no repo files beyond the mission's edits; verification/runbook only (post-merge, operator-owned — documented in quickstart.md, not the acceptance matrix per C-006).
- **Sequencing/depends-on**: IC-01, IC-02
- **Risks**: session-rotation at deploy can wedge the live WhatsApp DM lane → must pair with `openclaw gateway restart` (C-007, #583 SOP). agent-prompt-sync deploys on merge-to-main; verify md5 parity + smoke before closing.

## Branch Contract (restated)

- Current branch at plan start: `feat/author-escalation-workspace`
- Planning/base branch: `feat/author-escalation-workspace`
- Final merge target for completed changes: `feat/author-escalation-workspace` (mission WPs), then a separate `feat/author-escalation-workspace → main` merge is the office2 deploy trigger.
- `branch_matches_target`: true (single_branch topology; no coordination branch).
