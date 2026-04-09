---
title: "Felix — Personal AI Operating System: Architecture Specification v1.0"
doc_type: reference
supersedes: docs/design/personal-ai-system-spec-v03.md
status: draft
---

# Felix — Personal AI Operating System
## Architecture Specification v1.0

**Project**: kg-automation
**Author**: Kent Gale
**Status**: Draft — Pending Review
**Date**: 2026-03-29
**Supersedes**: `docs/design/personal-ai-system-spec-v03.md`

**Changelog**:
- v0.1–v0.3 — Personal AI Command & Accountability System (original scope)
- v1.0 — Expanded to Felix: five capability areas, agent team architecture,
  three-gate autonomy, central action logging, extensible design

---

## 1. Vision and Framing

**Felix** — named after Felix the Cat's magic bag, from which virtually
anything he wanted would emerge — is Kent Gale's AI-assisted personal
operating system. Felix is the complete system comprising five capability
areas and their associated agent teams.

Felix is not a task manager or a chatbot. It is an accountability and
automation infrastructure that spans system operations, executive function,
application development, content creation, and business operations. It
operates on the premise that Kent has declared who he intends to become and
what he intends to build. Felix's role is to hold those declarations in trust,
surface them persistently, and ensure the gap between intention and action is
never comfortable to ignore.

### Design Principles

1. **Transformative action over comfortable inaction.** Felix resists drift.
2. **Insistence is a feature.** Explicit permission to escalate and be
   uncomfortable to ignore when commitments are at risk.
3. **Kent has final say — always.** Felix negotiates and pushes back but
   never overrides.
4. **Transparency about limits.** Capability boundaries are declared
   immediately. Felix never fails silently.
5. **Narrow agent scope.** Each agent has one clearly defined responsibility.
6. **Earned autonomy.** Every agent starts at Human In The Middle. Autonomy
   is earned through demonstrated reliability.
7. **Central action logging.** All agent actions logged at granularity
   supporting human and machine auditability.
8. **Safety parameters and clear boundaries.** Agents stop and alert when
   asked to do something outside their scope.
9. **Extensible architecture.** The system accommodates new tools,
   integrations, and agent teams without major architectural rework.
10. **Privacy is absolute.** `02-Growth/_private/` is never accessed by any
    agent under any circumstance. No exceptions. No opt-in.

---

## 2. Five Capability Areas

### Area A: Core Hub — System Infrastructure

The team that builds, operates, and extends Felix. Core Hub is the
infrastructure team.

**Scope**: Research, design, development, implementation, testing, operation,
security, and governance of the automation system itself. Full awareness of
the system's own configuration and capabilities. Self-documenting.

**Agents**: felix-core-router (message routing), felix-core-heartbeat
(scheduled jobs), felix-core-audit (action log monitoring)

### Area B: SuperAdmin — Executive Digital Assistant

Kent's personal executive function layer. SuperAdmin performs executive and
personal administrative functions within the system created and maintained
by Core Hub and Kent.

**Scope**: Priority and commitment management, communications, calendar,
email, research, personal brand management, repeating reminders, escalation,
track record reporting.

**Agents**: felix-admin-briefing, felix-admin-calendar, felix-admin-email,
felix-admin-escalation, felix-admin-capture

### Area C: Development — Application & Business System Development

AI-assisted development using Claude Code and spec-kitty as implementation
tools.

**Scope**: Intentional consulting website, Intentional Index tool, metal
casework visual designer, and any future application development.

**Agents**: felix-dev-orchestrator, felix-dev-builder

### Area D: Content Creation

Content generation shared service across all teams. Canva confirmed;
additional tools TBD as content needs are better understood.

**Scope**: Blog posts, presentations, graphics, white papers, PDFs, marketing
materials, diagrams, multi-format content transformation. Serves Areas A–E.

**Agents**: felix-content-writer, felix-content-designer, felix-content-formatter

### Area E: BizOps — Business Operations

Running the digital aspects of Kent's businesses.

**Scope**: Marketing campaigns, prospect communications, customer support,
order management, CRM, invoicing, reporting, cross-platform content
distribution.

**Agents**: felix-bizops-crm, felix-bizops-marketing, felix-bizops-reporting

---

## 3. Physical Topology

