---
title: Personal AI Command & Accountability System — v0.3
doc_type: strategy
status: draft
---

# Personal AI Command & Accountability System
## Design Specification v0.3

**Project**: kg-automation  
**Author**: Kent Gale  
**Status**: Draft — Under Review  
**Date**: 2026-03-25  
**Changelog**:
- v0.1 — initial draft
- v0.2 — merged Cowork inbox pipeline, Wispr Flow input model, skill analysis, Goals-MOC structure, OQ-04 resolved
- v0.3 — replaced custom SQLite task store with Vikunja; removed Things3 sync entirely; added open source contribution posture

---

## 1. Purpose & Framing

This system is not a task manager. It is an accountability infrastructure designed to drive meaningful, transformative action at velocity — particularly in the presence of fear, resistance, or inertia.

The system operates on the premise that Kent has declared who he intends to become and what he intends to build. The agent's role is to hold those declarations in trust, surface them persistently, and ensure that the gap between intention and action is never comfortable to ignore.

This distinction governs every design decision in this document. Features that serve passive tracking are secondary. Features that serve active accountability are primary.

---

## 2. System Goals

1. **Frictionless capture**: Any input — voice, text, WhatsApp message, Obsidian inbox note — is captured and processed without requiring Kent to be at a computer or in a structured headspace.
2. **Goal-anchored prioritization**: Every task and project is evaluated against declared life and business priorities, not just urgency or recency.
3. **Proactive accountability**: The system follows up, escalates, and refuses to let important commitments quietly expire. It has permission to be insistent.
4. **Always-on operation**: Core functionality is available 24/7 regardless of whether the Mac is awake or accessible.
5. **Dual-identity awareness**: Tasks and calendar actions are always routed to the correct personal or business Google identity.
6. **Extensible foundation**: The architecture is designed for agent autonomy expansion, not just current assisted needs.
7. **Supply-chain safety**: No untrusted code executes near credentials or personal data. All integrations are pinned, audited, and scoped.
8. **Open source posture**: Where we build on open source (Vikunja, OpenClaw), improvements that solve common problems are contributed back upstream.

---

## 3. Architecture Overview

### 3.1 Physical Topology

```
[Kent]
  │
  ├── WhatsApp voice/text  ──────────────────────────────┐
  │                                                       │
  └── Wispr Flow (Mac/iPhone)                            │
        │ transcribes + polishes in-app                  │
        ▼                                                 │
  [Obsidian Inbox]                                        │
  00-Inbox/*.md                                           │
        │ (Obsidian Sync — real-time)                     │
        ▼                                                 ▼
[office2 — Ubuntu 24.04 LTS — always-on]◄───────[WhatsApp Webhook]
  │
  ├── OpenClaw (orchestration + intelligence layer)
  │     ├── Claude API (Anthropic direct — no proxy)
  │     ├── Path A: WhatsApp Command Pipeline
  │     │     ├── Whisper (local transcription)
  │     │     ├── Intent Parser skill
  │     │     └── Routes to: Vikunja API | Google Calendar | Dialogue
  │     │
  │     └── Path B: Obsidian Inbox Pipeline
  │           ├── inbox-processor skill (migrated from Cowork)
  │           ├── kent-voice skill (migrated from Cowork)
  │           ├── vault-writer skill (migrated from Cowork)
  │           └── Task Bridge: classified tasks → Vikunja API
  │
  ├── Vikunja (Docker — task store + web UI)
  │     ├── REST API ← OpenClaw writes tasks here
  │     ├── Web UI ← accessible from Mac/iPhone via Tailscale
  │     ├── SQLite backend (office2 local)
  │     └── Built-in views: Today, Upcoming, project lists, Kanban
  │
  ├── Goal Context Loader (reads constitution docs from Obsidian)
  ├── Content Abstraction Layer
  ├── Google Calendar API (OAuth — personal, phase 1)
  └── Heartbeat Scheduler (escalation engine + inbox poll)

[MacBook Pro]  ← authoring + interaction endpoint, no sync duties
  └── Obsidian (Obsidian Sync — bidirectional with office2)

[iPhone]
  └── Vikunja web UI via Tailscale (Today/Upcoming on the go)

[Second Brain — Content Substrate]
  ├── Obsidian vault: ~/second-brain/vault/Notes/
  │     ├── 00-Inbox/          ← capture landing zone
  │     ├── 01-Constitution/   ← agent context ceiling
  │     │     ├── Goals-MOC.md
  │     │     ├── Identity.md
  │     │     ├── Values.md
  │     │     ├── Vision.md
  │     │     └── Personal-Brand.md
  │     ├── 02-Growth/
  │     │     └── _private/    ← NEVER READ BY ANY AGENT (absolute)
  │     ├── 03-Health/
  │     ├── 04-Business/
  │     ├── 05-Finance/
  │     ├── 06-Journal/
  │     └── 07-Resources/
  ├── Google Docs (Intentional business content)
  ├── Intentional repo (website, published assets)
  └── Media / reference material
```

