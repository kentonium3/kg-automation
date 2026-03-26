# Personal AI Command & Accountability System
## Design Specification v0.2

**Project**: kg-automation  
**Author**: Kent Gale  
**Status**: Draft — Under Review  
**Date**: 2026-03-25  
**Changelog**: v0.2 — merged Cowork inbox pipeline, Wispr Flow input model, skill analysis, Goals-MOC structure, OQ-04 resolved

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

6. **Extensible foundation**: The architecture is designed for agent autonomy expansion, not just current manual-interaction needs.

7. **Supply-chain safety**: No untrusted code executes near credentials or personal data. All integrations are pinned, audited, and scoped.

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
  ├── OpenClaw (orchestration engine)
  │     ├── Claude API (Anthropic direct — no proxy)
  │     ├── Path A: WhatsApp Command Pipeline
  │     │     ├── Whisper (local transcription of voice notes)
  │     │     ├── Intent Parser skill
  │     │     └── Task/Calendar/Dialogue routing
  │     │
  │     └── Path B: Inbox Processing Pipeline
  │           ├── inbox-processor skill (migrated from Cowork)
  │           ├── kent-voice skill (migrated from Cowork)
  │           ├── vault-writer skill (migrated from Cowork)
  │           └── Task Bridge: flags → SQLite write
  │
  ├── SQLite Task Store (source of truth)
  ├── Goal Context Loader (reads constitution docs)
  ├── Content Abstraction Layer
  ├── Google Calendar API (OAuth — personal, phase 1)
  ├── Things3 Sync Queue → Dropbox → Mac LaunchAgent
  └── Heartbeat Scheduler (escalation + inbox poll)

[MacBook Pro]  ← syncing endpoint
  ├── Obsidian (Obsidian Sync — bidirectional)
  ├── LaunchAgent: Dropbox queue → Things3
  └── Things3: read-only view of task store

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
- OpenClaw management interface **never exposed to public internet**
- WhatsApp webhook: Tailscale tunnel or Cloudflare-protected endpoint (OQ-01)
- All API keys and credentials in office2 secrets store — never in skill code
- Obsidian Sync is the transport between devices for the second brain — office2 runs Obsidian CLI with sync daemon

---

## 4. The Two Input Paths

These are distinct cognitive modes and must not be conflated in UX or implementation.

### Path A — WhatsApp Command Channel

**Intent**: action, direction, scheduling, accountability dialogue  
**Always-on**: yes — Mac-independent  
**Flow**:
```
Kent speaks/types into WhatsApp
  → OpenClaw webhook receives message
  → Voice notes: Whisper (local, office2) transcribes
  → Intent Parser skill → structured intent
  → Routes to: task creation | calendar | dialogue | escalation response
```

### Path B — Obsidian Inbox Processing Pipeline

**Intent**: thought capture, second brain enrichment, constitution building  
**Always-on**: yes (office2) — but depends on Obsidian Sync health  
**Flow**:
```
Kent speaks via Wispr Flow (Mac or iPhone) into any Obsidian note
  → Wispr Flow transcribes + AI-polishes text in-app (not a pipeline component)
  → Note lands in 00-Inbox/ with status: unprocessed
  → Obsidian Sync propagates to office2 (near real-time)
  → Hourly poll: inbox-processor skill scans for unprocessed notes
  → Routes content to vault destinations per routing table
  → Task/commitment items: write to SQLite task store (replaces log flag)
  → Marks processed, writes processing log
```

**Wispr Flow is an input device, not a pipeline component.** It operates entirely on-device and outputs polished text into whatever app has focus. The pipeline starts when the note hits `00-Inbox/`.

**On-demand trigger**: "process my inbox now" via WhatsApp triggers an immediate Path B run without waiting for the next hourly poll.

---

## 5. Component Specifications

### 5.1 OpenClaw (Orchestration Engine)

**Runs on**: office2  
**Model**: Claude Sonnet (Anthropic API direct — no LiteLLM, no third-party routing)  
**Install**: pinned version, git clone, reviewed before updates  
**Skill policy**: no ClawHub community skills without source review

### 5.2 Existing Skills (Migrate from Cowork → office2)

Three skills exist, are production-quality, and migrate with minimal modification.

#### inbox-processor
**Current**: `~/second-brain/.claude/skills/inbox-processor/SKILL.md`  
**Function**: orchestrating skill — scans `00-Inbox/`, classifies content, routes to vault destinations  
**Migration changes**:
- Task/action-item and research-request classifications now write to SQLite instead of log only
- Scheduled via OpenClaw heartbeat (hourly) instead of Cowork
- Prerequisite check: verify Obsidian Sync is healthy before processing

**Routing table** (abridged):

