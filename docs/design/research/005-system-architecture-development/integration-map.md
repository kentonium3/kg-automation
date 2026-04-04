# Integration Map: Felix System Architecture

**Date**: 2026-03-29
**WP**: WP06 — Integration Map (Deliverable 2)
**Status**: Complete

---

## Core Hub (Area A) — System Infrastructure

| Integration | Purpose | Auth | Data Flow | Constraints | Status |
|-------------|---------|------|-----------|-------------|--------|
| Vikunja REST API | Task store CRUD, project management, labels | API token | Bidirectional | Tailscale-only (100.92.197.90:3456) | Deployed (F001) |
| Anthropic Claude API | LLM intelligence for all agents | API key | Request/response | Direct — no proxy/LiteLLM | Deployed (F002) |
| OpenClaw Gateway | Agent orchestration, skill execution | Internal | Internal | Localhost (127.0.0.1:18789) | Deployed (F002) |
| Obsidian Sync | Vault sync to office2 | Filesystem | Bidirectional | systemd daemon, continuous | Deployed |
| GitHub | Version control, CI | SSH key / PAT | Bidirectional | CI validates on push | Deployed |
| Tailscale | Network access control | System-managed | Network layer | All services bind to Tailscale IP | Deployed |
| OpenTelemetry Collector | Central action log ingestion | Internal | Ingest | New — must be deployed on office2 | **Planned** |

## SuperAdmin (Area B) — Executive Digital Assistant

| Integration | Purpose | Auth | Data Flow | Constraints | Status |
|-------------|---------|------|-----------|-------------|--------|
| Google Calendar | Scheduling, availability, time-blocking, reminders | OAuth2 (`personal-google`) | Bidirectional | Localhost redirect for initial auth; refresh tokens server-to-server | **Planned** |
| Gmail | Email triage, summarization, draft creation | OAuth2 (`personal-google` + Gmail scopes) | Bidirectional | Same OAuth2 pattern as Calendar | **Planned** |
| WhatsApp (Baileys) | Briefings, alerts, reminders, interactive commands | Session (QR pairing) | Bidirectional | Baileys exception accepted | Deployed (F004) |
| Vikunja | Task priorities, escalation state, saved filters | API token | Bidirectional | — | Deployed (F001) |
| transcribe-api | Voice note transcription | Network (Tailscale) | Audio in / text out | Tailscale-only (100.92.197.90:8787) | Deployed (F003) |
| Second Brain (Obsidian) | Constitution docs, inbox processing | Filesystem | Bidirectional (read constitution, write inbox routes) | 02-Growth/_private/ absolute boundary | Deployed |
| Google Contacts | Contact lookup for scheduling | OAuth2 (`personal-google`) | Read | Free with same OAuth2 credential | **Open decision** |
| Calendly | Scheduling links for external parties | API key or OAuth2 | Read/write | Optional — only if booking links needed | **Open decision** |

## Development (Area C) — Application & System Development

| Integration | Purpose | Auth | Data Flow | Constraints | Status |
|-------------|---------|------|-----------|-------------|--------|
| Claude Code | AI-assisted development | Anthropic API key (shared) | Interactive | Shell execution from OpenClaw | In use (manual) |
| spec-kitty | Spec-driven development workflow | CLI | Shell execution | Shell exec + webhook callbacks | In use (manual) |
| GitHub | Code repos, PRs, CI | SSH key / PAT | Bidirectional | — | Deployed |

## Content Creation (Area D) — Content Generation

| Integration | Purpose | Auth | Data Flow | Constraints | Status |
|-------------|---------|------|-----------|-------------|--------|
| Canva | Graphics, presentations, social media visuals, brand design | OAuth2 (Canva Connect API) | Bidirectional | Cloud SaaS, outbound HTTPS | **Planned** |
| Claude/Anthropic API | Text generation (all content types) | API key | Request/response | Already operational via OpenClaw | Deployed (F002) |
| Mermaid.js / D2 | Technical diagrams, architecture visuals | CLI (local) | Text in / SVG out | Runs locally on office2, free | **Open decision** (Mermaid already in use) |
| Video tools | Video content for social media | TBD | TBD | Phase 3+ capability | **Open decision** |
| Pandoc | PDF/white paper generation from markdown | CLI (local) | Markdown in / PDF out | Runs locally on office2, free | **Open decision** (pragmatic default) |

## BizOps (Area E) — Business Operations

| Integration | Purpose | Auth | Data Flow | Constraints | Status |
|-------------|---------|------|-----------|-------------|--------|
| HubSpot CRM | Leads, contacts, deals, pipeline, campaigns | Private app token | Bidirectional | Webhooks need polling (Tailscale-only); free tier rate limits | **Open decision** (mentioned, not confirmed) |
| Social media APIs / Buffer | Cross-platform publishing (LinkedIn, Instagram) | OAuth2 / API key | Write | Phase 2+ | **Open decision** |
| Email marketing platform | Campaign emails to audiences | API key / OAuth2 | Write | Distinct from personal Gmail triage | **Open decision** |
| Invoicing tool | Create/send invoices, track payments | TBD | Bidirectional | Depends on what Kent currently uses | **Open decision** |
| Order management | Metal casework orders and fulfillment | TBD | Bidirectional | Defer — metal casework is pre-revenue | **Open decision** |
| Website CMS | Blog post publishing | Git-based or API | Write | Likely Git-based from intentional repo | **Open decision** |

## Cross-Cutting Concerns

### OAuth2 Credential Consolidation

A single `personal-google` OAuth2 credential covers: Calendar, Gmail, Contacts, Docs, Slides. One authorization flow, multiple scopes. Same pattern for `intentional-google` (Phase 3).

### Webhook Receipt Strategy

Multiple integrations benefit from webhooks (HubSpot, Gmail push, payment events). Tailscale-only blocks direct receipt. Options:
1. **Polling** (recommended for Phase 1) — acceptable latency for solo business
2. **Tailscale Funnel** — exposes specific port via Tailscale infrastructure
3. **Cloudflare Worker relay** — lightweight serverless webhook forwarder

### Open Decisions Summary

| # | Integration | Area | Likely Default | Phase |
|---|-------------|------|---------------|-------|
| OD-1 | CRM (HubSpot?) | BizOps | HubSpot — Kent to confirm | 2 |
| OD-2 | Invoicing | BizOps | Unknown — Kent to decide | 2 |
| OD-3 | Order management | BizOps | Defer | 3+ |
| OD-4 | Social media scheduling | BizOps | Buffer or direct APIs | 2 |
| OD-5 | Email marketing | BizOps | HubSpot Email or Mailchimp | 2 |
| OD-6 | Diagram tool | Content | Mermaid (already in use) | 1 |
| OD-7 | Video tools | Content | Defer (Canva Video simple) | 3+ |
| OD-8 | PDF generation | Content | Pandoc | 2 |
| OD-9 | Contacts | SuperAdmin | Google Contacts (free) | 1 |
| OD-10 | Scheduling links | SuperAdmin | Optional | 2+ |
| OD-11 | OpenClaw email channel | SuperAdmin | Research needed | 1 |
| OD-12 | Webhook strategy | Cross-cutting | Polling | 1 |
