---
title: "F005: kg-automation System Architecture Review and Vision Expansion"
doc_type: func-spec
status: draft
feature: F005
---

# F005: kg-automation System Architecture Review and Vision Expansion

**Version**: 1.0
**Priority**: HIGH
**Type**: Research → Architecture

---

## Purpose

The current architecture spec (v0.3) was written as a personal accountability
and task management system. It is now understood to be too narrow. Kent has
articulated a significantly broader vision for an AI-assisted personal operating
system spanning five capability areas. This research project must:

1. Validate what has actually been built (F001–F004) against what was designed
2. Produce a full set of user stories across all five capability areas
3. Research and validate an architecture that can support the expanded vision
4. Produce a revised canonical architecture document (v1.0) that supersedes v0.3
5. Produce a phased feature and capability roadmap

**The output of this research project becomes the new canonical architecture
document and roadmap. Nothing else gets built until this is complete.**

---

## What This Is NOT

This is not a feature implementation spec. No code will be written. No services
will be deployed. The deliverable is a validated architecture document and
roadmap that will serve as the authoritative input for all future feature specs.

---

## Background: What Exists Today

### Implemented (F001–F004 in progress)

```
office2 (Ubuntu 24.04 LTS, always-on)
├── Vikunja (Docker, port 3456, Tailscale-only) — F001 complete
├── OpenClaw (npm-global, port 18789/127.0.0.1) — F002 complete
├── transcribe-api (Docker, port 8787, Tailscale-only) — F003 complete
└── WhatsApp channel (Baileys, personal number, QR paired) — F004 in progress

MacBook Pro
└── Obsidian vault synced to office2 via systemd daemon

Second brain
└── ~/second-brain/vault/Notes/ (Obsidian, numbered folders 00–07)
    ├── 01-Constitution/ — agent context ceiling
    └── 02-Growth/_private/ — ABSOLUTE PRIVACY BOUNDARY, never agent-accessible
```

### Key architectural decisions already made and locked

