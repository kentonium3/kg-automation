---
id: vision-framework
title: KG-Automation — Vision & Architecture
doc_type: reference
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2026-03-23'
revision: v2.0
audience: agents_and_humans
---

# KG-Automation — Vision & Architecture (v2.0)

> This document supersedes v0.1 entirely. See Section 8 for
> deprecation log.

---

## 1. Mission

KG-Automation is Kent Gale's personal AI operating system — a
composable, agent-ready infrastructure that functions as an
executive assistant and business operations platform.

The system eliminates manual administrative overhead and enables
agent-executed tasks within defined boundaries. It is designed
for progressive autonomy: starting with AI-assisted tasks
requiring human approval, evolving toward fully autonomous
execution as trust and capability mature.

---

## 2. Async Task Request Model

A core architectural principle: Kent submits task requests and
the system executes them asynchronously, returning results for
review — similar to delegating to a capable human assistant.

### How It Works

```
Kent submits request
  (voice via WisprFlow → Obsidian inbox,
   typed in chat, or WhatsApp via OpenClaw)
        ↓
Agent picks up task
  (from inbox, queue, or direct instruction)
        ↓
Agent executes autonomously
  (research, drafting, organizing, outreach,
   data gathering, scheduling)
        ↓
Result queued for Kent's review
  (document in vault, draft in Gmail,
   summary in WhatsApp, PR on GitHub)
        ↓
Kent approves, edits, or rejects
```

### Task Types

| Type | Example | Primary Agent |
|------|---------|---------------|
| Research | Market report on a target industry | Claude + Gemini CLI |
| Document drafting | Memo, email, thought leadership post | Claude |
| Inbox capture | Process voice note → vault entry | Cowork / office2 |
| Email management | Organize, summarize, draft replies | Jace.ai |
| Task management | Add/update Things 3, block calendar | office2 scripts |
| Deal work | CT worksheet completion, deal research | Claude Projects |
| Content pipeline | LinkedIn post, blog draft | Claude + Canva |
| Proactive check-in | WhatsApp priority reminder | OpenClaw |

Kent does not need to be present while tasks execute. Results
accumulate for batch review. This is the design intent.

---

## 3. Current Architecture

### 3.1 Platform

| Component | Role |
|-----------|------|
| MacBook Pro | Primary authoring and interaction |
| office2 (Linux, Tailscale) | Always-on automation hub |
| iPhone / iPad | Mobile capture and monitoring |
| GitHub | Version control, agent coordination |
| Obsidian Sync | Vault sync across all devices |

Windows is not a supported platform.

### 3.2 AI Tool Stack

| Tool | Role |
|------|------|
| Claude (Projects) | Strategic partner, document work, research |
| Claude Code | Repo management, scripting, agent tasks |
| Gemini CLI | Secondary research, cross-validation |
| WisprFlow | Voice → Obsidian 00-Inbox (Mac + iPhone) |
| Jace.ai | Email — drafting, labeling, newsletters |
| OpenClaw | Always-on agent runtime on office2 |
| Things 3 | Task management (Mac + iPhone) |
| Google Calendar | Scheduling |

### 3.3 Second Brain Structure

```
~/second-brain/           (Mac and office2 mirrored)
├── vault/                ← Obsidian notes (Obsidian Sync)
│   ├── 00-Inbox/         ← WisprFlow captures, raw input
│   ├── 01-Constitution/  ← Identity, Values, Vision, Goals
│   ├── 02-Growth/        ← Transformation work
│   │   └── _private/     ← Gitignored, never shared
│   ├── 03-Health/
│   ├── 04-Business/      ← Intentional, Acquisition, Metal Casework
│   ├── 05-Finance/
│   ├── 06-Journal/
│   └── 07-Resources/
├── intelligence/         ← Future: vector DB, embeddings
├── agents/               ← Agent logs and outputs
└── scripts/              ← Automation scripts
```

### 3.4 Repositories

| Repo | Purpose |
|------|---------|
| kentonium3/kg-automation | Automation system — architecture, scripts, AI instructions |
| kentonium3/second-brain | Personal knowledge infrastructure |
| kentonium3/intentional | Intentional LLC business operations |
| kentonium3/bake-tracker | Recipe tracking (active) |

All repos: protected main branch, agent changes via PR only.

### 3.5 Agent Access Model

| Actor | Access | Method |
|-------|--------|--------|
| Kent (kgale) | Full sudo on office2 | SSH key |
| Claude agent (claude user) | second-brain r/w, no sudo | SSH key, PR only |
| OpenClaw | office2 execution environment | WhatsApp interface |

---

## 4. Capability Scope

### Phase 1 — Executive Assistant (Current Priority)

All current build effort is here. Phase 2 does not start until
Phase 1 capabilities are stable and habitual.

#### 4.1 Voice Capture and Document Drafting
- WisprFlow dictation → Obsidian 00-Inbox
- Agent processes inbox → draft documents queued for review
- Output: memos, correspondence, thought leadership, project notes

#### 4.2 Task Management Integration
- Dictated or typed requests → Things 3 task creation
- Task updates, reschedules, and completions via agent
- Calendar blocking for priority tasks
- Integration: Things 3 + Google Calendar

#### 4.3 Email Management (Jace.ai)
- Promotional email → vendor folders, 30-day auto-purge
- Newsletter summarization with links for review
- Draft replies in Kent's voice
- Calendar scheduling from email context
- Scope: Gmail accounts only (Jace limitation — Outlook beta)
- Status: Trial recommended before full commitment

