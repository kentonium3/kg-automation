---
title: "Data, Privacy, and Identity Research: F005 System Architecture Development"
doc_type: explanation
status: approved
owners: [kgale]
divio_ambiguity: "overlap with data-architecture.md; consider consolidating"
---
# Data, Privacy, and Identity Research: F005 System Architecture Development

**Date**: 2026-03-29
**WP**: WP04 — Data, Privacy, and Identity Research
**Status**: Complete

---

## RQ-10: Data Ownership Model

### Decision

Data ownership is organized by data store with clear producer/consumer
relationships per capability area. Three primary stores (Vikunja, OpenClaw,
second brain) plus a new central action log store.

### Data Store Responsibilities

#### Vikunja — Task and Work State

| Data Type | Owner | Consumers | Access Pattern |
|-----------|-------|-----------|----------------|
| Tasks (CRUD, priorities, due dates) | SuperAdmin (B), BizOps (E) | All teams (read) | Real-time REST API |
| Projects and subprojects | Core Hub (A) manages structure | All teams | Read via API |
| Labels (personal, intentional, escalation-*) | Core Hub (A) defines | SuperAdmin, BizOps route by label | Read/write via API |
| Saved filters (Today, Upcoming, Overdue) | Core Hub (A) defines | SuperAdmin (briefings) | Read via API |
| Comments and task history | Producing team | Review/audit | Read via API |

**Retention**: SQLite database on host. Included in nightly Restic backup.
No explicit retention policy — tasks persist until completed or deleted.

#### OpenClaw — Agent State and Sessions

| Data Type | Owner | Consumers | Access Pattern |
|-----------|-------|-----------|----------------|
| Agent workspaces (AGENTS.md, SOUL.md, etc.) | Core Hub (A) manages | Each team reads its own | Filesystem |
| Session transcripts (JSONL) | Producing agent | Audit/review | File read |
| Cron run history | Core Hub (A) schedules | Monitoring | File read |
| Standing orders and tool policies | Core Hub (A) configures | Each agent reads its own | Config files |
| Channel credentials (Baileys session) | Core Hub (A) manages | OpenClaw gateway | Filesystem |
| Auth profiles (Anthropic API key, etc.) | Core Hub (A) manages | All agents | Config files |

**Retention**: Session transcripts and logs grow over time. Included in Restic
backup. Consider rotation policy for transcripts older than 90 days.

#### Second Brain — Content and Context

| Data Type | Owner | Consumers | Access Pattern |
|-----------|-------|-----------|----------------|
| 00-Inbox/ (capture landing zone) | Kent via Wispr Flow | Core Hub inbox-processor | File read/write |
| 01-Constitution/ (agent context) | Kent (curates) | Goal Context Loader, all agents (read-only) | File read |
| 02-Growth/ (personal development) | Kent | SuperAdmin (boundary TBD, see RQ-11) | File read (restricted) |
| 02-Growth/_private/ | Kent only | **NEVER AGENT-ACCESSIBLE** | **ABSOLUTE BOUNDARY** |
| 03-Health/ | Kent | SuperAdmin (reminders) | File read |
| 04-Business/ | Kent + agents | SuperAdmin, Development, BizOps | File read/write |
| 05-Finance/ | Kent | Reporting (future) | File read |
| 06-Journal/ | Kent + inbox-processor | None (personal) | File write (inbox-processor routes here) |
| 07-Resources/ | Kent | Content Creation, Development | File read |

**Retention**: Obsidian Sync manages. Included in Restic backup.

#### Central Action Log — NEW (must be created)

| Data Type | Owner | Consumers | Access Pattern |
|-----------|-------|-----------|----------------|
| Agent action records | All agents (producers) | Core Hub (audit), Kent (review) | Structured write, query read |
| Gate transition records | Core Hub (A) | Audit | Structured write |
| Cross-agent correlation | Core Hub (A) enriches | Audit | Derived data |

**Proposed implementation** (from WP02 research): OpenTelemetry collector on
office2 receiving OTLP exports from OpenClaw, enriched with Felix-specific
metadata (team, action type, autonomy gate level).

**Proposed location**: `/data/services/felix-audit/` on office2. Included in
Restic backup.

**Retention**: 90 days hot (queryable), 1 year cold (compressed JSONL archives).
Configurable per data sensitivity.

### Data Ownership Per Capability Area

| Area | Primary Store | What They Own | What They Consume |
|------|--------------|---------------|-------------------|
| Core Hub (A) | OpenClaw (config, agents), Action Log | System config, agent definitions, audit log | Everything (monitoring) |
| SuperAdmin (B) | Vikunja (tasks), Second Brain (constitution) | Tasks, priorities, briefing state | Calendar events, email summaries, vault content |
| Development (C) | Git repos (external to Felix) | Code, specs, docs | Vikunja tasks (project tracking) |
| Content Creation (D) | Canva (assets), Second Brain (04-Business/) | Generated content, brand assets | Requests from other teams |
| BizOps (E) | CRM (external), Vikunja (tasks) | Leads, deals, campaigns | Content from Area D, reports from Vikunja |

