---
title: "F004: WhatsApp Channel"
doc_type: func-spec
status: draft
feature: F004
---

# F004: WhatsApp Channel

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure + Integration

---

## Executive Summary

OpenClaw is running (F002 complete) but has no inbound communication channel.
WhatsApp is the primary interface through which Kent sends commands, voice notes,
and receives briefings, reminders, and escalations. This spec covers registering the dedicated Google Voice number with
Meta Cloud API, connecting it to OpenClaw on office2 via Cloudflare Tunnel,
and verifying the end-to-end message path.

Current gaps:
- ❌ No WhatsApp number dedicated to the system
- ❌ No Meta Cloud API credentials configured
- ❌ No webhook endpoint receiving WhatsApp messages
- ❌ OpenClaw not connected to any inbound channel

This spec delivers a functional WhatsApp channel: messages sent to the
dedicated number reach OpenClaw on office2, and OpenClaw can send replies.

---

## Problem Statement

**Current State:**
```
Kent
└── ❌ No WhatsApp channel to the system
└── ❌ No way to send commands or receive responses

office2
└── ✅ OpenClaw running on port 18789/127.0.0.1 (F002)
└── ❌ No inbound webhook configured
└── ❌ No WhatsApp credentials
```

**Target State:**
```
Kent (iPhone WhatsApp)
└── ✅ Dedicated WhatsApp number (Google Voice, free)
      │
      ▼
Meta Cloud API (official)
      │ webhook POST
      ▼
Webhook endpoint (office2, Tailscale-accessible)
      │
      ▼
OpenClaw gateway (127.0.0.1:18789)
      │
      ▼
✅ OpenClaw processes message, sends reply via Meta API
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Architecture and prior features**
   - `docs/design/architecture/data/service-inventory.json` — OpenClaw runs on
     port 18789, bound to 127.0.0.1. The webhook endpoint must bridge inbound
     traffic to this internal port.
   - `docs/design/architecture/data/network-topology.json` — Tailscale IPs for
     all devices. The webhook must be reachable from Meta's servers.
   - `docs/design/architecture/data/credential-manifest.json` — `whatsapp-meta`
     credential is planned here; F003 activates it.
   - `docs/handbooks/openclaw-ops.md` — OpenClaw configuration patterns
     established in F002.

2. **OpenClaw WhatsApp integration docs**
   - https://openclaw.ai/integrations — WhatsApp setup instructions
   - https://docs.openclaw.ai — How OpenClaw expects the webhook configured
   - Understand whether OpenClaw handles the Meta webhook verification
     challenge natively or requires separate handling.

3. **Meta Cloud API requirements**
   - Webhook verification requires a publicly reachable HTTPS endpoint OR a
     Cloudflare Tunnel / similar. office2 is Tailscale-only — this is the
     core network challenge to solve.
   - Meta requires webhook URL to respond to a GET verification challenge
     before messages flow.

4. **office2 network constraints**
   - `docs/design/architecture/data/network-topology.json` confirms office2
     is Tailscale-only with no public exposure.
   - The planning phase must determine how to make the webhook endpoint
     reachable by Meta's servers without exposing office2 publicly.

---

## Core Network Challenge

Meta's WhatsApp Cloud API requires a webhook URL that Meta's servers can reach
to deliver messages. office2 is Tailscale-only and must not be exposed to the
public internet.

**The resolution**: Use **Cloudflare Tunnel** (formerly Argo Tunnel) to create
a stable, publicly reachable HTTPS URL that proxies inbound Meta webhook traffic
to the OpenClaw gateway on office2, without opening any firewall ports or
exposing office2 publicly. Cloudflare Tunnel creates an outbound-only connection
from office2 to Cloudflare's edge — no inbound port is ever opened.

This is the required approach. Do not use ngrok (ephemeral URLs, session
limits). Do not expose port 18789 directly. Do not use 0.0.0.0 binding.

---

## Functional Requirements

### FR-1: WhatsApp Number

**What it must do:**
- The dedicated system number is a Google Voice number (free)
- This number becomes the permanent system contact — it should not change
- The number must be active and able to receive SMS or voice calls before
  Meta registration can proceed
- Cost: $0/month

**Note:** Google Voice is technically a VoIP number. Meta has tightened VoIP
number acceptance over time. The number has been obtained and identity
verification with Google is pending — Meta registration cannot proceed until
Google activates the number. If Meta rejects the VoIP number during
registration, a fallback PSTN number will be needed.

**Success criteria:**
- [ ] Google Voice number is active and can receive SMS/calls
- [ ] Number successfully registered with Meta Cloud API (OTP received)
- [ ] Number is distinct from Kent's personal WhatsApp number

---

### FR-2: Meta Cloud API App Configuration

**What it must do:**
- Create or configure a Meta developer app with WhatsApp Business API access
- Configure the webhook URL (Cloudflare Tunnel endpoint, see FR-4)
- Set the webhook verify token (stored in credential store, not hardcoded)
- Subscribe the app to `messages` webhook events at minimum
- Obtain and store the WhatsApp Business API access token

**Success criteria:**
- [ ] Meta app configured with webhook URL
- [ ] Webhook verification challenge passes (Meta confirms endpoint)
- [ ] App subscribed to `messages` events
- [ ] Access token stored in credential store as `whatsapp-meta`

---

### FR-3: Credential Store

**What it must do:**
- Add `whatsapp-meta` credential to `/data/services/openclaw/secrets/`
  following the pattern established in F002 (mode 600, claude-owned)
- Store the webhook verify token in credential store as `whatsapp-webhook-token`
- No tokens or secrets committed to repo

**Success criteria:**
- [ ] `/data/services/openclaw/secrets/whatsapp-meta` exists, mode 600
- [ ] `/data/services/openclaw/secrets/whatsapp-webhook-token` exists, mode 600
- [ ] No credential values in any committed file

---

### FR-4: Cloudflare Tunnel

**What it must do:**
- Install and configure `cloudflared` on office2 as a systemd service
- Create a Cloudflare Tunnel that exposes the OpenClaw webhook endpoint
  on a stable public HTTPS URL
- The tunnel must connect to the OpenClaw gateway on `127.0.0.1:18789`
  (or wherever OpenClaw expects webhook delivery — confirm during planning)
- Tunnel credentials stored at `/data/services/cloudflared/` (mode 700,
  claude-owned), backed up via existing Restic coverage
- `cloudflared.service` follows the same systemd pattern as F001/F002

**Security properties:**
- Cloudflare Tunnel creates an outbound-only connection — no inbound ports
  are opened on office2
- The public HTTPS URL is on Cloudflare's infrastructure, not office2
- Meta webhook traffic arrives at Cloudflare, is forwarded through the
  tunnel to office2 — office2 is never directly reachable from the internet

**Success criteria:**
- [ ] `cloudflared` installed and running as systemd service
- [ ] Stable public HTTPS URL assigned (ideally a custom subdomain, not
  a random `*.trycloudflare.com` URL)
- [ ] Tunnel forwards traffic to OpenClaw webhook endpoint on office2
- [ ] `curl https://[tunnel-url]/health` (or equivalent) responds from
  outside Tailscale network
