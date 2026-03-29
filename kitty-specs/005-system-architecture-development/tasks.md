# Work Packages: System Architecture Development

**Inputs**: Design documents from `kitty-specs/005-system-architecture-development/`
**Prerequisites**: plan.md (required), spec.md (required), research.md (research task register)

**Tests**: Manual review by Kent against success criteria SC-001 through SC-008. No automated test suite.

**Organization**: Fine-grained subtasks (`Txxx`) roll up into work packages (`WPxx`). Each work package must be independently deliverable and reviewable.

**Prompt Files**: Each work package references a matching prompt file in `tasks/`.

---

## Work Package WP01: Local Architecture Audit (Priority: P0)

**Goal**: Read all existing architecture docs, func-specs, handbooks, and constitution. Produce a validated inventory of what exists (F001-F004) vs. what was designed in v0.3, identifying drift, gaps, and undocumented state.
**Independent Test**: Audit document lists every deployed service, port, credential, and data flow with validation status. All deviations from v0.3 are identified.
**Prompt**: `tasks/WP01-local-audit.md`
**Requirement Refs**: FR-001
**Estimated Prompt Size**: ~350 lines

### Included Subtasks
- [x] T001 Read and catalog `docs/design/personal-ai-system-spec-v03.md` — extract all designed components, services, and data flows
- [x] T002 Read and catalog `docs/design/architecture/data/` JSON files — extract actual deployed state (services, credentials, ports, data flows)
- [x] T003 Read all func-specs (F001-F004) — extract what was specified for each feature
- [x] T004 Read all handbooks — extract what was actually implemented and documented operationally
- [x] T005 Read constitution — extract current governance state and identify gaps relative to the four new directives
- [x] T006 Produce audit report: designed vs. actual state, drift, gaps, undocumented state, governance gaps

### Implementation Notes
- All sources are local files in the repo — no external access needed
- JSON files in `docs/design/architecture/data/` are the authoritative state record
- Markdown architecture docs are narrative views
- The audit report feeds all subsequent research and deliverables

### Parallel Opportunities
- T001 through T005 can all be read in parallel
- T006 depends on all prior reads

### Dependencies
- None (starting package)

### Risks & Mitigations
- **Incomplete architecture docs**: Cross-reference JSON data files with handbooks and func-specs to fill gaps
- **v0.3 spec describes unbuilt features**: Mark these explicitly as "designed but not implemented"

---

## Work Package WP02: OpenClaw Capability Research (Priority: P0)

**Goal**: Research OpenClaw's native capabilities for agent teams, skills, orchestrators, logging, autonomy controls, external tool coordination, and identity/persona support. Answer research questions RQ-1 through RQ-5 and RQ-14.
**Independent Test**: Each research question has a Decision, Rationale, and Alternatives Considered section filled in with evidence from OpenClaw documentation.
**Prompt**: `tasks/WP02-openclaw-research.md`
**Requirement Refs**: FR-004, FR-009, FR-010
**Estimated Prompt Size**: ~450 lines

### Included Subtasks
- [x] T007 Research OpenClaw's native concepts: skills, agents, orchestrators — document how they map to the team model (RQ-1, RQ-2)
- [x] T008 Research OpenClaw's logging and observability capabilities (RQ-3)
- [x] T009 Research how autonomy gates and human-in-the-loop approval flows could be modeled in OpenClaw (RQ-4)
- [x] T010 Research OpenClaw's coordination with external tools like Claude Code and spec-kitty (RQ-5)
- [x] T011 Research OpenClaw's identity/persona model and how Felix as a system identity maps to it (RQ-14)
- [x] T012 Consolidate findings into research/openclaw-capabilities.md with Decision/Rationale/Alternatives for each question

### Implementation Notes
- Primary source: docs.openclaw.ai
- Secondary source: github.com/openclaw/openclaw (for source-level validation when docs are ambiguous)
- If OpenClaw doesn't natively support a concept (e.g., agent teams), document how to model it within what OpenClaw does support
- This is the critical path — most deliverables depend on these findings

