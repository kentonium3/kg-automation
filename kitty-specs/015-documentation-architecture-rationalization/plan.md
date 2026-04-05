# Implementation Plan: Documentation Architecture Rationalization

**Branch**: `main` | **Date**: 2026-04-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/015-documentation-architecture-rationalization/spec.md`

## Summary

Classify every active document in `docs/` against the Divio 4-type framework, create `docs/INDEX.md` as the master map referenced from `CLAUDE.md`, enforce runbook-vs-reference distinction within `docs/runbooks/`, document `docs/design/architecture/data/` as the canonical machine-readable artifact home, update the change-control protocol to require INDEX.md maintenance, and resolve F016's path dependencies.

**Technical approach**: Pure documentation curation — frontmatter correction, content moves via `git mv`, new INDEX.md authoring, reference-audit pass. No code, no tests, no tooling. Gap analysis produced during Phase 0 research lives in `research.md`; a distilled standards doc at `docs/design/standards/divio-classification.md` becomes the permanent reference.

## Technical Context

**Language/Version**: Markdown + YAML frontmatter (no executable code)
**Primary Dependencies**: N/A (no build tools, no runtime dependencies)
**Storage**: Files in `docs/`, committed to git
**Testing**: Manual review of INDEX.md completeness + reference-audit pass (no automated validators introduced per C-006)
**Target Platform**: kg-automation repo on GitHub; docs consumed by AI agents (Claude Code, OpenClaw) and human operator
**Project Type**: Documentation curation (single project)
**Performance Goals**: ≤3 link hops from CLAUDE.md to any active doc (NFR-001)
**Constraints**: `docs/design/architecture/data/` and `docs/diagnostics/` content untouched (C-001, C-002); `git mv` for all moves (C-003); zero broken references on feature branch (NFR-003)
**Scale/Scope**: ~40-60 active docs across `docs/`, classified by Divio type; 1 new INDEX.md; 1 new Divio standards reference doc; F016 spec path updates

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution template set**: `software-dev-default` with `TEST_FIRST` directive — this paradigm does not apply to a pure documentation-curation feature. No executable code is authored, so there are no tests to write first. TEST_FIRST is noted as non-applicable, not violated. See Complexity Tracking below.

**kg-automation standing requirements** (from `CLAUDE.md`):
- ✅ **Document-first / GitOps pattern**: Feature adds discoverability via INDEX.md; preserves version-control model.
- ✅ **System documentation comprehensive and current**: Feature strengthens comprehensiveness by indexing everything.
- ✅ **Machine-readable as authoritative record**: FR-006 formalizes `docs/design/architecture/data/` as the canonical home.
- ✅ **Architecture JSON not changed**: Confirmed — feature doesn't touch `docs/design/architecture/data/` content.
- ✅ **No writes to `~/second-brain/`**: Confirmed by C-005.
- ✅ **No changes to `.github/workflows/`**: Confirmed by C-004.

**Gate status**: PASS (TEST_FIRST flagged as N/A, all other standing requirements honored).

## Project Structure

### Planning Artifacts (this feature)

```text
kitty-specs/015-documentation-architecture-rationalization/
├── spec.md              # Documentation goals and user scenarios
├── plan.md              # This file
├── research.md          # Phase 0 — full Divio audit + gap analysis
├── data-model.md        # Phase 1 — doc_type / frontmatter schema + Divio mapping
├── quickstart.md        # Phase 1 — how to add a doc + pick its Divio type
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /spec-kitty.specify)
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Repository Structure (files modified/created by this feature)

