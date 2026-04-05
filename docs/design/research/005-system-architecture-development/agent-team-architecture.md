---
title: "Agent Team Architecture: Felix System Architecture"
doc_type: explanation
status: approved
owners: [kgale]
---
# Agent Team Architecture: Felix System Architecture

**Date**: 2026-03-29
**WP**: WP06 — Agent Team Architecture (Deliverable 3)
**Status**: Complete

---

## Team Definitions

### Modeling Approach

OpenClaw does not support "teams" natively. Teams are modeled as **named
agents** with isolated workspaces, independent tool policies, and routing
configuration. Each agent has its own IDENTITY.md, SOUL.md, AGENTS.md,
and TOOLS.md.

Agent-to-agent messaging must be explicitly enabled (`tools.agentToAgent`)
for cross-team coordination.

---

### Team A: Core Hub — felix-core

**Scope**: System infrastructure, monitoring, routing, agent lifecycle,
audit, and governance.

**Boundary**: Core Hub owns the system itself. It does not perform user-facing
tasks (no briefings, no content, no CRM). It enables all other teams.

**Agent Inventory**:

| Agent | Responsibility | Gate Start |
|-------|---------------|------------|
| felix-core-router | Message routing, team delegation, cross-team coordination | Gate 1 |
| felix-core-heartbeat | Scheduled jobs (inbox poll, escalation checks, health monitoring) | Gate 1 |
| felix-core-audit | Action log monitoring, anomaly detection, compliance checks | Gate 1 |

**Skills**: System health checks, agent configuration management, Vikunja
project structure maintenance, security baseline verification.

**Integration touchpoints**: All internal services (Vikunja, OpenClaw, Obsidian
Sync, Restic, security monitor). OpenTelemetry collector.

---

### Team B: SuperAdmin — felix-admin

**Scope**: Kent's executive function — task management, calendar, email,
briefings, reminders, escalation, priority negotiation.

**Boundary**: SuperAdmin operates within the system Core Hub maintains. It does
not modify system configuration, deploy services, or manage agents. It uses
integrations provided by Core Hub.

**Agent Inventory**:

| Agent | Responsibility | Gate Start |
|-------|---------------|------------|
| felix-admin-briefing | Daily briefings, weekly reviews, track record reports | Gate 1 |
| felix-admin-calendar | Meeting scheduling, time-blocking, conflict detection | Gate 1 |
| felix-admin-email | Email triage, summarization, draft creation | Gate 1 |
| felix-admin-escalation | Overdue task escalation, priority negotiation, reminders | Gate 1 |
| felix-admin-capture | Voice note processing, inbox classification, task routing | Gate 1 |

**Skills**: Vikunja CRUD, Google Calendar read/write, Gmail read/compose,
WhatsApp message formatting, Goal Context Loader, escalation state management.

**Integration touchpoints**: Vikunja, Google Calendar, Gmail, WhatsApp,
transcribe-api, second brain (01-Constitution, 00-Inbox).

---

### Team C: Development — felix-dev

**Scope**: AI-assisted application and system development using Claude Code
and spec-kitty.

**Boundary**: Development builds applications and systems. It does not manage
Felix infrastructure (that's Core Hub) or create marketing content (that's
Content Creation).

**Agent Inventory**:

| Agent | Responsibility | Gate Start |
|-------|---------------|------------|
| felix-dev-orchestrator | Development workflow management, spec-kitty coordination | Gate 1 |
| felix-dev-builder | Code implementation, testing, PR creation | Gate 1 |

**Skills**: Shell execution (Claude Code, spec-kitty, git), GitHub API,
code review patterns, test execution.

**Integration touchpoints**: Claude Code, spec-kitty, GitHub, Git repos.

---

### Team D: Content Creation — felix-content

**Scope**: Content generation across all formats — text, graphics,
presentations, PDFs. Shared service for all other teams.

