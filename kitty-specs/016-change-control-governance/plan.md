# Implementation Plan: Change Control Governance & Incident Management

**Branch**: `main` | **Date**: 2026-04-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/016-change-control-governance/spec.md`

## Summary

Establish a five-tier change control framework triggered by the 2026-04-03 Vikunja UFW outage. The implementation enriches service-inventory.json with dependency/health-check/risk-tier data, creates the risk taxonomy as machine-readable JSON, adds governance runbooks (pre-flight checklists, post-change verification), adds CLAUDE.md enforcement rules per tier, creates an incident postmortem template + the origin incident's first postmortem, formalizes the documentation standards principle in the Felix constitution, and produces a Mermaid service dependency diagram.

**Technical approach**: JSON schema extension (extend, don't replace), markdown governance docs, CLAUDE.md behavioral rules, Felix constitution edit + sync, Mermaid diagram in .view.md wrapper. All artifacts follow established kg-automation patterns validated during Phase 0 research.

## Technical Context

**Language/Version**: JSON (operational data), Markdown + YAML frontmatter (docs), Mermaid (diagrams), Bash (origin incident validation scripts)
**Primary Dependencies**: Existing `service-inventory.json` (schema v1.0 → v1.1), `network-topology.json`, CLAUDE.md, Felix constitution, change-control.md
**Storage**: Files in `docs/`, committed to git
**Testing**: Origin incident walkthrough validates framework end-to-end (FR-016). Manual validation of CLAUDE.md Tier 0 behavior via test prompt.
**Target Platform**: kg-automation repo on GitHub; governance docs consumed by AI agents and human operator
**Project Type**: Governance infrastructure (single project)
**Performance Goals**: Postmortem template completable in under 30 minutes (NFR-003)
**Constraints**: No automated drift detection (C-001), no monitoring/alerting (C-003); extend JSON schema without removing fields (NFR-004)
**Scale/Scope**: 11 services enriched, 1 new JSON taxonomy file, 3 new governance runbooks, 1 new postmortem template, 1 origin postmortem, 1 Mermaid diagram, CLAUDE.md + constitution edits

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution template set**: `software-dev-default` with `TEST_FIRST` directive.

**TEST_FIRST interpretation for F016**: The origin incident walkthrough (FR-016) serves as the "test" that validates the framework before acceptance. The pre-flight checklist is walked through the UFW scenario to prove it catches the port 443 gap — this IS a test-first approach applied to governance rather than code.

**kg-automation standing requirements**:
- ✅ **Architecture doc updates are part of the feature** — FR-011 through FR-015 explicitly require this.
- ✅ **JSON-as-authoritative-record** — FR-001, FR-002, FR-003 create/extend JSON files.
- ✅ **INDEX.md maintenance** — FR-015 requires INDEX.md updates per F015 change-control rule.
- ✅ **No writes to ~/second-brain/** — confirmed.
- ✅ **No changes to .github/workflows/** — confirmed.

**Gate status**: PASS.

## Project Structure

### Planning Artifacts (this feature)

```text
kitty-specs/016-change-control-governance/
├── spec.md              # Feature specification (16 FRs, 5 NFRs, 7 Cs)
├── plan.md              # This file
├── research.md          # Phase 0 — existing pattern analysis
├── data-model.md        # Phase 1 — JSON schema extensions + entity relationships
├── quickstart.md        # Phase 1 — validation approach per deliverable
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Repository Structure (files created/modified by this feature)

