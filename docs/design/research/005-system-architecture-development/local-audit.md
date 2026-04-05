---
title: "Local Architecture Audit: F005 System Architecture Development"
doc_type: reference
status: approved
owners: [kgale]
---
# Local Architecture Audit: F005 System Architecture Development

**Date**: 2026-03-29
**WP**: WP01 — Local Architecture Audit
**Status**: Complete

---

## Section 1: Deployed State (Actual — from JSON data + handbooks)

### Services

| Service | Type | Version | Port | Bind IP | systemd Unit | Status |
|---------|------|---------|------|---------|-------------|--------|
| Vikunja | Docker | 0.24.6 | 3456 | 100.92.197.90 | vikunja.service | Running |
| OpenClaw Gateway | npm-global | v2026.3.24 | 18789 | 127.0.0.1 | openclaw-gateway.service | Running |
| transcribe-api | Docker | transcribe_transcribe | 8787 | 100.92.197.90 | transcribe.service | Running |
| Obsidian Sync | Native binary | ob sync --continuous | — | — | obsidian-sync.service | Running |
| WhatsApp Channel | Baileys (via OpenClaw) | — | — | — | (part of openclaw-gateway) | Linked |

### Scheduled Jobs

| Job | Schedule | User | Purpose |
|-----|----------|------|---------|
| Restic Backup | 4 AM daily | claude (sudo) | GFS backup of /data/services, /data/transcripts, /home/* |
| Security Audit | 3 AM daily | claude | Baseline drift detection (ports, Docker, SSH keys, IOCs) |
| Timeshift | Auto (root) | root | OS snapshots (daily/7, weekly/4, monthly/3) |

### Credentials (Active)

| Name | Type | Storage Location | Used By |
|------|------|-----------------|---------|
| vikunja-admin | Username/password | Set interactively | Web UI, setup_vikunja.py |
| anthropic | API key | OpenClaw auth + /data/services/openclaw/secrets/anthropic | openclaw-gateway |
| vikunja-api | API token | /data/services/openclaw/secrets/vikunja-api | openclaw-gateway |
| restic-password | Password file | /home/claude/.config/restic/password | backup.sh |
| tailscale-auth | System-managed | Managed by tailscaled | Tailscale daemon |
| whatsapp-session | Session-managed | ~/.openclaw/credentials/whatsapp/ | openclaw-gateway |

### Hardware

| Host | Hardware | CPU | RAM | OS | Key Storage |
|------|----------|-----|-----|----|----|
| office2 | Dell XPS 8700 | Intel i7-4790 @ 3.60GHz (4c/8t) | 32 GB | Ubuntu 24.04 LTS | Root: 98 GB SSD, Data: 2.7 TB HDD, Backups: 1 TB USB |
| MacBook Pro | — | — | — | macOS | Authoring endpoint |
| iPhone 14 Pro Max | — | — | — | iOS | Mobile capture + monitoring |

### Network

- Tailnet: kentgale@ (3 devices)
- office2: Local 192.168.1.158 / Tailscale 100.92.197.90
- MacBook Pro: Tailscale 100.71.19.66
- iPhone: Tailscale 100.109.208.6
- Zero 0.0.0.0 bindings for managed services (verified post-F003)
- No public internet exposure

---

## Section 2: Designed State (from v0.3 Spec)

### Services Designed in v0.3

| Component | Designed Config | Designed Status |
|-----------|----------------|-----------------|
| Vikunja | Docker, port 3456, Tailscale-only, SQLite | Phase 1 item 1 |
| OpenClaw | office2, Claude Sonnet, Anthropic direct | Phase 1 item 2 |
| WhatsApp Integration | Dedicated number, Meta Cloud API | Phase 1 item 3 |
| Whisper Transcription | Local on office2 | Phase 1 item 4 |
| Intent Parser | WhatsApp → structured intent → Vikunja | Phase 1 item 5 |
| Vikunja API Skill | CRUD wrapper for all skills | Phase 1 item 6 |
| inbox-processor | Migrate from Cowork | Phase 1 item 7 |
| kent-voice | Migrate from Cowork | Phase 1 item 8 |
| vault-writer | Migrate from Cowork | Phase 1 item 9 |
| Hourly Inbox Poll | Heartbeat cron | Phase 1 item 10 |
| Goal Context Loader | Reads constitution docs | Phase 1 item 11 |
| Google Calendar | OAuth, personal account | Phase 1 item 12 |
| Task-Calendar Linking | Event ID in Vikunja | Phase 1 item 13 |
| Daily Briefing | WhatsApp message | Phase 1 item 14 |
| Escalation Engine | Levels 1-2 | Phase 1 item 15 |
| Content Abstraction Layer | Insulates skill code from paths | Phase 2-3 |
| Heartbeat Scheduler | Hourly, daily 8AM, Sunday 6PM | Phase 1-2 |

### v0.3 Phase Summary

| Phase | Scope | Items |
|-------|-------|-------|
| Phase 1 | Foundation MVP | 15 features (F001-F015) |
| Phase 2 | Accountability Engine | 6 items (escalation 3-4, priority negotiation, weekly review, etc.) |
| Phase 3 | Dual Identity & Content | 4 items (Intentional workspace, content layer) |
| Phase 4 | Agent Autonomy Expansion | 4 items (write-back, multi-agent, dashboards) |

### v0.3 Identity Model

| Identity | Vikunja Label | Google Account | Status |
|----------|---------------|----------------|--------|
| personal | personal | Personal Gmail | Labels exist (F001) |
| intentional | intentional | Intentional Workspace | Labels exist (F001) |

### v0.3 Architectural Decisions (Locked)

- OpenClaw is the orchestration engine
- Vikunja is the task store (replaced custom SQLite in v0.3)
- Anthropic API direct — no LiteLLM, no proxy
- Tailscale-only for all services
- office2 is the always-on hub
- 02-Growth/_private/ never agent-accessible

---

## Section 3: Specification State (from F001-F004 Func-Specs)

### F001: Vikunja Docker Deploy — COMPLETE

- Vikunja 0.24.6 running on office2:3456 (Tailscale-bound)
- SQLite on host filesystem, included in Restic backup
- Project structure: Everyday (Inbox/Someday) + 5 Area projects
- Identity labels created: personal (blue), intentional (green)
- Three saved filters: Today, Upcoming, Overdue
- systemd service with boot startup
- Ops runbook at docs/runbooks/vikunja-ops.md

### F002: OpenClaw Install — COMPLETE

- OpenClaw v2026.3.24 installed (npm-global)
- Bound to 127.0.0.1:18789 (localhost only)
- Direct Anthropic API connection verified (no proxy)
- Credential store pattern established at /data/services/openclaw/secrets/
- User-level systemd service (openclaw-gateway) for claude user
- Ops runbook at docs/runbooks/openclaw-ops.md

### F003: Whisper Transcription Skill — COMPLETE

- Reused existing transcribe-api Docker container
- Rebound from 0.0.0.0 to 100.92.197.90:8787 (Tailscale IP)
- OpenClaw whisper skill installed and functional
- Eliminated last 0.0.0.0 binding on office2
- systemd service (transcribe.service) with boot startup
- Ops runbook at docs/runbooks/transcribe-ops.md

### F004: WhatsApp Channel — COMPLETE

- **MAJOR EXCEPTION**: Baileys (unofficial protocol) instead of Meta Cloud API
  - OpenClaw has no Meta Cloud API channel
  - Risk accepted: personal single-user, low volume
- Linked as additional device on Kent's personal number (617) 930-0916
  - Not dedicated number as v0.3 designed
- DM policy: pairing, Group policy: allowlist
- Outbound WebSocket only — no inbound ports
- Session persists across restarts
- Ops runbook at docs/runbooks/whatsapp-ops.md

---

## Section 4: Drift Analysis (Designed vs Actual)

### D-001: WhatsApp API — MAJOR DRIFT

| Aspect | v0.3 Designed | Actual (F004) |
|--------|---------------|---------------|
| Protocol | Meta Cloud API (official) | Baileys (unofficial, WebSocket) |
| Number | Dedicated number (~$1-2/month via Twilio) | Kent's personal cell (617) 930-0916 as linked device |
| Webhook | Tailscale tunnel or Cloudflare endpoint | No webhook — outbound WebSocket only |
| Cost | $1-2/month for dedicated number | Free (uses existing personal account) |

**Impact on v1.0**: The Baileys exception is documented and accepted. v1.0 must reflect this as the actual architecture, not the designed Meta Cloud API approach. The exception policy in security-posture.md covers this.

### D-002: OpenClaw Binding — MINOR DRIFT

| Aspect | v0.3 Designed | Actual (F002) |
|--------|---------------|---------------|
| Binding | "Tailscale-only" (implied network-accessible) | 127.0.0.1 (localhost only) |

**Impact on v1.0**: Actually more restrictive than designed. OpenClaw is localhost-only, accessed only by local skills/services. This is better than the designed state. Document as-is.

### D-003: WhatsApp Webhook Architecture — DESIGN ELIMINATED

v0.3 described a webhook-based architecture (OQ-01: "Tailscale tunnel vs Cloudflare Worker?"). Baileys eliminates this entirely — no inbound webhook needed. OQ-01 is resolved by elimination.

**Impact on v1.0**: Simplification. Remove webhook architecture from design.

### D-004: Credential Manifest Drift

The credential-manifest.json still lists `whatsapp-meta` as a planned credential. F004 replaced this with `whatsapp-session` (Baileys session). The JSON was updated during F004 but the original planned credential name lingers in some docs.

**Impact on v1.0**: Minor cleanup. Ensure consistency.

---

## Section 5: Gap Analysis (Designed but Not Built)

### Items from v0.3 Phase 1 NOT yet implemented

| v0.3 Item | Feature # | Status | Notes |
|-----------|-----------|--------|-------|
| Intent Parser skill | F006 | Not built | Depends on Vikunja API skill (F005) |
| Vikunja API skill (CRUD wrapper) | F005 | Not built | Foundation for all task-writing skills |
| Migrate inbox-processor | F007 | Not built | Depends on F005 |
| Migrate kent-voice | F008 | Not built | |
| Migrate vault-writer | F009 | Not built | |
| Hourly inbox poll heartbeat | F010 | Not built | |
| Goal Context Loader | F011 | Not built | Depends on F007 pattern |
| Google Calendar skill | F012 | Not built | OAuth integration |
| Task-Calendar linking | F013 | Not built | Depends on F012 |
| Daily briefing heartbeat | F014 | Not built | Depends on F004 (done) + heartbeat engine |
| Escalation engine (levels 1-2) | F015 | Not built | Depends on Vikunja API skill |

**Summary**: 11 of 15 Phase 1 items remain. The four completed items (F001-F004) are the infrastructure foundation. The remaining 11 are skills, integrations, and automation that build on the foundation.

### Items from v0.3 Phases 2-4 NOT yet implemented

All Phase 2, 3, and 4 items remain unbuilt. These are post-foundation capabilities.

---

## Section 6: Undocumented State (Built but Not in v0.3)

### U-001: Two-tier Backup System

v0.3 mentions "Restic backup (4AM daily)" briefly. The actual implementation is a comprehensive two-tier system:
- Tier 1: Timeshift OS snapshots (daily/7, weekly/4, monthly/3)
- Tier 2: Restic encrypted GFS backup (daily/7, weekly/4, monthly/6, yearly/1)
- Dedicated 1 TB USB external backup drive
- Documented in docs/design/office2-backup-and-security.md

**Impact on v1.0**: This is more robust than designed. Document the full backup architecture.

### U-002: Security Monitoring System

v0.3 mentions "audit.sh (3AM daily)" briefly. The actual implementation is a comprehensive baseline drift detection system:
- 8 check types (Docker, services, ports, SSH keys, crontabs, pip, hosts, .pth files)
- Baseline files auto-updated after intentional changes
- C2 sinkholing in /etc/hosts
- Documented in docs/design/office2-backup-and-security.md

**Impact on v1.0**: Document fully. This is a Core Hub operational capability.

### U-003: Obsidian Sync Daemon

v0.3 describes Obsidian Sync but the actual systemd daemon (obsidian-sync.service) providing continuous sync to office2 was implemented before v0.3 was written.

**Impact on v1.0**: Document as existing infrastructure.

### U-004: Spec-Kitty Workflow System

The entire spec-kitty workflow (constitution, specify, plan, tasks, implement, review, merge) is not mentioned in v0.3 but is the primary development methodology.

**Impact on v1.0**: Document as Core Hub development tooling.

### U-005: Claude Code as Development Tool

Claude Code (this tool) is used extensively for development but is not mentioned in v0.3.

**Impact on v1.0**: Document as Development team (Area C) tooling.

### U-006: Agent Execution Model

The claude user account on office2 with scoped sudo, the SSH access model (office2-claude vs office2-kgale), and agent traceability requirements are implemented but not in v0.3.

**Impact on v1.0**: Document as Core Hub security and governance.

---

## Section 7: Governance Gap Analysis

### Current Governance (from constitution.md)

| Area | Current State |
|------|--------------|
| Testing Standards | validate_docs.py (frontmatter + secret scan) in CI; manual Python testing |
| Quality Gates | CI validation on every push to main; self-review of diff |
| Branch Strategy | Push directly to main; Claude Code/Desktop as review partner |
| Performance Benchmarks | Inbox 60s, WhatsApp 10s, CI 30s, heartbeat on time |
| Policy Summary | Intent, languages, testing, quality, review, performance, deployment |
| Exception Policy | Formal process with rationale, scope, expiration; hard boundaries defined |

### Gap Assessment Against New Constitution Directives

#### Gap G-001: Narrow Agent Scope — NOT ADDRESSED

**Current state**: The constitution does not define agent scope boundaries. There is no concept of "one agent, one responsibility." The current system has a single OpenClaw instance with skills, but no formal scope boundaries between them.

**What v1.0 must address**: Define scope boundaries for each agent within each capability area team. Establish enforcement mechanisms.

#### Gap G-002: Earned Autonomy (Three-Gate Model) — NOT ADDRESSED

**Current state**: No autonomy model exists. The claude user has a fixed set of permissions (no sudo, Docker group, secondbrain group). There is no concept of gates, progression, or earned trust.

**What v1.0 must address**: Define the three-gate model (Human In The Middle → Human Monitored → Autonomous). Define progression criteria per team. Map to OpenClaw capabilities (WP02 research needed).

#### Gap G-003: Central Action Logging — NOT ADDRESSED

**Current state**: Logging exists but is fragmented:
- OpenClaw has its own logs (journalctl --user -u openclaw-gateway)
- Vikunja has its own logs (Docker logs)
- Security audit has baselines but not action-level logging
- No central location for "what did agents do and when?"

**What v1.0 must address**: Define a central action log (location, format, retention, query interface). Determine if OpenClaw provides this natively (WP02 research needed).

#### Gap G-004: Safety Parameters and Clear Boundaries — PARTIALLY ADDRESSED

**Current state**: Some safety measures exist:
- Privacy boundary (02-Growth/_private/) — absolute, well-enforced
- No credentials in code — enforced by CI secret scan
- Agent traceability — claude user, SSH access model
- Supply chain safety — version pinning, source review

**What is missing**:
- Agents don't stop and alert when asked to do something they shouldn't — no formal boundary declaration mechanism
- No concept of "don't know how to do" graceful degradation at the agent level
- No formal "never fail silently" enforcement

**What v1.0 must address**: Formalize the safety parameter model beyond privacy and credentials. Define agent boundary behavior (stop + alert pattern).

---

## Summary

### Key Findings

1. **Infrastructure foundation is solid**: F001-F004 delivered the core platform (task store, orchestration, transcription, WhatsApp channel)
2. **Major design deviation**: Baileys replaces Meta Cloud API — accepted and documented
3. **11 of 15 Phase 1 items remain**: Skills, integrations, and automation not yet built
4. **Undocumented capabilities exist**: Backup system, security monitoring, spec-kitty workflow, Claude Code tooling, agent execution model are all more mature than v0.3 describes
5. **All four new constitution directives have governance gaps**: Narrow scope and earned autonomy are entirely missing. Central logging is fragmented. Safety parameters are partially addressed.
6. **Identity model is minimal**: Two labels exist but no routing automation. Metal casework (third identity) not in v0.3 at all.
7. **v0.3 feature numbering is obsolete**: F005 (this project) discards the v0.3 F005-F015 sequence. New numbering will be defined by the roadmap (WP08).