| Content type | Destination |
|---|---|
| Goal — new or update | `01-Constitution/Goals-MOC.md` + SQLite goal record |
| Task or action item | SQLite task store (`status: inbox`) + processing log |
| Research request | SQLite task store (`type: research-request`) + processing log |
| Values, principles | `01-Constitution/Values.md` |
| Vision, aspiration | `01-Constitution/Vision.md` |
| Growth/transformation | `02-Growth/` |
| Health/fitness | `03-Health/` |
| Business content | `04-Business/[Intentional\|Acquisition\|Metal-Casework]/` |
| Journal reflection | `06-Journal/` dated entry |
| Unclassifiable | `status: needs-review` in inbox |

#### kent-voice
**Function**: authoring style guide — all vault content sounds like Kent, not generic AI  
**Migration changes**: none

#### vault-writer
**Function**: file operations standard — frontmatter, naming, cross-linking, safety rules  
**Migration changes**: none

**Privacy absolute rule** (all three skills):  
`02-Growth/_private/` is **never** read, written, referenced, or logged by any agent under any circumstance.

### 5.3 Intent Parser (New — Path A)

**Function**: classifies WhatsApp input into structured intents

| Intent | Description |
|---|---|
| `task_create` | One or more tasks with metadata |
| `task_update` | Status change, reschedule, reprioritize |
| `task_complete` | Mark done |
| `task_abandon` | Abandon with reason |
| `negotiate_priority` | Triggers multi-turn dialogue |
| `calendar_query` | Ask about schedule |
| `inbox_process_now` | Trigger immediate Path B |
| `unknown_capability` | Graceful boundary declaration |

Ambiguity rule: ask one clarifying question before acting. Never guess silently.

### 5.4 Task Store

**Technology**: SQLite on office2 (source of truth)

```sql
Areas
  id, name, identity, description, active

Projects
  id, area_id, name, identity, status, notes,
  target_date, created_at, updated_at

Tasks
  id, project_id (nullable), title, notes,
  status,         -- inbox|someday|scheduled|today|completed|abandoned
  type,           -- task|research-request|goal
  identity,       -- personal|intentional
  source,         -- whatsapp|inbox-processor|manual
  priority,       -- 1-5
  due_date,
  scheduled_date,
  calendar_event_id (nullable),
  escalation_level,   -- 0-4
  last_followup_at,
  created_at, updated_at

FollowupLog
  id, task_id, sent_at, message_summary, escalation_level

GoalContextSnapshots
  id, loaded_at, constitution_hash
```

#### Conceptual Views

| View | Definition |
|---|---|
| **Inbox** | `status = inbox` — unprocessed, awaiting triage |
| **Today** | Due today or agent-selected from Upcoming |
| **Upcoming** | Due/scheduled within 14 days, by priority |
| **Someday** | Parked, surfaced in weekly review |
| **Projects** | Active with subtask completion progress |

### 5.5 Goal Context Loader

**Source documents** (read-only):
- `01-Constitution/Goals-MOC.md` — primary priority map
- `01-Constitution/Identity.md` — biographical context
- `01-Constitution/Values.md` — governing principles
- `01-Constitution/Vision.md` — aspirational future state
- `01-Constitution/Personal-Brand.md` — positioning

**Never reads**: `02-Growth/_private/` — absolute, no exceptions

**Constitution hash**: records hash on each load; if changed, re-evaluates pending priority conflicts.

**Write-read loop**: capture (Wispr Flow) → inbox-processor writes to Goals-MOC.md → Goal Context Loader reads it back → informs priority reasoning → drives task creation and escalation.

### 5.6 Content Abstraction Layer

Insulates skill code from hardcoded content paths.

```
ContentResolver.resolve(topic, identity)
  → searches registered sources in priority order

Phase 1: Obsidian vault only
Phase 2: + Google Docs (both identities)
Phase 3: + Intentional repo, media
```

### 5.7 Google Calendar Integration

**Phase 1**: personal Google account, OAuth2, Calendar read/write  
**Operations**: block time, read conflicts, update/remove on reschedule, never double-book  
**Phase 2**: Intentional Workspace calendar, routed by task `identity`

### 5.8 Things3 Sync (Mac View Layer)

Unidirectional push: SQLite → Dropbox JSON queue → Mac LaunchAgent → Things3  
Sync scope: Inbox, Today, Upcoming, Projects (not Someday)  
SQLite is always truth. Things3 is a view, not an editor.

### 5.9 Heartbeat & Escalation Engine

| Cadence | Trigger | Action |
|---|---|---|
| Hourly | Clock | Path B inbox scan |
| Hourly | Clock | Escalation level check on all open tasks |
| Daily 8AM | Clock | WhatsApp briefing: Today + Upcoming |
| Sunday 6PM | Clock | Weekly review: Someday surfacing, constitution freshness |
| On-demand | WhatsApp | Immediate Path B trigger |

#### Escalation Ladder

| Level | Trigger | Tone | Required response |
|---|---|---|---|
| 0 | Task created | — | Calendar event set if scheduled |
| 1 | 48h before due | Friendly reminder | None |
| 2 | Due date reached, incomplete | Firm nudge | None |
| 3 | 24h overdue | Insistent | Explicit: snooze / abandon / new date |
| 4 | 48h+ overdue with committed deadline | Critical | Priority negotiation — silence not accepted |