```
[Kent]
  ├── WhatsApp voice/text ──────────────────────────────┐
  ├── Wispr Flow (Mac/iPhone) → Obsidian 00-Inbox/      │
  └── Direct browser (Vikunja UI, Canva)                │
                                                         │
[office2 — Ubuntu 24.04 LTS — always-on hub]◄───────────┘
  │   Dell XPS 8700, i7-4790, 32GB RAM, GTX 1060 6GB
  │   Root: 98GB SSD | Data: 2.7TB HDD | Backups: 1TB USB
  │   Tailscale IP: 100.92.197.90
  │
  ├── OpenClaw Gateway (127.0.0.1:18789)
  │     ├── felix-core-router (message classification + routing)
  │     ├── felix-core-heartbeat (scheduled: inbox poll, briefings, escalation)
  │     ├── felix-core-audit (action log monitoring)
  │     ├── felix-admin-* (5 agents: briefing, calendar, email, escalation, capture)
  │     ├── felix-dev-* (2 agents: orchestrator, builder)
  │     ├── felix-content-* (3 agents: writer, designer, formatter)
  │     ├── felix-bizops-* (3 agents: crm, marketing, reporting)
  │     └── Claude API (Anthropic direct — no proxy)
  │
  ├── Vikunja (Docker, 100.92.197.90:3456)
  │     ├── REST API ← all agents read/write tasks
  │     ├── Web UI ← Kent via Tailscale (Mac/iPhone)
  │     └── SQLite ← backed up nightly via Restic
  │
  ├── transcribe-api (Docker, 100.92.197.90:8787)
  │     └── Whisper medium.en ← voice note transcription
  │
  ├── WhatsApp Channel (Baileys, outbound WebSocket)
  │     └── Kent's personal number (617) 930-0916 as linked device
  │
  ├── Obsidian Sync daemon (systemd, continuous)
  │     └── ~/second-brain/vault/ ← bidirectional sync
  │
  ├── Central Action Log (OpenTelemetry collector) [PLANNED]
  │     └── /data/services/felix-audit/
  │
  ├── Restic Backup (4AM daily, GFS retention)
  └── Security Monitor (3AM daily, baseline drift detection)

[MacBook Pro — Tailscale 100.71.19.66]
  └── Authoring + interaction endpoint (Obsidian, Claude Code, browser)

[iPhone 14 Pro Max — Tailscale 100.109.208.6]
  └── Mobile capture (Wispr Flow) + task monitoring (Vikunja web UI)
```

---

## 4. Agent Team Architecture

### Modeling Approach

OpenClaw does not support "teams" natively. Teams are modeled as **named
agents** with isolated workspaces, independent tool policies, per-agent
identity files (IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md), and routing
configuration.

All agents share the system-wide "Felix" identity on WhatsApp (single phone
number). Internal routing determines which agent-brain processes each message.

### Agent Inventory (16 agents across 5 teams)

| Team | Agent | Responsibility |
|------|-------|---------------|
| Core Hub | felix-core-router | Message classification and team routing |
| Core Hub | felix-core-heartbeat | Scheduled jobs (inbox poll, briefings, escalation checks) |
| Core Hub | felix-core-audit | Action log monitoring, anomaly detection |
| SuperAdmin | felix-admin-briefing | Daily/weekly briefings, track record reports |
| SuperAdmin | felix-admin-calendar | Meeting scheduling, time-blocking, conflicts |
| SuperAdmin | felix-admin-email | Email triage, summarization, drafts |
| SuperAdmin | felix-admin-escalation | Overdue escalation, priority negotiation, reminders |
| SuperAdmin | felix-admin-capture | Voice note processing, inbox classification |
| Development | felix-dev-orchestrator | Spec-kitty workflow management |
| Development | felix-dev-builder | Code implementation, testing, PRs |
| Content | felix-content-writer | Text content (blogs, posts, white papers, email) |
| Content | felix-content-designer | Visual content via Canva, diagrams |
| Content | felix-content-formatter | Multi-format transformation |
| BizOps | felix-bizops-crm | Lead management, deal pipeline, contacts |
| BizOps | felix-bizops-marketing | Campaign planning, cross-platform scheduling |
| BizOps | felix-bizops-reporting | Business reports, KPIs, pipeline summaries |

### Cross-Team Orchestration