```text
kg-automation/
├── CLAUDE.md                                           # MODIFIED — add refs to INDEX.md and constitution/
├── docs/
│   ├── INDEX.md                                        # NEW — master documentation map
│   ├── docs-readme.md                                  # MOVED → docs/archive/docs-readme.md
│   ├── constitution/                                   # (unchanged files; now linked from CLAUDE.md)
│   ├── design/
│   │   ├── standards/
│   │   │   └── divio-classification.md                 # NEW — permanent Divio reference doc
│   │   └── architecture/
│   │       ├── README.md                               # MODIFIED — declare data/ as canonical home
│   │       └── change-control.md                       # MODIFIED — require INDEX.md updates
│   ├── runbooks/                                       # frontmatter corrected across all files
│   │   ├── <each file>                                 # MODIFIED — doc_type + audience frontmatter
│   │   └── governance/                                 # (empty, ready for F016)
│   ├── postmortems/                                    # (empty, ready for F016)
│   ├── func-spec/
│   │   └── F016_change_control_governance.md           # MODIFIED — resolve TBD paths
│   └── archive/
│       └── docs-readme.md                              # MOVED from docs/docs-readme.md
└── [any file referencing moved paths]                  # MODIFIED — update references
```

**Structure Decision**: Documentation-only feature. All changes occur under `docs/` plus `CLAUDE.md` at repo root plus one F016 spec file path update. No `src/`, no `tests/`, no build artifacts.

## Phase 0: Research — Divio Audit & Gap Analysis

### Objective

Produce a point-in-time classification of every active document in `docs/` against the Divio 4-type framework (how-to/runbook, reference, explanation; tutorials absent by design). Identify gaps, misclassifications, and duplicate coverage. This output is the foundation for every downstream FR (FR-003 content moves, FR-004 frontmatter corrections, FR-008 INDEX.md authoring).

### Research Tasks

1. **Inventory every active document**: enumerate all `.md` and `.json` files under `docs/` (excluding `docs/archive/`), noting current path, current `doc_type` frontmatter value (if any), and title.
2. **Classify each document by Divio type** (internal-audience mapping per C-007):
   - **Runbook (how-to)**: prescriptive step-by-step, executable
   - **Reference**: describes system machinery (architecture docs, CLAUDE.md, service inventories as narrative)
   - **Explanation**: why things work the way they do (constitution, ADRs, postmortems, design principles)
   - Note ambiguity: if a doc mixes types, pick dominant and flag.
