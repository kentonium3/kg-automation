# Implementation Plan: Author felix-admin-habits workspace

**Branch**: `feat/author-habits-workspace` | **Date**: 2026-07-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/author-habits-workspace-01KXX9JZ/spec.md`

## Summary

Behavior-preserving authoring refactor of the `felix-admin-habits` OpenClaw workspace to the #587 standard. Content is re-homed to its canonical owner file (SOUL → voice+stance only; USER → filtered person-view with corrected scope; TOOLS → de-inlined volatile IDs + received date-handling); the stale "reports on patterns" claim is corrected; #409's weekly-report conflict is confirmed incorporated (single authoritative statement in AGENTS). Technical approach mirrors the #584 (capture) and #585 (escalation) authoring missions: markdown edits validated by the reused `validate_workspace.py` (habits-scoped `ok:true`), a content-conservation check, before/after morning-list-helper output for behavior preservation, then agent-prompt-sync deploy on merge-to-main + md5 parity + a live smoke.

## Technical Context

**Language/Version**: Markdown (OpenClaw workspace prompt files); Python 3.12 for the reused validator and any conservation checks
**Primary Dependencies**: `scripts/openclaw/agents/validate_workspace.py` (#587, reused as-is); agent-prompt-sync (`scripts/openclaw/deploy_agent_prompts.py`, #567/#136/#636); bash for smoke
**Storage**: N/A (no schema/state change); Vikunja Habits project resolved by name at runtime
**Testing**: habits-scoped `validate_workspace.py --json` assertion (`felix-admin-habits` → `ok:true`); row-by-row content-conservation checklist (data-model.md); behavior preservation = (a) morning-list helper before/after diff as a *no-helper/config-change* scope guard + (b) static-diff of the AGENTS tick/reply workflow commands/relay-verbatim/Output-Discipline/completion/habit-management rules + live smoke as the real prompt-behavior gate (post-plan Finding 2); FR-012 doc-sync of the `service-inventory.md` weekly-report rows to the JSON
**Target Platform**: office2 (Ubuntu 24.04); habits agent runs as a per-dispatch OpenClaw sub-agent
**Project Type**: single (agent workspace authoring — no new source structure)
**Performance Goals**: N/A (content refactor; zero behavior change is the goal)
**Constraints**: no behavior change to the live daily check-in / completion-marking workflows; four #587 invariants stay green; no `deploys/queued/` manifest (agent prompts deploy via agent-prompt-sync); rebaseline "not required" (#621); AGENTS.md ~15KB stays (no hard cap on a sub-agent)
**Scale/Scope**: 3 edited files (SOUL/USER/TOOLS) + AGENTS narrowly-only-if-warranted; 1 agent; no other files except mission artifacts

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter present (compact). Relevant directives and how this plan satisfies them:

- **DIRECTIVE_001 (Architectural Integrity / separation of concerns)** — this mission *is* a separation-of-concerns cleanup; each content block moves to its #587-canonical owner file. ✅ Advances, does not violate.
- **DIRECTIVE_024 (Locality of Change)** — the diff is scoped to one agent's workspace (NFR-002); blast radius minimized. ✅
- **DIRECTIVE_031 (Context-Aware Design)** — content is placed per the #587 concern→file ownership (the ubiquitous language of the workspace model). ✅
- **DIRECTIVE_003 (Decision Documentation)** — the move-table (data-model.md) and research.md record why each block moves. ✅
- **DIRECTIVE_010 (Specification Fidelity)** — behavior preservation (NFR-004) + content conservation (NFR-003) keep implementation faithful to the "no behavior change" spec. ✅

No charter violations. Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/author-habits-workspace-01KXX9JZ/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — the content move-table + conservation model
├── quickstart.md        # Phase 1 output — author→validate→merge→verify-sync→smoke→rollback
├── contracts/           # Phase 1 output — README only (no API surface)
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-habits/
├── SOUL.md       # EDITED — reduce to voice + one-line privacy stance
├── USER.md       # EDITED — filtered person-view; remove date-handling; correct scope claim
├── TOOLS.md      # EDITED — de-inline volatile IDs; receive date-handling; keep completion-comment contract
├── AGENTS.md     # EDITED ONLY IF it references SOUL as a privacy-enforcement home (narrow truthfulness fix)
└── IDENTITY.md   # NOT edited

scripts/openclaw/agents/validate_workspace.py   # REUSED as-is (the #587 invariant gate)

docs/design/architecture/service-inventory.md   # EDITED (FR-012) — weekly-report rows only, to match service-inventory.json
```

**Structure Decision**: No new source structure. This is markdown authoring within one existing agent directory, reuse of the existing validator, plus a bounded weekly-report-row correction to `service-inventory.md` (FR-012, post-plan Finding 4). The authoritative surface is `scripts/openclaw/agents/felix-admin-habits/`.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Concerns are NOT work packages. `/spec-kitty.tasks` translates these into WPs; they may collapse to one WP (the #584/#585 precedent, since post-merge acceptance cannot be a `kitty-specs`-owning WP).

### IC-01 — Author and validate the habits workspace

- **Purpose**: Re-home content to #587 ownership and prove the set is coherent, invariant-green, and behavior-preserving; fix the repo-wide weekly-report doc drift (FR-012).
- **Relevant requirements**: FR-001…FR-009, FR-011, FR-012, NFR-001, NFR-002, NFR-003, NFR-004
- **Affected surfaces**: `scripts/openclaw/agents/felix-admin-habits/{SOUL,USER,TOOLS,AGENTS}.md`; `docs/design/architecture/service-inventory.md` (weekly-report rows only, FR-012); reuses `validate_workspace.py`
- **Sequencing/depends-on**: none (branch already carries #587 from main)
- **Risks**: stripping the enforceable privacy rule from all files (Inv-A regression); dropping the weekly-out-of-scope statement from both AGENTS and SOUL; **de-inlining IDs — verified safe: the deterministic helpers resolve project id via `vikunja_refs.json` and the task set via sync-cache/`phase3-schedule.yaml`/morning artifact, NOT from TOOLS (post-plan Finding 1)**; treating the helper-output diff as a prompt-behavior gate when it only guards against helper/config edits (Finding 2 — pair it with a static AGENTS-workflow diff + smoke).

### IC-02 — Deploy, parity, and smoke (operator-owned, post-merge)

- **Purpose**: Deploy via agent-prompt-sync on merge-to-main and confirm parity + unchanged behavior on office2.
- **Relevant requirements**: FR-010, NFR-005
- **Affected surfaces**: office2 `/data/services/openclaw/<habits-deploy-dir>/` (dir confirmed at deploy — slug ≠ dir); agent-prompt-sync audit log
- **Sequencing/depends-on**: IC-01 merged to main
- **Risks**: deploy-dir misidentification (verify via `find` before parity, per the office2 deploy-paths runbook); these steps are operator-owned and documented in quickstart.md — they are NOT a `kitty-specs`-owning WP (the #584 lesson) and are excluded from the acceptance matrix (C-006).