- **Routing**: felix-core-router classifies inbound messages and delegates
  to the correct team agent
- **Request-response**: Teams request services from each other via
  agent-to-agent messaging (explicitly enabled per pair)
- **Broadcast**: Multi-team awareness for messages affecting multiple areas
- **Scheduled**: felix-core-heartbeat runs coordinated jobs (briefings
  compile data from multiple teams)

### Agent Communication (Least Privilege)

Agent-to-agent messaging is disabled by default. Only these pairs are enabled:

- core-router → all team agents (routing)
- admin-* → content-* (request materials)
- admin-* → bizops-* (query pipeline)
- bizops-* → content-* (request campaign content)
- bizops-* → dev-* (request tool development)
- dev-* → content-* (request documentation)
- All teams → core-audit (status reporting)

---

## 5. Three-Gate Autonomy Model

### Gate Definitions

| Gate | Name | Behavior | OpenClaw Config |
|------|------|----------|----------------|
| 1 | Human In The Middle | Agent proposes, Kent approves every action | `exec.ask: "always"`, `exec.security: "allowlist"` |
| 2 | Human Monitored | Agent acts on allowlisted operations, async review | `exec.ask: "on-miss"`, cron activity reports |
| 3 | Autonomous | Agent acts freely within scope, heartbeat monitoring | `exec.ask: "off"`, `exec.security: "full"` |

**Every agent starts at Gate 1. No exceptions.**

### Progression Criteria

| Transition | Minimum Duration | Requirements |
|-----------|-----------------|-------------|
| Gate 1 → 2 | 30 days (60 for high-risk) | Zero safety violations, consistent accuracy, Kent explicitly approves |
| Gate 2 → 3 | 90 days | Zero violations in monitoring period, action log clean, Kent explicitly approves, scope formally documented |

### Risk-Adjusted Timeline

| Team | Risk Profile | Gate 2 Target | Gate 3 Outlook |
|------|-------------|---------------|----------------|
| Core Hub | High | 60+ days | Possibly never for config agents |
| SuperAdmin | Medium | 30 days (read); 60 (write) | Selective (briefings likely, email unlikely) |
| Development | Medium | 30 days | Selective (tests likely, production code unlikely) |
| Content | Low-Medium | 30 days | Likely for draft generation |
| BizOps | Medium-High | 60 days | Selective (reports likely, customer comms unlikely) |

---

## 6. Integration Catalog

### Deployed (F001–F004)

| Integration | Purpose | Auth | Port/Access |
|-------------|---------|------|-------------|
| Vikunja REST API | Task store | API token | 100.92.197.90:3456 |
| Anthropic Claude API | LLM intelligence | API key | Outbound HTTPS |
| WhatsApp (Baileys) | Messaging channel | Session (QR) | Outbound WebSocket |
| transcribe-api | Voice transcription | Network (Tailscale) | 100.92.197.90:8787 |
| Obsidian Sync | Vault sync | Filesystem | systemd daemon |
| GitHub | Version control, CI | SSH key | Outbound |
| Tailscale | Network access | System-managed | Mesh VPN |

### Planned

| Integration | Purpose | Auth | Area | Phase |
|-------------|---------|------|------|-------|
| Google Calendar | Scheduling, time-blocking | OAuth2 | SuperAdmin | 1 |
| Gmail | Email triage, drafts | OAuth2 (same cred) | SuperAdmin | 1 |
| Canva | Graphics, presentations | OAuth2 | Content | 2 |
| OpenTelemetry Collector | Central action log | Internal | Core Hub | 1 |
| HubSpot CRM | Leads, pipeline, campaigns | Private app token | BizOps | 2 |

### Open Decisions

| Need | Area | Phase | Options |
|------|------|-------|---------|
| Invoicing | BizOps | 2 | Stripe, QuickBooks, Wave, FreshBooks |
| Social media scheduling | BizOps | 2 | Buffer, direct APIs, HubSpot Social |
| Email marketing | BizOps | 2 | HubSpot Email, Mailchimp, Listmonk |
| Order management | BizOps | 3+ | Custom, Shopify — defer (metal casework pre-revenue) |
| Video tools | Content | 3+ | Canva Video, Synthesia — defer |
| Diagram tool | Content | 1 | Mermaid (de facto), D2 |
| PDF generation | Content | 2 | Pandoc (pragmatic default) |
| Webhook strategy | Cross-cutting | 1 | Polling (recommended), Tailscale Funnel, CF Worker |