### 3.2 Network & Access

- office2 accessible from Mac and iPhone via **Tailscale**
- Vikunja web UI served on office2:3456, Tailscale-only — never public internet
- OpenClaw management interface Tailscale-only — never public internet
- WhatsApp webhook: Tailscale tunnel or Cloudflare-protected endpoint (OQ-01)
- All API keys and credentials in office2 secrets store — never in skill code
- Obsidian Sync daemon (`ob sync --continuous` via systemd) provides near real-time vault sync to office2

---

## 4. The Two Input Paths

These are distinct cognitive modes and must not be conflated in UX or implementation.

### Path A — WhatsApp Command Channel

**Intent**: action, direction, scheduling, accountability dialogue  
**Always-on**: yes — Mac-independent

```
Kent speaks/types into WhatsApp
  → OpenClaw webhook receives message
  → Voice notes: Whisper (local, office2) transcribes
  → Intent Parser skill → structured intent
  → Routes to: Vikunja API (task) | Google Calendar | dialogue
```

### Path B — Obsidian Inbox Processing Pipeline

**Intent**: thought capture, second brain enrichment, constitution building  
**Always-on**: yes — depends on Obsidian Sync health (systemd daemon)

```
Kent speaks via Wispr Flow (Mac or iPhone) into Obsidian note
  → Wispr Flow transcribes + polishes in-app (not a pipeline component)
  → Note lands in 00-Inbox/ with status: unprocessed
  → Obsidian Sync propagates to office2 (near real-time via systemd daemon)
  → Hourly poll: inbox-processor scans for unprocessed notes
  → Routes content to vault destinations per routing table
  → Task/commitment items → Vikunja API (replaces log flag)
  → Marks processed, writes processing log
```

**Wispr Flow is an input device, not a pipeline component.** It outputs polished text into whatever app has focus. The pipeline starts when the note hits `00-Inbox/`.

**On-demand trigger**: "process my inbox now" via WhatsApp triggers immediate Path B run.

---

## 5. Component Specifications

### 5.1 Vikunja — Task Store & UI Layer

**Runs on**: office2 (Docker container)  
**Version**: latest stable, pinned for production  
**Database**: SQLite (office2 local, backed up via existing Restic at 4AM)  
**Access**: web UI at `http://office2:3456` via Tailscale  
**API**: REST, JWT authentication, full CRUD  
**License**: AGPL-3.0 — open source, contributions welcome

#### Project Structure (Things-Inspired)

```
Everyday (parent project — the GTD layer)
  ├── Inbox          ← unprocessed captures
  ├── Someday        ← parked, not forgotten
  └── [saved filter: Today]   ← cross-project, due today
  └── [saved filter: Upcoming] ← cross-project, next 14 days

Areas (parent projects — life domains)
  ├── Personal Growth & Transformation
  │     └── [subprojects per initiative]
  ├── Health & Conditioning
  │     └── [subprojects per protocol]
  ├── Intentional LLC
  │     └── [subprojects: consulting, brand, pipeline]
  ├── Business Acquisition
  │     └── CT-90day, Deal Research, Deal Pipeline
  └── Metal Casework
        └── Market Research, Supplier Research
```

#### Key Vikunja Features Used

| Feature | Usage |
|---|---|
| Projects + subprojects | Areas → Projects hierarchy |
| Labels | `personal` / `intentional` identity routing |
| Priorities (1-5) | Agent-assigned against goal context |
| Due dates + reminders | Drive escalation engine |
| Saved filters | Cross-project Today, Upcoming, Overdue views |
| Quick Add Magic | Future: natural language task entry in UI |
| CalDAV | Future: optional iOS Reminders sync |
| REST API | OpenClaw reads/writes all tasks programmatically |
| Webhooks | Future: trigger OpenClaw on task events |

