---
title: "Integration and Tool Research: F005 System Architecture Development"
doc_type: explanation
status: approved
owners: [kgale]
---
# Integration and Tool Research: F005 System Architecture Development

**Date**: 2026-03-29
**WP**: WP03 — Integration and Tool Research
**Status**: Complete

---

## RQ-6: SuperAdmin Integrations (Capability Area B)

### Confirmed Integrations

**1. Google Calendar**
- **Purpose**: Meeting scheduling, availability checking, time-blocking, conflict detection, repeating appointment reminders
- **Auth**: OAuth2 (personal Google account Phase 1, Intentional Workspace Phase 3). Credential `personal-google` planned for F012.
- **Data flow**: Bidirectional — read events for briefings/conflicts, write events for scheduling
- **Constraints**: OAuth2 authorization code flow uses localhost redirect on MacBook for one-time auth. After initial grant, refresh tokens work server-to-server from office2. No inbound connections needed.

**2. Gmail**
- **Purpose**: Email triage, summarization, draft creation, search
- **Auth**: OAuth2 (same `personal-google` credential — add Gmail scopes)
- **Data flow**: Bidirectional — read for triage, write for drafts/replies
- **Constraints**: Same OAuth2 pattern as Google Calendar. See RQ-9 for full analysis.

**3. WhatsApp (already integrated — F004)**
- **Purpose**: Briefing delivery, escalation alerts, repeating reminders, interactive task negotiation, on-demand triggers
- **Auth**: Baileys linked-device session (QR pairing). Credential: `whatsapp-session`
- **Data flow**: Bidirectional
- **Status**: Deployed and operational

**4. Vikunja (already integrated — F001)**
- **Purpose**: Task CRUD, priority management, escalation state (labels), project/area views, saved filter queries
- **Auth**: API token (`vikunja-api`)
- **Data flow**: Bidirectional
- **Status**: Deployed and operational

**5. Whisper/transcribe-api (already integrated — F003)**
- **Purpose**: Voice note transcription for capture-classify-route pipeline
- **Auth**: Tailscale network access (no token)
- **Data flow**: Audio in, text out
- **Status**: Deployed and operational

**6. Obsidian Vault / Second Brain (already integrated)**
- **Purpose**: Goal Context Loader reads constitution docs, inbox-processor routes content
- **Auth**: Filesystem access on office2 (via Obsidian Sync daemon)
- **Data flow**: Bidirectional — read constitution, write processed notes
- **Constraints**: `02-Growth/_private/` absolutely never accessed
- **Status**: Deployed and operational

### Open Decisions

**7. Contacts/Address Book — OPEN DECISION**
- **Need**: Track record reporting, meeting scheduling with external parties
- **Options**:
  - (a) Google Contacts API — comes free with same `personal-google` OAuth2 credential
  - (b) HubSpot CRM contacts (if HubSpot adopted for BizOps)
  - (c) No dedicated integration — contacts remain manual
- **Criteria**: If scheduling meetings with external parties by name, Google Contacts is zero-cost since OAuth2 credential already covers it

**8. Scheduling Link Service — OPEN DECISION**
- **Need**: Meeting scheduling for external parties (booking links)
- **Options**:
  - (a) Calendly API — Kent already has a Calendly account per identity model
  - (b) Cal.com (self-hosted on office2, Tailscale-only)
  - (c) No scheduling link — OpenClaw proposes times via Calendar free/busy and emails them
- **Criteria**: Volume of external scheduling, prospect expectations, self-host preference

### Cross-Cutting Notes

- **Dual identity routing**: Every Google service action must route to correct identity (personal vs Intentional) based on Vikunja labels. Phase 3 concern but architecture must accommodate it.
- **Track record reporting**: Requires Vikunja historical query (completed tasks, dates). No new integration — intelligence is in the OpenClaw skill.
- **Repeating reminders**: Vikunja supports natively. Delivery is WhatsApp. Gap is the heartbeat skill — not an integration.

---

## RQ-7: BizOps Business Systems (Capability Area E)

### Confirmed Integration

**1. HubSpot CRM**
- **Purpose**: Lead capture, contact management, deal pipeline, marketing campaign management
- **Auth**: Private app token (server-to-server, no callback) or OAuth2
- **Data flow**: Bidirectional — read pipeline for reports, write contacts/deals
- **Constraints**:
  - Webhooks require public URL — Tailscale-only blocks direct receipt. Options: poll API on schedule, Cloudflare Worker relay, or Tailscale Funnel.
  - Free tier: 100 API calls/10 sec. Sufficient for solo consultancy.
  - Marketing Hub features (email campaigns, sequences) require paid tiers.
- **Status**: Mentioned in spec but Kent should confirm as the CRM choice

### Open Decisions

**2. CRM Platform (if HubSpot not confirmed) — OPEN DECISION**
- **Need**: Contact management, lead tracking, deal pipeline
- **Options**:
  - (a) HubSpot Free CRM — rich features, good API, private app tokens work behind Tailscale
  - (b) Vikunja as lightweight CRM — use projects/labels for deal tracking, no new integration
  - (c) Folk or Attio — modern lightweight CRMs with good APIs
