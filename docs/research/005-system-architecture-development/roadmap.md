# Feature and Capability Roadmap: Felix System Architecture

**Date**: 2026-03-29 (revised 2026-03-29)
**WP**: WP08 — Feature and Capability Roadmap (Deliverable 6)
**Status**: Complete — revised to reflect prioritized feedback
**Note**: Previous F005-F015 numbering from v0.3 is discarded. New feature
numbers are assigned below based on the validated v1.0 architecture.

---

## Guiding Principle

The roadmap follows a user/infrastructure/user/infrastructure pattern.
Infrastructure is only built when a specific user feature requires it.
No infrastructure is built speculatively. The immediate roadmap (Phase 1)
is detailed and firm. Phase 2 is directional. Phase 3 is intentional but
loose — experience using Phase 1 and 2 features will inform the details.

**Top priority**: Goal/outcome management and commitment/habit tracking.
These capabilities are foundational — if Felix helps Kent focus on fewer,
more intentional actions and tracks follow-through, everything else gets
easier. All other capability areas are subordinate until these are
functional and delivering daily value.

---

## Current State: What Has Been Built (F001–F004)

| Feature | What | Capability Area | What It Enables |
|---------|------|----------------|-----------------|
| F001 | Vikunja Docker deploy, project structure, identity labels, saved filters | Core Hub (A) | Task store for all teams, web UI for Kent |
| F002 | OpenClaw install, credential store, Anthropic API direct | Core Hub (A) | Agent orchestration engine, LLM intelligence |
| F003 | Whisper transcription skill, transcribe-api rebind to Tailscale-only | Core Hub (A) | Voice note processing pipeline |
| F004 | WhatsApp channel (Baileys), QR pairing, E2E messaging verified | Core Hub (A) | Inbound/outbound messaging channel |

**Current capability coverage**:
- Infrastructure is in place: task store, orchestration, transcription, WhatsApp
- Zero automation is running — no agents, no skills, no heartbeats
- No goal declarations, no habit tracking, no briefings, no escalation

---

## Phase 1: Goal Management and Commitment Tracking

**Theme**: Make a serious game of doing what you say you're going to do.

**Entry criteria**: F005 (this research project) complete and approved.

**Exit criteria**: Kent can declare goals with target dates and evidence,
track recurring commitments daily via WhatsApp, see weekly progress
reports, and receive persistent escalation on overdue items. The core
accountability loop is operational.

**Pattern**: user → infra → user → infra → user → infra → user → infra

---

### F006 — User Feature: Goal and Outcome Structure

