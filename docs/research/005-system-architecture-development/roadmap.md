# Feature and Capability Roadmap: Felix System Architecture

**Date**: 2026-03-29
**WP**: WP08 — Feature and Capability Roadmap (Deliverable 6)
**Status**: Complete
**Note**: Previous F005-F015 numbering from v0.3 is discarded. New feature
numbers are assigned below based on the validated v1.0 architecture.

---

## Current State: What Has Been Built (F001–F004)

| Feature | What | Capability Area | What It Enables |
|---------|------|----------------|-----------------|
| F001 | Vikunja Docker deploy, project structure, identity labels, saved filters | Core Hub (A) | Task store for all teams, web UI for Kent |
| F002 | OpenClaw install, credential store, Anthropic API direct | Core Hub (A) | Agent orchestration engine, LLM intelligence |
| F003 | Whisper transcription skill, transcribe-api hardening (Tailscale-only) | Core Hub (A) | Voice note processing pipeline |
| F004 | WhatsApp channel (Baileys), QR pairing, E2E messaging verified | Core Hub (A) | Inbound/outbound messaging channel |

**Current capability coverage**:
- Core Hub: Infrastructure deployed, no agent teams or automation yet
- SuperAdmin: Task store exists (Vikunja), no automation
- Development: Claude Code and spec-kitty used manually, not Felix-integrated
- Content Creation: No integrations
- BizOps: No integrations

---

## Phase 1: Foundation Completion

**Entry criteria**: F005 (this research project) complete and approved.
**Exit criteria**: All foundation features deployed. All 5 teams can operate
at Gate 1. Central action logging active.

**Goal**: Complete the infrastructure foundation so that capability areas can
grow independently.

### F006: Central Action Logging

**Description**: Deploy OpenTelemetry collector on office2. Configure OpenClaw
to export traces, metrics, and logs via OTLP. Create Felix-specific enrichment
layer (team, action type, autonomy gate). Queryable audit store at
`/data/services/felix-audit/`.

**Area**: Core Hub (A)
**Priority**: P0 — all teams need this before operating
**Dependencies**: F002 (OpenClaw deployed)
**Complexity**: Medium
**Enables**: Governance compliance, Gate 1 operation for all agents

### F007: Agent Team Structure

**Description**: Configure 5 teams as named agents in OpenClaw with isolated
workspaces, identity files, standing orders, and tool policies. Configure
felix-core-router for message classification and team routing. Enable
agent-to-agent messaging per the communication matrix. Set all agents to
Gate 1.

**Area**: Core Hub (A)
**Priority**: P0 — prerequisite for all team operations
**Dependencies**: F002 (OpenClaw), F006 (logging — agents must log from start)
**Complexity**: Large
**Enables**: All five capability areas

### F008: Google Calendar + Gmail Integration (OAuth2)

**Description**: Implement OAuth2 authorization flow (localhost redirect on
MacBook, refresh tokens to office2). Create Calendar and Gmail API skills
for OpenClaw. Store `personal-google` credential in secrets store.

**Area**: SuperAdmin (B)
**Priority**: P0 — enables scheduling, briefings, email triage
**Dependencies**: F002 (OpenClaw), F007 (agent team — felix-admin-calendar,
felix-admin-email need to exist)
**Complexity**: Medium
**Enables**: B-04 (scheduling), B-05 (email triage), B-06 (calendar coordination)

### F009: Vikunja API Skill

**Description**: Create OpenClaw skill wrapping Vikunja REST API for task
CRUD, label management, filter queries, project management. This is the
foundation skill used by all task-writing agents.

**Area**: Core Hub (A)
**Priority**: P0 — all task-related automation depends on this
**Dependencies**: F001 (Vikunja), F002 (OpenClaw)
**Complexity**: Medium
**Enables**: F010-F013, all task automation

### F010: Constitution Update

