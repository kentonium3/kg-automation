# Implementation Plan: Author main agent workspace

**Branch**: `feat/author-main-workspace` | **Date**: 2026-07-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/author-main-workspace-01KXE90Z/spec.md`

## Summary

Re-author Felix's `main` (front-desk / orchestrator) OpenClaw workspace to the
#587 authoring standard: fix the two failing shared invariants (privacy →
enforceable home; add the Output Discipline block), author the two factory-
template files (`IDENTITY.md`, `TOOLS.md`), clean `SOUL.md` to voice-only
(role → `AGENTS.md`, "why" → `USER.md`), and fold in two approved behavior
improvements (EA-orchestrator role framing; tighter delegation reliability).
Deterministic verification is the existing
#587 validator; deploy is via agent-prompt-sync on merge-to-main (no manifest);
a post-deploy smoke test on office2 confirms no regression on the live agent.

## Technical Context

**Language/Version**: Markdown (OpenClaw agent prompt files) + Python 3.12 (existing validator, reused — no new code)
**Primary Dependencies**: `scripts/openclaw/agents/validate_workspace.py` (from #587); the #587 standard doc `docs/design/openclaw-workspace-authoring-standard.md`; the felix-admin-capture workspace as the Output Discipline canonical source
**Storage**: N/A — prompt files live in the repo at `scripts/openclaw/agents/main/`
**Testing**: `python3 -m scripts.openclaw.agents.validate_workspace --json` (invariant gate — **main-scoped**: read main's `ok:true`, not the process exit, which is independently RED via calendar/#635); `scripts/openclaw/agents/tests/test_agents_md_size.py` (12K cap); the existing `scripts/openclaw/agents/tests/` suite; an evidence-based post-deploy smoke test (after session rotation) documented in `quickstart.md`
**Target Platform**: OpenClaw agent runtime on office2 (Ubuntu 24.04 LTS); deployed copy at `/data/services/openclaw/data/` (main's agent-prompt-sync destination — verified via service-inventory)
**Project Type**: single
**Performance Goals**: N/A (prompt authoring)
**Constraints**: Tier 3 (agent prompts); deploy via agent-prompt-sync on merge-to-main — **no `deploys/queued/` manifest** (#636 boundary); rebaseline **not required** (agent prompt files not hashed by `audit.sh`, #621); **`main/AGENTS.md` < 12,000 B hard cap** (post-plan Codex F4) — resolved by moving privacy rule + delegation/timelog mechanics to `TOOLS.md` and keeping only rules + a lean adapted Output Discipline block in AGENTS; **live main session rotated** (`rotate_main_session.py`) before smoke (Codex F5); zero behavior regression on the live front-desk agent
**Scale/Scope**: one agent workspace (`main`) — five standard files re-authored + a one-line roster note in the #587 standard; `GOVERNANCE.md` and `felix-file-issue.py` unchanged

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter present (compact mode). Relevant directives and this mission's posture:

- **DIRECTIVE_001 (Architectural Integrity)** — PASS. The #587 file-ownership contract *is* separation of concerns; this mission enforces it (each concern in exactly one owner file).
- **DIRECTIVE_003 (Decision Documentation)** — PASS. The design decisions (scope, purpose-home, GOVERNANCE.md handling, folded improvements) are recorded in the issue #583 body and this plan.
- **DIRECTIVE_010 (Specification Fidelity)** — PASS. Implementation is authored to the spec's FR/NFR/C rows; the validator + review enforce fidelity.
- **DIRECTIVE_024 (Locality of Change)** — PASS. Blast radius is one agent workspace; no service, credential, port, or data-flow change.
- **DIRECTIVE_031 (Context-Aware Design)** — PASS. Content is authored within the OpenClaw workspace bounded context; the #587 ownership table is the ubiquitous language.

No violations. Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/author-main-workspace-01KXE90Z/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (content-conservation model + invariants)
├── quickstart.md        # Phase 1 output (author → validate → deploy → verify → smoke → rollback)
├── contracts/           # Phase 1 output (README: no API surface)
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/openclaw/agents/
├── main/                         # THE SUBJECT — re-authored this mission
│   ├── IDENTITY.md               # authored from factory scaffold (Felix + vibe)
│   ├── SOUL.md                   # reduced to voice-only + one-line privacy stance
│   ├── USER.md                   # absorbs filtered Kent-context + Felix "why"
│   ├── TOOLS.md                  # authored from factory scaffold to real surface
│   ├── AGENTS.md                 # role statement, Output Discipline, enforceable privacy,
│   │                             #   consolidated red lines + delegation (rules)
│   ├── GOVERNANCE.md             # UNCHANGED (acknowledged in standard/roster only)
│   └── felix-file-issue.py       # UNCHANGED
└── validate_workspace.py         # REUSED as-is (invariant checker)

docs/design/
└── openclaw-workspace-authoring-standard.md   # +1-line roster note re: main's on-demand GOVERNANCE.md
```