- **OpenClaw** is the orchestration engine — not negotiable
- **Vikunja** is the task store — not negotiable
- **Anthropic API direct** — no LiteLLM, no proxy — not negotiable
- **Tailscale-only** for all services — not negotiable
- **office2** is the always-on hub — not negotiable
- **Baileys** for WhatsApp (accepted exception, documented in constitution)
- **02-Growth/_private/** is never agent-accessible — absolute, non-negotiable

### Current spec document

`docs/design/personal-ai-system-spec-v03.md` — this document is the
current canonical reference but must be superseded by the output of this
research project.

---

## The Expanded Vision

Kent describes the system as **"Felix"** — named after Felix the Cat's magic
bag, from which virtually anything he wanted would emerge. Felix is the
AI-assisted personal operating system as a whole — the complete system
comprising five capability areas and their associated agent teams.

### Capability Area A: Core Hub — System Infrastructure

The team that builds, operates, and extends Felix. Core Hub is the
infrastructure team.

**In scope:**
- Research, design, development, implementation, testing, operation, security,
  and governance of the automation system itself
- Full awareness of the system's own configuration and capabilities
- Agents that can safely modify and extend capabilities at Kent's direction
- Self-documenting — the system knows what it can do

**Key question for research**: What is the right architecture for a system
that safely modifies itself? What autonomy gates and safety controls are needed?

### Capability Area B: SuperAdmin — Executive Digital Assistant

Kent's personal executive function layer.

**In scope:**
- Priority and commitment management
- Communications and email
- Calendar management
- Research on topics of interest
- Personal brand management
- Generation of materials and artifacts
- Anything related to Kent's personal functioning

**Boundary TBD**: The degree to which this team assists with personal
transformation and areas near the private boundary (`02-Growth/`) is
to be determined — but the absolute privacy boundary on `02-Growth/_private/`
is non-negotiable regardless.

**Scope boundary**: SuperAdmin performs executive and personal administrative
functions within the system created and maintained by Core Hub and Kent.
Integration requirements (Google Calendar, Gmail, etc.) remain to be
fully enumerated during research.

### Capability Area C: Development — Application & Business System Development

AI-assisted development of applications and systems for business operations.

**Concrete examples:**
- Intentional consulting website (currently in code): new features such as
  a blog, connections to HubSpot
- Intentional Index tool — AI-assisted evaluation tool for prospects/customers
  to assess their support delivery operations
- Metal casework project: visual designer tool and website
- Any future business application development

**Tooling**: This team uses Claude Code and spec-kitty as implementation
tools for building applications and projects requiring development.

### Capability Area D: Content Creation

Copy and visual content creation across all projects and businesses.

**In scope:**
- Web copy
- Diagrams and architecture visuals
- Presentations
- Graphics and images
- White papers and PDFs
- Marketing materials
- Serves other teams (A, B, C, E) as a shared service

**Tooling**: The full tool suite is TBD. Canva is confirmed. Additional
tools will be identified as content needs from other teams are better
understood.

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

**Key question for research**: What business systems need integration?
HubSpot is mentioned. What others? How does BizOps relate to the
Intentional LLC business and the metal casework business separately?

---

## New Constitution Directives to Incorporate

The following directives must be incorporated into the constitution and
reflected in the architecture:

**A. Narrow agent scope**
Agents must be built to be narrow in scope to aid troubleshooting and
maintenance. Highly granular responsibilities give orchestrators more
flexible options for execution.

**B. Earned autonomy — three-gate model**
Agents must earn autonomy by progressing through proven performance gates:
1. Human In The Middle — agent proposes, human approves every action
2. Human Monitored — agent acts, human reviews logs
3. Autonomous — agent acts independently within defined bounds

No agent starts at Autonomous. Every agent starts at Human In The Middle.

**C. Central action logging**
Agents and orchestrators shall log all actions in a central location at a
granularity that supports human and machine auditability.

**D. Safety parameters and clear boundaries**
Agents and orchestrators shall be built with safety parameters and clear
boundaries. They stop and alert if asked to do something they shouldn't
do or do not know how to do. They never fail silently.

---

## User Stories to Generate

The research phase must produce a comprehensive set of user stories covering
all five capability areas. These user stories become the authoritative
requirements input for the roadmap. Start from the concrete functionality
already described and expand from there.

User stories must follow the format:
`As [persona], I want [capability], so that [outcome].`

Personas: Kent (primary), Felix (the system acting on Kent's behalf)

### Seed stories — expand and validate these

**Capability A (Core Hub)**
- As Kent, I want to add a new integration to the system by describing what
  I want, so that Felix can research, propose, implement, and validate it
  without me writing code.
- As Kent, I want to know the current capabilities and configuration of the
  system at any time, so that I can make informed decisions about what to
  build next.
- As Felix, I want to know my own configuration and what I am able to do,
  so that I can accurately report my capabilities and limitations to Kent.

**Capability B (SuperAdmin)**
- As Kent, I want to dictate a voice note and have it automatically
  classified, routed, and actioned, so that I can capture thoughts without
  being at a computer.
- As Kent, I want a daily briefing delivered to my WhatsApp each morning,
  so that I start the day with clear priorities.
- As Kent, I want overdue commitments escalated to me persistently until
  I resolve them, so that important work doesn't quietly expire.
- As Kent, I want to schedule a meeting by describing it in natural language,
  so that my calendar is updated without manual entry.
- As Kent, I want my email triaged and summarized, so that I can process
  communications efficiently.
- As Kent, I want my do-list and calendar coordinated and updated so priorities are given time on the calendar for work to be done.
- As Kent, I want interactive alerting and negotiation of tasks, conflicting priorities, oversubscribed commitments and tasks so the most important decisions and tasks get done.
- As Kent, I want to be reminded of repeating tasks and appointments on my phone via WhatsApp such as meditation, exercise, physical therapy, meetings, calls, etc. and I want to be able to mark them as complete, rescheduled, or "will not do".
- As Kent, I want to track and get reports on my track record of getting things done when I say they will be done.

**Capability C (Development)**
- As Kent, I want to describe a new feature for the Intentional website and
  have it researched, designed, and implemented, so that the site evolves
  without me managing every detail.
- As Kent, I want to build the Intentional Index tool with AI assistance,
  so that I can offer it to prospects without needing to code it entirely
  myself.

**Capability D (Content Creation)**
- As Kent, I want to describe a blog post idea and have a draft produced,
  so that I can focus on review and refinement rather than generation.
- As Kent, I want a presentation created from a brief, so that I can deliver
  professional materials without spending hours in PowerPoint.
- As Kent, I want to have different versions of a topic generated that are approriate as a blog post, LinkedIn teaser post, white paper, Instagram post, or email.
- As Kent, I want any videos I generate make available to post on LinkedIn or Instagram as resources for marketing and content campaigns.
- As Kent, I want to be able to describe conceptual diagrams and graphics and have a few versions of them generated so I can iterate on them with IA assistance until satisfied. (I assume this uses an approriate AI tool to generate these diagrams and graphics)

**Capability E (BizOps)**
- As Kent, I want new leads from my website automatically entered into my
  CRM with context, so that no prospect falls through the cracks.
- As Kent, I want to describe a marketing campaign and have the plan generated along with materials for my review and approval before it is executed.
- As Kent, I want to describe a series of blog posts and have the system schedule versions of them to appear on my personal web site, LinkedIn, Instagram, and in email to the target audiences.
- As Kent, I want a weekly business report delivered to my WhatsApp, so that
  I have situational awareness without pulling reports manually.

---

## Research Questions

The research phase must answer these questions before the architecture can
be designed. These are genuine unknowns — research must discover the answers,
not assume them.

### Infrastructure and orchestration

1. What is the right multi-team architecture within OpenClaw? Does OpenClaw
   support the concept of agent teams natively, or does this need to be
   modeled differently?
2. How should the five capability areas map to OpenClaw skills, agents, and
   orchestrators? What is the correct granularity?
3. What is the right mechanism for agent action logging? Does OpenClaw have
   native support, or does this need a separate logging layer?
4. How should the three-gate autonomy model (Human In The Middle → Human
   Monitored → Autonomous) be implemented within OpenClaw?
5. Claude Code and spec-kitty are tools used by the Development team (Area C).
   How should OpenClaw orchestrate or coordinate with these tools?

### Integrations

6. What integrations are needed for Capability B (SuperAdmin)?
   Minimum: Google Calendar, Gmail. What else?
7. What business systems are needed for Capability E (BizOps)?
   HubSpot is mentioned. What CRM, invoicing, order management systems
   does Kent currently use or plan to use?
8. What AI tools are needed for Capability D (Content Creation)?
   Canva is confirmed. What additional tools are required to serve content
   needs across all capability areas?
9. What is the right approach to email integration given security constraints?

### Data and privacy

10. What data should persist in Vikunja vs OpenClaw vs the second brain?
    What is the canonical data model for each capability area?
11. What is the right scope boundary for SuperAdmin relative to the privacy
    boundary on `02-Growth/_private/`?
12. What constitutes the "personal brand" content domain and where does it
    live in the second brain structure?

### Architecture and identity

13. The current spec describes two identities (personal, intentional).
    The expanded vision adds metal casework as a third business context.
    How should the identity model be extended?
14. Felix is the name of the complete system — all five capability areas
    collectively. How should this system-wide identity be represented within
    OpenClaw's architecture?

---

## Constraints (Non-Negotiable)

These constraints are locked and must be respected in the output architecture:

- **OpenClaw** is the orchestration engine
- **Vikunja** is the task store
- **Anthropic API direct** — no LiteLLM, no proxy
- **Tailscale-only** for all services — no public internet exposure
- **office2** is the always-on hub (Dell XPS 8700, Ubuntu 24.04 LTS, 32GB RAM,
  GTX 1060 6GB GPU, 2.73TB HDD at /data)
- **02-Growth/_private/** is never agent-accessible — absolute, no exceptions
- **No credentials in code** — ever
- **Agents start at Human In The Middle** — autonomy must be earned
- **Narrow agent scope** — each agent has one clearly defined responsibility
- **All agent actions logged centrally** — non-negotiable
- **Extensible architecture** — capability areas will grow as core
  infrastructure matures. The system design must accommodate new tools,
  integrations, and agent teams without major architectural rework.

---

## Deliverables

The output of this research project must include:

### Deliverable 1: Comprehensive User Story Catalog
A complete set of user stories across all five capability areas, validated
against Kent's described functionality and expanded to cover obvious gaps.
Format: structured markdown, grouped by capability area.

### Deliverable 2: Integration Map
A complete map of every external system, API, or service that needs to be
integrated, organized by capability area. For each integration: purpose,
authentication method, data flow direction, and any known constraints.

### Deliverable 3: Agent Team Architecture
A proposed architecture for the five agent teams within OpenClaw, including:
- Team names and scope boundaries
- Agent granularity within each team
- Orchestration patterns between teams
- How Core Hub relates to the other capability area teams
- How new agents, tools, and integrations are onboarded into a capability area
- How the three-gate autonomy model applies per team

### Deliverable 4: Data Architecture
A revised data model covering:
- What lives in Vikunja (tasks, projects, labels, metadata)
- What lives in the second brain (content, context, constitution)
- What lives in OpenClaw (skills, sessions, agent state)
- What lives in a central action log (and where that log lives)
- Identity model extended for personal / Intentional / metal casework

### Deliverable 5: Revised Canonical Architecture Document (v1.0)
A complete replacement for `docs/design/personal-ai-system-spec-v03.md`.
Must cover:
- Vision and framing
- All five capability areas
- Physical topology (unchanged hardware, updated logical architecture)
- Agent team structure
- Integration catalog
- Data architecture
- Security architecture (updated for expanded scope)
- Identity model
- Phased implementation approach
- New constitution directives incorporated

### Deliverable 6: Feature and Capability Roadmap
A phased roadmap organized by capability area, not just sequential feature
numbers. Must show:
- What is already built (F001–F004)
- What completes the current foundation (F005–F015 as currently planned)
- Phase 2: capability area buildout, prioritized
- Phase 3: advanced capabilities
- Dependencies between capabilities
- Which capabilities are prerequisite for others

---

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

---

## Success Criteria

This research project is complete when:

- [ ] All six deliverables are produced and committed to the repo
- [ ] The user story catalog covers all five capability areas with no obvious gaps
- [ ] The integration map identifies every known external system
- [ ] The agent team architecture is consistent with OpenClaw's actual capabilities
  (validated through research, not assumed)
- [ ] The revised architecture document v1.0 is coherent, non-contradictory,
  and consistent with what has already been built
- [ ] The new constitution directives (narrow scope, earned autonomy, central
  logging, safety parameters) are incorporated throughout
- [ ] The roadmap is realistic given the current infrastructure and constraints
- [ ] Kent has reviewed and approved the output before any new feature specs
  are written against it

---

## What Happens After This Research Project

Once Kent approves the output:

1. The revised architecture document becomes the new canonical reference
2. The constitution is updated to incorporate the new directives
3. The feature roadmap replaces the current Phase 1 sequence as the build order
4. All future func-specs are written against the new architecture
5. The architecture documentation store (`docs/design/architecture/`) is
   updated to reflect the v1.0 architecture

**No new feature specs will be written until this research project is
complete and approved.**

---

**END OF RESEARCH BRIEF**
