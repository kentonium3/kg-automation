---
title: "Felix — Capability Roadmap & Strategy"
doc_type: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2026-04-03'
revision: v0.3
audience: agents_and_humans
---

# Felix — Capability Roadmap & Strategy
## Living Document — Status & Decision Support

**Last updated**: 2026-04-03 | **Current focus**: Executive Assistant (Area B) | **F-Series**: F013 complete, F014 next

---

## North Star

Felix is Kent Gale's personal AI operating system — an accountability and automation
infrastructure spanning five capability areas. It is not a task manager or a chatbot.

Felix operates on a founding premise: Kent has declared who he intends to become and
what he intends to build. Felix holds those declarations in trust, surfaces them
persistently, and ensures the gap between intention and action is never comfortable
to ignore.

Felix exists to deliver extraordinary and unprecedented personal leverage through
emerging AI technologies. The purpose is concrete: use AI-assisted automation to build
and run businesses that generate wealth, while affording the time and freedom to live
fully. AI agent orchestration, automated research, autonomous business operations, and
AI-generated content and code are not productivity tools layered onto existing work —
they are the engine of a fundamentally different way of building and operating. Felix
is how that engine is built and kept running.

**What full maturity looks like**: Five integrated agent teams operating across all
life domains — autonomously executing within earned boundaries, escalating
appropriately, and creating compounding leverage on Kent's time and decision quality.
Businesses that run. Wealth that compounds. Time that is Kent's to direct.

---

## Five Capability Areas

| Area | Name | Purpose | Status |
|------|------|---------|--------|
| A | Core Hub | Build, operate, govern, and secure Felix | Sufficient ↻ |
| B | Executive Assistant | Personal executive function and accountability | Active 🔄 |
| C | Development | AI-assisted application and business system development | Not started ⬜ |
| D | Content Creation | Cross-team content generation (shared service) | Not started ⬜ |
| E | Business Operations | Digital business operations across all ventures | Not started ⬜ |

**Note on Core Hub (A)**: Infrastructure, governance, and security — not a user-facing
capability area. "Sufficient" means it supports everything currently active, not that
it is closed. Core Hub grows with every new area activation. Key planned expansions:
OpenTelemetry action logging, security agent (adversarial inspection + threat intel
ingestion), governance framework for directed self-modification, off-site backup,
and active alerting. See *Roadmap Principles* and *Open Decisions — D06*.

**Note on area iteration**: Each area starts with basic core capabilities. As learning
accumulates and concrete needs emerge — particularly from consulting and business
acquisition work — the sequence cycles back. Areas are not built once and closed; they
are iterated as the system and its purposes mature.

---

## Roadmap Principles

These principles govern how the Felix feature sequence is designed. They apply to every
area and capability cluster.

### User/infrastructure development cycle

Felix features alternate intentionally between user-facing capabilities and the
infrastructure required to support them. The general pattern is: **user feature →
infrastructure feature → user feature**. Neither type is more important. User features
are the point; infrastructure features are what make the next user feature possible.

This cycle exists because delivering only user features without the underlying
infrastructure produces brittle systems, while building only infrastructure without
delivering user value produces expensive scaffolding nobody uses. The cycle is the
discipline for keeping both in balance.

### Infrastructure is active, not complete

An infrastructure cluster is sufficient at any moment only relative to the user features
it currently supports. Every new user capability that requires new infrastructure will
reactivate infrastructure work. This is expected and correct — it is a sign the system
is growing, not a sign of poor planning.

When a cluster is marked "sufficient," it means it is not blocking anything currently
planned. It does not mean it is closed. Infrastructure clusters cycle between active and
sufficient as the system grows. The Infrastructure Core cluster will never be permanently
complete.

### The flywheel goal

Well-designed infrastructure investments unlock multiple subsequent user features — not
just the one immediately ahead. A Vikunja API skill enabled every agent that touches
tasks. A Calendar OAuth integration will enable every scheduling capability across
multiple clusters. The architectural goal is for infrastructure investments to have this
leverage property: each one removing a constraint that was blocking several things at
once, compressing the time to deliver user value and accelerating the cycle.

The flywheel is working when completed infrastructure features disproportionately enable
user features — when each infrastructure investment returns more user value per unit of
work than the one before it.