---

## RQ-11: SuperAdmin Privacy Boundary

### Decision

SuperAdmin has **tiered read access** to the second brain with the absolute
`02-Growth/_private/` boundary preserved. Write access is limited to
inbox-processor routing.

### Access Tiers

| Zone | SuperAdmin Access | Rationale |
|------|------------------|-----------|
| 00-Inbox/ | Read + Write (inbox-processor) | Landing zone for captures — must process |
| 01-Constitution/ | Read-only | Agent context ceiling — informs priority reasoning |
| 02-Growth/ (excluding _private/) | **Read-only, with Kent's explicit opt-in** | Personal growth content may inform reminders and task context, but agent should not assume access. Kent must explicitly grant per-folder or per-file. |
| 02-Growth/_private/ | **NEVER ACCESSIBLE** | Absolute, non-negotiable. No exceptions. No opt-in possible. |
| 03-Health/ | Read-only | Informs health-related reminders (exercise, PT, meditation) |
| 04-Business/ | Read + Write (agent-generated content) | Business content is agent-accessible |
| 05-Finance/ | No access (future) | Financial data is sensitive — defer access decision |
| 06-Journal/ | Write-only (inbox-processor routes here) | Agent writes journal entries but does not read existing ones |
| 07-Resources/ | Read-only | Reference material for research and content |

### Boundary Enforcement

1. **Configuration-level**: Agent standing orders explicitly list accessible
   paths. Paths not listed are denied by default (allowlist, not denylist).
2. **File-level**: The `02-Growth/_private/` absolute boundary is enforced at
   the skill level (every skill that touches the vault must check paths) AND
   at the constitution level (global agent instruction).
3. **Audit-level**: Central action log records all vault access. Any access
   to `02-Growth/` triggers an audit event. Any attempted access to
   `02-Growth/_private/` triggers an alert.
4. **Review-level**: Quarterly review of vault access patterns by Kent.

### Open Items for Kent

- **02-Growth/ opt-in**: Kent must decide which non-private folders under
  02-Growth/ (if any) SuperAdmin may read. Default is no access until
  explicitly granted.
- **06-Journal/ read access**: Should SuperAdmin be able to read journal entries
  for context? Current recommendation is no (write-only for inbox-processor).
- **05-Finance/ future access**: If financial reporting becomes a SuperAdmin
  capability, access must be explicitly granted with clear scope.

---

## RQ-12: Personal Brand Content Domain

### Decision

Personal brand content is a **cross-cutting concern** that spans multiple
stores and capability areas. It does not have a single canonical location —
instead, the brand is expressed through content created by Area D, managed
by Area B, and distributed by Area E.

### Brand Content Map

| Content Type | Where It Lives | Who Creates | Who Distributes |
|-------------|---------------|-------------|-----------------|
| Brand strategy and positioning | 01-Constitution/Personal-Brand.md | Kent (curates) | SuperAdmin reads for context |
| Blog posts (source) | Git repo (intentional) or 04-Business/ | Content Creation (D) | BizOps (E) publishes |
| LinkedIn posts | Generated on demand | Content Creation (D) | BizOps (E) schedules |
| White papers / PDFs | `/data/content/` on office2 or 04-Business/ | Content Creation (D) | BizOps (E) distributes |
| Graphics and visuals | Canva (cloud) | Content Creation (D) | BizOps (E) uses in campaigns |
| Presentations | Canva (cloud) | Content Creation (D) | Kent delivers, BizOps shares |
| Email marketing content | CRM/email platform | Content Creation (D) drafts | BizOps (E) sends |

### Brand Content Storage Recommendation

- **Strategy and guidelines**: `01-Constitution/Personal-Brand.md` (already
  exists in v0.3 design) — read by all content-producing agents
- **Source content (text)**: `04-Business/content/` in second brain — markdown
  source for blog posts, articles, white papers
- **Generated assets**: `/data/content/` on office2 — PDFs, exported graphics,
  video content
- **Design assets**: Canva cloud — managed through Canva API
- **Published content**: Lives in destination platforms (website repo, LinkedIn,
  etc.) — not stored centrally after publication

### Open Items for Kent

- **Does Kent want a centralized content calendar?** This could live in Vikunja
  (as a project with tasks per content piece) or in the CRM (if HubSpot's
  marketing hub is adopted). Recommendation: Vikunja for now.
