---
work_package_id: WP08
title: Feature and Capability Roadmap
dependencies:
- WP07
- WP02
- WP05
requirement_refs:
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 005-system-architecture-development-WP08-merge-base
base_commit: 1f2ec33e4a04a3d27a659b527b4a1cd89ef83d0d
created_at: '2026-03-29T04:00:19.325910+00:00'
subtasks:
- T043
- T044
- T045
- T046
- T047
- T048
history:
- timestamp: '2026-03-29T03:15:46Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/roadmap.md/
execution_mode: code_change
mission_id: 01KN5QX3WEJQ6KMCTQ8K1FX4FS
owned_files:
- docs/design/roadmap.md
wp_code: WP08
---

# Work Package Prompt: WP08 – Feature and Capability Roadmap

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP08 --base WP07`

---

## Objective

Produce Deliverable 6: a phased roadmap organized by capability area showing
what has been built (F001-F004), foundation completion, capability area
buildout, and advanced capabilities with dependencies and prerequisite
relationships. The previous F005-F015 numbering is discarded — this roadmap
assigns new feature numbers based on the validated v1.0 architecture.

## Context

The v1.0 canonical architecture document (from WP07) defines the full system.
The roadmap translates that architecture into an implementable sequence of
features and capabilities, phased realistically for a single-operator system
on office2 hardware.

The roadmap must balance:
- Foundation work that enables multiple capability areas
- Quick wins that demonstrate value
- Dependencies between capabilities
- The extensibility principle (build for growth, not just current needs)

## Detailed Guidance

### T043: Map F001-F004 to Capability Areas

**Purpose**: Establish the baseline — what has already been built and which
capability areas it serves.

**Steps**:
1. Map each completed feature to capability area(s):
   - **F001 (Vikunja)**: Core Hub infrastructure + SuperAdmin task store
   - **F002 (OpenClaw)**: Core Hub infrastructure (orchestration engine)
   - **F003 (transcribe-api)**: Core Hub infrastructure (voice processing)
   - **F004 (WhatsApp channel)**: Core Hub infrastructure (communication channel)
2. For each feature, note:
   - What capability it primarily serves
   - What capabilities it enables as a prerequisite
   - What's still missing to make it fully useful for its capability area
3. Identify the current capability coverage:
   - Core Hub: Partially built (infrastructure deployed, no agent teams yet)
   - SuperAdmin: Task store exists, no automation yet
   - Development: No Felix-integrated tooling yet (Claude Code/spec-kitty used manually)
   - Content Creation: No integrations yet
   - BizOps: No integrations yet

---

### T044: Define Phase 1 — Foundation Completion

**Purpose**: Define what must be built to complete the foundation before
capability areas can grow independently.

**Steps**:
1. Identify foundation gaps from the v1.0 architecture:
   - Central action logging (constitution directive, needed by all teams)
   - Agent team structure in OpenClaw (needed before any team can operate)
   - Autonomy gate framework (needed before any agent can advance past Gate 1)
   - Constitution update (incorporate new directives formally)
   - Architecture documentation update (deploy v1.0, retire v0.3)
2. For each foundation item:
   - Assign a new feature number (F006, F007, etc.)
   - Brief description (1-2 sentences)
   - Which capability areas are blocked until this is done
   - Estimated complexity (small, medium, large)
   - Dependencies on other foundation items
3. Define Phase 1 entry criteria: "F005 complete and approved"
4. Define Phase 1 exit criteria: "All foundation features deployed, all teams
   can operate at Gate 1"

---

### T045: Define Phase 2 — Capability Area Buildout

**Purpose**: Define the prioritized buildout of each capability area.

**Steps**:
1. For each capability area, identify the first features needed:
   - **Core Hub (A)**: System self-awareness, agent lifecycle management
   - **SuperAdmin (B)**: Daily briefing, voice note processing, calendar integration
   - **Development (C)**: OpenClaw-integrated development workflows
   - **Content Creation (D)**: Canva integration, content pipeline
   - **BizOps (E)**: HubSpot integration, lead capture
2. Prioritize across capability areas:
   - What delivers the most immediate value to Kent?
   - What has the fewest dependencies?
   - What demonstrates the system's potential most effectively?
3. For each feature:
   - Assign feature numbers
   - Brief description
   - Capability area(s) served
   - Dependencies (within and across areas)
   - Estimated complexity
4. Identify parallel tracks — features across different capability areas
   that can be built simultaneously
5. Define Phase 2 entry criteria: "Phase 1 foundation complete"

---

### T046: Define Phase 3 — Advanced Capabilities

**Purpose**: Define advanced features that build on the Phase 2 foundation.

**Steps**:
1. Identify advanced capabilities from user stories:
   - Cross-team automated workflows
   - Agents at Gate 2 or Gate 3 autonomy
   - Advanced content generation (video, multi-format campaigns)
   - Proactive system behavior (system initiates actions, not just responds)
   - Multi-business orchestration
2. For each advanced capability:
   - Assign feature numbers
   - Brief description
   - Prerequisites from Phase 1 and Phase 2
   - Estimated complexity
3. Note which capabilities depend on open decisions being resolved (e.g.,
   Content Creation tools beyond Canva)
4. Define Phase 3 as aspirational but realistic — flag items that may
   require hardware upgrades or additional services

---

### T047: Map Feature Dependencies

**Purpose**: Create a comprehensive dependency map across all phases.

**Steps**:
1. For every feature in Phases 1-3:
   - List its prerequisites (other features that must be done first)
   - List what it enables (features that depend on it)
2. Identify the critical path — the longest chain of dependencies
3. Identify parallel tracks — independent chains that can be built
   simultaneously across capability areas
4. Check for circular dependencies — resolve if found
5. Produce a dependency graph (text-based, Mermaid, or ASCII)

---

### T048: Produce Roadmap Document

**Purpose**: Compile everything into the roadmap deliverable.

**Steps**:
1. Determine output location (propose `docs/design/roadmap.md` or similar)
2. Structure the document:
   - **Introduction**: Purpose, how to read this roadmap, relationship to v1.0
   - **Current State**: F001-F004 mapped to capability areas (from T043)
   - **Phase 1: Foundation** (from T044)
     - Feature list with numbers, descriptions, dependencies
     - Entry/exit criteria
     - Estimated sequence
   - **Phase 2: Capability Buildout** (from T045)
     - Feature list organized by capability area
     - Prioritization rationale
     - Parallel tracks
   - **Phase 3: Advanced Capabilities** (from T046)
     - Feature list with prerequisites
     - Aspirational items noted
   - **Dependency Graph** (from T047)
   - **Open Decisions**: Features that depend on unresolved tool/integration choices
   - **Constraints and Assumptions**: Hardware limits, single operator, etc.
3. Include a summary table: all features with phase, area, priority, dependencies

**Output file**: Location to be confirmed (suggest `docs/design/roadmap.md`)

---

## Definition of Done

- [ ] F001-F004 mapped to capability areas
- [ ] Phase 1 foundation features defined with feature numbers
- [ ] Phase 2 capability buildout features defined and prioritized
- [ ] Phase 3 advanced capabilities defined
- [ ] Dependency graph complete — no circular dependencies
- [ ] Critical path and parallel tracks identified
- [ ] Roadmap document produced
- [ ] All feature numbers are new (previous F005-F015 numbering discarded)
- [ ] Roadmap is realistic for single operator on office2 hardware

## Risks

- **Roadmap is too ambitious**: Phase 3 is aspirational — mark items that may not be feasible
- **Dependencies create a long serial chain**: Maximize parallel tracks across capability areas
- **Hardware limitations not considered**: Note items that may require upgrades
- **Open decisions block planning**: Features depending on unresolved choices are marked clearly

## Reviewer Guidance

Verify that:
- Every capability area has features in at least Phase 1 and Phase 2
- Dependencies are accurate and complete
- Phase entry/exit criteria are clear
- The roadmap is realistic (not a wishlist)
- Open decisions are explicitly linked to affected features
- The previous F005-F015 numbering is not used anywhere

## Activity Log

- 2026-03-29T04:00:19Z – claude – shell_pid=67938 – lane=doing – Assigned agent via workflow command
- 2026-03-29T04:02:31Z – claude – shell_pid=67938 – lane=for_review – Ready for review: 23 features across 3 phases. F006-F010 foundation, F011-F018 capability buildout (4 parallel tracks), F019-F028 advanced. Critical path identified. 5 open decisions mapped to blocked features. Previous numbering discarded.
- 2026-03-29T04:02:38Z – claude – shell_pid=68664 – lane=doing – Started review via workflow command
- 2026-03-29T04:02:55Z – claude – shell_pid=68664 – lane=approved – Review passed: 23 features across 3 phases with new numbering. Dependency graph is clean (no cycles). Critical path and shortest-path-to-value identified. Parallel tracks maximize throughput. Open decisions mapped to blocked features — Phase 1/2 core tracks are unblocked. Realistic constraints documented.