### Parallel Opportunities
- T007 through T011 can be researched in parallel (different doc sections)
- T012 depends on all prior research

### Dependencies
- None (can start in parallel with WP01)

### Risks & Mitigations
- **OpenClaw docs are incomplete**: Fall back to GitHub source code for validation
- **OpenClaw doesn't support a needed concept**: Document the gap and propose modeling alternatives
- **Docs describe planned features not yet released**: Verify feature availability in the installed version on office2

---

## Work Package WP03: Integration and Tool Research (Priority: P0)

**Goal**: Research integration needs across all five capability areas. Answer research questions RQ-6 through RQ-9. For confirmed tools, document integration approach. For TBD tools, document the open decision with need, options, and criteria.
**Independent Test**: Each capability area has its integration needs documented. Confirmed tools have integration details. Open decisions have need/options/criteria.
**Prompt**: `tasks/WP03-integration-research.md`
**Requirement Refs**: FR-003
**Estimated Prompt Size**: ~400 lines

### Included Subtasks
- [x] T013 Research SuperAdmin integration needs — Google Calendar, Gmail, and identify additional requirements from user stories (RQ-6)
- [x] T014 Research BizOps business system needs — HubSpot and identify CRM, invoicing, order management requirements (RQ-7)
- [x] T015 Research Content Creation tool needs beyond Canva — analyze content requirements from user stories across all teams (RQ-8)
- [x] T016 Research email integration approaches given Tailscale-only and security constraints (RQ-9)
- [x] T017 Consolidate findings into research/integration-needs.md with confirmed tools, open decisions, and per-capability summaries

### Implementation Notes
- External tool docs should be consulted only to the depth needed to answer the research questions
- Where a tool choice hasn't been made, document: what is needed, what options exist, selection criteria
- User stories in the spec (especially the seed stories for Areas B, D, E) are the primary requirements source
- Email integration is particularly constrained by Tailscale-only — research must address this

### Parallel Opportunities
- T013 through T016 can be researched in parallel (different capability areas)
- T017 depends on all prior research

### Dependencies
- None (can start in parallel with WP01 and WP02)

### Risks & Mitigations
- **Kent hasn't chosen tools for some areas**: Document as open decisions — this is expected and acceptable
- **Tool doesn't support Tailscale-only constraint**: Flag as a constraint conflict and document alternatives
- **Integration requires public internet exposure**: Flag as constraint conflict with C-005 (Tailscale-only)

---

## Work Package WP04: Data, Privacy, and Identity Research (Priority: P0)

**Goal**: Research data ownership across Vikunja, OpenClaw, and second brain. Define the SuperAdmin privacy boundary. Map personal brand content domain. Extend the identity model for three business contexts. Answer research questions RQ-10 through RQ-13.
**Independent Test**: Each research question has documented findings. Data ownership is clear per capability area. Privacy boundary is defined. Identity model covers all three contexts.
**Prompt**: `tasks/WP04-data-privacy-identity.md`
**Requirement Refs**: FR-005, FR-008
**Estimated Prompt Size**: ~350 lines

### Included Subtasks
- [x] T018 Research data ownership model: what persists in Vikunja vs OpenClaw vs second brain per capability area (RQ-10)
- [x] T019 Define SuperAdmin privacy boundary relative to 02-Growth/ (excluding _private/ which is absolute) (RQ-11)
- [x] T020 Map personal brand content domain and its location in second brain structure (RQ-12)
- [x] T021 Design identity model extension for personal, Intentional, and metal casework contexts (RQ-13)
- [x] T022 Consolidate findings into research/data-privacy-identity.md

### Implementation Notes
- 02-Growth/_private/ is absolute non-negotiable — research must not weaken this boundary
- Vikunja API docs may be needed (scoped to understanding data model capabilities)
- The identity model in v0.3 covers two identities (personal, intentional) — this extends to three
- Personal brand content domain may be an open decision requiring Kent's input

### Parallel Opportunities
- T018 through T021 can be researched in parallel (different concerns)
- T022 depends on all prior research

### Dependencies
- Depends on WP02 (OpenClaw capabilities inform data ownership decisions)

