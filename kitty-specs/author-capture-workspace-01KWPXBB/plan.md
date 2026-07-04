# Implementation Plan: Author felix-admin-capture Workspace

**Branch**: `feat/author-capture-workspace` | **Date**: 2026-07-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/author-capture-workspace-01KWPXBB/spec.md`

## Summary

Re-author felix-admin-capture's `SOUL.md`, `USER.md`, and `TOOLS.md` into a clean,
self-contained set against the OpenClaw Workspace Authoring Standard (#587, merged
`ad7ee47d`), relocating leaked content to its correct owner file with **zero behavior
change**. AGENTS.md is touched only to receive relocated material (the label taxonomy).
The `scripts/openclaw/agents/validate_workspace.py` checker (from #587) is the
mechanical gate for the shared invariants. On merge to main, the files deploy to office2
automatically via the existing agent-prompt-sync pull pipeline (#567/#136) — no manifest
authored. A post-deploy smoke test confirms capture processes the inbox identically.

**Technical approach**: pure content relocation guided by an explicit move-table (locked
with Kent across the 2026-06-28 / 07-03 design sessions), verified by (a) the #587
validator, (b) a content-conservation check that relocated blocks land in exactly one
place, and (c) an inbox smoke test comparing routing decisions pre/post deploy.

## Technical Context

**Language/Version**: Markdown (OpenClaw agent prompt files) + Python 3.12 (existing
`validate_workspace.py` from #587, reused not modified) + Bash (verification/smoke).
**Primary Dependencies**: `scripts/openclaw/agents/validate_workspace.py` (#587 validator);
`scripts/openclaw/deploy/deploy_agent_prompts.py` (agent-prompt-sync pipeline, #567/#136);
`scripts/inbox/*` helpers (capture's deterministic Step 1–7 recipes — unchanged, referenced
by the smoke test).
**Storage**: Files only — `scripts/openclaw/agents/felix-admin-capture/{SOUL,USER,TOOLS,AGENTS}.md`
in repo; deployed copies at `/data/services/openclaw/inbox-agent/` on office2.
**Testing**: `validate_workspace.py` (invariant gate, must PASS for capture); a content-move
verification (relocated blocks present in destination, absent from source); an inbox smoke
test on office2 (`prescan` + a classify/route dry comparison) confirming no routing-decision
change. No new automated pytest is required — the #587 validator already has coverage; this
mission authors content, it does not add deterministic logic.
**Target Platform**: office2 (Ubuntu 24.04 LTS) OpenClaw runtime; authored on Mac.
**Project Type**: single (prompt-authoring + verification within kg-automation).
**Performance Goals**: N/A (authoring mission — no runtime performance surface).
**Constraints**: Zero observable behavior change (NFR-001); byte-for-byte repo↔office2 parity
after sync (NFR-003); AGENTS.md edits limited to receiving the label taxonomy (C-002);
no direct office2 edits — merge-to-main is the deploy trigger (C-003).
**Scale/Scope**: One agent, 4 files touched (3 authored + AGENTS.md receiver), ~4 content
blocks relocated.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter present (`.kittify/doctrine`, software-dev-default). Active directives and how this
plan satisfies them:

- **DIRECTIVE_001 (Architectural Integrity / separation of concerns)** — This mission's
  entire purpose is enforcing single-responsibility across the workspace files per the #587
  ownership contract. ✅ Directly served.
- **DIRECTIVE_024 (Locality of Change)** — Scope is one agent's files; AGENTS.md edits are
  bounded to the label-taxonomy receiver. Blast radius is minimal and reviewable. ✅
- **DIRECTIVE_031 (Context-Aware Design)** — Content is relocated to align with each file's
  ubiquitous role (SOUL=voice, TOOLS=environment, AGENTS=rules) per the standard. ✅
- **DIRECTIVE_033 (Targeted Staging)** — Commits stage only capture's four files (+ mission
  artifacts); no blanket `git add -A`. ✅
- **DIRECTIVE_010 (Specification Fidelity)** — Spec was amended in-plan (FR-9/C-003 deploy
  path) so implemented behavior matches the corrected spec; the deviation is documented, not
  silent. ✅
- **DIRECTIVE_034 (Test-First)** — The verifiable gate (`validate_workspace.py` PASS for
  capture) exists *before* authoring and defines done; authoring drives it green. Behavior
  preservation is checked by the smoke test. This is the applicable "test-first" surface for
  a content-authoring mission (no new production logic to TDD). ✅
- **DIRECTIVE_003 (Decision Documentation)** — The move-table, the FR-9 deploy correction,
  and the ADD-removal rationale are recorded in `research.md`. ✅

**Project directive DIR-001 (production runs on office2; Mac is authoring only)** — honored:
no direct office2 edits; deploy via the pull pipeline on merge.

No violations. Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/author-capture-workspace-01KWPXBB/
├── plan.md              # This file
├── research.md          # Phase 0 — move-table, deploy-path finding, ADD rationale, invariant homing
├── data-model.md        # Phase 1 — the content-block → owner-file model + conservation rules
├── quickstart.md        # Phase 1 — author → validate → merge → verify-sync → smoke runbook
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-capture/
├── SOUL.md      # AUTHORED — voice/stance only; role deleted, privacy→one-line stance, ADD removed
├── USER.md      # AUTHORED — filtered person-view; date-handling removed, ADD removed
├── TOOLS.md     # AUTHORED — tool surface + relocated date-handling; label list → pointer only
└── AGENTS.md    # RECEIVER — gains the Available Labels taxonomy beside Step 3; nothing else changes

scripts/openclaw/agents/validate_workspace.py   # #587 validator — REUSED, not modified
scripts/openclaw/deploy/deploy_agent_prompts.py # agent-prompt-sync — deploy path, not modified
```

**Structure Decision**: No new source structure. This is an authoring mission over four
existing files plus reuse of the #587 validator and the #567 deploy pipeline. All work is
content relocation + verification; no new modules, no `src/` changes.

## Implementation Concern Map

> Concerns are architectural areas, not work packages. `/spec-kitty.tasks` translates these
> into executable WPs.

### IC-01 — Author SOUL / USER / TOOLS (the three-file relocation)

- **Purpose**: Relocate leaked content to the correct owner file per the #587 contract, with
  zero behavior change, producing the authored SOUL/USER/TOOLS set.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-007 (privacy homing),
  NFR-002 (de-dup).
- **Affected surfaces**: `felix-admin-capture/{SOUL,USER,TOOLS}.md`.
- **Sequencing/depends-on**: none (first).
- **Risks**: Accidentally changing wording that alters behavior (must be pure relocation);
  dropping the enforceable privacy rule when reducing SOUL to a stance (FR-007 guards this).

### IC-02 — AGENTS.md label-taxonomy receiver

- **Purpose**: Move the `### Available Labels` taxonomy from TOOLS.md into AGENTS.md beside the
  Step 3 `github_issue` route; leave TOOLS.md with only a pointer (no inlined list).
- **Relevant requirements**: FR-006; C-002 (AGENTS edits limited to this receiver).
- **Affected surfaces**: `felix-admin-capture/AGENTS.md` (receiver), `TOOLS.md` (pointer).
- **Sequencing/depends-on**: pairs with IC-01's TOOLS authoring (same TOOLS edit).
- **Risks**: Scope-creeping AGENTS.md beyond the receiver; the label list going stale again
  (mitigated — TOOLS keeps only a pointer, per the standard's staleness-trap rule).

### IC-03 — Validate, deploy, verify parity, smoke-test

- **Purpose**: Prove the authored set passes #587 invariants, deploys via the pull pipeline on
  merge, matches office2 byte-for-byte, and causes no observable capture behavior change.
- **Relevant requirements**: FR-008 (validate), FR-009 (deploy via agent-prompt-sync),
  FR-010 (parity), FR-011 (smoke), NFR-001/003/004, SC-002/003/004/005 (rollback).
- **Affected surfaces**: `validate_workspace.py` (run), office2 `inbox-agent/` (deployed),
  `agent-prompt-sync.jsonl` (audit evidence).
- **Sequencing/depends-on**: IC-01, IC-02 (authoring must be complete + merged).
- **Risks**: agent-prompt-sync timer not live on office2 (verify before relying on auto-deploy);
  rebaseline expectation (#621 gap — likely "not required"; confirm at merge); smoke-test
  baseline must be captured pre-deploy to compare against.