**Description**: Update `.kittify/constitution/constitution.md` to formally
incorporate the four new directives (narrow scope, earned autonomy, central
logging, safety parameters). Update architecture documentation store to
reflect v1.0.

**Area**: Core Hub (A)
**Priority**: P1 — governance formalization
**Dependencies**: F005 (v1.0 document approved)
**Complexity**: Small
**Enables**: Governance compliance for all agents

### Phase 1 Dependency Graph

```
F005 (this project) ──→ F010 (Constitution Update)
                    ──→ F006 (Action Logging) ──→ F007 (Agent Teams) ──→ F008 (Google OAuth2)
                                                                    ──→ F009 (Vikunja API Skill)
```

**Parallel tracks**: F006 and F009 can start simultaneously after F005.
F010 can start immediately after F005. F007 depends on F006. F008 depends
on F007.

---

## Phase 2: Capability Area Buildout

**Entry criteria**: Phase 1 foundation complete (F006-F010 deployed).
**Exit criteria**: Each capability area has its first operational features.
Agents operating at Gate 1 with demonstrated reliability.

**Goal**: Each area builds its initial automation. Multiple areas can build
in parallel since they operate on different integrations.

### SuperAdmin (Area B) — First Features

**F011: Voice Capture Pipeline**
- Inbox-processor skill migrated from Cowork concept. Scans 00-Inbox/ hourly.
  Routes content to vault destinations and tasks to Vikunja.
- Dependencies: F007, F009
- Complexity: Medium
- Enables: B-01 (voice capture), B-15 (process inbox now)

**F012: Daily Briefing**
- felix-admin-briefing compiles daily briefing from Vikunja (Today/Upcoming/
  Overdue), Google Calendar (events), and optionally CRM pipeline. Delivers
  via WhatsApp at 8 AM.
- Dependencies: F007, F008, F009
- Complexity: Medium
- Enables: B-02 (daily briefing), B-12 (weekly review)

**F013: Escalation Engine**
- felix-admin-escalation monitors overdue tasks via Vikunja labels
  (escalation-1 through escalation-4). Sends WhatsApp reminders with
  increasing urgency. Interactive resolution (snooze/abandon/new date).
- Dependencies: F007, F009
- Complexity: Medium
- Enables: B-03 (escalation), B-07 (priority negotiation), B-08 (reminders)

### Content Creation (Area D) — First Features

**F014: Canva Integration**
- Connect Canva API via OAuth2. Create skill for design generation, export,
  brand kit access. Assign to felix-content-designer.
- Dependencies: F007
- Complexity: Medium
- Enables: D-02 (presentations), D-05 (diagrams/graphics), D-06 (brand identity)

**F015: Content Pipeline**
- felix-content-writer generates multi-format content (blog, LinkedIn, white
  paper, email) from briefs using Claude API. felix-content-formatter
  transforms between formats. Output to second brain (04-Business/) or
  `/data/content/`.
- Dependencies: F007
- Complexity: Medium
- Enables: D-01 (blog drafts), D-03 (multi-format), D-07 (white papers)

### BizOps (Area E) — First Features

**F016: CRM Integration**
- Connect HubSpot (or confirmed CRM) via private app token. Create skill for
  contact CRUD, deal pipeline, lead tracking. Polling for updates (no webhook).
- Dependencies: F007, **CRM platform confirmed (open decision OD-1)**
- Complexity: Medium
- Enables: E-01 (lead capture), E-05 (pipeline tracking), E-06 (prospect comms)

**F017: Business Reporting**
- felix-bizops-reporting generates weekly business report from Vikunja tasks,
  CRM pipeline, and campaign metrics. Delivers via WhatsApp.
- Dependencies: F007, F009, F016
- Complexity: Small
- Enables: E-04 (weekly report)

### Development (Area C) — First Features

**F018: Felix-Integrated Development Workflows**
- felix-dev-orchestrator coordinates spec-kitty workflows via shell execution.
  Triggers Claude Code sessions. Receives completion via OpenClaw inbound
  webhooks from CI. Development status in daily briefing.