#### Saved Filters (pre-configured at setup)

```
Today:    due_date <= now/d && done = false
Upcoming: due_date > now/d && due_date <= now+14d && done = false
Overdue:  due_date < now/d && done = false
Someday:  project = Someday && done = false
```

#### Open Source Contribution Candidates

The known limitation — subproject tasks not automatically visible in parent project view — is a real workflow gap that affects any GTD-style hierarchy. Once we've built around it with saved filters and validated the workaround pattern, this is a strong upstream contribution candidate. Track in kg-automation issues.

### 5.2 OpenClaw — Orchestration & Intelligence Layer

**Runs on**: office2  
**Model**: Claude Sonnet (Anthropic API direct — no LiteLLM, no proxy)  
**Install**: pinned version, git clone, reviewed before updates  
**Skill policy**: no ClawHub community skills without source review  

OpenClaw is the intelligence. Vikunja is the store. They communicate via Vikunja's REST API.

### 5.3 Existing Skills — Migrate from Cowork → office2

Three production-quality skills migrate with minimal changes.

#### inbox-processor
**Current**: `~/second-brain/.claude/skills/inbox-processor/SKILL.md`  
**Migration changes**:
- Task/action-item classification: write to **Vikunja API** (Inbox project) instead of log flag
- Research-request classification: write to Vikunja with label `research-request`
- Scheduled via OpenClaw heartbeat (hourly) instead of Cowork
- Pre-run health check: `systemctl is-active obsidian-sync`

**Routing table** (abridged):

| Content type | Destination |
|---|---|
| Goal — new or update | `01-Constitution/Goals-MOC.md` + Vikunja (if actionable) |
| Task or action item | Vikunja Inbox project via API |
| Research request | Vikunja Inbox, label: `research-request` |
| Values, principles | `01-Constitution/Values.md` |
| Vision, aspiration | `01-Constitution/Vision.md` |
| Growth/transformation | `02-Growth/` |
| Health/fitness | `03-Health/` |
| Business content | `04-Business/[domain]/` |
| Journal reflection | `06-Journal/` dated entry |
| Unclassifiable | `status: needs-review` in Obsidian inbox |

#### kent-voice
**Migration changes**: none — migrates as-is

#### vault-writer
**Migration changes**: none — migrates as-is

**Privacy absolute rule** (all three skills, non-negotiable):  
`02-Growth/_private/` is **never** read, written, referenced, or logged by any agent under any circumstance.

### 5.4 Intent Parser — New, Path A

Classifies WhatsApp input into structured intents:

| Intent | Action |
|---|---|
| `task_create` | POST to Vikunja API → Inbox project |
| `task_update` | PATCH task in Vikunja |
| `task_complete` | PATCH task done = true |
| `task_abandon` | PATCH task with abandon label + note |
| `negotiate_priority` | Multi-turn dialogue mode |
| `calendar_query` | Read Google Calendar |
| `inbox_process_now` | Trigger immediate Path B run |
| `unknown_capability` | Declare limit, offer to learn |

Ambiguity rule: ask one clarifying question before acting. Never guess silently.

### 5.5 Goal Context Loader

**Source documents** (read-only, loaded at heartbeat start):
- `01-Constitution/Goals-MOC.md` — primary priority map
- `01-Constitution/Identity.md` — biographical context
- `01-Constitution/Values.md` — governing principles
- `01-Constitution/Vision.md` — aspirational future state
- `01-Constitution/Personal-Brand.md` — positioning

**Never reads**: `02-Growth/_private/` — absolute, no exceptions  
**Constitution hash**: records hash on each load; re-evaluates conflicts if changed

**Write-read loop**: Wispr Flow capture → inbox-processor enriches Goals-MOC.md → Goal Context Loader reads it → informs priority reasoning → drives task creation and escalation in Vikunja.

### 5.6 Content Abstraction Layer

Insulates skill code from hardcoded content paths as second brain expands.

```
ContentResolver.resolve(topic, identity)
  Phase 1: Obsidian vault only
  Phase 2: + Google Docs (both identities)
  Phase 3: + Intentional repo, media
```

### 5.7 Google Calendar Integration

