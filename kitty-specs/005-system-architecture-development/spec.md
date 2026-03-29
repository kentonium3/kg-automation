# Feature Specification: System Architecture Development

**Feature Branch**: `005-system-architecture-development`
**Created**: 2026-03-29
**Status**: Draft
**Mission**: Research
**Input**: `docs/func-spec/F005_system_architecture_review.md` — research brief describing expanded vision

## Overview

This is a research mission. No code will be written. No services will be deployed.
The deliverable is a validated architecture document and phased roadmap that
becomes the authoritative input for all future feature specifications.

The current architecture spec (v0.3) was written as a personal accountability
and task management system. Kent has articulated a significantly broader vision
for an AI-assisted personal operating system called **Felix** — named after
Felix the Cat's magic bag. Felix encompasses five capability areas, each with
its own agent team, spanning system infrastructure, executive assistance,
application development, content creation, and business operations.

**The output of this research project becomes the new canonical architecture
document and roadmap. No new feature specs will be written until this is
complete and approved.**

## Background: What Exists Today

### Implemented (F001-F004)

| Feature | What Was Built | Status |
|---------|---------------|--------|
| F001 | Vikunja (Docker, port 3456, Tailscale-only) | Complete |
| F002 | OpenClaw (npm-global, port 18789/127.0.0.1) | Complete |
| F003 | transcribe-api (Docker, port 8787, Tailscale-only) | Complete |
| F004 | WhatsApp channel (Baileys, personal number, QR paired) | Complete |

### Key Architectural Decisions (Locked)

