# Implementation Plan: Author felix-admin-tasker workspace

**Branch**: `feat/author-tasker-workspace` | **Date**: 2026-07-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/author-tasker-workspace-01KXXEVB/spec.md`

## Summary

Behavior-preserving authoring refactor of the `felix-admin-tasker` OpenClaw workspace to the #587 standard. Content is re-homed to its canonical owner file (SOUL → voice-only + one-line privacy stance; USER → filtered person-view with the duplicated enforceable privacy rule removed and scope text corrected; TOOLS → corrected action-log format + behavioral rule removed), keeping the agent's runtime behavior unchanged (it already passes `validate_workspace.py` and must stay green). `AGENTS.md` and `IDENTITY.md` are not edited — AGENTS already owns every concern being removed. Technical approach mirrors the #584 (capture), #585 (escalation), and #582 (habits) authoring missions: markdown edits validated by the reused `validate_workspace.py` (tasker-scoped `ok:true`), a content-conservation check, a byte-identical AGENTS/IDENTITY scope guard for behavior preservation, then agent-prompt-sync deploy on merge-to-main + md5 parity + a live smoke.

## Technical Context

**Language/Version**: Markdown (OpenClaw workspace prompt files); Python 3.12 for the reused validator and any conservation checks
**Primary Dependencies**: `scripts/openclaw/agents/validate_workspace.py` (#587, reused as-is); agent-prompt-sync (`scripts/openclaw/deploy/deploy_agent_prompts.py`, #567/#136/#636); `scripts/openclaw/observation/log_action.py` + `config.py` (the authority the TOOLS action-log format must match, FR-008); bash for smoke
**Storage**: N/A (no schema/state change); Vikunja projects/labels resolved by name at runtime
**Testing**: tasker-scoped `validate_workspace.py --json` assertion (`felix-admin-tasker` → `ok:true`); row-by-row content-conservation checklist (data-model.md); behavior preservation = (a) `AGENTS.md`/`IDENTITY.md` byte-identical before/after as the scope guard + (b) live smoke as the real prompt-behavior gate
**Target Platform**: office2 (Ubuntu 24.04); tasker agent runs as a per-dispatch OpenClaw sub-agent (delegation from felix-admin-capture)
**Project Type**: single (agent workspace authoring — no new source structure)
**Performance Goals**: N/A (content refactor; zero behavior change is the goal)
**Constraints**: no behavior change to the live task-proposal / structuring / enrichment workflows; four #587 invariants stay green; no `deploys/queued/` manifest (agent prompts deploy via agent-prompt-sync); rebaseline "not required" (#621); AGENTS.md (~17KB) untouched (no hard cap on a sub-agent)
**Scale/Scope**: 3 edited files (SOUL/USER/TOOLS); AGENTS and IDENTITY not touched; 1 agent; no other files except mission artifacts

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter present (compact). Relevant directives and how this plan satisfies them:

- **DIRECTIVE_001 (Architectural Integrity / separation of concerns)** — this mission *is* a separation-of-concerns cleanup; each content block moves to its #587-canonical owner file. ✅ Advances, does not violate.
- **DIRECTIVE_024 (Locality of Change)** — the diff is scoped to one agent's three files (NFR-002); blast radius minimized (AGENTS/IDENTITY untouched). ✅
- **DIRECTIVE_031 (Context-Aware Design)** — content is placed per the #587 concern→file ownership (the ubiquitous language of the workspace model). ✅
- **DIRECTIVE_003 (Decision Documentation)** — the move-table (data-model.md) and research.md record why each block moves. ✅
- **DIRECTIVE_010 (Specification Fidelity)** — behavior preservation (NFR-004) + content conservation (NFR-003) keep implementation faithful to the "no behavior change" spec. ✅

No charter violations. Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/author-tasker-workspace-01KXXEVB/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — the content move-table + conservation model
├── quickstart.md        # Phase 1 output — author→validate→merge→verify-sync→smoke→rollback
├── contracts/           # Phase 1 output — README only (no API surface)
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-tasker/
├── SOUL.md       # EDITED — reduce to voice + one-line privacy stance (drop Purpose, Behavioral principles, full Privacy)
├── USER.md       # EDITED — filtered person-view; remove duplicated Privacy rule; trim role re-statement; de-dup comms line
├── TOOLS.md      # EDITED — correct action-log format (FR-008); remove behavioral confirmation rule; keep privacy path + token rule
├── AGENTS.md     # NOT edited (already owns role, confirmation rule, enforceable privacy; no SOUL-as-privacy-home reference)
└── IDENTITY.md   # NOT edited

scripts/openclaw/agents/validate_workspace.py         # REUSED as-is (the #587 invariant gate)
scripts/openclaw/observation/log_action.py, config.py # READ-ONLY reference (proves the FR-008 action-log drift)
```

**Structure Decision**: No new source structure. This is markdown authoring within one existing agent directory plus reuse of the existing validator. Unlike #582 habits (which corrected a repo-wide `service-inventory.md` weekly-report drift), tasker has no analogous cross-doc drift in scope — the one stale-text fix (action-log format) lives inside the target `TOOLS.md`. The authoritative surface is `scripts/openclaw/agents/felix-admin-tasker/`.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Concerns are NOT work packages. `/spec-kitty.tasks` translates these into WPs; they may collapse to one WP (the #584/#585/#582 precedent, since post-merge acceptance cannot be a `kitty-specs`-owning WP).

### IC-01 — Author and validate the tasker workspace

- **Purpose**: Re-home content to #587 ownership and prove the set is coherent, invariant-green, and behavior-preserving; correct the stale TOOLS action-log format (FR-008).
- **Relevant requirements**: FR-001…FR-010, NFR-001, NFR-002, NFR-003, NFR-004
- **Affected surfaces**: `scripts/openclaw/agents/felix-admin-tasker/{SOUL,USER,TOOLS}.md`; reuses `validate_workspace.py`; reads `log_action.py`/`config.py` for the FR-008 correct format
- **Sequencing/depends-on**: none (branch already carries #587 from main)
- **Risks**: stripping the enforceable privacy rule from all files (Inv-A regression) — it must survive in AGENTS + TOOLS after SOUL is reduced to a stance and USER's copy is removed; dropping the confirmation-while-Assisted rule from all files (it must survive in AGENTS after SOUL's Behavioral principles and TOOLS' Restriction line are removed); accidentally editing AGENTS/IDENTITY (NFR-002/NFR-004a require them byte-identical); getting the FR-008 corrected format wrong (must match `log_action.py`'s actual `<log_dir>/<agent>/YYYY-MM-DD.jsonl` output).

### IC-02 — Deploy, parity, and smoke (operator-owned, post-merge)

- **Purpose**: Deploy via agent-prompt-sync on merge-to-main and confirm parity + unchanged behavior on office2.
- **Relevant requirements**: FR-011, NFR-005
- **Affected surfaces**: office2 `/data/services/openclaw/tasker-agent/` (deploy dir — slug ≠ dir, confirmed via service-inventory.json; re-verify via `find` at deploy); agent-prompt-sync audit log
- **Sequencing/depends-on**: IC-01 merged to main
- **Risks**: deploy-dir misidentification (verify via `find` before parity, per the office2 deploy-paths runbook); these steps are operator-owned and documented in quickstart.md — they are NOT a `kitty-specs`-owning WP (the #584 lesson) and are excluded from the acceptance matrix (C-006).