**Phase 1**: personal Google account, OAuth2, Calendar read/write  
**Operations**: block time, read conflicts before scheduling, update/remove on reschedule, never double-book  
**Vikunja link**: tasks with calendar events store the Google Calendar event ID in Vikunja task description or custom field  
**Phase 2**: Intentional Workspace calendar, routed by task label (`personal` / `intentional`)

### 5.8 Heartbeat & Escalation Engine

**Runs on**: office2, OpenClaw cron system

| Cadence | Trigger | Action |
|---|---|---|
| Hourly | Clock | Path B: scan `00-Inbox/` for unprocessed notes |
| Hourly | Clock | Query Vikunja for tasks needing escalation check |
| Daily 8AM | Clock | WhatsApp briefing: Today view + Upcoming preview |
| Sunday 6PM | Clock | Weekly review: Someday surfacing, constitution freshness check |
| On-demand | WhatsApp command | Immediate Path B trigger |

#### Escalation Ladder

| Level | Trigger | Tone | Required response |
|---|---|---|---|
| 0 | Task created | — | Calendar event set if scheduled |
| 1 | 48h before due | Friendly reminder | None |
| 2 | Due date reached, incomplete | Firm nudge | None |
| 3 | 24h overdue | Insistent | Explicit: snooze / abandon / new date |
| 4 | 48h+ overdue with committed deadline | Critical | Priority negotiation — silence not accepted |

**Agent permission**: levels 3 and 4 are not polite. The agent has explicit permission to be uncomfortable to ignore. Final decisions belong to Kent; the agent's job is to make avoidance costly.

Escalation state is tracked via Vikunja labels (`escalation-1` through `escalation-4`) applied and updated by OpenClaw. This keeps escalation state visible in the UI without a separate database.

### 5.9 WhatsApp Integration

**Number**: dedicated  
**API**: Meta Cloud API (official) — no unofficial bridges  
**Cost**: free tier for personal use; dedicated number ~$1–2/month via Twilio  
**Dialogue modes**: Command | Dialogue | Briefing

---

## 6. Identity & Credential Model

| Identity | Label in Vikunja | Google Account | Other |
|---|---|---|---|
| `personal` | `personal` | personal Gmail + Calendar + Drive | GitHub, Calendly |
| `intentional` | `intentional` | Intentional Workspace | Canva, web services |

Every task in Vikunja carries an identity label. Calendar and email operations use the label to select the correct credential set.

**Credential store** (office2): named sets (`personal-google`, `intentional-google`, `whatsapp-meta`, `anthropic`, `vikunja-api`) injected at runtime. Never in skill source code.

---

## 7. Security Architecture

| Threat | Mitigation |
|---|---|
| Supply chain | OpenClaw + Vikunja pinned versions; changelogs reviewed before updates |
| LLM proxy poisoning | Anthropic API direct — no LiteLLM |
| Skill injection | No ClawHub skills without source review |
| Credential exposure | Named credential store; excluded from logs; never in skill code |
| Prompt injection via WhatsApp | Scoped `claude` system user; sandboxed skill execution |
| Network exposure | Vikunja and OpenClaw Tailscale-only; no public ports |
| Monitoring | Existing `audit.sh` (3AM daily): process diffs, ports, SSH keys, IOCs |
| C2 sinkholing | Existing `/etc/hosts` sinkhole extended to new AI service endpoints |
| Vikunja data | SQLite included in existing Restic backup (4AM daily, GFS retention) |

---

## 8. Open Questions

| # | Question | Status |
|---|---|---|
| OQ-01 | WhatsApp webhook: Tailscale tunnel vs Cloudflare Worker? | Deferred to FEAT-002 |
| OQ-02 | Whisper model size for office2 hardware? | Deferred to FEAT-003 |
| OQ-04 | Does agent ever read private growth content? | **Resolved: NO. Absolute rule.** |
| OQ-05 | Tasks spanning both identities? | Deferred to Phase 3 |
| OQ-06 | Obsidian CLI sync mode on office2? | **Resolved: continuous daemon via systemd** |

---

## 9. Implementation Phases

### Phase 1: Foundation (MVP)