- Dependencies: F007, F006 (logging)
- Complexity: Medium
- Enables: C-03 (orchestrated dev), C-05 (dev status in briefing), C-06 (async Claude Code)

### Phase 2 Dependency Graph

```
Phase 1 Complete
  │
  ├── SuperAdmin Track:  F011 (Capture) ──→ F012 (Briefing) ──→ F013 (Escalation)
  │
  ├── Content Track:     F014 (Canva) ──┐
  │                      F015 (Pipeline)┘ (parallel)
  │
  ├── BizOps Track:      F016 (CRM) ──→ F017 (Reporting)
  │                      [blocked by OD-1 CRM decision]
  │
  └── Development Track: F018 (Dev Workflows)
```

**Parallel tracks**: All four area tracks can proceed simultaneously.
Within SuperAdmin, F011-F013 are sequential. BizOps F016 is blocked until
Kent confirms CRM choice.

---

## Phase 3: Advanced Capabilities

**Entry criteria**: Phase 2 features operational, agents demonstrating
reliability at Gate 1. Some agents may advance to Gate 2.
**Exit criteria**: Cross-team automation working, advanced content types,
multi-business operations.

### Cross-Team Automation

**F019: Cross-Team Request Routing**
- Enable automated request flow between teams (BizOps → Content Creation
  for campaign materials, SuperAdmin → Content Creation for meeting prep).
  Requires agent-to-agent messaging patterns validated in Phase 2.
- Dependencies: F014, F015 (Content pipeline operational)
- Complexity: Medium

**F020: Multi-Business Identity Routing**
- Extend identity model to fully route by Vikunja label across calendar,
  email, CRM, and content. Add Intentional Google Workspace credentials.
  Add metal casework label and routing.
- Dependencies: F008, F016
- Complexity: Medium

### Advanced SuperAdmin

**F021: Goal Context Loader**
- Reads constitution docs (Goals-MOC, Identity, Values, Vision, Personal-Brand)
  to inform priority reasoning. Constitution hash tracking for change detection.
- Dependencies: F007
- Complexity: Small

**F022: Track Record Reporting**
- Historical analysis of task completion vs. due dates. Trend reporting.
  Delivered via WhatsApp or as part of weekly review.
- Dependencies: F009, F012
- Complexity: Small

### Advanced Content

**F023: Cross-Platform Publishing**
- Automated scheduling and publishing to LinkedIn, Instagram, personal
  website, and email. Requires social media API integration or Buffer.
- Dependencies: F015, **Social media tool confirmed (OD-4)**
- Complexity: Medium-Large

**F024: Email Marketing Campaigns**
- Campaign creation, audience management, send scheduling via confirmed
  email marketing platform.
- Dependencies: F016, **Email marketing platform confirmed (OD-5)**
- Complexity: Medium

### Advanced BizOps

**F025: Invoicing Integration**
- Connect invoicing tool. Create/send invoices from work descriptions.
  Track payments.
- Dependencies: **Invoicing tool confirmed (OD-2)**
- Complexity: Medium

**F026: Metal Casework Operations**
- When metal casework business becomes active: order management, customer
  communications, separate CRM pipeline or instance.
- Dependencies: F020 (identity routing), **Order management tool confirmed (OD-3)**
- Complexity: Large

### Advanced Core Hub

**F027: Agent Autonomy Advancement**
- Formal process for advancing agents from Gate 1 → Gate 2 based on
  performance data from action log. Tooling to review agent performance
  and make gate transition decisions.
- Dependencies: F006, F007, 90+ days of operation
- Complexity: Medium

**F028: System Self-Diagnosis**
- Core Hub agents diagnose common issues (service down, credential expired,
  sync stalled) and propose remediation to Kent.
- Dependencies: F007
- Complexity: Medium

---

## Phase Summary