#### 4.4 Proactive Accountability (OpenClaw)
- WhatsApp interface for proactive priority check-ins
- Time management suggestions based on open commitments
- Requires: OpenClaw on office2 with WhatsApp integration

#### 4.5 Research Pipeline
- Typed or dictated research request → async agent execution
- Report generated and queued in vault for review
- Tools: Claude, Gemini CLI, web search

#### 4.6 Obsidian Inbox Processing ⭐ FOUNDATIONAL DEPENDENCY
- office2 agent reviews 00-Inbox three times daily
- Parses raw voice dumps and typed notes
- Routes content to appropriate domain folders
- Updates canonical documents (Values, Goals, Vision, project files)
- Creates new files where content warrants it
- Updates frontmatter status on processed items
- Implementation: office2 cron + Claude Code (via claude user)

> This capability is a foundational dependency for the entire
> system. All other capabilities operate against second brain
> content. Until the corpus is rich and current, everything
> else is limited. This ships before Phase 1 is considered
> operational.

#### 4.7 Thought Leadership Pipeline
- Dictated inputs → organized topic collections
- Output destinations:
  - Intentional website blog posts
  - LinkedIn articles and teasers
  - Prospect and client email sequences

#### 4.8 CT Acquisition Support (Immediate Focus)

The Contrarian Thinking 90-day intensive is the current primary
use case driving Phase 1 build priority. The system must support:

- **Course consumption** — watching videos, working through
  units, capturing key frameworks to vault (CT-Learning/)
- **Worksheet and materials completion** — uploading PDFs and
  spreadsheet templates, providing inputs by voice or typing,
  agent generates completed materials
- **Deal research** — async research requests on target
  industries, markets, and specific businesses
- **Deal sourcing** — outreach to sellers and brokers,
  tracking pipeline
- **Communication management** — tracking responses,
  managing deal-related email threads
- **Weekly meeting preparation** — agenda, open questions,
  progress summary

All CT outputs are organized in:
`vault/04-Business/Acquisition/CT-Learning/`

### Phase 2 — Business Operations (Future)

*Specified after Phase 1 is stable.*

- HubSpot or lightweight CRM integration
- Instagram content generation
- Personal website / personal brand build
- Metal casework market research automation
- Deal tracking dashboard

### Phase 3 — Extended Automation (Future)

*Specified after Phase 2 is stable.*

- RAG / vector DB layer on office2 (Chroma or Qdrant)
- Google Sheets dynamic memory for agent workflows
- Broader multi-agent orchestration

---

## 5. Planned Integrations

These integrations are on the roadmap. Not all are implemented.

| Integration | Phase | Purpose |
|-------------|-------|---------|
| Things 3 | 1 | Task creation and management |
| Google Calendar | 1 | Scheduling and time blocking |
| Gmail (via Jace.ai) | 1 | Email management |
| WhatsApp (via OpenClaw) | 1 | Proactive agent interface |
| GitHub | 1 | Agent coordination, PR workflow |
| LinkedIn | 2 | Thought leadership publishing |
| Canva | 2 | Content design and generation |
| GSuite (Docs, Sheets) | 2 | Document and memory layer |
| Web properties (Intentional) | 2 | Blog publishing pipeline |
| HubSpot | 2 | CRM and deal tracking |

---

## 6. Design Principles

1. **Async by default** — Kent submits, agent executes, Kent
   reviews. Presence not required during execution.
2. **Automation-first** — anything done more than once manually
   should be automated.
3. **Zero manual maintenance** — no procedure requiring regular
   human intervention to keep the system running.
4. **Agent-ready architecture** — design for eventual autonomous
   execution, not just current assisted use.
5. **Privacy by design** — sensitive content never leaves
   controlled infrastructure; _private/ is local-only.
6. **GitOps** — all agent changes via PR, main always clean.
7. **Progressive autonomy** — Level 1 (AI drafts, human
   approves) before Level 2 (AI executes, human monitors)
   before Level 3 (AI autonomous within boundaries).
8. **Phase discipline** — Phase 2 does not start until Phase 1
   is working reliably.

---

## 7. Roadmap

Managed via GitHub Issues: kentonium3/kg-automation

Priority labels: P0 Critical → P4 Wishlist
Type labels: feature, enhancement, infrastructure, bug,
             documentation, security
Status labels: ready, in-progress, blocked, in-review,
               parked, wont-fix

See Issues tab for current open items.

---

## 8. Deprecation Log (v0.1 → v2.0)

| Deprecated | Reason |
|-----------|--------|
| Windows platform | Abandoned — Mac/Linux only |
| ECI workers | Replaced by office2 + claude user |
| Handoff Runner (JSON protocol) | Replaced by GitHub PR workflow |
| Windows Task Scheduler | Replaced by office2 systemd |
| Dropbox coordination layer | Replaced by Git/GitHub |
| "Generate business infrastructure packages" mission | Scope revised — personal OS, not product factory |
| Multi-AI JSON handoff files | Replaced by GitHub Issues + PRs |
| Machine inspectability mandate (JSON schemas) | Over-engineered for current scope |

---

> Agent note: This file is canonical for kg-automation v2.0.
> All agent instructions, scripts, and documentation must
> align with this architecture. Do not reference v0.1 concepts.