- **OpenClaw** is the orchestration engine
- **Vikunja** is the task store
- **Anthropic API direct** — no LiteLLM, no proxy
- **Tailscale-only** for all services
- **office2** is the always-on hub
- **Baileys** for WhatsApp (accepted exception, documented in constitution)
- **02-Growth/_private/** is never agent-accessible — absolute, non-negotiable

### Current Spec Document

`docs/design/personal-ai-system-spec-v03.md` — this document is the current
canonical reference but must be superseded by the output of this research.

## The Expanded Vision: Felix

Felix is the AI-assisted personal operating system as a whole — the complete
system comprising five capability areas and their associated agent teams.

### Capability Area A: Core Hub — System Infrastructure

The team that builds, operates, and extends Felix. Core Hub is the
infrastructure team.

**In scope:**
- Research, design, development, implementation, testing, operation, security,
  and governance of the automation system itself
- Full awareness of the system's own configuration and capabilities
- Agents that can safely modify and extend capabilities at Kent's direction
- Self-documenting — the system knows what it can do

### Capability Area B: SuperAdmin — Executive Digital Assistant

Kent's personal executive function layer. SuperAdmin performs executive and
personal administrative functions within the system created and maintained
by Core Hub and Kent.

**In scope:**
- Priority and commitment management
- Communications and email
- Calendar management
- Research on topics of interest
- Personal brand management
- Generation of materials and artifacts
- Anything related to Kent's personal functioning

**Boundary**: The degree to which this team assists with personal
transformation and areas near the private boundary (`02-Growth/`) is
to be determined — but the absolute privacy boundary on `02-Growth/_private/`
is non-negotiable regardless.

### Capability Area C: Development — Application & Business System Development

AI-assisted development of applications and systems for business operations.
This team uses Claude Code and spec-kitty as implementation tools for
building applications and projects requiring development.

**Concrete examples:**
- Intentional consulting website: new features such as a blog, HubSpot connections
- Intentional Index tool — AI-assisted evaluation tool for prospects/customers
- Metal casework project: visual designer tool and website
- Any future business application development

### Capability Area D: Content Creation

Copy and visual content creation across all projects and businesses. The full
tool suite is TBD. Canva is confirmed. Additional tools will be identified as
content needs from other teams are better understood.

**In scope:**
- Web copy
- Diagrams and architecture visuals
- Presentations
- Graphics and images
- White papers and PDFs
- Marketing materials
- Serves other teams (A, B, C, E) as a shared service

### Capability Area E: BizOps — Business Operations

Running the digital aspects of Kent's businesses.

**In scope:**
- Marketing campaigns
- Prospect communications
- Customer support
- Order management
- CRM functions
- Invoicing
- Reporting and alerting
- Operates inside business systems as the marketing, sales, account management,
  support, and accounting team

## User Scenarios & Testing

### Scenario 1 — Architecture Validation (Priority: P0)

Kent needs the current system state (F001-F004) validated against what was
originally designed, with gaps and drift identified.

**Why this priority**: The new architecture must build on an accurate
understanding of what exists, not what was planned.

**Acceptance Scenarios**:

1. **Given** all four features are deployed, **When** the architecture is
   audited, **Then** every deployed service, port, credential, and data flow
   is documented accurately.
2. **Given** the v0.3 spec exists, **When** compared to actual state, **Then**
   all deviations from the original plan are identified and documented.

---

### Scenario 2 — User Story Catalog (Priority: P0)

Kent needs a comprehensive set of user stories across all five capability areas
that captures the full scope of the expanded vision.

**Why this priority**: User stories are the authoritative requirements input
for the roadmap and all future feature specs.

**Acceptance Scenarios**:

1. **Given** seed stories exist in the research brief, **When** expanded, **Then**
   every capability area has user stories covering its described functionality.
2. **Given** the catalog is complete, **When** reviewed by Kent, **Then** no
   obvious capability gaps remain.

---

### Scenario 3 — Integration and Tool Discovery (Priority: P0)

Kent needs a complete map of external systems, APIs, and tools required across
all capability areas.

**Acceptance Scenarios**:

1. **Given** the five capability areas, **When** integration needs are
   researched, **Then** each required external system is identified with
   purpose, authentication method, data flow direction, and constraints.
2. **Given** Canva is confirmed for Content Creation, **When** additional
   tool needs are analyzed, **Then** known tools are documented and TBD
   areas are explicitly marked.

---

### Scenario 4 — Agent Team Architecture Design (Priority: P0)

Kent needs a proposed architecture for the five agent teams within OpenClaw
that is validated against OpenClaw's actual capabilities.

**Acceptance Scenarios**:

1. **Given** OpenClaw is the orchestration engine, **When** the team structure
   is designed, **Then** it maps correctly to OpenClaw's native concepts
   (skills, agents, orchestrators).
2. **Given** the three-gate autonomy model, **When** applied to the architecture,
   **Then** each team has clear autonomy gates and progression criteria.

---

### Scenario 5 — Canonical Architecture Document (Priority: P0)

Kent needs a revised architecture document (v1.0) that supersedes v0.3 and
covers the full expanded vision.

**Acceptance Scenarios**:

1. **Given** all research is complete, **When** the document is produced, **Then**
   it covers vision, all five capability areas, topology, agent teams,
   integrations, data architecture, security, identity model, and phased approach.
2. **Given** the new constitution directives, **When** incorporated, **Then**
   narrow agent scope, earned autonomy, central logging, and safety parameters
   are reflected throughout.
3. **Given** the document is reviewed, **When** checked for consistency, **Then**
   it is non-contradictory with what has already been built (F001-F004).

---

### Scenario 6 — Feature and Capability Roadmap (Priority: P0)

Kent needs a phased roadmap organized by capability area that replaces the
previous feature sequence.

**Acceptance Scenarios**:

1. **Given** the architecture is defined, **When** the roadmap is produced,
   **Then** it shows what is built (F001-F004), foundation completion, and
   phased capability buildout with dependencies.
2. **Given** the previous F005-F015 numbering is discarded, **When** the
   roadmap is produced, **Then** new feature numbers and priorities are
   assigned based on the validated architecture.

---

### Edge Cases

- What if OpenClaw doesn't natively support the agent team concept? The
  architecture must document how to model teams within OpenClaw's actual
  capabilities.
- What if a research question reveals a constraint that conflicts with a locked
  architectural decision? Document the conflict and present options to Kent.
  Do not unilaterally resolve.
- What if the expanded vision exceeds what office2's hardware can support?
  Document capacity constraints and phase accordingly.

## Requirements

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Current state audit | As Kent, I want the actual deployed state of F001-F004 validated against the original design so I know exactly what exists. | High | Open |
| FR-002 | User story catalog | As Kent, I want a comprehensive user story catalog across all five capability areas so the full scope of the vision is captured as requirements. | High | Open |
| FR-003 | Integration map | As Kent, I want a complete map of every external system and API needed so integration work can be planned accurately. | High | Open |
| FR-004 | Agent team architecture | As Kent, I want a proposed agent team architecture validated against OpenClaw's actual capabilities so the design is implementable. | High | Open |
| FR-005 | Data architecture | As Kent, I want a revised data model covering Vikunja, second brain, OpenClaw, and action logging so data ownership is clear. | High | Open |
| FR-006 | Canonical architecture document | As Kent, I want a v1.0 architecture document that supersedes v0.3 so all future features are built against a validated design. | High | Open |
| FR-007 | Feature roadmap | As Kent, I want a phased roadmap organized by capability area so I know what to build and in what order. | High | Open |
| FR-008 | Identity model extension | As Kent, I want the identity model extended for personal, Intentional, and metal casework contexts so all business identities are covered. | Medium | Open |
| FR-009 | Constitution directive incorporation | As Kent, I want the new constitution directives (narrow scope, earned autonomy, central logging, safety parameters) reflected in the architecture. | High | Open |
| FR-010 | OpenClaw capability research | As Felix, I want OpenClaw's native capabilities researched (teams, logging, autonomy gates) so the architecture maps to reality. | High | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Research validity | All architecture decisions must be validated against actual tool capabilities through research, not assumed | Quality | High | Open |
| NFR-002 | Document coherence | The v1.0 architecture document must be internally non-contradictory and consistent with F001-F004 as built | Quality | High | Open |
| NFR-003 | Roadmap realism | The phased roadmap must be realistic given current infrastructure, hardware constraints, and one-person operator model | Quality | High | Open |
| NFR-004 | Extensibility | The architecture must accommodate new tools, integrations, and agent teams without major architectural rework | Architecture | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | No code output | This research produces documents only — no code, no deployments, no configuration changes | Scope | High | Open |
| C-002 | OpenClaw is orchestration engine | Architecture must use OpenClaw as the orchestration engine — not negotiable | Architecture | High | Open |
| C-003 | Vikunja is task store | Architecture must use Vikunja as the task store — not negotiable | Architecture | High | Open |
| C-004 | Anthropic API direct | No LiteLLM, no proxy — Anthropic API only | Architecture | High | Open |
| C-005 | Tailscale-only | All services Tailscale-only — no public internet exposure | Security | High | Open |
| C-006 | office2 is the hub | office2 (Dell XPS 8700, Ubuntu 24.04 LTS, 32GB RAM, GTX 1060 6GB, 2.73TB HDD) is the always-on hub | Infrastructure | High | Open |
| C-007 | Privacy boundary | 02-Growth/_private/ is never agent-accessible — absolute, no exceptions | Privacy | High | Open |
| C-008 | No credentials in code | No credentials committed to code — ever | Security | High | Open |
| C-009 | Human In The Middle default | All agents start at Human In The Middle autonomy level — autonomy must be earned | Governance | High | Open |
| C-010 | Narrow agent scope | Each agent has one clearly defined responsibility | Governance | High | Open |
| C-011 | Central action logging | All agent actions logged centrally — non-negotiable | Governance | High | Open |
| C-012 | Extensible architecture | Architecture must accommodate new tools, integrations, and agent teams without major architectural rework | Architecture | High | Open |
| C-013 | Approved before use | Kent must review and approve all deliverables before any new feature specs are written against them | Process | High | Open |

### Key Entities

- **Felix**: The AI-assisted personal operating system as a whole — the complete
  system comprising five capability areas.
- **Core Hub (Area A)**: The infrastructure team that builds, operates, and
  extends Felix.
- **SuperAdmin (Area B)**: Kent's executive and personal administrative function
  layer operating within Felix.
- **Development (Area C)**: AI-assisted application and system development using
  Claude Code and spec-kitty.
- **Content Creation (Area D)**: Content generation shared service across all
  teams. Canva confirmed, additional tools TBD.
- **BizOps (Area E)**: Digital business operations for Kent's businesses.
- **Three-gate autonomy model**: Human In The Middle -> Human Monitored ->
  Autonomous. Every agent starts at gate 1.
- **office2**: Always-on Ubuntu 24.04 LTS hub running all services.
- **v0.3 spec**: Current canonical architecture document to be superseded.

## Research Questions

These are genuine unknowns that must be answered through research.

### Infrastructure and Orchestration

1. What is the right multi-team architecture within OpenClaw? Does OpenClaw
   support agent teams natively, or must this be modeled differently?
2. How should the five capability areas map to OpenClaw skills, agents, and
   orchestrators? What is the correct granularity?
3. What is the right mechanism for agent action logging? Does OpenClaw have
   native support, or does this need a separate logging layer?
4. How should the three-gate autonomy model be implemented within OpenClaw?
5. Claude Code and spec-kitty are tools used by the Development team (Area C).
   How should OpenClaw orchestrate or coordinate with these tools?

### Integrations

6. What integrations are needed for SuperAdmin (Area B)? Minimum: Google
   Calendar, Gmail. What else?
7. What business systems are needed for BizOps (Area E)? HubSpot is mentioned.
   What CRM, invoicing, order management systems are needed?
8. What AI tools are needed for Content Creation (Area D)? Canva is confirmed.
   What additional tools are required to serve content needs across all areas?
9. What is the right approach to email integration given security constraints?

### Data and Privacy

10. What data should persist in Vikunja vs OpenClaw vs the second brain?
    What is the canonical data model for each capability area?
11. What is the right scope boundary for SuperAdmin relative to the privacy
    boundary on `02-Growth/_private/`?
12. What constitutes the "personal brand" content domain and where does it
    live in the second brain structure?

### Architecture and Identity

13. The current spec describes two identities (personal, intentional). The
    expanded vision adds metal casework as a third business context. How
    should the identity model be extended?
14. Felix is the name of the complete system — all five capability areas
    collectively. How should this system-wide identity be represented within
    OpenClaw's architecture?

## Deliverables

### Deliverable 1: Comprehensive User Story Catalog
A complete set of user stories across all five capability areas, validated
against Kent's described functionality and expanded to cover obvious gaps.

### Deliverable 2: Integration Map
A complete map of every external system, API, or service that needs to be
integrated, organized by capability area.

### Deliverable 3: Agent Team Architecture
A proposed architecture for the five agent teams within OpenClaw, including
team scope boundaries, agent granularity, orchestration patterns, how Core Hub
relates to the other teams, how new agents/tools/integrations are onboarded,
and how the three-gate autonomy model applies.

### Deliverable 4: Data Architecture
A revised data model covering Vikunja, second brain, OpenClaw, central action
log, and identity model extended for personal / Intentional / metal casework.

### Deliverable 5: Revised Canonical Architecture Document (v1.0)
A complete replacement for `docs/design/personal-ai-system-spec-v03.md`
covering vision, all five capability areas, topology, agent teams,
integrations, data architecture, security, identity model, phased approach,
and new constitution directives.

### Deliverable 6: Feature and Capability Roadmap
A phased roadmap organized by capability area showing what is built (F001-F004),
foundation completion, capability area buildout, and advanced capabilities
with dependencies and prerequisite relationships.

## Study These Files First

Before beginning research, the planning phase MUST read:

1. `docs/design/personal-ai-system-spec-v03.md` — current canonical architecture
2. `docs/design/architecture/` — all files in the architecture store
3. `docs/design/architecture/data/` — all JSON data files (authoritative state)
4. `.kittify/constitution/constitution.md` — current constitution
5. `docs/func-spec/F001_vikunja_docker_deploy.md` through
   `docs/func-spec/F004_whatsapp_channel.md` — what has been specced
6. `docs/handbooks/` — all handbooks (what has been implemented)
7. `CLAUDE.md` — project-level agent instructions

## Success Criteria

- **SC-001**: All six deliverables are produced and committed to the repo.
- **SC-002**: The user story catalog covers all five capability areas with no
  obvious gaps.
- **SC-003**: The integration map identifies every known external system.
- **SC-004**: The agent team architecture is consistent with OpenClaw's actual
  capabilities (validated through research, not assumed).
- **SC-005**: The v1.0 architecture document is coherent, non-contradictory,
  and consistent with what has been built (F001-F004).
- **SC-006**: The new constitution directives are incorporated throughout.
- **SC-007**: The roadmap is realistic given current infrastructure and constraints.
- **SC-008**: Kent has reviewed and approved all deliverables before any new
  feature specs are written against them.