### Risks & Mitigations
- **Privacy boundary near 02-Growth/ is ambiguous**: Present options to Kent — do not decide unilaterally
- **Personal brand domain overlaps with business content**: Document the overlap and propose clear boundaries
- **Identity model complexity**: Keep it as simple as possible while covering all three contexts

---

## Work Package WP05: User Story Catalog (Priority: P1)

**Goal**: Produce Deliverable 1 — a comprehensive user story catalog across all five capability areas, expanding the seed stories from the research brief using findings from WP01-WP04.
**Independent Test**: Every capability area has user stories covering its described functionality. No obvious capability gaps remain. Stories follow the standard format.
**Prompt**: `tasks/WP05-user-story-catalog.md`
**Requirement Refs**: FR-002
**Estimated Prompt Size**: ~400 lines

### Included Subtasks
- [x] T023 Expand Core Hub (Area A) user stories using OpenClaw capability findings from WP02
- [x] T024 Expand SuperAdmin (Area B) user stories using integration and privacy findings from WP03 and WP04
- [x] T025 Expand Development (Area C) user stories using Claude Code/spec-kitty coordination findings from WP02
- [x] T026 Expand Content Creation (Area D) user stories using tool research from WP03
- [x] T027 Expand BizOps (Area E) user stories using business system research from WP03
- [x] T028 Gap analysis — review catalog for missing capabilities and cross-team interactions
- [x] T029 Produce research/user-story-catalog.md with all stories grouped by capability area