### 5.10 WhatsApp Integration

**Number**: dedicated  
**API**: Meta Cloud API (official) — no unofficial bridges  
**Cost**: free tier for personal use; number ~$1–2/month via Twilio  
**Dialogue modes**: Command | Dialogue | Briefing

---

## 6. Identity & Credential Model

| Identity | Google Account | Other |
|---|---|---|
| `personal` | personal Gmail + Calendar + Drive | GitHub, Calendly |
| `intentional` | Intentional Workspace | Canva, web services |

Credentials stored in scoped office2 secrets store. Named sets injected at runtime. Never in skill code.

---

## 7. Security Architecture

| Threat | Mitigation |
|---|---|
| Supply chain | OpenClaw pinned; changelog reviewed before updates |
| LLM proxy poisoning | Anthropic API direct — no LiteLLM |
| Skill injection | No ClawHub skills without source review |
| Credential exposure | Named credential store; excluded from logs |
| Prompt injection | Scoped `claude` user; sandboxed skills |
| Network | Tailscale-only management; no public exposure |
| Monitoring | Existing `audit.sh` (3AM) + C2 sinkholing |

---

## 8. Open Questions

| # | Question | Status |
|---|---|---|
| OQ-01 | WhatsApp webhook: Tailscale tunnel vs Cloudflare Worker? | Deferred to FEAT-002 |
| OQ-02 | Whisper model size for office2 hardware? | Deferred to FEAT-003 |
| OQ-03 | Things3 sync: `things-cli` vs URL scheme? | Deferred to FEAT-016 |
| OQ-04 | Does agent ever read private growth content? | **Resolved: NO. Absolute rule.** |
| OQ-05 | Tasks spanning both identities? | Deferred to Phase 3 |
| OQ-06 | Obsidian CLI sync on office2: daemon or triggered pull? | Pending diagnostic |

---

## 9. Implementation Phases

### Phase 1: Foundation (MVP)
1. OpenClaw install on office2
2. WhatsApp integration
3. Whisper transcription skill
4. Intent Parser skill
5. SQLite task store
6. Task CRUD skill
7. Migrate inbox-processor + task bridge to SQLite
8. Migrate kent-voice skill
9. Migrate vault-writer skill
10. Hourly inbox poll + on-demand trigger
11. Goal Context Loader
12. Personal Google Calendar skill
13. Task → Calendar event linking
14. Daily briefing heartbeat
15. Level 1–2 escalation heartbeat
16. Things3 sync queue + Mac LaunchAgent

### Phase 2: Accountability Engine
Full escalation ladder, priority negotiation, weekly review, Someday surfacing, capability boundary handler

### Phase 3: Dual Identity & Content Expansion
Intentional Google Workspace, calendar/task routing by identity, Google Drive content sources, Content Abstraction Layer

### Phase 4: Agent Autonomy Expansion
Second brain write-back, multi-agent delegation, iPhone Shortcuts, accountability reporting

---

## 10. Spec-Kitty Feature Sequence (Phase 1)

```
FEAT-001  OpenClaw baseline install on office2
FEAT-002  WhatsApp channel (dedicated number, Meta Cloud API)
FEAT-003  Whisper transcription skill (local)
FEAT-004  Intent Parser skill
FEAT-005  SQLite task store + schema
FEAT-006  Task CRUD skill
FEAT-007  Migrate inbox-processor + task bridge to SQLite
FEAT-008  Migrate kent-voice skill
FEAT-009  Migrate vault-writer skill
FEAT-010  Hourly inbox poll + on-demand WhatsApp trigger
FEAT-011  Goal Context Loader
FEAT-012  Personal Google Calendar skill
FEAT-013  Task → Calendar event linking
FEAT-014  Daily briefing heartbeat
FEAT-015  Level 1–2 escalation heartbeat
FEAT-016  Things3 sync queue + Mac LaunchAgent
```

**Sequencing note**: FEAT-007–009 before FEAT-011. Constitution document (`Goals-MOC.md` structure already established) should be reviewed by Kent before FEAT-011 is built — it is the foundation everything else reasons against.

---

## 11. Operating Principles

1. **Transformative action over comfortable inaction.** The agent actively resists drift.
2. **Insistence is a feature.** Explicit permission to escalate when committed deadlines are at risk.
3. **Kent has final say — always.** The agent negotiates and pushes back. It does not override.
4. **Transparency about limits.** Declare capability boundaries immediately. Never fail silently.
5. **Goal context is the compass.** Every action evaluated against the constitution docs.
6. **The second brain is the content; the system is the engine.** Acts on declared intentions. Does not define them.
7. **Security over convenience.** No new integration without reviewing credential handling.
8. **Privacy is absolute.** `02-Growth/_private/` is never accessed by any agent or skill.

---

*Living spec. Version increments on architectural change. Tactical implementation in feature specs managed by spec-kitty.*