### Reading the cluster view

The cluster status table is a snapshot, not a ledger. The feature type tag in the
F-series tables (U: user-facing, I: infrastructure) and cluster membership together
tell the full story of where work is concentrated at any given time.

---

## Why Executive Assistant First

Three reinforcing reasons, in order of weight:

**1. Learning and discovery** — EA development is the primary vehicle for learning
agent orchestration, the OpenClaw runtime, the three-gate autonomy model, and the
full technology stack. This knowledge is the prerequisite for building Areas C–E
competently. Building the wrong thing here has compounding costs. Building correctly
creates compounding leverage.

**2. Time leverage** — EA capabilities directly return time to Kent across all five
life domains. Every hour recovered funds capacity for everything else.

**3. Accountability and decision support** — The system's founding value proposition.
Goal management, commitment tracking, and habit accountability are the reason Felix
exists. These must be real before anything else is worth building.

### EA Foundation Threshold (D01 — Resolved)

EA is ready to expand to additional capability areas when all of the following are true:

- [ ] Voice capture → structured task creation and updates work reliably without friction
- [ ] Voice capture → calendar event creation and updates work reliably without friction
- [ ] Proactive accountability is real (actual insistence, not just task listing)
- [ ] Goal context is live and influences task prioritization
- [ ] Daily briefing delivers actionable signal, not noise
- [ ] Daily task prioritization and calendaring of work sessions is negotiated smoothly;
      effective voice interaction patterns are established
- [ ] Deep research job management works end-to-end: request by voice, autonomous
      execution, notification on completion (e.g., metal casework industry report)
- [ ] Next EA expansion priorities are explicitly defined before expansion begins

---

## Area B: Executive Assistant — Current State

### Feature Clusters

| Cluster | Description | Type | Status |
|---------|-------------|------|--------|
| Infrastructure Core | Task store, runtime, voice pipeline, messaging channel | I | ↻ Sufficient |
| Knowledge Foundation | Goal structure, vault cleanup, constitution and governance | I/U | ↻ Sufficient |
| Task Intelligence | Structured task creation, enrichment, clarification via agent | U | ↻ Sufficient* |
| Accountability Engine | Escalation, commitment tracking, proactive follow-up, negotiation | U | ⬜ Planned |
| Briefing & Reporting | Daily briefing, weekly review, track record, Someday surfacing | U | ⬜ Planned |
| Calendar Integration | Time-blocking, conflict detection, task ↔ calendar event linking | I/U | ⬜ Planned |
| Email Integration | Triage, digest, solicitation management, identity routing | I/U | ⬜ Planned |

**I = infrastructure · U = user-facing · I/U = delivers both**
*Task Intelligence: F013 complete. Refinement work identified and tracked; not blocking next cluster.

### F-Series Feature Progress

**Completed: F001–F013**

| # | Feature | Type | Cluster |
|---|---------|------|---------|
| F001 | Vikunja Docker deploy + project structure | I | Infrastructure Core |
| F002 | OpenClaw install + credential store + Anthropic API | I | Infrastructure Core |
| F003 | Whisper transcription skill | I | Infrastructure Core |
| F004 | WhatsApp channel (Baileys) | I | Infrastructure Core |
| F005 | System architecture review + spec standards | I | Infrastructure Core |
| F006 | Goal + outcome structure (declaration format, Goals-MOC) | U | Knowledge Foundation |
| F007 | Vikunja API skill (CRUD wrapper) | I | Infrastructure Core |
| F008 | Inbox processing migration to office2 | U | Infrastructure Core |
| F009 | Daily habit check-in | U | Accountability Engine |
| F010 | Obsidian sync office2 | I | Infrastructure Core |
| F011 | Second brain vault cleanup | U | Knowledge Foundation |
| F012 | Constitution + agent governance setup | I | Knowledge Foundation |
| F013 | Vikunja Task Intelligence Agent (`felix-admin-tasker`) | U | Task Intelligence |