3. **Detect misclassifications**: docs whose current `doc_type` doesn't match Divio type; docs in the wrong directory given their type.
4. **Detect duplicates**: multiple docs covering the same ground.
5. **Identify gaps**: Divio types with no coverage in a given area (e.g., no runbook for a service that clearly needs one).
6. **Catalogue inbound references**: for every doc whose path might change, list all files (CLAUDE.md, func-spec/*, ai-agents/*, .claude/*, kitty-specs/*) that reference it.
7. **Flag agent-executable runbooks**: runbooks whose steps could be automated by an agent skill (for FR-005 audience field).

### Research Output

See [research.md](research.md) for:
- Complete document inventory with current and target Divio classifications
- List of misclassifications and proposed corrections
- List of duplicate coverage
- Gap list by Divio type
- Reference audit map (what references what, for every doc whose path may change)
- Agent-executable runbook candidate list

**`docs/diagnostics/` exemption** (C-002): inventory this directory's files but do not recommend restructuring or archival; frontmatter review is incidental and non-blocking.

## Phase 1: Design — Divio Schema & Authoring Flow

### Objective

Define the canonical `doc_type` schema, the Divio-to-directory mapping rules, and the authoring flow that future docs must follow.

### Data Model

See [data-model.md](data-model.md) for:
- Canonical `doc_type` frontmatter values: `runbook`, `reference`, `explanation`, `spec`, `diagnostic`, `postmortem`, `standard` — with definition of each
- Required and optional frontmatter fields per doc_type
- Divio-to-directory mapping rules (which canonical home each type lives in)
- `audience` field schema (`human-only` | `agent-executable` | `both`)

### Authoring Flow

See [quickstart.md](quickstart.md) for:
- Decision tree: which Divio type is my doc?
- Placement rules: which canonical home does that type live in?
- Frontmatter template per doc_type
- INDEX.md update protocol

### No API Contracts

No APIs, no code — `contracts/` directory intentionally not created. This is a documentation-curation feature.

### Agent Context Update

N/A — no agent-executed skills are scaffolded by this feature. The agent-executable runbook flags identified in research are informational for future skill-conversion work (out of scope here per "Out of Scope" in spec).

## Phase 2: Implementation

Work package breakdown happens in `/spec-kitty.tasks`. Anticipated work packages (for sizing only — not authoritative):

1. **Audit & classify**: Execute Phase 0 research; land `research.md` with full inventory.
2. **Create Divio standards doc**: Author `docs/design/standards/divio-classification.md` from the Divio mapping defined in data-model.md.
3. **Correct frontmatter**: Apply `doc_type` + `audience` corrections to all `docs/runbooks/` files.
4. **Content moves**: Move misclassified content out of `docs/runbooks/` to correct canonical homes using `git mv`.
5. **Create INDEX.md**: Author `docs/INDEX.md` covering every active directory and key doc.
6. **Update CLAUDE.md**: Add references to INDEX.md and `docs/constitution/FELIX-CONSTITUTION.md`.
7. **Update architecture README + change-control**: State canonical data home; require INDEX.md updates on every feature.
8. **Resolve F016 paths**: Update F016 spec with resolved paths, remove TBDs.
9. **Archive docs-readme.md**: `git mv` old index to `docs/archive/`.
10. **Reference-audit pass**: Update every inbound reference broken by moves; verify zero broken links.

## Complexity Tracking

| Violation / Mismatch | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Constitution template set is `software-dev-default` with `TEST_FIRST`, but feature is pure doc curation | Constitution template applies project-wide; cannot be per-feature-overridden in 3.0.3 | Switching constitution template set mid-project would ripple across F001-F014 history; per-feature mission tag (`documentation`) is the intended override mechanism but not honored by setup-plan (see workflow journal) |
| plan.md scaffolded from software-dev template instead of documentation-mission template | spec-kitty 3.0.3 setup-plan bug — constitution template set overrides meta.json `mission` (logged in workflow journal) | Letting workflow proceed naturally per user directive; plan content hand-adapted to doc feature rather than replacing template |
| meta.json contains false-positive `documentation_state.generators_configured` (jsdoc, sphinx) | setup-plan's scanner heuristic false-positively detected these (logged in workflow journal) | Leaving as-is per "no manual compensation" directive; flagged in workflow journal for upstream fix |
| No `contracts/` directory created | N/A — no APIs in doc curation feature | Standard spec-kitty software-dev phase includes contracts/; intentionally skipped for this mission |
| No automated link-checker or CI validator | Out of scope per C-006; introducing tooling is a separate feature | Manual review of INDEX.md + reference-audit is sufficient for kg-automation's scale (~40-60 docs) |

## Risks & Dependencies

**Risks**:
- **Reference breaks after content moves**: Mitigated by reference-audit pass before moves (Phase 0 research task 6) and by NFR-003 (zero broken references required).
- **Divio classification ambiguity on borderline docs**: Mitigated by dominant-type rule (C-007) and by noting ambiguity in frontmatter.
- **INDEX.md goes stale immediately after acceptance**: Mitigated by FR-011 — change-control protocol update makes INDEX.md maintenance mandatory on every future feature.
- **Agent-executable flagging introduces scope creep**: Mitigated — flagging is informational only; no skill conversion in this feature.

**Dependencies**:
- **Prerequisite (completed)**: Physical directory restructuring done as out-of-cycle task (renaming `handbooks/` → `runbooks/`, moving `research/` under `docs/design/`, creating `runbooks/governance/` and `postmortems/`, archiving orphaned dirs).
- **Downstream (unblocked by this feature)**: F016 — Change Control Governance. F015's FR-012 resolves F016's path TBDs.

## Branch Strategy Recap

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **`branch_matches_target`**: `true` — current branch matches intended landing branch.
- **Branch strategy summary**: Current branch at workflow start: main. Planning/base branch for this feature: main. Completed changes must merge into main.
