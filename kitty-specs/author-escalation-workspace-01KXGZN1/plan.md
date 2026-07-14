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
**Target Platform**: office2 (Ubuntu 24.04, agents run as the `claude` user); agent-prompt-sync deploy dest is `/data/services/openclaw/escalation-agent/` (NOT `data/felix-admin-escalation/` — corrected per Codex HIGH-3; slug≠deploy-dir). SKILL.md is NOT agent-prompt-sync'd and syncs by a separate path.
**Project Type**: single (repo-resident agent prompt authoring)
**Performance Goals**: N/A (authoring; no runtime perf surface)
**Constraints**: refactor + internal-coherence fixes (no feature/behavior additions); diff scoped to the NFR-002 file set; no `deploys/queued/` manifest; rebaseline expected "not required" (#621)
**Scale/Scope**: 4 escalation workspace files edited (SOUL/USER/TOOLS + AGENTS narrowly), IDENTITY unchanged; plus SKILL.md, escalation-ops.md, setup_vikunja.py, test_enumerate_candidates.py; single agent (`felix-admin-escalation`)

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

`contracts/` holds `post-plan-review-resolutions.md` (the Codex findings + dispositions; also satisfies the accept-gate `contracts/` requirement). No API surface.

### Source Code (repository root) — expanded per post-plan Codex

```
scripts/openclaw/agents/felix-admin-escalation/
├── SOUL.md      # EDITED — voice/stance only (trim role, privacy→stance, ADD-justification)
├── USER.md      # EDITED — filtered person-view (remove Date handling)
├── TOOLS.md     # EDITED — receive Date handling; remove Goals(11); fix Z→ET-offset (FR-010)
├── AGENTS.md    # EDITED (NARROW) — Z→ET-offset (FR-010) + enforcement-sentence fix (FR-012); nothing else
└── IDENTITY.md  # UNCHANGED

scripts/openclaw/skills/escalation/SKILL.md   # EDITED — remove Goals(11) candidate-model refs (FR-011)
docs/runbooks/escalation-ops.md               # EDITED — remove Goals(11) prose (FR-011)
scripts/vikunja/setup_vikunja.py              # EDITED — remove dormant "Goals" saved-filter block (FR-007)
tests/escalation/test_enumerate_candidates.py # EDITED — de-Goals(11) the generic exclusion test (FR-011)

scripts/openclaw/agents/validate_workspace.py # REUSED (not edited) — invariant checker (escalation-scoped assertion)
```

**Structure Decision**: single-project repo-resident authoring. Edited surfaces = the four escalation workspace markdown files (AGENTS narrowly), the escalation SKILL.md, the escalation-ops runbook, the dormant setup script, and one unit test. The validator is reused, not modified.

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

### IC-02 — Fully absorb #724 (all Goals(11) surfaces) + date-format coherence

- **Purpose**: Remove EVERY residual reference to the deleted Goals project (11) — TOOLS.md query + table, dormant `setup_vikunja.py`, escalation SKILL.md candidate-model, escalation-ops.md runbook, and the exclusion unit test — and fix the reschedule Z-examples (TOOLS + AGENTS) to the ET-offset form so the moved no-Z rule is coherent (Codex HIGH-1/HIGH-2/LOW-9).
- **Relevant requirements**: FR-006, FR-007, FR-010, FR-011
- **Affected surfaces**: escalation `TOOLS.md` + `AGENTS.md` (narrow), `scripts/openclaw/skills/escalation/SKILL.md`, `docs/runbooks/escalation-ops.md`, `scripts/vikunja/setup_vikunja.py`, `tests/escalation/test_enumerate_candidates.py`
- **Sequencing/depends-on**: IC-01 (TOOLS.md/AGENTS.md edited by both — same WP is fine)
- **Risks**: keep Habits(13) exclusion intact; keep the exclusion test's mechanism assertion meaningful after switching off id 11; SKILL.md is NOT agent-prompt-sync'd (separate deploy — verify at §7a); the Z→offset fix is behavior-adjacent (a correctness fix) — verify via the FR-010/NFR-004 checks.

### IC-02b — AGENTS truthfulness fix

- **Purpose**: After SOUL is reduced to a stance, correct the AGENTS privacy-enforcement sentence so it no longer claims SOUL enforces the rule (Codex MED-5).
- **Relevant requirements**: FR-012, FR-008
- **Affected surfaces**: escalation `AGENTS.md` (one sentence)
- **Sequencing/depends-on**: IC-01 (must reflect the reduced SOUL)
- **Risks**: keep the edit to the single sentence; do not perturb the Output Discipline block (Invariant B) or any other AGENTS content.

### IC-03 — Validate, deploy, and smoke-test

- **Purpose**: Prove both invariants still pass, no content was dropped, and the deployed agent behaves unchanged.
- **Relevant requirements**: FR-009; NFR-001, NFR-002, NFR-004, NFR-005
- **Affected surfaces**: no repo files beyond the mission's edits; verification/runbook only (post-merge, operator-owned — documented in quickstart.md, not the acceptance matrix per C-006).
- **Sequencing/depends-on**: IC-01, IC-02, IC-02b
- **Risks**: use the escalation-SCOPED validator assertion (whole-fleet exits 1 on calendar/#635 — Codex HIGH-4); verify parity at the CORRECT dest `/data/services/openclaw/escalation-agent/` (Codex HIGH-3); SKILL.md needs a separate sync (§7a); behavior evidence is the deterministic `enumerate_candidates` before/after (Codex MED-8) plus live smoke; session-rotation must pair with `openclaw gateway restart` (C-007, #583 SOP).

## Branch Contract (restated)

- Current branch at plan start: `feat/author-escalation-workspace`
- Planning/base branch: `feat/author-escalation-workspace`
- Final merge target for completed changes: `feat/author-escalation-workspace` (mission WPs), then a separate `feat/author-escalation-workspace → main` merge is the office2 deploy trigger.
- `branch_matches_target`: true (single_branch topology; no coordination branch).