### OAuth2 Credential Consolidation

One `personal-google` OAuth2 credential covers: Calendar, Gmail, Contacts,
Docs, Slides. Authorization via localhost redirect on MacBook (one-time);
refresh tokens work server-to-server from office2 thereafter.

---

## 7. Data Architecture

### Data Stores

| Store | Role | Key Data | Backup |
|-------|------|----------|--------|
| Vikunja (SQLite) | Task and work state | Tasks, projects, labels, filters | Restic nightly |
| OpenClaw | Agent state and config | Workspaces, sessions, logs, credentials | Restic nightly |
| Second Brain (Obsidian) | Content and context | Constitution, inbox, business content, journal | Obsidian Sync + Restic |
| Central Action Log | Unified audit trail | Agent actions, gate transitions, correlation | Restic nightly |

### Data Ownership Per Area

| Area | Primary Store | Owns | Consumes |
|------|--------------|------|----------|
| Core Hub (A) | OpenClaw, Action Log | Config, agents, audit | Everything (monitoring) |
| SuperAdmin (B) | Vikunja, Second Brain | Tasks, priorities, briefings | Calendar, email, vault |
| Development (C) | Git repos (external) | Code, specs, docs | Vikunja (tracking) |
| Content (D) | Canva, Second Brain | Content, brand assets | Requests from other teams |
| BizOps (E) | CRM (external), Vikunja | Leads, deals, campaigns | Content from D, reports |

### Identity Model

Three business contexts routed by Vikunja labels:
- `personal` — Kent's personal life, health, growth, personal brand
- `intentional` — Consulting, professional services (Intentional LLC)
- `metalcasework` — Product business (when active)

Every integration that touches business context (CRM, calendar, email, content)
routes by identity label.

---

## 8. Security Architecture

### Network Security

- All services bind to Tailscale IP (100.92.197.90) or localhost — never 0.0.0.0
- No public internet exposure for any service
- No port forwarding or NAT traversal outside Tailscale
- Docker networking bypassed via explicit IP binding
- Zero 0.0.0.0 bindings for managed services (verified post-F003)

### Credential Management

- No credentials in committed files — ever (enforced by CI secret scan)
- Secrets store at `/data/services/openclaw/secrets/` (mode 700 dir, mode 600 files)
- Credentials owned by `claude` user, container injection via env vars
- Stable credential names: `anthropic`, `vikunja-api`, `whatsapp-session`,
  `personal-google` (planned), `intentional-google` (planned)

### Agent Security

- **Narrow scope**: Each agent has one responsibility (constitution directive)
- **Earned autonomy**: Gate 1 default, progression through demonstrated reliability
- **Central logging**: All actions logged via OpenTelemetry to audit store
- **Explicit boundaries**: Agents stop and alert on out-of-scope requests
- **Tool policies**: Per-agent allow/deny lists for executable binaries
- **Agent-to-agent**: Messaging disabled by default, enabled per pair

### Privacy Boundaries

- **Absolute**: `02-Growth/_private/` — never read, written, referenced, or
  logged by any agent. No exceptions. No opt-in possible.
- **Restricted**: `02-Growth/` (non-private) — SuperAdmin read-only with
  Kent's explicit per-folder opt-in
- **Protected**: `06-Journal/` — write-only for inbox-processor
- **Accessible**: `01-Constitution/`, `04-Business/`, `07-Resources/` —
  read/write per access rules
- **Enforcement**: Allowlist (deny by default), skill-level path checks,
  constitution directive, audit log alerts

### Exception Policy

Exceptions to architecture and security policies must be documented with:
- **Constraint**: Which policy is being excepted
- **Rationale**: Why the exception is necessary
- **Scope**: What the exception covers and its boundaries
- **Expiration**: When it expires, or "no expiration" with justification
- **Feature**: Which feature introduced the exception

**Active Exceptions**:

| Constraint | Exception | Rationale | Feature |
|-----------|-----------|-----------|---------|
| Official API only | WhatsApp uses Baileys (unofficial) | OpenClaw has no Meta Cloud API channel; personal single-user, low volume | F004 |

