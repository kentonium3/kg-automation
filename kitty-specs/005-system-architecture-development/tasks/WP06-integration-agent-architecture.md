---
work_package_id: WP06
title: Integration Map and Agent Team Architecture
lane: "doing"
dependencies:
- WP02
- WP03
requirement_refs:
- FR-003
- FR-004
- FR-009
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 005-system-architecture-development-WP06-merge-base
base_commit: 89af6f0c50cf069f2e5a82d694a17db19d57d7d3
created_at: '2026-03-29T03:50:26.502803+00:00'
subtasks:
- T030
- T031
- T032
- T033
- T034
- T035
agent: "claude"
shell_pid: "66468"
history:
- timestamp: '2026-03-29T03:15:46Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP06 – Integration Map and Agent Team Architecture

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP06 --base WP03`

---

## Objective

Produce Deliverables 2 and 3: the integration map and agent team architecture.
These are produced together because integration requirements directly inform
team scope boundaries and agent design.

## Context

WP02 provides OpenClaw's native capabilities (how teams, skills, agents,
orchestrators work). WP03 provides integration needs per capability area.
This WP synthesizes both into a concrete integration map and a proposed
agent team architecture.

## Detailed Guidance

### T030: Compile Integration Map (Deliverable 2)

**Purpose**: Produce a complete map of every external system, API, or service
that needs integration.

**Steps**:
1. Pull integration findings from WP03's `research/integration-needs.md`
2. Organize by capability area:
   - **Core Hub (A)**: Internal system integrations (Vikunja API, OpenClaw
     internal, GitHub, Tailscale)
   - **SuperAdmin (B)**: Google Calendar, Gmail, WhatsApp (existing),
     Vikunja (existing), plus any additional
   - **Development (C)**: Claude Code, spec-kitty, GitHub
   - **Content Creation (D)**: Canva, plus TBD tools
   - **BizOps (E)**: HubSpot, plus TBD business systems
3. For each integration entry, document:
   - **Purpose**: What capability it enables
   - **Authentication**: OAuth2, API key, service account, session, etc.
   - **Data flow**: Read, write, bidirectional
   - **Constraints**: Tailscale-only compatibility, rate limits, cost
   - **Status**: Confirmed, open decision, or already integrated
4. Include cross-cutting integrations (e.g., email used by multiple teams)
5. Include an "Open Decisions" section for unresolved tool choices

---

### T031: Design Agent Team Architecture (Deliverable 3 — structure)

**Purpose**: Design the five agent teams within OpenClaw based on capability
research.

**Steps**:
1. Using WP02's OpenClaw capability findings, design:
   - **Team names**: Core Hub, SuperAdmin, Development, Content Creation, BizOps
   - **Scope boundaries**: What each team owns and doesn't own
   - **How teams map to OpenClaw concepts**: Skills, agents, orchestrators,
     namespaces, or whatever modeling approach WP02 recommended
2. For each team, define:
   - Team orchestrator (if applicable)
   - Agent inventory (narrow-scope agents within the team)
   - Skills used by the team
   - Integration touchpoints
3. Keep agents narrow in scope per constitution directive C-010
4. Each agent should have one clearly defined responsibility

---

### T032: Design Cross-Team Orchestration Patterns

**Purpose**: Define how teams interact and how Core Hub relates to other teams.

**Steps**:
1. Define orchestration patterns:
   - How does Core Hub coordinate the other four teams?
   - How do teams request services from each other (e.g., BizOps → Content Creation)?
   - What is the escalation path when a team can't handle a request?
2. Define communication patterns:
   - Event-driven (one team emits, others subscribe)?
   - Request-response (one team calls another)?
   - Orchestrated (Core Hub mediates all cross-team interactions)?
3. Consider the user stories — what cross-team interactions are needed?
4. Document the patterns with concrete examples

---

### T033: Apply Three-Gate Autonomy Model Per Team

**Purpose**: Define how the autonomy model applies to each team and its agents.

**Steps**:
1. For each team, define:
   - **Default gate**: All agents start at Gate 1 (Human In The Middle)
   - **Progression criteria**: What must be true to advance to Gate 2, then Gate 3
   - **Gate-specific behavior**: What actions are allowed at each gate
2. Consider that different teams may have different risk profiles:
   - Core Hub (system modification): Higher risk → stricter progression
   - Content Creation (drafting content): Lower risk → faster progression possible
   - BizOps (customer communications): Medium risk → careful progression
3. Using WP02's findings on OpenClaw autonomy support, map gates to
   OpenClaw's actual mechanisms
4. Define what "earned autonomy" means in practice — metrics, time periods,
   review checkpoints

---

### T034: Design Agent/Tool Onboarding Process

**Purpose**: Define how new agents, tools, and integrations are added to
capability areas — supporting the extensibility constraint.

**Steps**:
1. Define the onboarding lifecycle:
   - How is a new agent proposed and approved?
   - How is a new tool integration added?
   - How is a new capability area created (if ever needed)?
2. Define configuration patterns:
   - Where does agent configuration live?
   - How are skills registered?
   - How are integrations connected?
3. Define validation requirements:
   - What must be true before a new agent goes live?
   - What testing/validation is required?
   - Who approves the addition?
4. This process should be simple enough to not impede growth but
   structured enough to maintain system integrity

---

### T035: Produce Deliverable Documents

**Purpose**: Write the integration map and agent team architecture documents.

**Steps**:
1. Create `kitty-specs/005-system-architecture-development/research/integration-map.md`
   - Structured by capability area
   - Integration entries with all required fields
   - Open decisions summary table
2. Create `kitty-specs/005-system-architecture-development/research/agent-team-architecture.md`
   - Team definitions with scope boundaries
   - Agent inventory per team
   - Cross-team orchestration patterns
   - Autonomy model per team
   - Onboarding process
3. Both documents should cross-reference each other

**Output files**:
- `research/integration-map.md`
- `research/agent-team-architecture.md`

---

## Definition of Done

- [ ] Integration map covers every known external system
- [ ] Every integration entry has purpose, auth, data flow, constraints, status
- [ ] Agent team architecture maps to OpenClaw's actual capabilities
- [ ] Five teams defined with scope boundaries and agent inventories
- [ ] Cross-team orchestration patterns documented with examples
- [ ] Three-gate autonomy model applied per team with progression criteria
- [ ] Agent/tool onboarding process defined
- [ ] Both deliverable documents written to `research/`

## Risks

- **OpenClaw modeling limitations**: If teams can't be modeled cleanly, document the trade-offs
- **Too many agents per team**: Start narrow — agents can be added later (extensibility)
- **Autonomy gates are impractical**: Ensure gates map to real OpenClaw mechanisms

## Reviewer Guidance

Verify that:
- Integration map has no gaps — every user story's integration need is covered
- Agent scope is narrow (one responsibility per agent) per constitution
- Cross-team patterns are concrete, not abstract
- Autonomy model is practical and maps to OpenClaw capabilities
- Onboarding process supports extensibility without sacrificing governance

## Activity Log

- 2026-03-29T03:50:26Z – claude – shell_pid=65140 – lane=doing – Assigned agent via workflow command
- 2026-03-29T03:54:24Z – claude – shell_pid=65140 – lane=for_review – Ready for review: Integration map with 30+ entries and 12 open decisions. Agent team architecture with 5 teams, 16 agents, 4 orchestration patterns, 3-gate autonomy model, onboarding process, and communication matrix.
- 2026-03-29T03:54:50Z – claude – shell_pid=66468 – lane=doing – Started review via workflow command