**Structure Decision**: Single-project. All authored content lives under
`scripts/openclaw/agents/main/`; the only file touched outside that directory is
the #587 standard doc (a one-line roster acknowledgment, FR-009). No new source
modules, no new tests beyond exercising the reused validator.

## Complexity Tracking

Not required — Charter Check passed with no violations.

## Implementation Concern Map

> Implementation concerns are NOT work packages. `/spec-kitty.tasks` translates
> these into WPs. The five files are tightly coupled (content moves *between*
> them), so the content-authoring concerns will likely collapse into a single
> coherent WP to avoid cross-lane conflicts on the same workspace — the tasks
> phase decides.

### IC-01 — SOUL/USER content separation

- **Purpose**: Reduce `SOUL.md` to voice-only and relocate its non-voice content, so voice/stance and Kent-context live in their correct owner files.
- **Relevant requirements**: FR-001, FR-002; the "why" → USER decision.
- **Affected surfaces**: `main/SOUL.md`, `main/USER.md`.
- **Sequencing/depends-on**: none (but tightly coupled to IC-03 — content lands in AGENTS).
- **Risks**: over-stripping SOUL (losing the strong Voice); leaving USER/SOUL communication-style duplication.

### IC-02 — TOOLS/IDENTITY authoring from scaffold

- **Purpose**: Replace the two factory templates with `main`'s real tool surface and identity card.
- **Relevant requirements**: FR-003, FR-004; Invariant A (TOOLS carries the enforceable privacy path).
- **Affected surfaces**: `main/TOOLS.md`, `main/IDENTITY.md`.
- **Sequencing/depends-on**: none.
- **Risks**: inlining stale lists in TOOLS (use pointers); IDENTITY vibe needs Kent's review-time refinement.

### IC-03 — AGENTS re-authoring + AGENTS↔TOOLS rebalance (both invariant fixes + folded improvements)

- **Purpose**: Make `AGENTS.md` carry the role statement, adapted Output Discipline block (Inv-B), full routing matrix, and consolidated red lines — while staying under the 12K cap by pushing mechanics + the enforceable privacy rule to `TOOLS.md` (Inv-A home).
- **Relevant requirements**: FR-005, FR-006 (Inv-A via TOOLS + Inv-B via AGENTS), FR-007, FR-008 (red lines); NFR-005 (byte cap).
- **Affected surfaces**: `main/AGENTS.md`, `main/TOOLS.md` (tightly co-authored with IC-02).
- **Sequencing/depends-on**: receives content from IC-01; must land an **adapted** (not mirrored) Output Discipline block and the full six-specialist routing matrix (escalation + tasker must survive). The message-identity line is left unchanged (de-hardcode dropped).
- **Risks (Codex-surfaced)**: (F1) silently dropping current AGENTS blocks — mitigated by the full keep/move/drop table in `data-model.md`; (F2) dropping escalation/tasker routing; (F3) importing capture-specific inbox text; (F4) blowing the 12K cap. All have explicit resolutions in `data-model.md` / `research.md`.

### IC-04 — Standard acknowledgment + validation gate

- **Purpose**: Record GOVERNANCE.md's out-of-standard status and prove both invariants pass.
- **Relevant requirements**: FR-009, NFR-001, NFR-002; SC-001, SC-002, SC-003, SC-005.
- **Affected surfaces**: `docs/design/openclaw-workspace-authoring-standard.md`; the validator output for `main`.
- **Sequencing/depends-on**: after IC-01..03.
- **Risks**: none material; the validator is deterministic.

### IC-05 — Deploy, parity, session-rotation, smoke (post-merge operator)

- **Purpose**: Verify the live deploy and no regression on the front-desk agent.
- **Relevant requirements**: FR-010, NFR-003, NFR-004; SC-004.
- **Affected surfaces**: `/data/services/openclaw/data/` (main's deploy dest); `scripts/openclaw/helpers/rotate_main_session.py`; documented in `quickstart.md` (not a code WP — planning_artifact WPs cannot own `kitty-specs/` paths, per the #584 lesson).
- **Sequencing/depends-on**: after merge-to-main.
- **Risks**: agent-prompt-sync timing (the tick that pulls runs old code; the *next* tick writes the change); **the live session caches its prompt — must run `rotate_main_session.py` before smoke** (Codex F5, INV-9) else smoke tests the stale prompt; smoke must be evidence-based and exercise a real delegation route.