**Hard Boundaries (no exceptions possible)**: Privacy boundaries
(`02-Growth/_private/`), credential-in-code prohibition, agent traceability.

### Monitoring

- **Security audit**: Daily at 3 AM — Docker images, services, ports, SSH keys,
  crontabs, pip packages, hosts file, .pth files
- **Backup verification**: Nightly Restic with weekly integrity check
- **Action log audit**: felix-core-audit monitors for anomalies
- **C2 sinkholing**: Blocked domains in `/etc/hosts`

---

## 9. Constitution and Governance

### Current Constitution

Located at `.kittify/constitution/constitution.md`. Governs:
- Testing standards, quality gates, branch strategy
- Performance benchmarks, deployment constraints
- Policy summary, exception policy

### New Directives (to be incorporated)

**A. Narrow Agent Scope** — Agents must be built narrow to aid troubleshooting
and maintenance. One responsibility per agent. Orchestrators gain flexible
execution options from granular agents.

**B. Earned Autonomy — Three-Gate Model** — Agents progress through
Human In The Middle → Human Monitored → Autonomous. Every agent starts at
Gate 1. Progression requires demonstrated reliability and Kent's explicit
approval.

**C. Central Action Logging** — All agents and orchestrators log all actions
centrally at granularity supporting human and machine auditability. Implemented
via OpenTelemetry collector on office2.

**D. Safety Parameters and Clear Boundaries** — Agents stop and alert when
asked to do something outside their scope or that they don't know how to do.
They never fail silently.

### Operating Principles

1. Transformative action over comfortable inaction
2. Insistence is a feature
3. Kent has final say — always
4. Transparency about limits
5. Goal context is the compass
6. The second brain is the content; the system is the engine
7. Security over convenience
8. Privacy is absolute
9. Open source posture
10. Extensible by design

---

## 10. Phased Implementation Approach

### What Exists (F001–F004)

| Feature | What | Area |
|---------|------|------|
| F001 | Vikunja Docker deploy, project structure, identity labels | Core Hub |
| F002 | OpenClaw install, credential store, Anthropic API | Core Hub |
| F003 | Whisper transcription skill, transcribe-api hardening | Core Hub |
| F004 | WhatsApp channel (Baileys), QR pairing, E2E verified | Core Hub |

**Current state**: Infrastructure foundation deployed. No agent teams,
no automation skills, no external integrations beyond WhatsApp.

### Foundation Phase (Next)

Before any capability area can grow, the foundation must be completed:
- Central action logging (OpenTelemetry collector)
- Agent team structure in OpenClaw (5 teams, routing)
- Autonomy gate framework
- Google Calendar + Gmail integration (OAuth2)
- Vikunja API skill (CRUD wrapper for all agents)
- Constitution update (incorporate new directives)

### Capability Buildout Phase

Each area builds its first features independently:
- SuperAdmin: Daily briefing, voice capture pipeline, escalation engine
- Development: OpenClaw-integrated spec-kitty workflows
- Content Creation: Canva integration, content pipeline
- BizOps: HubSpot CRM, lead capture

### Advanced Phase

Cross-team workflows, advanced autonomy (Gate 2/3 agents), video content,
multi-business orchestration, proactive system behavior.

**Detailed roadmap**: See Deliverable 6 (WP08) — Feature and Capability Roadmap.

---

## 11. Open Questions and Decisions

These items require Kent's input and are documented rather than assumed:

| # | Topic | Options | Impact |
|---|-------|---------|--------|
| 1 | CRM confirmation | HubSpot (mentioned) vs alternatives | BizOps integration |
| 2 | Invoicing tool | Stripe, QuickBooks, Wave, FreshBooks | BizOps billing |
| 3 | Metal casework Google account | New Workspace, shared, TBD | Identity routing |
| 4 | Metal casework CRM | Shared HubSpot pipeline vs separate | BizOps routing |
| 5 | 02-Growth/ access scope | Which non-private folders for SuperAdmin | Privacy boundary |
| 6 | Journal read access | Should SuperAdmin read journal entries? | Privacy |
| 7 | Webhook receipt strategy | Polling vs Tailscale Funnel vs CF Worker | Real-time notifications |
| 8 | Content calendar location | Vikunja vs CRM | Content workflow |

---

*Living document. Version increments on architectural change. Detailed feature
specs managed by spec-kitty against this architecture.*