1. Vikunja Docker deploy on office2 (+ project structure setup)
2. OpenClaw install and configuration on office2
3. WhatsApp integration (dedicated number, Meta Cloud API)
4. Whisper transcription skill (local, office2)
5. Intent Parser skill (WhatsApp → structured intent → Vikunja API)
6. Vikunja API skill (CRUD wrapper used by all other skills)
7. Migrate inbox-processor skill + task bridge to Vikunja API
8. Migrate kent-voice skill
9. Migrate vault-writer skill
10. Hourly inbox poll heartbeat + on-demand WhatsApp trigger
11. Goal Context Loader skill (reads constitution docs)
12. Personal Google Calendar skill (OAuth + event management)
13. Task → Calendar event linking (event ID stored in Vikunja task)
14. Daily briefing heartbeat (WhatsApp: Today + Upcoming)
15. Level 1–2 escalation heartbeat (Vikunja label-based state)

### Phase 2: Accountability Engine

1. Full escalation ladder (levels 3–4, dialogue-based resolution)
2. Priority conflict negotiation skill
3. Weekly review heartbeat (Someday surfacing, constitution freshness)
4. Upcoming view with calendar conflict awareness
5. Unknown capability handler (graceful boundary declaration)
6. Evaluate Vikunja subproject task aggregation for upstream contribution

### Phase 3: Dual Identity & Content Expansion

1. Intentional Google Workspace credentials registered
2. Calendar and Google Drive routing by task label
3. Content Abstraction Layer (Google Docs sources, both identities)
4. Intentional repo content source

### Phase 4: Agent Autonomy Expansion

1. Second brain write-back (decision logs, meeting notes, processed insights)
2. Multi-agent delegation (Claude Code for dev, Gemini for research)
3. iPhone Shortcuts for mobile capture augmentation
4. Accountability reporting (weekly/monthly dashboards)

---

## 10. Spec-Kitty Feature Sequence (Phase 1)

```
FEAT-001  Vikunja Docker deploy on office2 + initial project structure
FEAT-002  OpenClaw baseline install and configuration on office2
FEAT-003  WhatsApp channel (dedicated number, Meta Cloud API)
FEAT-004  Whisper transcription skill (local, office2)
FEAT-005  Vikunja API skill (CRUD wrapper — used by all agent skills)
FEAT-006  Intent Parser skill (WhatsApp text + transcript → Vikunja)
FEAT-007  Migrate inbox-processor skill + task bridge to Vikunja API
FEAT-008  Migrate kent-voice skill to office2
FEAT-009  Migrate vault-writer skill to office2
FEAT-010  Hourly inbox poll + on-demand WhatsApp trigger heartbeat
FEAT-011  Goal Context Loader skill (reads constitution docs)
FEAT-012  Personal Google Calendar skill (OAuth + event management)
FEAT-013  Task → Calendar event linking
FEAT-014  Daily briefing heartbeat (WhatsApp)
FEAT-015  Level 1–2 escalation heartbeat (Vikunja label state)
```

**Sequencing notes**:
- FEAT-001 (Vikunja) before FEAT-005 (API skill) — API skill needs a running instance to test against
- FEAT-005 (Vikunja API skill) before FEAT-006, 007 — all task-writing skills depend on it
- FEAT-007–009 (skill migration) before FEAT-011 (Goal Context Loader) — inbox-processor defines the canonical pattern for reading constitution docs
- Constitution document review (Goals-MOC.md structure) should happen alongside FEAT-001 — it is the foundation the intelligence layer reasons against

---

## 11. Operating Principles

These govern the agent's behavior and are included in OpenClaw system prompt configuration:

1. **Transformative action over comfortable inaction.** The agent actively resists drift. Incomplete commitments are signal, not noise.
2. **Insistence is a feature.** Explicit permission to escalate, repeat, and be uncomfortable to ignore when committed deadlines are at risk.
3. **Kent has final say — always.** The agent negotiates and pushes back. It does not override.
4. **Transparency about limits.** Capability boundaries are declared immediately. The agent never fails silently or approximates.
5. **Goal context is the compass.** Every action evaluated against the constitution docs. Tasks are not created in isolation.
6. **The second brain is the content; the system is the engine.** Acts on declared intentions. Does not define them.
7. **Security over convenience.** No new integration without reviewing credential handling. No dependency update without reviewing the diff.
8. **Privacy is absolute.** `02-Growth/_private/` is never accessed by any agent or skill under any circumstance.
9. **Open source posture.** Where we build on open source tools, improvements that solve common problems are contributed back. We benefit from the commons and we give back to it.

---

*Living spec. Version increments on architectural change. Tactical implementation in feature specs managed by spec-kitty.*