- [ ] office2 has no new publicly exposed ports (`ss -tlnp` unchanged)
- [ ] Tunnel credentials in `/data/services/cloudflared/` under Restic coverage

---

### FR-5: OpenClaw WhatsApp Integration

**What it must do:**
- Configure OpenClaw to use the WhatsApp channel with the Meta Cloud API
  credentials from the credential store
- Verify OpenClaw can send an outbound message to Kent's personal WhatsApp
  from the dedicated number
- Verify an inbound message from Kent reaches OpenClaw

**Success criteria:**
- [ ] OpenClaw configured with WhatsApp channel credentials
- [ ] Sending a message to the dedicated number delivers it to OpenClaw
- [ ] OpenClaw sends a reply that arrives on Kent's iPhone WhatsApp
- [ ] Voice notes sent to the number are received by OpenClaw (transcription
  is F003 — for now, confirm the audio payload arrives)

---

### FR-6: Security Audit Baseline Reset

**What it must do:**
- Reset security audit baselines after `cloudflared` installation
- The new outbound tunnel connection and systemd service will otherwise
  trigger daily false-positive alerts

**Success criteria:**
- [ ] Security audit baselines reset
- [ ] Next audit run produces no alerts for `cloudflared`

---

### FR-7: Operations Runbook

**What it must do:**
- Create `docs/handbooks/whatsapp-ops.md` covering:
  - Dedicated WhatsApp number and where it's registered
  - How to restart the Cloudflare Tunnel service
  - How to rotate the WhatsApp access token
  - How to verify the webhook is receiving messages
  - What to do if Meta disables the webhook
  - Tunnel URL and how to update it in Meta's config if it changes

**Success criteria:**
- [ ] Runbook exists at `docs/handbooks/whatsapp-ops.md`
- [ ] All topics covered
- [ ] Passes doc validation (frontmatter compliant)

---

## Architecture Documentation Updates

F004 changes the deployed system. Update the following as part of
implementation — not as a separate task.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add `cloudflared` service entry |
| `data/credential-manifest.json` | Move `whatsapp-meta` from planned to active; add `whatsapp-webhook-token` |
| `data/network-topology.json` | Add Cloudflare Tunnel entry — note it is outbound-only, no new inbound ports |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Add `cloudflared` to Running Services and Deployment Details |
| `credentials-and-secrets.md` | Move `whatsapp-meta` to Active; add `whatsapp-webhook-token` |
| `security-posture.md` | Note Cloudflare Tunnel as the approved external ingress pattern |

### No Changes Required

- `hardware-inventory.json` — no hardware changes
- `data-flows.json` / `data-flows.md` — full data flow documented in F006 (Intent Parser)
- `physical-topology.md` / `.mmd` — no topology changes (Tailscale mesh unchanged)