**Boundary**: Content Creation produces content. It does not publish or
distribute (that's BizOps or the requesting team). It does not manage
brand strategy (that's SuperAdmin via constitution docs).

**Agent Inventory**:

| Agent | Responsibility | Gate Start |
|-------|---------------|------------|
| felix-content-writer | Blog posts, LinkedIn posts, white papers, email copy, web copy | Gate 1 |
| felix-content-designer | Graphics, presentations, visual content via Canva | Gate 1 |
| felix-content-formatter | Multi-format transformation (same content → blog, LinkedIn, email, etc.) | Gate 1 |

**Skills**: Claude text generation with brand guidelines, Canva API, Mermaid/D2
diagram generation, Pandoc PDF generation, multi-format content templates.

**Integration touchpoints**: Canva, Anthropic API, Mermaid/D2, Pandoc,
second brain (04-Business, 01-Constitution/Personal-Brand.md).

---

### Team E: BizOps — felix-bizops

**Scope**: Digital business operations — CRM, marketing, customer support,
invoicing, reporting, campaign execution.

**Boundary**: BizOps operates business systems. It does not create content
(requests from Content Creation) or build tools (requests from Development).

**Agent Inventory**:

| Agent | Responsibility | Gate Start |
|-------|---------------|------------|
| felix-bizops-crm | Lead management, deal pipeline, contact management | Gate 1 |
| felix-bizops-marketing | Campaign planning, execution, cross-platform scheduling | Gate 1 |
| felix-bizops-reporting | Weekly business reports, pipeline summaries, KPIs | Gate 1 |

**Skills**: HubSpot API (when confirmed), social media posting, email marketing,
report generation, identity-based routing (personal/intentional/metalcasework).

**Integration touchpoints**: HubSpot (planned), social media APIs (planned),
email marketing platform (planned), Vikunja (task tracking), WhatsApp (reports).

---

## Cross-Team Orchestration Patterns

### Pattern 1: Core Hub as Router

felix-core-router is the primary message handler for inbound messages
(WhatsApp, email, webhooks). It classifies the message intent and routes
to the appropriate team agent.

```
Inbound message (WhatsApp/webhook)
  → felix-core-router classifies intent
  → Routes to: felix-admin-* (personal task/calendar/email)
              felix-bizops-* (business inquiry/lead)
              felix-dev-* (development request)
              felix-content-* (content request)
```

### Pattern 2: Request-Response Between Teams

When one team needs services from another (e.g., BizOps needs content from
Content Creation), the pattern is:

```
felix-bizops-marketing needs blog post graphics
  → Sends request to felix-content-designer via agent-to-agent messaging
  → felix-content-designer produces assets
  → Returns result to felix-bizops-marketing
  → felix-bizops-marketing publishes
```

This requires `tools.agentToAgent` enabled between specific agent pairs.

### Pattern 3: Broadcast for Multi-Team Awareness

For messages that affect multiple teams (e.g., Kent says "I have a meeting
with a prospect tomorrow about metal casework"):

```
Inbound message
  → felix-core-router identifies multi-team relevance
  → Routes primary action to felix-admin-calendar (schedule meeting)
  → Notifies felix-bizops-crm (update deal pipeline)
  → Notifies felix-content-designer (prepare materials if needed)
```

OpenClaw broadcast groups (WhatsApp-only, experimental) could handle this
for WhatsApp messages. For non-WhatsApp triggers, Core Hub explicitly
routes to multiple agents.

### Pattern 4: Scheduled Coordination

felix-core-heartbeat runs scheduled tasks that touch multiple teams:

```
Daily 8AM briefing:
  → Queries Vikunja (tasks from all teams)
  → Queries Google Calendar (events)
  → Queries HubSpot (pipeline updates — when available)
  → Compiles briefing via felix-admin-briefing
  → Sends via WhatsApp
```

---

## Three-Gate Autonomy Model Per Team

### Gate Definitions (All Teams)

| Gate | Name | Behavior | OpenClaw Config |
|------|------|----------|----------------|
| 1 | Human In The Middle | Agent proposes, human approves every action | `tools.exec.ask: "always"`, `tools.exec.security: "allowlist"` |
| 2 | Human Monitored | Agent acts on allowlisted operations, async review | `tools.exec.ask: "on-miss"`, cron-based activity reports |
| 3 | Autonomous | Agent acts freely within scope, heartbeat monitoring | `tools.exec.ask: "off"`, `tools.exec.security: "full"` |

### Gate Progression Criteria

**Every agent starts at Gate 1. No exceptions.**

To advance from Gate 1 → Gate 2:
- Minimum 30 days of operation at Gate 1
- Zero safety boundary violations
- Consistent accurate classification/routing (for router agents)
- Kent explicitly approves the transition
- Transition logged in central action log

To advance from Gate 2 → Gate 3:
- Minimum 90 days of operation at Gate 2
- Zero safety boundary violations in monitoring period
- Action log review shows no anomalous patterns
- Kent explicitly approves the transition
- Scope boundaries formally documented and locked

### Risk-Adjusted Gate Progression

| Team | Risk Profile | Expected Gate 2 Timeline | Expected Gate 3 |
|------|-------------|-------------------------|-----------------|
| Core Hub (A) | High (system modification) | 60+ days | Possibly never for config agents |
| SuperAdmin (B) | Medium (personal data, communications) | 30 days for read-only; 60 for write | Selective (briefings maybe, email drafts unlikely) |
| Development (C) | Medium (code changes) | 30 days | Selective (tests maybe, production code unlikely) |
| Content Creation (D) | Low-Medium (content drafts) | 30 days | Likely for draft generation |
| BizOps (E) | Medium-High (customer communications) | 60 days | Selective (reports maybe, customer comms unlikely) |

### Gate Switching Implementation

Gate transitions are config changes to each agent's section in `openclaw.json`:
1. Core Hub administrator (Kent or felix-core-audit) updates the agent's
   `tools.exec.ask` and `tools.exec.security` settings
2. The change is committed to the config repo
3. OpenClaw gateway picks up the new config
4. Central action log records the gate transition (custom hook)

---

## Agent/Tool Onboarding Process

### Adding a New Agent

1. **Propose**: Document the agent's purpose, scope, team, and initial skills
   in a brief (markdown). Kent reviews.
2. **Configure**: Create workspace directory with IDENTITY.md, SOUL.md,
   AGENTS.md, TOOLS.md. Set tool policies to Gate 1 (most restrictive).
3. **Register**: Add agent to `openclaw.json` with routing bindings.
4. **Test**: Run agent in isolation with test scenarios. Verify scope boundaries.
5. **Deploy**: Enable agent in production. Log the deployment in action log.
6. **Monitor**: 30-day Gate 1 observation period begins.

### Adding a New Integration

1. **Evaluate**: Document the integration purpose, auth method, data flow,
   and Tailscale-only compatibility.
2. **Credential setup**: Add credentials to office2 secrets store following
   the established pattern (mode 700 directory, mode 600 files).
3. **Skill creation**: Create an AgentSkills-compatible skill folder with
   SKILL.md defining the integration interface.
4. **Assign to team**: Attach the skill to the appropriate team agent(s).
5. **Test**: Verify integration works end-to-end at Gate 1.
6. **Document**: Update architecture docs per change-control.md.

### Adding a New Tool

1. **Evaluate**: Document the tool, its purpose, license, and security review.
2. **Install**: Install on office2 following the established pattern (pinned
   version, reviewed before updates).
3. **Create skill**: If the tool needs agent access, create a skill that wraps it.
4. **Security baseline**: Reset security audit baselines to account for the new tool.
5. **Document**: Update service inventory and architecture docs.

---

## Agent Communication Matrix

| From → To | core-router | admin-* | dev-* | content-* | bizops-* |
|-----------|------------|---------|-------|-----------|----------|
| core-router | — | Route messages | Route requests | Route requests | Route requests |
| admin-* | Escalate unknown | Internal | Request dev work | Request content | — |
| dev-* | Report status | — | Internal | — | — |
| content-* | Report completion | — | — | Internal | Return assets |
| bizops-* | Report status | — | Request dev | Request content | Internal |

Agent-to-agent messaging must be explicitly enabled for each allowed pair.
Pairs not in this matrix should NOT have messaging enabled (principle of
least privilege).
