---
work_package_id: WP04
title: Data, Privacy, and Identity Research
dependencies:
- WP02
requirement_refs:
- FR-005
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 005-system-architecture-development-WP02
base_commit: 429c23da90bbb24066fe016b559802b83057cf05
created_at: '2026-03-29T03:45:30.558195+00:00'
subtasks:
- T018
- T019
- T020
- T021
- T022
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
wp_code: WP04
---

# Work Package Prompt: WP04 – Data, Privacy, and Identity Research

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP04 --base WP02`

---

## Objective

Research data ownership across the system's data stores, define privacy
boundaries for SuperAdmin, map the personal brand content domain, and extend
the identity model for three business contexts. Answer research questions
RQ-10 through RQ-13.

## Context

The system has three primary data stores: Vikunja (tasks), OpenClaw (agent
state, sessions, skills), and the second brain (Obsidian vault — content,
context, constitution). The expanded vision requires clear data ownership per
capability area. The privacy boundary on `02-Growth/_private/` is absolute
and non-negotiable. The identity model currently covers two contexts (personal,
Intentional) and must extend to three (adding metal casework).

This WP depends on WP02 because OpenClaw's data storage capabilities (from
the capability research) inform data ownership decisions.

## Detailed Guidance

### T018: Data Ownership Model (RQ-10)

**Purpose**: Define what data persists in each data store, organized by
capability area.

**Steps**:
1. Catalog current data stores and their roles:
   - **Vikunja**: Tasks, projects, labels, metadata, comments
   - **OpenClaw**: Skills, sessions, agent state, conversation history,
     credentials (Baileys session)
   - **Second brain**: Content, context documents, constitution, notes,
     journal entries
   - **Central action log**: To be defined (may be in OpenClaw, Vikunja,
     or separate)
2. Using WP02's OpenClaw capability findings, determine:
   - What data OpenClaw stores natively vs. what must be external
   - Whether OpenClaw's storage is suitable for action logging
3. For each capability area, define data ownership:
   - **Core Hub (A)**: System configuration, deployment state, action logs
   - **SuperAdmin (B)**: Task priorities, calendar state, email summaries,
     briefing history
   - **Development (C)**: Spec-kitty artifacts, code repos (external to Felix)
   - **Content Creation (D)**: Generated content, templates, brand assets
   - **BizOps (E)**: CRM data, campaign state, reports, invoicing records
4. For each data item: which store owns it, access pattern, retention

**Output**: Data ownership model per capability area

---

### T019: SuperAdmin Privacy Boundary (RQ-11)

**Purpose**: Define the scope boundary for SuperAdmin relative to the second
brain's privacy zones.

**Steps**:
1. Review the second brain structure:
   - `~/second-brain/vault/Notes/` with numbered folders 00-07
   - `01-Constitution/` — agent context ceiling (agents can read this)
   - `02-Growth/_private/` — ABSOLUTE PRIVACY BOUNDARY (never agent-accessible)
   - Other 02-Growth/ areas — boundary TBD
2. Define clear rules for SuperAdmin access:
   - What in the second brain can SuperAdmin read?
   - What can SuperAdmin write?
   - What is off-limits beyond _private/?
   - How are boundary violations detected and prevented?
3. Consider the user stories:
   - Personal brand management may touch second brain content
   - Research on topics of interest may read from notes
   - Reminders and task management don't need second brain access
4. Propose a tiered access model or clear boundary definition
5. **CRITICAL**: Do not weaken the `02-Growth/_private/` absolute boundary.
   Present options for other areas to Kent — do not decide unilaterally.

**Output**: Privacy boundary definition with access rules

---

### T020: Personal Brand Content Domain (RQ-12)

**Purpose**: Define what constitutes "personal brand" content and where it
lives in the system.

**Steps**:
1. Review user stories related to personal brand:
   - Blog posts, LinkedIn posts, white papers
   - Marketing materials
   - Presentations
   - Professional presence management
2. Determine where brand content should live:
   - In the second brain (alongside other knowledge)?
   - In a dedicated content store?
   - In the CRM/marketing system?
   - Split across multiple stores?
3. Consider:
   - Content Creation (Area D) produces this content
   - BizOps (Area E) distributes it
   - SuperAdmin (Area B) manages personal brand strategy
   - Multiple teams need access
4. This may be an open decision requiring Kent's input — document options
   with pros/cons if so

**Output**: Personal brand content domain definition (or open decision)

---

### T021: Identity Model Extension (RQ-13)

**Purpose**: Extend the identity model from two contexts (personal, Intentional)
to three (adding metal casework).

**Steps**:
1. Review current identity model in v0.3 spec:
   - Personal identity (Kent Gale)
   - Intentional LLC identity (business)
2. Define what the metal casework identity requires:
   - Separate business branding?
   - Separate email/communications?
   - Separate CRM/customer base?
   - Separate content/marketing?
3. Using WP02's findings on OpenClaw persona support, design:
   - How identities map to OpenClaw configuration
   - How identity affects channel routing (e.g., WhatsApp messages)
   - How identity affects content generation (branding, tone, templates)
4. Consider cross-identity interactions:
   - Kent is the operator across all identities
   - Some tools may be shared (e.g., same CRM, different pipelines)
   - Some content may span identities (personal brand vs. business brand)

**Output**: Extended identity model covering three contexts

---

### T022: Consolidate Data/Privacy/Identity Findings

**Purpose**: Produce a single research document with all findings.

**Steps**:
1. Create `kitty-specs/005-system-architecture-development/research/data-privacy-identity.md`
2. Structure the document:
   - **Data Ownership Model** — from T018
   - **Privacy Boundary Definition** — from T019
   - **Personal Brand Content Domain** — from T020
   - **Extended Identity Model** — from T021
3. For each section, include Decision/Rationale/Alternatives where applicable
4. Flag open decisions that need Kent's input

**Output file**: `kitty-specs/005-system-architecture-development/research/data-privacy-identity.md`

---

## Definition of Done

- [ ] Data ownership defined for all five capability areas across all data stores
- [ ] SuperAdmin privacy boundary defined with clear access rules
- [ ] 02-Growth/_private/ absolute boundary preserved without weakening
- [ ] Personal brand content domain defined or documented as open decision
- [ ] Identity model extended to cover personal, Intentional, and metal casework
- [ ] Findings consolidated in `research/data-privacy-identity.md`

## Risks

- **Privacy boundary ambiguity near 02-Growth/**: Present options to Kent — never decide unilaterally
- **Data ownership conflicts between teams**: Establish clear "owner" vs "consumer" relationships
- **Identity model adds unwanted complexity**: Keep as simple as possible for three contexts

## Reviewer Guidance

Verify that:
- 02-Growth/_private/ boundary is absolute and unweakened
- Data ownership has no ambiguous items (every data type has a clear owner)
- Identity model is practical (not theoretical) — maps to real configuration
- Open decisions are clearly flagged for Kent's input

## Activity Log

- 2026-03-29T03:45:30Z – claude – shell_pid=63902 – lane=doing – Assigned agent via workflow command
- 2026-03-29T03:48:20Z – claude – shell_pid=63902 – lane=for_review – Ready for review: data ownership model across 4 stores, tiered privacy boundary with absolute 02-Growth/_private/ preserved, personal brand mapped as cross-cutting, identity model extended to 3 contexts. 8 open items for Kent documented.
- 2026-03-29T03:48:35Z – claude – shell_pid=64682 – lane=doing – Started review via workflow command
- 2026-03-29T03:48:43Z – claude – shell_pid=64682 – lane=approved – Review passed: Data ownership model covers all 5 areas across 4 stores. Privacy boundary is robust (4-level enforcement, allowlist approach, absolute _private/ preserved). Identity model extends cleanly to 3 contexts via Vikunja labels. 8 open items for Kent are well-structured configuration decisions, not architectural blockers.