### Implementation Notes
- Start from seed stories in `docs/func-spec/F005_system_architecture_review.md`
- User stories follow format: `As [persona], I want [capability], so that [outcome].`
- Personas: Kent (primary), Felix (the system acting on Kent's behalf)
- Cross-team stories are important — e.g., BizOps requesting content from Content Creation
- Include stories that reflect the new constitution directives (autonomy gates, logging, safety)

### Parallel Opportunities
- T023 through T027 can be drafted in parallel (different capability areas)
- T028-T029 depend on all prior drafts

### Dependencies
- Depends on WP01, WP02, WP03, WP04 (research findings inform story expansion)

### Risks & Mitigations
- **Scope creep in stories**: Stories define desired capabilities, not implementation — keep them outcome-focused
- **Missing cross-team interactions**: Gap analysis (T028) specifically checks for this

---

## Work Package WP06: Integration Map and Agent Team Architecture (Priority: P1)

**Goal**: Produce Deliverables 2 and 3 — the integration map and agent team architecture. These are produced together because the integration map directly informs team scope and agent boundaries.
**Independent Test**: Integration map covers every known external system. Agent team architecture maps correctly to OpenClaw's native concepts. Three-gate autonomy model is applied. Onboarding process for new agents/tools is documented.
**Prompt**: `tasks/WP06-integration-agent-architecture.md`
**Requirement Refs**: FR-003, FR-004, FR-009, FR-010
**Estimated Prompt Size**: ~500 lines

### Included Subtasks
- [x] T030 Compile integration map from WP03 research — organize by capability area with purpose, auth, data flow, constraints
- [x] T031 Design agent team architecture within OpenClaw based on WP02 findings — team names, scope boundaries, agent granularity
- [x] T032 Design orchestration patterns between teams — how Core Hub relates to other teams, cross-team communication
- [x] T033 Apply three-gate autonomy model per team — define progression criteria for each gate
- [x] T034 Design onboarding process for new agents, tools, and integrations into capability areas
- [x] T035 Produce research/integration-map.md and research/agent-team-architecture.md

### Implementation Notes
- Integration map entries: purpose, authentication method, data flow direction, known constraints, open decisions
- Agent architecture must be validated against OpenClaw's actual capabilities (not assumed)
- The autonomy model applies differently per team — Core Hub agents may need stricter gates than Content Creation agents
- Onboarding process supports the extensibility constraint (C-012)

### Parallel Opportunities
- T030 and T031-T034 can be drafted in parallel (different deliverables)
- T035 depends on both streams

### Dependencies
- Depends on WP02, WP03 (OpenClaw capabilities and integration research)

### Risks & Mitigations
- **OpenClaw can't model teams as designed**: Propose alternative modeling within what OpenClaw supports
- **Integration map has many open decisions**: This is expected — document them clearly

---

## Work Package WP07: Data Architecture and Canonical Architecture Document (Priority: P1)

**Goal**: Produce Deliverables 4 and 5 — the data architecture and the v1.0 canonical architecture document that supersedes v0.3. The data architecture feeds directly into the canonical document.
**Independent Test**: Data ownership is clear for every capability area. v1.0 document covers all required sections. Document is non-contradictory with F001-F004 as built. Constitution directives are incorporated throughout.
**Prompt**: `tasks/WP07-data-arch-canonical-doc.md`
**Requirement Refs**: FR-005, FR-006, FR-008, FR-009
**Estimated Prompt Size**: ~500 lines

### Included Subtasks
- [x] T036 Produce data architecture from WP04 research — what lives in Vikunja, second brain, OpenClaw, and action log
- [x] T037 Extend identity model for personal, Intentional, and metal casework contexts
- [x] T038 Draft v1.0 canonical architecture document — vision, capability areas, topology
- [x] T039 Write agent team structure and integration catalog sections using WP06 outputs
- [x] T040 Write data architecture and security architecture sections
- [x] T041 Incorporate constitution directives throughout (narrow scope, earned autonomy, central logging, safety)
- [x] T042 Validate consistency with F001-F004 as built (using WP01 audit)

### Implementation Notes
- v1.0 replaces `docs/design/personal-ai-system-spec-v03.md`
- Output location: `docs/design/personal-ai-system-spec-v1.0.md`
- The document must be self-contained — a reader should understand the full system from this document alone
- Security architecture section must address Tailscale-only, credential management, privacy boundaries
- Data architecture goes to research/data-architecture.md; v1.0 doc goes to docs/design/

### Parallel Opportunities
- T036-T037 (data architecture) can be drafted in parallel with T038 (document structure)
- T039-T042 depend on prior subtasks and WP06 outputs

### Dependencies
- Depends on WP01 (audit), WP04 (data/identity research), WP05 (user stories), WP06 (integration map + agent architecture)

### Risks & Mitigations
- **Document becomes too long**: Structure with clear sections and cross-references rather than duplicating content
- **Inconsistency with existing deployment**: WP01 audit provides the ground truth — always cross-reference
- **Constitution directives conflict with existing patterns**: Document the conflict and propose resolution

---

## Work Package WP08: Feature and Capability Roadmap (Priority: P1)

**Goal**: Produce Deliverable 6 — a phased roadmap organized by capability area showing what is built, foundation completion, and phased capability buildout with dependencies and prerequisite relationships.
**Independent Test**: Roadmap shows F001-F004 as built. New feature numbers are assigned. Dependencies between capabilities are mapped. Phases are realistic given current infrastructure.
**Prompt**: `tasks/WP08-roadmap.md`
**Requirement Refs**: FR-007
**Estimated Prompt Size**: ~350 lines

### Included Subtasks
- [ ] T043 Map F001-F004 to capability areas in the roadmap (what's already built)
- [ ] T044 Define Phase 1: Foundation completion — what must be built before capability areas can grow
- [ ] T045 Define Phase 2: Capability area buildout — prioritized by dependency and business value
- [ ] T046 Define Phase 3: Advanced capabilities — cross-team features, autonomous operations
- [ ] T047 Map dependencies between features and capabilities — prerequisite relationships
- [ ] T048 Produce the roadmap document with feature numbers, priorities, and phase assignments

### Implementation Notes
- Previous F005-F015 numbering is discarded — new feature numbers assigned by this roadmap
- Roadmap must be realistic given: one-person operator, office2 hardware, current services
- Each phase should have clear entry criteria (what must be true before starting)
- The roadmap should indicate which features enable extensibility vs. are extensions themselves
- Output location: to be determined (research/ or docs/design/roadmap/)

### Parallel Opportunities
- T043 (existing features) can be done first, then T044-T046 in parallel
- T047-T048 depend on all phases being defined

### Dependencies
- Depends on WP07 (canonical architecture document — roadmap must be consistent with v1.0)

### Risks & Mitigations
- **Roadmap is too ambitious**: Scope to realistic phases given single operator — flag aspirational items
- **Dependencies create long critical paths**: Identify parallel tracks across capability areas
- **Phase boundaries are unclear**: Define explicit entry/exit criteria for each phase

---

## Dependency Graph

```
WP01: Local Audit ─────────────┐
WP02: OpenClaw Research ───────┤
WP03: Integration Research ────┤──→ WP05: User Stories ──→ WP07: Data Arch + v1.0 Doc ──→ WP08: Roadmap
WP04: Data/Privacy/Identity ───┘──→ WP06: Integration Map + Agent Arch ──┘
   (depends on WP02)
```

**Parallel tracks:**
- WP01, WP02, WP03 can all start simultaneously
- WP04 starts after WP02 completes
- WP05 and WP06 can run in parallel after WP01-WP04 complete
- WP07 depends on WP05 and WP06
- WP08 depends on WP07

## Subtask-to-WP Coverage Matrix

| Subtask | WP | Description |
|---------|-----|-------------|
| T001 | WP01 | Read and catalog v0.3 spec |
| T002 | WP01 | Read and catalog architecture JSON data |
| T003 | WP01 | Read all func-specs (F001-F004) |
| T004 | WP01 | Read all handbooks |
| T005 | WP01 | Read constitution, identify governance gaps |
| T006 | WP01 | Produce audit report |
| T007 | WP02 | Research OpenClaw skills/agents/orchestrators |
| T008 | WP02 | Research OpenClaw logging capabilities |
| T009 | WP02 | Research autonomy gate implementation |
| T010 | WP02 | Research external tool coordination |
| T011 | WP02 | Research identity/persona model |
| T012 | WP02 | Consolidate OpenClaw findings |
| T013 | WP03 | Research SuperAdmin integrations |
| T014 | WP03 | Research BizOps business systems |
| T015 | WP03 | Research Content Creation tools |
| T016 | WP03 | Research email integration |
| T017 | WP03 | Consolidate integration findings |
| T018 | WP04 | Research data ownership model |
| T019 | WP04 | Define SuperAdmin privacy boundary |
| T020 | WP04 | Map personal brand content domain |
| T021 | WP04 | Design identity model extension |
| T022 | WP04 | Consolidate data/privacy/identity findings |
| T023 | WP05 | Expand Core Hub user stories |
| T024 | WP05 | Expand SuperAdmin user stories |
| T025 | WP05 | Expand Development user stories |
| T026 | WP05 | Expand Content Creation user stories |
| T027 | WP05 | Expand BizOps user stories |
| T028 | WP05 | Gap analysis for missing capabilities |
| T029 | WP05 | Produce user story catalog document |
| T030 | WP06 | Compile integration map |
| T031 | WP06 | Design agent team architecture |
| T032 | WP06 | Design cross-team orchestration |
| T033 | WP06 | Apply autonomy model per team |
| T034 | WP06 | Design agent/tool onboarding process |
| T035 | WP06 | Produce integration map + agent architecture docs |
| T036 | WP07 | Produce data architecture document |
| T037 | WP07 | Extend identity model document |
| T038 | WP07 | Draft v1.0 canonical architecture document |
| T039 | WP07 | Write agent team + integration sections |
| T040 | WP07 | Write data architecture + security sections |
| T041 | WP07 | Incorporate constitution directives throughout |
| T042 | WP07 | Validate consistency with F001-F004 |
| T043 | WP08 | Map F001-F004 to roadmap |
| T044 | WP08 | Define Phase 1 foundation completion |
| T045 | WP08 | Define Phase 2 capability buildout |
| T046 | WP08 | Define Phase 3 advanced capabilities |
| T047 | WP08 | Map feature dependencies |
| T048 | WP08 | Produce roadmap document |

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: approved
- WP02: approved
- WP03: approved
- WP04: approved
- WP05: approved
- WP06: approved
- WP07: in_progress
<!-- status-model:end -->