**Success criteria:**
- [ ] All modified JSON files have `updated_by: "F004"`
- [ ] Markdown views match JSON sources
- [ ] `security-posture.md` documents Cloudflare Tunnel as approved ingress pattern

---

## Out of Scope

- ❌ Whisper transcription of voice notes — F003 (audio payload arrives but
  is not processed in this feature)
- ❌ Intent parsing of messages — F006
- ❌ Any task creation or responses beyond echo/connectivity verification — F006+
- ❌ Telegram, iMessage, or other channels — not planned
- ❌ WhatsApp group chat support — personal DM only

---

## Success Criteria

**Complete when:**

### Channel Established
- [ ] Dedicated Google Voice number active and registered with Meta Cloud API
- [ ] Meta Cloud API app configured and verified

### Infrastructure
- [ ] `cloudflared` running as systemd service on office2
- [ ] Tunnel endpoint reachable from public internet (verified from outside Tailscale)
- [ ] No new inbound ports on office2

### End-to-End Verification
- [ ] Message from Kent's iPhone → dedicated number → reaches OpenClaw
- [ ] OpenClaw reply → arrives on Kent's iPhone WhatsApp
- [ ] Voice note payload arrives at OpenClaw (content not processed yet)

### Credentials
- [ ] `whatsapp-meta` and `whatsapp-webhook-token` in credential store
- [ ] No credentials in committed files

### Security
- [ ] Audit baselines reset

### Documentation
- [ ] `docs/handbooks/whatsapp-ops.md` complete and CI-passing
- [ ] Architecture docs updated

---

## Architecture Principles

### Cloudflare Tunnel as the Ingress Pattern

This feature establishes Cloudflare Tunnel as the approved and only method
for ingesting external webhook traffic to office2. The principle: office2
never accepts inbound connections from the public internet. All external
traffic arrives via outbound-originated tunnels.

This pattern is reusable. Future integrations requiring external webhooks
(e.g., GitHub webhooks, calendar push notifications) should follow this
same pattern.

### Official API Only

Meta Cloud API is the only approved WhatsApp integration method. Unofficial
bridges (`whatsapp-web.js`, Baileys, or similar) that use WhatsApp Web
sessions are prohibited — they risk account ban and use session scraping
rather than an official API.

---

## Constitutional Compliance

✅ **Security over convenience**: Cloudflare Tunnel preserves the
Tailscale-only posture. No ports opened. No 0.0.0.0 binding.

✅ **No credentials in code**: All WhatsApp credentials in the credential
store, following F002 pattern.

✅ **Official integrations only**: Meta Cloud API, not unofficial bridges.

✅ **Linux/office2 target**: `cloudflared` targets Ubuntu 24.04 LTS.

✅ **Docs adjacent**: Runbook and architecture docs updated alongside deployment.

---

## Risk Considerations

**Risk: Meta disables the app or webhook**
- Meta can disable WhatsApp Business API apps for policy violations or
  inactivity. The entire WhatsApp channel goes silent.
- Mitigation: Document recovery procedure in runbook. Monitor via the
  security audit log. Consider a daily heartbeat message (F014) as a
  passive liveness check.

**Risk: Cloudflare Tunnel URL changes**
- The tunnel URL is registered with Meta. If it changes, the webhook stops
  receiving messages.
- Mitigation: Use a stable custom subdomain (e.g., via a Cloudflare Zone),
  not a randomly assigned `trycloudflare.com` URL. Document URL in runbook
  and in `network-topology.json`.

**Risk: `cloudflared` supply chain**
- `cloudflared` is a Cloudflare-maintained binary. It receives the same
  scrutiny as other pinned dependencies.
- Mitigation: Pin to a specific reviewed version. Security audit's process
  and port monitoring will detect unexpected network activity.

---

## Notes for Implementation

**Planning phase decisions:**
- Determine the exact webhook path OpenClaw expects (e.g., `/webhook`,
  `/api/whatsapp`) by reading OpenClaw's WhatsApp integration docs
- Determine whether `cloudflared` should tunnel to port 18789 directly
  or to a different OpenClaw-managed endpoint
- Confirm whether OpenClaw handles Meta's GET webhook verification
  challenge automatically

**Number activation prerequisite:**
- Google Voice identity verification must be complete before Meta
  registration can proceed
- Once Google activates the number, register with Meta via Meta Business
  Manager — receive OTP via SMS or voice call to complete verification
- Google Voice is the number provider only — Meta Cloud API is used
  directly for messaging

**`cloudflared` installation:**
- Planning phase should research the correct installation method for Ubuntu 24.04 LTS
  and the appropriate config/credential structure for the Cloudflare Tunnel
- Pin to a specific version consistent with the project's security posture
- All tunnel config and credentials must land under `/data/services/cloudflared/`
  (for Restic backup coverage) — planning phase determines the exact structure

---

**END OF SPECIFICATION**
