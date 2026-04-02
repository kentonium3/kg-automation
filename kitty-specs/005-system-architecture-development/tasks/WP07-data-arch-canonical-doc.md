---
work_package_id: WP07
title: Data Architecture and Canonical Architecture Document
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-006
- FR-008
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 005-system-architecture-development-WP01
base_commit: 325bb965119e74f43543db7511a3b1891f69a97b
created_at: '2026-03-29T03:55:42.107133+00:00'
subtasks:
- T036
- T037
- T038
- T039
- T040
- T041
- T042
history:
- timestamp: '2026-03-29T03:15:46Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: kitty-specs/005-system-architecture-development/
execution_mode: planning_artifact
mission_id: 01KN5QX3WEJQ6KMCTQ8K1FX4FS
owned_files:
- kitty-specs/005-system-architecture-development/**
wp_code: WP07
---

# Work Package Prompt: WP07 – Data Architecture and Canonical Architecture Document

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP07 --base WP06`

---

## Objective

Produce Deliverables 4 and 5: the data architecture document and the v1.0
canonical architecture document that supersedes
`docs/design/personal-ai-system-spec-v03.md`. This is the culmination of
all research — synthesizing the audit, OpenClaw capabilities, integrations,
agent architecture, user stories, and data/privacy findings into the new
authoritative architecture document.

## Context

All research WPs (WP01-WP04) and synthesis WPs (WP05-WP06) feed into this
work package. The v1.0 document must be self-contained — a reader should
understand the full Felix system from this document alone. It must be
non-contradictory with F001-F004 as built and incorporate the new constitution
directives throughout.

**Output locations**:
- Data architecture: `kitty-specs/005-system-architecture-development/research/data-architecture.md`
- v1.0 document: `docs/design/personal-ai-system-spec-v1.0.md`

## Detailed Guidance

### T036: Produce Data Architecture Document (Deliverable 4)

**Purpose**: Formalize the data architecture from WP04 research into a
standalone deliverable.

**Steps**:
1. Pull findings from WP04's `research/data-privacy-identity.md`
2. Structure the data architecture:
   - **Vikunja**: Tasks, projects, labels, metadata — what lives here and why
   - **Second brain**: Content, context, constitution — access rules, boundaries
   - **OpenClaw**: Skills, sessions, agent state — what OpenClaw owns
   - **Central action log**: Location, format, retention, query patterns
3. For each data store:
   - What capability areas are producers vs consumers
   - Access patterns (real-time, batch, on-demand)
   - Retention policies
   - Backup and recovery
4. Include data flow diagrams (text-based, e.g., ASCII or Mermaid)
5. Include the privacy boundary model from WP04

**Output file**: `research/data-architecture.md`

---

### T037: Extend Identity Model Document

**Purpose**: Formalize the identity model extension from WP04 into the data
architecture.

**Steps**:
1. Pull identity model findings from WP04
2. Document:
   - Personal identity (Kent Gale) — scope, channels, content
   - Intentional LLC identity — scope, channels, content, CRM
   - Metal casework identity — scope, channels, content, CRM
3. Define how identities interact with:
   - OpenClaw personas/configuration
   - Channel routing (WhatsApp, email)
   - Content generation (branding, tone)
   - CRM/business system separation
4. Include identity in the data architecture document

---

### T038: Draft v1.0 Canonical Architecture Document Structure

**Purpose**: Create the document structure and write the high-level sections.

**Steps**:
1. Create `docs/design/personal-ai-system-spec-v1.0.md`
2. Document structure:
   - **Vision and Framing**: Felix as an AI-assisted personal operating system
   - **Five Capability Areas**: Core Hub, SuperAdmin, Development, Content
     Creation, BizOps
   - **Physical Topology**: office2, MacBook Pro, iPhone — unchanged hardware
   - **Logical Architecture**: OpenClaw as orchestration engine, five teams
   - **Agent Team Structure**: From WP06
   - **Integration Catalog**: From WP06
   - **Data Architecture**: From T036
   - **Security Architecture**: Updated for expanded scope
   - **Identity Model**: From T037
   - **Constitution and Governance**: Updated directives
   - **Phased Implementation Approach**: Overview (roadmap in WP08)
3. Write the Vision and Framing section:
   - Felix origin and purpose
   - What exists today (F001-F004, from WP01 audit)
   - The expanded vision
   - Design principles (extensibility, narrow scope, earned autonomy)

---

### T039: Write Agent Team and Integration Sections

**Purpose**: Incorporate WP06 deliverables into the v1.0 document.

**Steps**:
1. Pull from WP06's `research/agent-team-architecture.md`:
   - Write the Agent Team Structure section
   - Include team definitions, scope boundaries, agent inventory
   - Include orchestration patterns
   - Include autonomy model
2. Pull from WP06's `research/integration-map.md`:
   - Write the Integration Catalog section
   - Include confirmed integrations with details
   - Include open decisions (marked clearly)
3. Ensure consistency between the two sections

---

### T040: Write Data Architecture and Security Sections

**Purpose**: Incorporate data architecture and write the security section.

**Steps**:
1. Pull from T036's data architecture:
   - Write the Data Architecture section in v1.0
   - Include data ownership, flows, retention
   - Include privacy boundaries
2. Write the Security Architecture section:
   - **Network**: Tailscale-only — no public exposure
   - **Credentials**: No credentials in code, credential store model
   - **Agent security**: Narrow scope, autonomy gates, action logging
   - **Privacy**: 02-Growth/_private/ absolute boundary, tiered access elsewhere
   - **Exception policy**: Formal process with rationale, scope, expiration
3. Include the identity model from T037

---

### T041: Incorporate Constitution Directives Throughout

**Purpose**: Ensure the four new constitution directives are reflected in every
relevant section of the v1.0 document.

**Steps**:
1. Review each section of the v1.0 document for:
   - **Narrow agent scope (C-010)**: Is scope enforced in team architecture?
   - **Earned autonomy (C-009)**: Is the three-gate model in the governance section?
   - **Central action logging (C-011)**: Is logging in the data architecture?
   - **Safety parameters (Directive D)**: Are boundaries in the security section?
2. Add explicit references to these directives where they apply
3. Ensure no section contradicts these directives
4. Write the Constitution and Governance section:
   - Current constitution (reference)
   - New directives to be incorporated
   - How they affect each capability area

---

### T042: Validate Consistency with F001-F004

**Purpose**: Final consistency check — the v1.0 document must not contradict
what has been built.

**Steps**:
1. Pull the audit findings from WP01's `research/local-audit.md`
2. For each deployed service (Vikunja, OpenClaw, transcribe-api, WhatsApp):
   - Verify it appears correctly in v1.0's topology section
   - Verify ports, protocols, access controls match reality
   - Verify credentials are referenced correctly
3. For each architectural decision in F001-F004:
   - Verify v1.0 is consistent (or explicitly notes where v1.0 supersedes)
4. For the Baileys exception:
   - Verify it appears in the exception policy
   - Verify the WhatsApp channel is documented correctly
5. Document any inconsistencies found and resolve them

---

## Definition of Done

- [ ] Data architecture document produced in `research/data-architecture.md`
- [ ] Identity model extended and documented
- [ ] v1.0 canonical architecture document produced at `docs/design/personal-ai-system-spec-v1.0.md`
- [ ] All required sections written (vision, capability areas, topology, teams, integrations, data, security, identity, governance, phased approach)
- [ ] Constitution directives incorporated throughout
- [ ] Consistency with F001-F004 validated — no contradictions
- [ ] Document is self-contained — a reader can understand the full system

## Risks

- **Document becomes unwieldy**: Use clear section structure and cross-references
- **Inconsistency with existing deployment**: WP01 audit is the ground truth
- **Open decisions make the document feel incomplete**: Clearly mark them — this is acceptable for a v1.0 that will be iterated

## Reviewer Guidance

Verify that:
- The document is self-contained and coherent
- No section contradicts another
- F001-F004 deployed state is accurately represented
- Constitution directives appear in every relevant section
- Open decisions are clearly marked (not hidden as assumptions)
- The document could be handed to a new team member as the complete system reference

## Activity Log

- 2026-03-29T03:55:42Z – claude – shell_pid=66703 – lane=doing – Assigned agent via workflow command
- 2026-03-29T03:59:25Z – claude – shell_pid=66703 – lane=for_review – Ready for review: data architecture document + v1.0 canonical architecture document. v1.0 covers all 11 required sections, incorporates 4 constitution directives, validated consistent with F001-F004. 8 open decisions documented for Kent.
- 2026-03-29T03:59:37Z – claude – shell_pid=67722 – lane=doing – Started review via workflow command
- 2026-03-29T03:59:57Z – claude – shell_pid=67722 – lane=approved – Review passed: v1.0 document covers all 11 required sections. Consistent with F001-F004 deployed state. All 4 constitution directives incorporated throughout (design principles, agent architecture, security, data architecture). Self-contained and coherent. 8 open decisions clearly documented.