| Phase | Features | Key Deliverables | Parallel Tracks |
|-------|----------|-----------------|-----------------|
| Current | F001-F004 | Infrastructure foundation | — |
| F005 | Research | v1.0 architecture, roadmap | — |
| Phase 1 | F006-F010 | Logging, teams, OAuth2, Vikunja API, constitution | F006+F009+F010 parallel |
| Phase 2 | F011-F018 | Briefings, escalation, Canva, content pipeline, CRM, dev workflows | 4 area tracks parallel |
| Phase 3 | F019-F028 | Cross-team, multi-business, publishing, invoicing, autonomy | Multiple parallel tracks |

## Feature Dependency Map (All Phases)

```
F001-F004 (deployed)
  │
  └── F005 (this project)
        │
        ├── F006 (Action Logging) ───────────────────────────────┐
        │     └── F007 (Agent Teams) ───────────────────────────┤
        │           ├── F008 (Google OAuth2) ──→ F012 (Briefing)│
        │           ├── F009 (Vikunja API) ──→ F011 (Capture)   │
        │           │                     ──→ F013 (Escalation)  │
        │           ├── F014 (Canva) ───────────────────────────┤
        │           ├── F015 (Content Pipeline) ────────────────┤
        │           ├── F016 (CRM) [blocked: OD-1] ──→ F017    │
        │           ├── F018 (Dev Workflows)                    │
        │           └── F021 (Goal Context) ──→ F022 (Tracking) │
        │                                                        │
        ├── F010 (Constitution Update)                           │
        │                                                        │
        └── Phase 3 features depend on Phase 2 ─────────────────┘
              F019 (Cross-Team) ← F014, F015
              F020 (Multi-Business) ← F008, F016
              F023 (Publishing) ← F015, [OD-4]
              F024 (Email Marketing) ← F016, [OD-5]
              F025 (Invoicing) ← [OD-2]
              F026 (Metal Casework Ops) ← F020, [OD-3]
              F027 (Autonomy Advancement) ← F006, F007, 90+ days
              F028 (Self-Diagnosis) ← F007
```

## Critical Path

The longest dependency chain is:
```
F005 → F006 → F007 → F008 → F012 (Daily Briefing)
```

This means the daily briefing (one of the highest-value SuperAdmin features)
requires all foundation work complete first. Estimated: 4-5 feature cycles
after F005.

**Shortest path to value**: F005 → F006 → F007 → F009 → F011 (Voice Capture
Pipeline). This enables the core capture-classify-route workflow.

## Open Decisions That Block Features

| Decision | Blocks | Phase | Impact if Deferred |
|----------|--------|-------|-------------------|
| OD-1: CRM platform | F016, F017 | Phase 2 | BizOps delayed |
| OD-2: Invoicing tool | F025 | Phase 3 | Invoicing delayed |
| OD-3: Order management | F026 | Phase 3 | Metal casework ops delayed (acceptable — pre-revenue) |
| OD-4: Social media tool | F023 | Phase 3 | Cross-platform publishing delayed |
| OD-5: Email marketing | F024 | Phase 3 | Campaign email delayed |

**Phase 1 and Phase 2 SuperAdmin/Content/Dev tracks are NOT blocked by any
open decisions.** Only BizOps F016 is blocked by OD-1 (CRM confirmation).

## Constraints and Assumptions

- **Single operator**: Kent is the only user. Roadmap is paced for one person
  directing AI agents, not a team.
- **office2 hardware**: Dell XPS 8700 with 32GB RAM, i7-4790, 2.7TB HDD.
  May constrain concurrent service count in later phases.
- **Tailscale-only**: No public internet exposure. Webhook-dependent features
  use polling unless Kent approves Tailscale Funnel.
- **Feature cycle time**: Estimated 1-3 days per feature using spec-kitty +
  Claude Code, depending on complexity.
- **Gate progression**: Agents need 30-90 days at each gate before advancing.
  Phase 3 autonomous features require significant Gate 1/2 history.