**What it delivers to Kent**: A formal place in the system to declare goals
using the outcome declaration format ("On [date], I have [outcome] as
evidenced by [observable proof]"). Goal declarations live in Vikunja as
a dedicated project with date anchoring and in Obsidian (01-Constitution/)
as the authoritative reference. No new services deployed.

**Why first**: Until goals exist as structured data the system can reason
against, everything else is just task management. This feature creates the
anchor for all subsequent priority and commitment decisions.

**Capability area**: SuperAdmin (B) — Goal and Outcome Management
**User stories**: B-G01, B-G02, B-G04
**Dependencies**: F001 (Vikunja), F004 (WhatsApp for capture)
**Infrastructure built**: Vikunja project structure extended for goal
declarations. Goal template defined in Obsidian.
**Complexity**: Small — configuration and structure, no new services

**Success criteria**:
- [ ] Kent can declare a goal via WhatsApp voice note and have it structured
  and stored in Vikunja and Obsidian
- [ ] All active goal declarations visible in a single Vikunja view with
  target dates
- [ ] Goal declaration format documented and usable

---

### F007 — Infrastructure: Vikunja API Skill

**What it enables**: OpenClaw can read and write Vikunja tasks, projects,
labels, and filters programmatically. Foundation skill for all task
automation — nothing that touches Vikunja works without this.

**Capability area**: Core Hub (A)
**Dependencies**: F001 (Vikunja), F002 (OpenClaw)
**Complexity**: Medium — REST API wrapper skill

**Success criteria**:
- [ ] OpenClaw can create, read, update, and delete tasks via Vikunja API
- [ ] OpenClaw can query by project, label, due date, and filter
- [ ] Skill tested end-to-end against live Vikunja instance

---

### F008 — User Feature: Daily Habit Check-in and Commitment Tracking

**What it delivers to Kent**: Daily WhatsApp prompts for each recurring
commitment (meditation, exercise, PT, learning blocks, etc.). Kent marks
each as complete / rescheduled / will-not-do directly in WhatsApp. State
stored in Vikunja. Weekly pattern report shows completion rate this week
vs. last week across all habits.

**Why here**: This is the core of the accountability loop. Once goals
exist (F006) and Vikunja can be written to (F007), this feature closes the
daily loop — capture intent, track execution, report pattern.

**Capability area**: SuperAdmin (B) — Commitment and Habit Tracking
**User stories**: B-H01, B-H02, B-H03, B-H04, B-08, B-09
**Dependencies**: F004 (WhatsApp), F006 (goal structure), F007 (Vikunja API)
**Infrastructure built**: Minimal agent (felix-admin-heartbeat) configured
in OpenClaw. Cron job for daily check-in delivery. Weekly report cron.
**Complexity**: Medium

**Success criteria**:
- [ ] Daily habit check-in delivered via WhatsApp at configured time
- [ ] Kent can respond complete / rescheduled / will-not-do and state is recorded
- [ ] Weekly pattern report delivered showing this-week vs. last-week rates
- [ ] Track record is visible in Vikunja

---

### F009 — Infrastructure: Constitution Update and Minimal Agent Setup

**What it enables**: Constitution formally updated with the four new
directives. Only the specific agents needed for the Phase 1 features are
configured — felix-admin-heartbeat (already started in F008) and
felix-core-router (minimal routing for WhatsApp → correct handler). All
agents set to Gate 1.

**Why minimal**: Don't build all five teams before knowing which agents
deliver value. Build what's needed for the features in flight.

**Capability area**: Core Hub (A)
**Dependencies**: F005 approval, F008 (agents to configure)
**Complexity**: Small

**Success criteria**:
- [ ] Constitution updated with narrow scope, earned autonomy, central
  logging, and safety parameter directives
- [ ] felix-admin-heartbeat operational at Gate 1
- [ ] felix-core-router routes WhatsApp messages to correct handler

---

### F010 — User Feature: Escalation Engine

**What it delivers to Kent**: Persistent follow-up on tasks and commitments
that are overdue or unaddressed. Escalation increases in urgency over time
(levels 1–4). Interactive resolution via WhatsApp: snooze / abandon / new
date / negotiate. Agent has explicit permission to be uncomfortable to ignore.

**Why here**: Goal declarations and habit tracking are only useful if the
system follows through when Kent doesn't. This feature adds the insistence.

**Capability area**: SuperAdmin (B)
**User stories**: B-03, B-07, B-H05, B-H06
**Dependencies**: F007 (Vikunja API), F008 (habit state), F009 (agents)
**Infrastructure built**: felix-admin-escalation agent configured.
Escalation label taxonomy in Vikunja (escalation-1 through escalation-4).
**Complexity**: Medium

**Success criteria**:
- [ ] Overdue tasks escalate through four levels via WhatsApp
- [ ] Kent can snooze, abandon, or set a new date interactively
- [ ] Escalation state visible in Vikunja via labels
- [ ] Agent does not accept silence at level 3+

---

### F011 — Infrastructure: Central Action Logging

**What it enables**: OpenTelemetry collector deployed on office2. OpenClaw
exports traces, metrics, and logs. Felix-specific enrichment layer (team,
action type, autonomy gate). Queryable at `/data/services/felix-audit/`.

**Why here (not earlier)**: Placed after the first wave of user features
are live and generating agent activity worth logging. Building audit
infrastructure before any agents were running would have been speculative.
Now there's real activity to capture.

**Capability area**: Core Hub (A)
**Dependencies**: F008, F010 (agents operational)
**Complexity**: Medium

**Success criteria**:
- [ ] All agent actions from felix-admin-* captured in structured log
- [ ] Log queryable for audit review
- [ ] Gate transitions recorded

---

### F012 — User Feature: Daily Briefing

**What it delivers to Kent**: Morning WhatsApp briefing at 8 AM: active
goals with days-to-target, today's tasks and calendar, habit check-in
prompt, upcoming escalations. By this point the goal structure, habit
tracking, and escalation engine are all feeding into it. The briefing is
the daily operating summary.

**Capability area**: SuperAdmin (B)
**User stories**: B-02, B-G05, B-10
**Dependencies**: F007 (Vikunja API), F009 (agents), F010 (escalation state)
**Infrastructure built**: felix-admin-briefing agent. Daily cron at 8 AM.
**Complexity**: Medium

**Success criteria**:
- [ ] Briefing delivered daily at 8 AM via WhatsApp
- [ ] Briefing includes active goals with target dates
- [ ] Briefing includes today's tasks, overdue items, and upcoming escalations
- [ ] Briefing includes habit check-in prompt

---

### F013 — Infrastructure: Google OAuth2 + Calendar Integration

**What it enables**: One-time OAuth2 authorization (localhost redirect on
Mac). Refresh tokens stored in office2 secrets store. Google Calendar
API skill for OpenClaw. Google Contacts (free with same credential).

**Why here**: Calendar is needed to give tasks and goals time blocks (F014).
Placed after the core accountability loop (F006–F012) is operational.

**Capability area**: SuperAdmin (B)
**Dependencies**: F002 (OpenClaw credential store), F007 (Vikunja API skill)
**Complexity**: Medium

**Success criteria**:
- [ ] OAuth2 authorization complete for personal Google account
- [ ] Refresh tokens in office2 secrets store
- [ ] OpenClaw can read and write Google Calendar events

---

### F014 — User Feature: Calendar and Task Coordination

**What it delivers to Kent**: Declared goals and committed tasks are given
time blocks on the calendar. Calendar and task list stay synchronized.
Conflict detection before scheduling. Meeting scheduling from natural
language via WhatsApp. Recurring habits from the private boundary appear
as calendar events without exposing their origin.

**Capability area**: SuperAdmin (B)
**User stories**: B-04, B-06, B-13, B-14, B-P01
**Dependencies**: F007 (Vikunja API), F012 (briefing), F013 (Calendar)
**Infrastructure built**: felix-admin-calendar agent configured.
**Complexity**: Medium

**Success criteria**:
- [ ] Tasks with due dates can be time-blocked on Google Calendar
- [ ] Calendar conflict detection works before scheduling
- [ ] Recurring habits appear on calendar (origin stays private)
- [ ] Meeting scheduling via WhatsApp creates calendar events

---

### Phase 1 Dependency Graph

```
F005 (approved)
  │
  ├── F006 (Goal Structure) ──→ F007 (Vikunja API) ──→ F008 (Habit Tracking)
  │                                                         │
  │                                                         ▼
  │                                                    F009 (Constitution + Agents)
  │                                                         │
  │                                                         ▼
  │                                                    F010 (Escalation)
  │                                                         │
  │                                                         ▼
  │                                                    F011 (Action Logging)
  │                                                         │
  │                                                         ▼
  │                                                    F012 (Daily Briefing)
  │                                                         │
  │                                                    F013 (Google OAuth2)
  │                                                         │
  │                                                         ▼
  └──────────────────────────────────────────────────→ F014 (Calendar Coordination)
```

**Critical path**: F005 → F006 → F007 → F008 → F009 → F010 → F012 → F013 → F014

**Shortest path to first value**: F006 (goal structure) — immediate,
no new services.

**First time-sensitive value**: F008 (daily habit check-in) — four
features in.

---

## Phase 2: Capture Pipeline and Business Foundations

**Theme**: Complete the capture-to-action loop and establish the first
business operations capability.

**Entry criteria**: Phase 1 complete. Kent is using goal declarations,
habit tracking, escalation, and daily briefing daily. The accountability
loop is working.

**Exit criteria**: Voice capture from Obsidian inbox is automated. First
BizOps capability (CRM) is operational. Content creation pipeline can
produce drafts on demand.

**Note on certainty**: Phase 2 features are directional. The exact
sequencing will be refined based on what's most valuable after Phase 1
is operational. The user/infra pattern continues.

---

### F015 — User Feature: Voice Capture Pipeline

**What it delivers to Kent**: Obsidian inbox processed hourly (and
on-demand via WhatsApp). Notes classified and routed to vault destinations.
Task/commitment items routed to Vikunja. The full capture-classify-route
loop from Wispr Flow → Obsidian → Felix → Vikunja.

**Capability area**: SuperAdmin (B)
**User stories**: B-01, B-15
**Dependencies**: F007 (Vikunja API), F009 (agents)
**Infrastructure built**: felix-admin-capture agent. Hourly inbox poll cron.
**Complexity**: Medium (migrates inbox-processor from Cowork pattern)

---

### F016 — Infrastructure: Weekly Review Skeleton

**What it enables**: Weekly review cron (Sunday 6 PM). Queries goal
progress, habit completion rates, Someday surfacing, constitution
freshness check. Feeds the weekly pattern report already started in F008.

**Capability area**: SuperAdmin (B)
**Dependencies**: F008, F012, F015

---

### F017 — User Feature: Goal Progress Review (Weekly)

**What it delivers to Kent**: Sunday evening WhatsApp summary: progress
toward each declared outcome, habit completion rates this week vs. last,
Someday items surfaced for consideration, upcoming week preview.

**Capability area**: SuperAdmin (B)
**User stories**: B-G05, B-H03, B-12
**Dependencies**: F012 (briefing agent), F015 (capture), F016 (weekly cron)

---

### F018 — Infrastructure: CRM Integration (pending OD-1 decision)

**What it enables**: HubSpot (or confirmed CRM) connected via private app
token. Contact CRUD, deal pipeline, lead tracking. Polling for updates.

**Blocked by**: Open Decision OD-1 — Kent must confirm CRM platform
before this can be specced.

**Capability area**: BizOps (E)
**Dependencies**: F009 (agents), OD-1 confirmed

---

### F019 — User Feature: Lead Capture and Pipeline Tracking

**What it delivers to Kent**: New leads from website auto-entered into
CRM with context. Deal pipeline visible in weekly business report.
Prospect follow-ups managed via WhatsApp commands.

**Capability area**: BizOps (E)
**User stories**: E-01, E-04, E-05
**Dependencies**: F018 (CRM integration)

---

### F020 — Infrastructure: Canva Integration

**What it enables**: Canva API via OAuth2. Design generation, export,
brand kit access assigned to felix-content-designer.

**Capability area**: Content Creation (D)
**Dependencies**: F009 (agents)

---

### F021 — User Feature: Content Draft Pipeline

**What it delivers to Kent**: Blog posts, LinkedIn posts, white papers,
and email copy generated from briefs via WhatsApp. Multi-format
transformation (one brief → blog + LinkedIn + email versions).
Output to second brain (04-Business/) or office2.

**Capability area**: Content Creation (D)
**User stories**: D-01, D-02, D-03, D-07
**Dependencies**: F020 (Canva), F009 (agents)

---

## Phase 3: Advanced Capabilities and Cross-Team Automation

**Theme**: Cross-team automation, multi-business operations, advanced
content, autonomy progression.

**Certainty level**: Intentional but loose. Phase 1 and 2 experience
will substantially shape the details.

**Entry criteria**: Phase 2 operational. Agents have 30–90 days of Gate 1
history. Some agents ready for Gate 2 evaluation.

### Indicative Phase 3 Features (subject to revision)

- **F022**: Cross-team request routing (BizOps → Content, SuperAdmin → Content)
- **F023**: Multi-business identity routing (Intentional Workspace, metal casework label)
- **F024**: Goal Context Loader (constitution docs inform every priority decision)
- **F025**: Cross-platform publishing (LinkedIn, Instagram, website, email)
- **F026**: Email marketing campaigns (Mailchimp or HubSpot Email)
- **F027**: Invoicing integration (tool TBD — open decision OD-2)
- **F028**: Felix-integrated development workflows (spec-kitty + Claude Code via OpenClaw)
- **F029**: Agent autonomy advancement (formal Gate 1 → Gate 2 process based on audit log)
- **F030**: System self-diagnosis (Core Hub detects service failures and proposes fixes)
- **F031**: Metal casework operations (when business is active — order management, CRM)

---

## Phase Summary

| Phase | Features | Primary Theme | Certainty |
|-------|----------|--------------|-----------|
| Deployed | F001–F004 | Infrastructure foundation | Complete |
| F005 | Research | Architecture and roadmap | Complete |
| Phase 1 | F006–F014 | Goal management and commitment tracking | High — detailed and firm |
| Phase 2 | F015–F021 | Capture pipeline and business foundations | Medium — directional |
| Phase 3 | F022–F031 | Cross-team, advanced content, autonomy | Low — intentional but loose |

---

## Full Feature Dependency Map

```
F001–F004 (deployed)
  │
  └── F005 (this project, approved)
        │
        ├── F006 (Goal Structure) ─→ F007 (Vikunja API) ─→ F008 (Habit Tracking)
        │                                                        │
        │                                                   F009 (Constitution + Agents)
        │                                                        │
        │                                                   F010 (Escalation)
        │                                                        │
        │                                                   F011 (Action Logging)
        │                                                        │
        │                                                   F012 (Daily Briefing)
        │                                                        │
        │                                               F013 (Google OAuth2)
        │                                                        │
        │                                               F014 (Calendar Coordination)
        │                                                        │
        │                                     ┌──────────────────┤
        │                                     │                  │
        │                              F015 (Capture)    F018 (CRM) [blocked: OD-1]
        │                                     │                  │
        │                              F016 (Weekly Infra)  F019 (Lead Capture)
        │                                     │
        │                              F017 (Weekly Review)
        │                                     │
        │                             F020 (Canva) ─→ F021 (Content Pipeline)
        │
        Phase 3 features build on Phase 2 operations and agent history
```

---

## Open Decisions Blocking Features

| Decision | Blocks | Phase | Action Needed |
|----------|--------|-------|--------------|
| OD-1: CRM platform (HubSpot?) | F018, F019 | Phase 2 | Kent confirms CRM choice |
| OD-2: Invoicing tool | F027 | Phase 3 | Kent decides invoicing tool |
| OD-3: Order management | F031 | Phase 3 | Defer — metal casework pre-revenue |
| OD-4: Social media tool | F025 | Phase 3 | Buffer or direct APIs |
| OD-5: Email marketing | F026 | Phase 3 | HubSpot Email or Mailchimp |

**Phase 1 is completely unblocked.** All F006–F014 features can proceed
without any open decision being resolved.

---

## Constraints and Assumptions

- **Single operator**: Kent is the only user. Roadmap paced for one person
  directing AI agents, not a team.
- **Privacy is absolute**: `02-Growth/_private/` — no agent access under
  any circumstance. Operational artifacts (calendar events, habits) from
  private work surface into Felix; underlying content never does.
- **office2 hardware**: Dell XPS 8700, 32GB RAM, i7-4790, 2.7TB HDD.
  Sufficient for Phase 1–2. May be a factor in Phase 3 concurrency.
- **Tailscale-only**: No public internet exposure. Webhook-dependent
  features use polling unless Kent approves Tailscale Funnel.
- **Feature cycle time**: Estimated 1–3 days per feature using spec-kitty
  + Claude Code depending on complexity.
- **Gate progression**: Agents need 30–90 days at each gate before
  advancing. Phase 3 autonomous features require substantial Gate 1/2 history.
- **Roadmap is living**: Phase 2 and 3 details will be revised based on
  what's learned operating Phase 1 features. This is expected and healthy.