```text
kg-automation/
├── CLAUDE.md                                           # MODIFIED — add Change Control Guardrails section
├── docs/
│   ├── INDEX.md                                        # MODIFIED — add new governance files
│   ├── constitution/
│   │   └── FELIX-CONSTITUTION.md                       # MODIFIED — add Directive 5: Documentation Standards
│   ├── design/architecture/
│   │   ├── README.md                                   # MODIFIED — add governance refs + taxonomy to Data Files
│   │   ├── change-control.md                           # MODIFIED — add risk taxonomy + checklist + verification refs
│   │   ├── security-posture.md                         # MODIFIED — reference change control governance
│   │   ├── service-inventory.md                        # MODIFIED — match enriched JSON
│   │   ├── physical-topology.md                        # MODIFIED — add dependency diagram ref
│   │   ├── service-dependencies.view.md                # NEW — Mermaid service dependency diagram
│   │   └── data/
│   │       ├── service-inventory.json                  # MODIFIED — add deps/health/config/risk_tier (v1.1)
│   │       ├── network-topology.json                   # MODIFIED — add tailscale_serve config
│   │       └── change-risk-taxonomy.json               # NEW — five-tier taxonomy
│   ├── runbooks/governance/
│   │   ├── pre-flight-checklist.md                     # NEW — Tier 0/1 and Tier 2 checklists
│   │   ├── post-change-verification.md                 # NEW — per-tier verification protocol
│   │   └── incident-postmortem-template.md             # NEW — reusable postmortem template
│   └── issues/postmortems/
│       └── 2026-04-03-vikunja-ufw-outage.md            # NEW — first real postmortem
└── .kittify/constitution/constitution.md                # MODIFIED — handbooks→runbooks already done; doc standards TBD
```

**Structure Decision**: Governance infrastructure. All changes under `docs/`, `CLAUDE.md`, constitution. No `src/`, no `tests/`, no deploy scripts.

## Phase 0: Research

**Completed** — see [research.md](research.md).

Key findings:
- service-inventory.json has 11 services, no dependency/health-check data, schema v1.0
- CLAUDE.md guardrail rules best placed after Permissions section
- Felix constitution structure supports Directive 5 placement after Safety Parameters
- Mermaid .view.md pattern established with subgraphs and %% source comments
- Origin incident root cause chain validated: UFW port 443 → Tailscale serve → Vikunja

## Phase 1: Design

**Completed** — see [data-model.md](data-model.md) and [quickstart.md](quickstart.md).

Key design decisions:
- risk_tier uses integer 0-4 matching taxonomy (not "critical/essential/supporting")
- Schema 1.0 → 1.1 (backward-compatible, all new fields optional)
- Dependencies use specific `target` format for pre-flight impact analysis
- Health checks use method enum with "none" for services without endpoints
- Postmortem follow-on actions use placeholder format for Vikunja task references
- Diagrams use Mermaid in .view.md wrapper per existing physical-topology pattern

## Anticipated Work Package Breakdown

*Detailed WPs generated by `/spec-kitty.tasks`. This is a sizing preview only.*

1. **Risk taxonomy + service inventory enrichment** — create taxonomy JSON, extend all 11 service records, update network-topology
2. **Pre-flight checklist + post-change verification** — create governance runbooks
3. **CLAUDE.md guardrail rules** — write per-tier enforcement, Tier 0 Hard Lock
4. **Postmortem template + origin incident** — create template, complete first postmortem
5. **Documentation standards principle** — constitution edit + CLAUDE.md pointer + constitution sync
6. **Service dependency diagram** — Mermaid .view.md
7. **Architecture doc updates + INDEX.md** — README, change-control, security-posture, service-inventory.md, physical-topology.md, INDEX.md
8. **Origin incident walkthrough** — validate pre-flight checklist catches port 443 gap

## Risks & Dependencies

**Risks**:
- **Service inventory enrichment is large scope** — 11 services × 4 new fields each. Some services may have undocumented dependencies or no health-check endpoint. Mitigated by capturing best-known state and flagging gaps.
- **CLAUDE.md Tier 0 Hard Lock wording** — must be precise enough to prevent override by urgency framing while still enabling Kent to get Claude Code assistance with script generation. Mitigated by matching existing absolute-rule patterns ("never...").
- **Constitution edit triggers sync** — need to run `spec-kitty constitution sync` afterward. Known pattern from F015.

**Dependencies**:
- **F015 completed** — INDEX.md, Divio standard, change-control INDEX.md rule all in place.
- **Standing requirement** — architecture doc updates are part of implementation, not separate.

## Branch Strategy Recap

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **`branch_matches_target`**: `true`