**Planned (not yet spec'd, sequenced by dependency)**

| Feature | Type | Cluster | Depends On |
|---------|------|---------|------------|
| Escalation engine (F014) | I | Accountability Engine | F013 |
| Commitment Manager Agent | U | Accountability Engine | F013, F014 |
| Google Calendar skill — OAuth (F015) | I | Calendar Integration | F013 |
| Task ↔ calendar event linking (F016) | U | Calendar Integration | F015 |
| Daily briefing heartbeat (F017) | U | Briefing & Reporting | F013, F015 |
| Level 1–2 escalation heartbeat (F018) | U | Accountability Engine | F014, F015 |
| Gmail integration skill (F019) | I | Email Integration | F015 OAuth creds |
| Email triage + digest agent (F020) | U | Email Integration | F019 |
| Solicitation folder hygiene (F021) | U | Email Integration | F019 |
| Deep research job management | U | Task Intelligence | F014, F017 |

---

## Open Decisions

Resolved decisions are retained for record. Open decisions require action before
dependent features can be spec'd.

| # | Decision | Status |
|---|----------|--------|
| D01 | EA Foundation Threshold | ✅ Resolved — see above |
| D02 | Capability area sequencing | ✅ Resolved — see below |
| D03 | Email integration path | ✅ Resolved — Gmail direct |
| D04 | Webhook strategy | ⏸ Deferred — not blocking |
| D05 | Agent vault read permissions | ✅ Resolved — see below |
| D06 | Security and Governance as Core Hub capabilities | 🔄 Scoping required |
| D07 | CRM / relationship management tooling | 🔍 Research required |

### D02 — Capability area sequencing (Resolved)

1. **Content (D) second** — shared service consumed by all other areas; builds leverage
   across the whole system before it's needed
2. **BizOps (E) third** — basic core capabilities focused on revenue; consulting and
   metal casework business operations
3. **Development (C) organic** — emerges from ongoing Felix build work; not a discrete
   activation

Each area starts with basic core capabilities. As learning accumulates and concrete
needs emerge — particularly from consulting work and business acquisition — the sequence
iterates. Areas C, D, and E will each see multiple passes as requirements become clearer.

### D03 — Email integration path (Resolved)

**Decision**: Gmail direct via Google OAuth2 API. Avoids Jace.ai cost and dependency.
If Google API costs prove comparable to or greater than Jace.ai, decision is revisited.

**Email management priorities (in order)**:
1. Intelligent inflow triage: identify items requiring immediate or near-term attention
   and action; separate from information of interest
2. Digest formatting: information-of-interest items surfaced in digest form
3. Solicitation classification: commercial solicitations filed to a designated folder
4. Solicitation hygiene routine: retain X days per vendor, purge obsolete solicitations
   on a schedule

Identity routing (personal vs. Intentional vs. metalbox) applies from the start.

### D04 — Webhook strategy (Deferred)

Webhooks allow external services to push real-time notifications to Felix rather than
Felix polling on a schedule. The constraint: webhooks require a publicly reachable
HTTPS endpoint, which conflicts with the Tailscale-only network posture. Receipt would
require Tailscale Funnel or a Cloudflare Worker relay. Not needed by any currently
planned feature. Revisit when a specific capability demands near-real-time response
(e.g., immediate alerting on flagged email).

### D05 — Agent vault read permissions (Resolved)

**Decision**: Agents may read any vault folder or file as determined by their area of
concern and intentional architectural design. Scope is defined per agent in standing
orders, not as a blanket system-wide policy.

Permissions may be implemented by direction (rules and skill configuration) or at the
OS level via user and group access controls. Both mechanisms are valid and may be
combined. `02-Growth/_private/` remains absolutely off-limits to all agents — no
exceptions, no opt-in.

A formal agent permission strategy is needed as the agent inventory grows. This is
tracked under D06 / Core Hub governance work.

### D06 — Security and Governance as Core Hub capabilities (Scoping required)

Security and Governance are foundational Core Hub capabilities, not optional enhancements.

**Security scope**:
- Best-practice design advisor role integrated into feature development workflow
- Automated inspection and monitoring (existing `audit.sh` is the foundation; needs
  active alerting and expanded coverage)
- Published threat intelligence ingestion: CISA, SANS ISC, NVD, and similar feeds
  processed and surfaced as actionable advisories
- Supply chain compromise is the primary threat vector of concern: dependency pinning,
  source review, and provenance verification are non-negotiable practices
- Evaluation of a dedicated security agent (non-Claude model for adversarial mindset)

**Governance scope**:
- Essential prerequisite for any directed self-modification of Felix or its subsystems
- Defines what changes agents may propose to their own configuration, skills, and scope
- Audit trail and approval workflow for system-modifying actions
- Change control that distinguishes routine feature work from structural self-modification

**Action required**: Scope a Core Hub feature spec covering security agent architecture
and governance framework before any self-modification capability is designed.

### D07 — CRM and relationship management tooling (Research required)

HubSpot is currently installed and was selected for familiarity, not fitness. Research
is required before committing to any integration.

**Requirements span at least three distinct use cases**:

1. **Personal networking** — maintaining relationships with people Kent wants to know
   and be around; not a sales funnel, a relationship investment tracker
2. **Intentional LLC** — consulting pipeline management; low volume, high value, high
   touch; relationship depth matters more than throughput
3. **Online business (metalbox and future)** — marketing automation, lead capture,
   ecommerce order integration, customer support; high volume relative to consulting

These use cases may be best served by a single API-forward platform, or by separate
tools purpose-fit for each. The rapidly evolving CRM and relationship intelligence
space warrants research before commitment.

**Research questions**:
- What API-forward CRM platforms best serve all three use cases, or which
  combination of tools covers them without excessive integration overhead?
- Does HubSpot's API coverage, pricing, and architecture fit, or is there a
  better-suited alternative given the full requirements?
- Is there a personal relationship management tool (personal CRM) that warrants
  a separate integration alongside a business CRM?

**Next action**: Assign a deep research job to Felix once the research job management
capability (see planned features) is available. Until then, HubSpot remains in place
but no integration work should begin.

---

## Capability Sequencing

```
Core Hub (A) ─── Sufficient (grows continuously)
     │ Governance + Security scoping (D06)
     ▼
Executive Assistant (B) ─── CURRENT FOCUS
  [EA Foundation Threshold — 8 criteria, D01 resolved]
     │
     ▼
Content (D) ─── Second: shared service, enables B and E
     │
     ▼
BizOps (E) ─── Third: basic core, revenue focus
     │
     ▼
Development (C) ─── Organic, concurrent with above

────────────────────────────────────────────────────
Each area iterates. Activation is not a single pass.
Consulting and acquisition work drives re-prioritization.
```

---

## Design Principles (Stable)

These govern every feature decision. They change only with deliberate review.

1. **Transformative action over comfortable inaction** — Felix resists drift
2. **Insistence is a feature** — Explicit permission to escalate when commitments are at risk
3. **Kent has final say — always** — Felix negotiates and pushes back; it does not override
4. **Transparency about limits** — Agents declare boundaries; never fail silently
5. **Narrow agent scope** — One responsibility per agent
6. **Earned autonomy** — Gate 1 (Human In Middle) → Gate 2 (Monitored) → Gate 3 (Autonomous)
7. **Central action logging** — All agent actions logged at machine-auditable granularity
8. **Privacy is absolute** — `02-Growth/_private/` is never accessed by any agent. No exceptions.
9. **GitOps and spec discipline** — Protected main branch; specs before implementation; "What and Why, not How"
10. **Extensible architecture** — New tools and agent teams without major rework
11. **Security and governance are first-class** — Supply chain integrity, adversarial inspection,
    and change governance are built in, not bolted on

---

## Document Maintenance

| Section | Update frequency | Trigger |
|---------|-----------------|---------|
| North Star | On strategic pivot only | Fundamental change to mission |
| Five Capability Areas — status | Per area activation | Area goes active or iterates |
| Roadmap Principles | On strategic pivot only | Change to development approach |
| F-Series progress | Per feature completion | F-series completion checklist |
| Feature clusters — status | Per cluster status change | Active ↔ Sufficient transition |
| Open Decisions | On new question or resolution | Discovery, research result, or decision |
| Capability Sequencing | On strategic pivot | EA Threshold reached or sequencing shifts |
| Design Principles | Quarterly or on major pivot | Architectural change |

---

*This is a living document. It is the authoritative source for roadmap intent,
capability status, and open decisions. Tactical feature specs live in
`docs/func-spec/`. The reference architecture lives in
`docs/design/personal-ai-system-spec-v1.0.md`.*

*Version increments on structural change. Minor updates (status, decisions) are
made in place with `last_updated` refreshed.*
