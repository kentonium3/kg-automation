# Implementation Plan: Cross-Repo Standing Rules Sweep

**Branch**: `feat/cross-repo-standing-rules-sweep` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/cross-repo-agent-rules-sweep-01KWR6N6/spec.md`

## Summary

Complete the remaining #649 sweep by reviewing kg-automation guidance surfaces
for rules that must apply in every repository session, classifying each
candidate, and updating `.agents/rules/cross-repo-standing-rules.md` only for
short always-on rules or stale wording that conflicts with linked runbooks. The
plan deliberately avoids global `~/.claude/CLAUDE.md` edits and avoids changing
active Spec Kitty mission state.

## Technical Context

**Language/Version**: Markdown governance documents plus Python 3.11 docs validator
**Primary Dependencies**: `tooling/scripts/validate_docs.py`, ripgrep, Git, Spec Kitty 3.2.4
**Storage**: Git-tracked repository files only; no runtime storage
**Testing**: `python tooling/scripts/validate_docs.py`, targeted `rg` checks for stale standing-rules language and protected rules
**Target Platform**: Local repository documentation and globally imported agent instruction surface
**Project Type**: Documentation/governance update in a single repository
**Performance Goals**: Standing-rules file remains reviewable in under 3 minutes and under 80 nonblank lines
**Constraints**: No global `~/.claude/CLAUDE.md` mutation without explicit approval; no reads of forbidden private paths; no public posting
**Scale/Scope**: One canonical rule file plus mission-owned planning artifacts; no deployed services or code paths

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Charter / Doctrine Concern | Status | Plan Response |
| --- | --- | --- |
| DIRECTIVE_003 Decision Documentation | PASS | Candidate classifications and non-promotions are captured in `research.md` and, when needed, implementation notes. |
| DIRECTIVE_024 Locality of Change | PASS | Live edits are limited to `.agents/rules/cross-repo-standing-rules.md` unless validation finds a directly blocking drift. |
| DIRECTIVE_033 Targeted Staging | PASS | Commits must stage explicit mission files and the canonical rule file only; no blanket staging. |
| DIRECTIVE_037 Living Documentation Sync | PASS | The plan checks the standing-rules file against linked runbooks, especially `docs/runbooks/spec-kitty-bug-reporting.md`. |
| Privacy Boundary | PASS | The sweep excludes forbidden private paths and does not inspect private second-brain content. |
| Change-Risk Taxonomy | PASS | Tier 4 docs/governance update; no deployed service, credential, topology, or runtime state changes. |

## Project Structure

### Documentation (this mission)

```text
kitty-specs/cross-repo-agent-rules-sweep-01KWR6N6/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/requirements.md
└── tasks.md                  # Created later by /spec-kitty.tasks
```

### Source / Documentation Surfaces

```text
.agents/rules/cross-repo-standing-rules.md      # Primary live artifact
docs/runbooks/spec-kitty-bug-reporting.md       # Linked protocol source
docs/constitution/FELIX-CONSTITUTION.md         # Candidate boundary source, read-only
CLAUDE.md / CODEX.md / AGENTS.md                # Candidate rule sources, read-only unless directly in scope
scripts/openclaw/agents/**/{AGENTS,SOUL,TOOLS}.md # Agent-specific candidate sources, read-only
```

**Structure Decision**: Keep the implementation as a small documentation
mission. No helper script is required because the deterministic work is a
bounded grep/read/classify sweep and the change is expected to be one Markdown
file.

## Complexity Tracking

No charter complexity violations.

## Phase 0 Research

Research is captured in [research.md](./research.md). It defines the candidate
classification categories, the surfaces to inspect, and the promotion rules for
the standing-rules file.

## Phase 1 Design

Design artifacts:

- [data-model.md](./data-model.md) defines the lightweight candidate-rule model.
- [quickstart.md](./quickstart.md) defines the execution and validation sequence.
- No API contracts are generated because this mission does not introduce an API,
  event payload, or integration boundary.

## Implementation Concern Map

### IC-01 — Candidate Sweep And Classification

- **Purpose**: Find possible universal rules and classify them before editing the canonical library.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-007
- **Affected surfaces**: `CLAUDE.md`, `CODEX.md`, `AGENTS.md`, `.agents/rules/`, `docs/runbooks/`, `docs/constitution/`, `scripts/openclaw/agents/**`
- **Sequencing/depends-on**: none
- **Risks**: Over-broad search output can hide important candidates; use focused `rg` queries and bounded reads.

### IC-02 — Standing-Rules Library Update

- **Purpose**: Apply only universal short rules and stale wording fixes to the canonical cross-repo library.
- **Relevant requirements**: FR-003, FR-004, FR-005, FR-006, NFR-001, NFR-002
- **Affected surfaces**: `.agents/rules/cross-repo-standing-rules.md`
- **Sequencing/depends-on**: IC-01
- **Risks**: The file can become a runbook dump; keep long procedures linked, not duplicated.

### IC-03 — Validation And Closeout

- **Purpose**: Prove the library is concise, current, and retains existing protections.
- **Relevant requirements**: NFR-004, SC-002, SC-003, SC-004, SC-005
- **Affected surfaces**: Validation commands and mission notes
- **Sequencing/depends-on**: IC-02
- **Risks**: A clean docs validator is necessary but not sufficient; add targeted checks for stale paste-buffer wording and required protection headings.

## Branch Contract

Current branch at plan start: `feat/cross-repo-standing-rules-sweep`.
Planning/base branch: `feat/cross-repo-standing-rules-sweep`.
Final merge target for completed changes: `feat/cross-repo-standing-rules-sweep`.
`branch_matches_target`: `true`.