- **Brand guidelines document**: Does `01-Constitution/Personal-Brand.md`
  currently exist and is it sufficient? Or does Kent need to create/expand it?

---

## RQ-13: Identity Model Extension

### Decision

Extend the current two-identity model (personal, intentional) to three by
adding metal casework. Each identity is a **business context** with its own
branding, credentials, CRM pipeline, and content — all managed by the same
Felix system and the same Kent operator.

### Extended Identity Model

| Identity | Scope | Vikunja Label | OpenClaw Persona | Google Account | CRM | Status |
|----------|-------|---------------|-----------------|----------------|-----|--------|
| Personal | Kent's personal life, health, growth, personal brand | `personal` (blue) | Default — "Felix" responds as Kent's personal assistant | Personal Gmail + Calendar | N/A | Active (F001) |
| Intentional LLC | Consulting business, professional services | `intentional` (green) | "Felix" with Intentional branding in SOUL.md | Intentional Workspace (future) | HubSpot (planned) | Labels active, routing deferred |
| Metal Casework | Product business, manufacturing, ecommerce | `metalcasework` (new color TBD) | "Felix" with metal casework branding in SOUL.md | TBD (new Google account or shared) | TBD (may share HubSpot with separate pipeline) | Not yet created |

### How Identity Routing Works

1. **Task creation**: Every task in Vikunja gets an identity label
   (personal/intentional/metalcasework). The producing agent or Kent applies it.
2. **Calendar routing**: Calendar operations use the label to select the
   correct Google credential set. Personal → personal-google. Intentional →
   intentional-google. Metal casework → TBD.
3. **Email routing**: Email operations use the label to select the correct
   Gmail account.
4. **Content branding**: Content Creation agents read the identity label and
   apply the correct brand guidelines (tone, visual identity, templates).
5. **CRM routing**: BizOps routes leads and deals to the correct CRM pipeline
   based on identity label.

### OpenClaw Implementation

Based on WP02 findings:
- Each team agent has its own `SOUL.md` with identity-aware instructions
- Standing orders include identity-based routing rules
- WhatsApp channel is shared (single Felix identity) — internal routing by
  agent handles the rest
- For outbound email, identity determines which Gmail account sends

### What Must Be Configured for Metal Casework

1. Create `metalcasework` label in Vikunja (color TBD)
2. Add metal casework projects under the existing "Metal Casework" area project
3. Decide: new Google account or shared with personal/Intentional?
4. Decide: separate HubSpot pipeline or separate CRM instance?
5. Create brand guidelines in 01-Constitution/ or 04-Business/

### Cross-Identity Interactions

- **Kent is the operator across all identities** — single person, unified
  briefings and priority management
- **Tools may be shared**: Same CRM (different pipelines), same Canva account
  (different brand kits), same Felix instance
- **Content may span identities**: Kent's personal brand may reference
  Intentional work. Blog posts may serve both personal brand and Intentional
  marketing.
- **Financial separation**: Invoicing and accounting must be strictly
  separated per business entity (legal requirement)

### Open Items for Kent

- **Metal casework Google account**: New Workspace, shared personal, or other?
- **Metal casework CRM**: Share HubSpot with Intentional (separate pipelines)
  or separate system?
- **Metal casework label color**: Assign when creating in Vikunja
- **Brand guidelines scope**: How detailed do metal casework brand guidelines
  need to be at this stage? (Business is in research/feasibility phase)

---

## Summary

### Key Decisions

1. **Data ownership is store-based**: Vikunja (tasks), OpenClaw (agent state),
   second brain (content/context), central action log (audit)
2. **Central action log**: New store at `/data/services/felix-audit/` using
   OpenTelemetry collector
3. **Privacy boundary**: Tiered access with 02-Growth/_private/ absolute. Other
   zones have explicit rules. Allowlist approach (deny by default).
4. **Personal brand**: Cross-cutting — no single store. Strategy in
   constitution, source in second brain, assets in Canva/office2, published
   to destination platforms.
5. **Identity model**: Three identities via Vikunja labels + OpenClaw persona
   config. Routing by label at every integration point.

### Open Items for Kent

| # | Question | Impact |
|---|----------|--------|
| 1 | Which 02-Growth/ folders (non-private) should SuperAdmin access? | Privacy boundary scope |
| 2 | Should SuperAdmin read journal entries? | 06-Journal/ access |
| 3 | Content calendar: Vikunja or CRM? | Content workflow |
| 4 | Does Personal-Brand.md exist and is it sufficient? | Brand content baseline |
| 5 | Metal casework Google account approach? | Identity infrastructure |
| 6 | Metal casework CRM approach? | BizOps routing |
| 7 | Metal casework label color? | Vikunja config |
| 8 | Metal casework brand guidelines scope at this stage? | Content Creation readiness |