- **Criteria**: Pipeline scale, marketing automation needs, consolidation preference, cost

**3. Invoicing — OPEN DECISION**
- **Need**: Create/send invoices, track payments, accounts receivable
- **Options**:
  - (a) Stripe Invoicing — integrated if using Stripe for payments. Server-to-server API.
  - (b) QuickBooks Online — full accounting + invoicing. OAuth2.
  - (c) Wave — free invoicing/accounting. Limited API.
  - (d) FreshBooks — invoicing-focused, good API. OAuth2.
- **Criteria**: Current invoicing tool (unknown — question for Kent), full accounting vs invoicing only, payment processing integration
- **Research gap**: No mention of current invoicing/accounting tool in repo

**4. Order Management — OPEN DECISION**
- **Need**: For metal casework business — orders, fulfillment, customer communications
- **Options**:
  - (a) Custom-built (Development team) — part of visual designer tool/website
  - (b) Shopify — handles orders, payments, fulfillment. Server-to-server API.
  - (c) WooCommerce — self-hosted alternative
  - (d) Defer — metal casework is research/feasibility phase, likely premature
- **Criteria**: Business maturity, product vs custom order model, self-host preference
- **Recommendation**: Defer until business model solidifies (metalbox is "research/feasibility study")

**5. Social Media Management — OPEN DECISION**
- **Need**: Schedule and publish across LinkedIn, Instagram, personal website, email
- **Options**:
  - (a) Buffer — multi-platform scheduling, API available. SaaS.
  - (b) Hootsuite — enterprise-oriented, more expensive
  - (c) Direct API integration — LinkedIn API, Instagram Graph API, website CMS API
  - (d) HubSpot Social (paid tier) — consolidation if HubSpot adopted
- **Criteria**: Platform count, posting frequency, analytics needs, SaaS vs direct integration

**6. Email Marketing — OPEN DECISION**
- **Need**: Marketing emails to target audiences (distinct from personal Gmail triage)
- **Options**:
  - (a) HubSpot Email Marketing (paid tier) — CRM integration
  - (b) Mailchimp — free tier for small lists, good API
  - (c) SendGrid/Postmark — API-first, works behind Tailscale
  - (d) Listmonk (self-hosted) — open source, runs on office2, requires SMTP relay
- **Criteria**: List size, campaign sophistication, CRM integration, self-host preference

**7. Website CMS / Blog — OPEN DECISION**
- **Need**: Publish blog posts to personal site
- **Options**:
  - (a) Git-based publishing — markdown in intentional repo, CI deploys. No new integration.
  - (b) Headless CMS (Ghost, Strapi) — content API
  - (c) WordPress REST API
- **Criteria**: Current website technology (intentional repo appears code-based)
- **Recommendation**: Git-based publishing is most natural given existing setup

### Cross-Cutting Notes

- **Multi-business identity**: BizOps serves Intentional LLC and (eventually) metal casework. Identity routing via Vikunja labels.
- **HubSpot as consolidation hub**: CRM + email marketing + social publishing + lead capture in one ecosystem. Tradeoff: vendor lock-in and cost at paid tiers.
- **Webhook receipt problem**: Multiple BizOps integrations use webhooks. Systematic options: polling (simplest), Tailscale Funnel, Cloudflare Worker relay.

---

## RQ-8: Content Creation Tools (Capability Area D)

### Confirmed Integrations

**1. Canva**
- **Purpose**: Graphics, presentations, social media visuals, marketing materials, brand design
- **Auth**: Canva Connect API via OAuth2. MCP tools already available in Claude Code environment.
- **Data flow**: Bidirectional — create designs, export assets, manage brand kits
- **Constraints**: Cloud SaaS, outbound HTTPS from office2. No webhook needed.
- **Capabilities**: Design generation (including structured), brand kits, export, asset management, folders, editing transactions.

**2. Claude/Anthropic API (already locked)**
- **Purpose**: Text generation — blog posts, LinkedIn posts, white papers, email copy, web copy, captions
- **Auth**: API key (`anthropic`), already deployed
- **Data flow**: Request/response
- **Status**: Operational via OpenClaw

### Open Decisions

**3. Diagram/Architecture Visual Generation — OPEN DECISION**
- **Need**: Conceptual diagrams, process flows, architecture visuals
- **Options**:
  - (a) Mermaid.js — text-to-diagram, Claude generates syntax natively. Free, local, already used in repo (`.mmd` files in architecture docs)
  - (b) D2 (Terrastruct) — modern diagram-as-code, better visuals than Mermaid. Free, local.
  - (c) Canva AI generation — better for marketing than technical diagrams
  - (d) DALL-E/Midjourney/Stable Diffusion — for conceptual graphics, not technical diagrams
- **Criteria**: Technical vs marketing diagrams, editability, local execution preference
- **Recommendation**: Mermaid/D2 for technical diagrams (already in use), Canva for marketing visuals

