---
work_package_id: WP03
title: Integration and Tool Research
lane: "doing"
dependencies: []
requirement_refs:
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: cd735ae94882c2248543139e182847a72002ec2f
created_at: '2026-03-29T03:32:11.498031+00:00'
subtasks:
- T013
- T014
- T015
- T016
- T017
shell_pid: "61173"
history:
- timestamp: '2026-03-29T03:15:46Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP03 – Integration and Tool Research

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP03`

---

## Objective

Research integration needs across all five capability areas. Answer research
questions RQ-6 through RQ-9. For confirmed tools, document the integration
approach. For tools where a choice hasn't been made, document the open decision
with need, options, and criteria.

## Context

The expanded vision requires integrations across SuperAdmin (calendar, email),
Development (Claude Code, spec-kitty — already answered), Content Creation
(Canva confirmed, others TBD), and BizOps (HubSpot mentioned, others TBD).
All integrations must respect the Tailscale-only constraint — no public
internet exposure for services.

External tool investigation is scoped to only what's needed to answer the
research questions. Do not do deep dives into tools that haven't been selected.

## Detailed Guidance

### T013: SuperAdmin Integrations (RQ-6)

**Purpose**: Identify all integrations needed for the SuperAdmin (Area B)
capability area.

**Steps**:
1. Review SuperAdmin user stories from the spec and research brief:
   - Voice note capture, classification, routing
   - Daily briefing delivery via WhatsApp
   - Overdue commitment escalation
   - Meeting scheduling via natural language
   - Email triage and summarization
   - To-do/calendar coordination
   - Interactive task negotiation
   - Repeating task/appointment reminders via WhatsApp
   - Track record reporting
2. For each story, identify what integrations are needed:
   - **Google Calendar**: scheduling, availability, event management
   - **Gmail**: email triage, summarization, draft creation
   - **WhatsApp** (already integrated via F004): briefings, reminders, alerts
   - **Vikunja** (already integrated via F001): task management, priorities
   - **Others?**: Identify any additional integrations needed
3. For each integration, document:
   - Purpose (what capability it enables)
   - Authentication method (OAuth2, API key, etc.)
   - Data flow direction (read, write, bidirectional)
   - Known constraints (Tailscale-only, rate limits, etc.)
4. Flag open decisions where tool choice hasn't been made

**Output**: SuperAdmin integration requirements

---

### T014: BizOps Business Systems (RQ-7)

**Purpose**: Identify business systems needed for BizOps (Area E).

**Steps**:
1. Review BizOps user stories from the spec and research brief:
   - Lead capture from website to CRM
   - Marketing campaign planning and execution
   - Blog post scheduling across platforms
   - Weekly business reports
   - Prospect communications
   - Customer support
   - Order management
   - Invoicing
2. Identify required system categories:
   - **CRM**: HubSpot is mentioned — research what HubSpot provides
   - **Invoicing**: What does Kent currently use or plan to use? (open decision)
   - **Order management**: For metal casework — what's needed? (open decision)
   - **Marketing automation**: Is HubSpot sufficient or is a separate tool needed?
   - **Social media management**: LinkedIn, Instagram posting (open decision)
3. For confirmed tools (HubSpot): document integration approach
4. For open decisions: document need, options (at least 2-3), selection criteria

**Output**: BizOps integration requirements with confirmed and open decisions

---

### T015: Content Creation Tools (RQ-8)

**Purpose**: Identify AI tools needed for Content Creation (Area D) beyond Canva.

**Steps**:
1. Review Content Creation user stories from the spec and research brief:
   - Blog post drafting
   - Presentation creation from briefs
   - Multi-format content generation (blog, LinkedIn, white paper, Instagram, email)
   - Video content for LinkedIn/Instagram
   - Conceptual diagrams and graphics generation
2. Map each content type to tool requirements:
   - **Canva** (confirmed): graphics, presentations, some social media content
   - **Text generation**: Claude/Anthropic API (already locked as direct)
   - **Diagram generation**: What tools can produce architecture diagrams,
     conceptual visuals? (open decision)
   - **Video generation/editing**: What tools are available? (open decision)
   - **Social media scheduling**: Cross-platform posting capability (open decision)
3. For open decisions: document need, options, selection criteria
4. Note which tools serve multiple teams (Content Creation is a shared service)

**Output**: Content Creation tool requirements with confirmed and open decisions

---

### T016: Email Integration Approach (RQ-9)

**Purpose**: Determine the right approach to email integration given the
Tailscale-only security constraint.

**Steps**:
1. Identify email integration needs:
   - Gmail reading (triage, summarization) — SuperAdmin
   - Gmail sending (drafts, replies) — SuperAdmin
   - Email marketing (campaigns) — BizOps
2. Research integration approaches:
   - **Gmail API via OAuth2**: Can this work with Tailscale-only? (OAuth
     callback needs to reach the server)
   - **Gmail API via service account**: Does this bypass the callback issue?
   - **IMAP/SMTP**: Traditional approach — works behind Tailscale?
   - **OpenClaw Gmail channel/skill**: Does OpenClaw have native email support?
3. Assess each approach against constraints:
   - Tailscale-only (no public internet exposure)
   - Security (credentials, token storage)
   - Functionality (read, send, search, labels)
4. Recommend an approach or document the decision with options

**Output**: Email integration decision or open decision with options

---

### T017: Consolidate Integration Findings

**Purpose**: Produce a single research document with all integration findings.

**Steps**:
1. Create `kitty-specs/005-system-architecture-development/research/integration-needs.md`
2. Structure by capability area:
   - **Core Hub (A)**: Internal system integrations (already built)
   - **SuperAdmin (B)**: From T013
   - **Development (C)**: Claude Code + spec-kitty (already answered in spec)
   - **Content Creation (D)**: From T015
   - **BizOps (E)**: From T014
3. Include a cross-cutting section for email (T016)
4. For each integration entry: purpose, auth, data flow, constraints, status
   (confirmed/open decision)
5. Include an "Open Decisions Summary" table listing all unresolved tool choices

**Output file**: `kitty-specs/005-system-architecture-development/research/integration-needs.md`

---

## Definition of Done

- [ ] All four research questions (RQ-6 through RQ-9) answered
- [ ] Every capability area has integration needs documented
- [ ] Confirmed tools have integration details (purpose, auth, data flow)
- [ ] Open decisions documented with need, options, and selection criteria
- [ ] Email integration approach assessed against Tailscale-only constraint
- [ ] Findings consolidated in `research/integration-needs.md`

## Risks

- **Many open decisions**: This is expected — document them clearly rather than guessing
- **Tailscale-only conflicts with OAuth callbacks**: Research alternative auth flows
- **Tool landscape changes rapidly**: Document current state, note that options may evolve

## Reviewer Guidance

Verify that:
- Every user story in the spec has its integration needs addressed
- Open decisions have at least 2-3 options with clear criteria
- Tailscale-only constraint is checked for every integration
- No tool choice is assumed without explicit confirmation from Kent
