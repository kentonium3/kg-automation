# Data Architecture: Felix System Architecture

**Date**: 2026-03-29
**WP**: WP07 — Data Architecture (Deliverable 4)
**Status**: Complete

---

## Data Stores

### 1. Vikunja — Task and Work State

**Role**: Canonical store for all tasks, priorities, projects, and work state.

| Data Category | Examples | Access Pattern | Retention |
|---------------|---------|----------------|-----------|
| Tasks | Title, description, due date, priority, done status | REST API (real-time CRUD) | Persist until deleted |
| Projects & Subprojects | Area hierarchy (Everyday, Growth, Health, Intentional, Metal Casework) | REST API | Persist |
| Labels | Identity (personal, intentional, metalcasework), escalation state (escalation-1..4) | REST API | Persist |
| Saved Filters | Today, Upcoming, Overdue, Someday | REST API | Persist |
| Comments | Task notes, agent annotations | REST API | Persist with task |
| Task History | Completion dates, status transitions | REST API (query) | Persist |

**Producers**: SuperAdmin (B), BizOps (E), Core Hub (A) for structure
**Consumers**: All teams (read for briefings, reports, coordination)
**Backup**: SQLite at `/data/services/vikunja/data/vikunja.db`, included in nightly Restic

### 2. OpenClaw — Agent State and Configuration

**Role**: Agent runtime state, session history, credentials, and configuration.

| Data Category | Examples | Access Pattern | Retention |
|---------------|---------|----------------|-----------|
| Agent workspaces | IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md per agent | Filesystem | Persist (config) |
| Session transcripts | Full conversation history per session (JSONL) | Filesystem (read) | 90 days hot, then archive |
| Gateway logs | All gateway events (JSONL) | Filesystem | 30 days, then rotate |
| Command logs | All executed commands (JSONL) | Filesystem | 90 days |
| Cron run history | Scheduled job results (JSONL) | Filesystem | 30 days |
| Standing orders | Scope, triggers, approval gates per agent | Config files | Persist (config) |
| Channel credentials | Baileys session, API tokens | Filesystem (mode 600) | Persist (secrets) |
| Auth profiles | Anthropic key, Vikunja token, Google OAuth tokens | Config/secrets | Persist (secrets) |

**Producers**: All agents (session transcripts), Core Hub (config)
**Consumers**: Core Hub (monitoring), audit (log review)
**Backup**: `/home/claude/.openclaw/` and `/data/services/openclaw/` in Restic

### 3. Second Brain — Content and Context

**Role**: Knowledge store, constitution, content substrate. Synced via Obsidian.

| Zone | Content | Agent Access | Access Mode |
|------|---------|-------------|-------------|
| 00-Inbox/ | Capture landing zone | Core Hub inbox-processor | Read + Write |
| 01-Constitution/ | Goals-MOC, Identity, Values, Vision, Personal-Brand | All agents (Goal Context Loader) | Read-only |
| 02-Growth/ (non-private) | Personal development content | SuperAdmin (opt-in only) | Read-only (restricted) |
| 02-Growth/_private/ | Private content | **NEVER ACCESSIBLE** | **ABSOLUTE BOUNDARY** |
| 03-Health/ | Health protocols, fitness notes | SuperAdmin (reminders) | Read-only |
| 04-Business/ | Business content, brand assets, client notes | SuperAdmin, Content Creation, BizOps | Read + Write |
| 05-Finance/ | Financial records | No agent access (future) | None |
| 06-Journal/ | Personal journal entries | Core Hub inbox-processor | Write-only |
| 07-Resources/ | Reference material | Content Creation, Development | Read-only |

**Producers**: Kent (primary), Core Hub inbox-processor (routes to zones)
**Consumers**: Per access rules above
**Backup**: Obsidian Sync + Restic backup of office2 copy

### 4. Central Action Log — NEW

**Role**: Unified audit trail for all agent actions across all teams.

**Implementation**: OpenTelemetry collector on office2 receiving OTLP exports
from OpenClaw, enriched with Felix-specific metadata.

| Data Category | Source | Format | Retention |
|---------------|--------|--------|-----------|
| Agent actions | All agents via OpenTelemetry | Structured JSONL | 90 days hot, 1 year cold |
| Gate transitions | Core Hub | Structured events | 1 year (governance audit) |
| Cross-agent correlation | Enrichment layer | Derived linkage | 90 days |
| Performance metrics | OpenClaw diagnostics | OTLP metrics | 30 days |

**Location**: `/data/services/felix-audit/` on office2
**Backup**: Included in nightly Restic

---

## Identity Model

### Three-Identity Model

| Identity | Vikunja Label | Google Account | CRM Pipeline | Content Brand |
|----------|---------------|----------------|-------------|---------------|
| Personal | `personal` (blue, #2196f3) | Personal Gmail + Calendar | N/A | Kent Gale personal brand |
| Intentional LLC | `intentional` (green, #4caf50) | Intentional Workspace (future) | HubSpot (planned) | Intentional consulting brand |
| Metal Casework | `metalcasework` (TBD) | TBD | TBD (separate pipeline or CRM) | Metal casework brand |

### Identity Routing

1. **Task creation** → Identity label applied by producing agent or Kent
2. **Calendar operations** → Label selects Google credential set
3. **Email operations** → Label selects Gmail account
4. **Content generation** → Label selects brand guidelines from constitution
5. **CRM operations** → Label routes to correct pipeline/instance
6. **Financial operations** → Strictly separated per business entity

---

## Data Flow Diagram

```
Kent (voice/text/WhatsApp)
  │
  ├── WhatsApp → OpenClaw Gateway → felix-core-router
  │                                    ├── felix-admin-* (tasks, calendar, email)
  │                                    ├── felix-bizops-* (leads, campaigns)
  │                                    ├── felix-dev-* (development requests)
  │                                    └── felix-content-* (content requests)
  │
  ├── Wispr Flow → Obsidian 00-Inbox → Obsidian Sync → office2
  │                                      → felix-core-heartbeat (hourly poll)
  │                                        → Routes to vault destinations + Vikunja
  │
  └── Direct (Vikunja UI, browser) → Vikunja REST API
                                       → Agents read via API

All agents ──→ OpenTelemetry ──→ Central Action Log
                                   → felix-core-audit monitors
```

---

## Privacy Boundary Model

```
Second Brain Access Zones:

  ┌──────────────────────────────┐
  │ 00-Inbox/ [R+W: Core Hub]   │  ← Capture landing zone
  ├──────────────────────────────┤
  │ 01-Constitution/ [R: All]   │  ← Agent context ceiling
  ├──────────────────────────────┤
  │ 02-Growth/ [R: opt-in only] │  ← Kent must explicitly grant
  │  ┌──────────────────────┐   │
  │  │ _private/ [BLOCKED]  │   │  ← ABSOLUTE — no exceptions, no opt-in
  │  └──────────────────────┘   │
  ├──────────────────────────────┤
  │ 03-Health/ [R: SuperAdmin]  │  ← Reminders, protocols
  ├──────────────────────────────┤
  │ 04-Business/ [R+W: agents]  │  ← Business content, fully accessible
  ├──────────────────────────────┤
  │ 05-Finance/ [NONE]          │  ← No agent access (future decision)
  ├──────────────────────────────┤
  │ 06-Journal/ [W: inbox-proc] │  ← Write-only (agents don't read)
  ├──────────────────────────────┤
  │ 07-Resources/ [R: agents]   │  ← Reference material
  └──────────────────────────────┘

Enforcement: Allowlist (deny by default), skill-level path checks,
             constitution directive, audit log alerts
```