**4. Video Content — OPEN DECISION**
- **Need**: Video for LinkedIn/Instagram marketing
- **Options**:
  - (a) Canva Video — already integrated, limited vs dedicated tools
  - (b) Synthesia/HeyGen — AI talking head videos from text. SaaS, API available.
  - (c) Descript — video editing with AI. Desktop app, limited API.
  - (d) FFmpeg + scripts — programmatic assembly on office2. High effort.
  - (e) Defer to Phase 3+
- **Criteria**: Volume, video type, budget, AI presenter acceptability
- **Recommendation**: Phase 3+ capability. Start with Canva Video for simple content.

**5. PDF/White Paper Generation — OPEN DECISION**
- **Need**: Professional PDFs, white papers with formatting
- **Options**:
  - (a) Pandoc (markdown → PDF via LaTeX) — free, local, Claude generates markdown
  - (b) Canva — design-focused PDFs
  - (c) Google Docs API — create in Docs, export PDF
  - (d) Typst — modern typesetting, simpler than LaTeX, local
- **Criteria**: Formatting complexity, brand consistency, local preference
- **Recommendation**: Pandoc for text-heavy documents, Canva for designed/visual PDFs

### Cross-Cutting Notes

- **Content Creation as shared service**: Area D serves all other areas. Architecture must support requests routed from SuperAdmin, Development, and BizOps.
- **Multi-format pipeline**: Generating "different versions of a topic" is primarily a Claude skill — same source transformed to format-appropriate versions. Tool integrations are for publishing/rendering.
- **Asset management**: Generated content needs storage. Options: Canva folders (Canva assets), second brain (text), dedicated `/data/content/` on office2.

---

## RQ-9: Email Integration Approach

### Decision

**Gmail API via OAuth2 (Authorization Code Flow)** is the recommended approach.

### Rationale

1. **Full functionality**: Gmail API provides thread-aware reading, label management, draft creation, search with Gmail operators — matches all SuperAdmin user stories
2. **Tailscale-only compatible**: One-time OAuth2 authorization uses localhost redirect on MacBook. After that, all API access is outbound HTTPS from office2. No inbound connections needed.
3. **Works for both identities**: OAuth2 authorization code flow works for personal Gmail and Intentional Workspace. Service accounts only work for Workspace.
4. **Scoped security**: OAuth2 scopes allow least-privilege access (gmail.readonly for triage agents, gmail.compose for draft agents). Tokens in office2 secrets store.
5. **Established pattern**: Credential manifest already plans `personal-google` OAuth2 credential (F012). Gmail uses same client — just add scopes.

### One-Time Setup Flow

1. Create OAuth2 client in Google Cloud Console (desktop application type)
2. On MacBook, run authorization script — opens browser, handles localhost redirect
3. Exchange auth code for access + refresh tokens
4. Transfer refresh token to office2 secrets store
5. OpenClaw uses refresh token for ongoing API access — all outbound

### Alternatives Considered

- **Service Account (Option B)**: Does NOT work with personal Gmail. Only works with Google Workspace via domain-wide delegation. Rejected as primary.
- **IMAP/SMTP (Option C)**: Significantly limited — no thread view, no label management, no Gmail-native search. Same OAuth2 effort required. Rejected.
- **OpenClaw Native Email (Option D)**: Not rejected — flagged as open research item. If OpenClaw has native email channel, it may wrap Gmail API with OAuth2, becoming the preferred implementation of the same approach.

### Gaps

- Refresh tokens expire if unused for 6 months or on password change — re-auth requires MacBook browser flow
- **Open research**: Check OpenClaw docs for native email channel support (could change implementation approach)

---

## Open Decisions Summary

| # | Need | Area | Likely Default | Phase |
|---|------|------|---------------|-------|
| OD-1 | CRM platform | BizOps | HubSpot (mentioned) | Phase 2 |
| OD-2 | Invoicing tool | BizOps | Unknown — question for Kent | Phase 2 |
| OD-3 | Order management | BizOps | Defer (metal casework pre-revenue) | Phase 3+ |
| OD-4 | Social media scheduling | BizOps | Buffer or direct APIs | Phase 2 |
| OD-5 | Email marketing | BizOps | HubSpot Email or Mailchimp | Phase 2 |
| OD-6 | Diagram generation | Content Creation | Mermaid (already in use) | Phase 1 |
| OD-7 | Video content | Content Creation | Defer (Canva Video for simple) | Phase 3+ |
| OD-8 | PDF/white paper | Content Creation | Pandoc (pragmatic default) | Phase 2 |
| OD-9 | Contacts integration | SuperAdmin | Google Contacts (free w/ OAuth2) | Phase 1 |
| OD-10 | Scheduling links | SuperAdmin | Optional (Calendly or none) | Phase 2+ |
| OD-11 | OpenClaw native email | SuperAdmin | Research needed | Phase 1 |
| OD-12 | Webhook receipt strategy | Cross-cutting | Polling (simplest) | Phase 1 |

## OAuth2 Credential Consolidation

Google Calendar, Gmail, Contacts, Slides, and Docs all use the same OAuth2 client with different scopes. A single `personal-google` credential with combined scopes covers all Google integrations. Same for `intentional-google`. Already reflected in credential manifest.
