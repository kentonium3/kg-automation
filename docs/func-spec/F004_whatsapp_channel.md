---
title: "F004: WhatsApp Channel"
doc_type: func-spec
status: draft
feature: F004
---

# F004: WhatsApp Channel

**Version**: 1.3
**Priority**: HIGH
**Type**: Integration

---

## Executive Summary

OpenClaw is running (F002 complete) but has no inbound communication channel.
WhatsApp is the primary interface through which Kent sends commands, voice notes,
and receives briefings, reminders, and escalations. This spec covers pairing
OpenClaw with the dedicated Google Voice WhatsApp account via Baileys (OpenClaw's
native WhatsApp channel) and verifying the end-to-end message path.

Current gaps:
- ❌ OpenClaw has no WhatsApp channel configured
- ❌ No WhatsApp session paired with OpenClaw

This spec delivers a functional WhatsApp channel: messages sent to the dedicated
number reach OpenClaw on office2, and OpenClaw can send replies to Kent's
personal WhatsApp.

---

## Problem Statement

**Current State:**
```
Kent (iPhone WhatsApp — personal number)
└── ❌ No connection to OpenClaw

office2
└── ✅ OpenClaw running (F002)
└── ✅ WhatsApp channel added and enabled in OpenClaw config
└── ❌ No WhatsApp session linked (not paired)
```

**Target State:**
```
Kent (iPhone WhatsApp — personal number)
      │  messages to (617) 564-0182
      ▼
Baileys (persistent outbound WebSocket — no inbound ports)
      │
      ▼
OpenClaw gateway on office2
      │
      ▼
✅ OpenClaw processes message, sends reply to Kent's WhatsApp
```

---

## Architecture Decision: Baileys via OpenClaw Native Channel

During planning research, it was discovered that OpenClaw's WhatsApp integration
uses **Baileys** (an unofficial WhatsApp Web protocol library), not Meta Cloud
API. OpenClaw has no Meta Cloud API channel.

**Decision**: Use OpenClaw's native Baileys-based WhatsApp channel. The
original constraint against unofficial bridges has been **removed** with the
following rationale:

- This is a personal single-user system with low message volume
- Baileys is OpenClaw's only WhatsApp path — there is no official API
  alternative within OpenClaw
- Account ban risk is acceptable and documented in the project constitution
- The simplification (no Tailscale Funnel, no Meta app, no webhook, no Meta
  number registration) is substantial

**What this means architecturally:**
- No Meta Cloud API app needed
- No Tailscale Funnel needed (Baileys uses outbound WebSocket, not inbound webhook)
- No webhook verification challenge
- Authentication is via QR code scan, not API tokens
- Session credentials are managed by OpenClaw internally
- No inbound ports opened on office2

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Architecture and prior features**
   - `docs/design/architecture/data/service-inventory.json` — OpenClaw
     gateway details established in F002
   - `docs/handbooks/openclaw-ops.md` — OpenClaw configuration patterns,
     service management, credential store location

2. **OpenClaw WhatsApp/Baileys integration docs**
   - https://openclaw.ai/integrations — WhatsApp setup instructions
   - https://docs.openclaw.ai — How OpenClaw configures Baileys channel
   - Determine how OpenClaw surfaces the QR code
   - Determine where Baileys stores session credentials on office2

---

## Functional Requirements

### FR-1: WhatsApp Channel Configuration and Pairing

**What it must do:**
- Configure DM access control to restrict the channel to Kent's personal number
- Complete QR code pairing of the Google Voice WhatsApp account with OpenClaw
- Session credentials must persist across OpenClaw restarts and office2 reboots

**Success criteria:**
- [ ] `openclaw channels list` shows WhatsApp as "linked, enabled"
- [ ] DM access restricted to Kent's personal number
- [ ] Group chat policy blocks all group chats
- [ ] Session persists across OpenClaw service restart
- [ ] No session credentials committed to repo

---

### FR-2: End-to-End Verification

**What it must do:**
- Verify a text message from Kent's personal WhatsApp reaches OpenClaw
- Verify OpenClaw's reply arrives on Kent's iPhone
- Verify a voice note audio payload arrives at OpenClaw (transcription is F003
  scope — confirm arrival only)

**Success criteria:**
- [ ] Text message from Kent's iPhone reaches OpenClaw and reply returns
- [ ] Round-trip under 10 seconds
- [ ] Voice note audio payload visible in OpenClaw logs

---

### FR-3: Session Persistence

**What it must do:**
- Verify the Baileys session survives OpenClaw restarts without re-pairing
- Verify reconnection within 30 seconds after restart

**Success criteria:**
- [ ] Session reconnects automatically after `systemctl --user restart openclaw-gateway`
- [ ] Reconnection within 30 seconds
- [ ] Messages flow normally after restart

---

### FR-4: Port Safety Verification

**What it must do:**
- Confirm no new inbound ports opened on office2
- Baileys uses outbound WebSocket — this is a verification step, not a
  configuration step

**Success criteria:**
- [ ] `ss -tlnp` shows no new ports compared to pre-deployment baseline
- [ ] No `0.0.0.0` bindings for any managed services

---

### FR-5: Security Audit Baseline Reset

**What it must do:**
- Reset security audit baselines after WhatsApp channel is active
- The new persistent outbound WebSocket connection may affect baselines

**Success criteria:**
- [ ] Security audit baselines reset
- [ ] Next audit run produces no unexpected alerts

---

### FR-6: Operations Runbook

**What it must do:**
- Create `docs/handbooks/whatsapp-ops.md` covering:
  - How Baileys pairing works
  - How to check channel status
  - How to re-pair if the session expires or is invalidated
  - What to do if WhatsApp logs out all linked devices
  - Baileys risk acceptance rationale

**Success criteria:**
- [ ] Runbook exists at `docs/handbooks/whatsapp-ops.md`
- [ ] Passes doc validation (frontmatter compliant)

---

## Architecture Documentation Updates

F004 makes the following changes to the deployed system.

### JSON Updates Required

| File | Change |
|---|---|
| `data/credential-manifest.json` | Update `whatsapp-meta` planned entry to reflect Baileys session approach (managed by OpenClaw internally, not external credential store) |
| `data/service-inventory.json` | Add WhatsApp channel info to OpenClaw entry |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Note WhatsApp channel under OpenClaw deployment details |
| `credentials-and-secrets.md` | Update `whatsapp-meta` entry to reflect Baileys |
| `security-posture.md` | Record Baileys exception with rationale |

### No Changes Required

- `network-topology.json` — no new ports or inbound exposure
- `hardware-inventory.json` — no hardware changes
- `data-flows.json` / `data-flows.md` — full data flow documented in F006
- `physical-topology.md` — no topology changes

**Success criteria:**
- [ ] All modified JSON files have `updated_by: "F004"`
- [ ] Markdown views match JSON sources
- [ ] `security-posture.md` records Baileys exception

---

## Out of Scope

- ❌ Whisper transcription of voice notes — F003 (audio payload arrives but
  is not processed in this feature)
- ❌ Intent parsing of messages — F006
- ❌ Any task creation or responses beyond echo/connectivity verification — F006+
- ❌ Meta Cloud API / webhook — not used (Baileys handles this natively)
- ❌ Tailscale Funnel — not needed (no inbound webhook required)
- ❌ WhatsApp group chat support — personal DM only

---

## Success Criteria

**Complete when:**

### Channel
- [ ] WhatsApp channel linked and enabled in OpenClaw
- [ ] DM restricted to Kent's personal number

### End-to-End
- [ ] Text message round-trip verified
- [ ] Voice note payload arrival verified
- [ ] Session persists across restart

### Security
- [ ] No new inbound ports on office2
- [ ] Audit baselines reset

### Documentation
- [ ] `docs/handbooks/whatsapp-ops.md` complete and CI-passing
- [ ] Architecture docs updated

---

## Architecture Principles

### Baileys as Accepted Exception

OpenClaw's native WhatsApp channel uses Baileys (unofficial WhatsApp Web
protocol). This is an accepted exception documented in the project constitution.
Rationale: personal single-user system, low volume, OpenClaw has no official
API alternative. Account ban risk is understood and accepted.

### No Public Exposure

Baileys uses an outbound WebSocket connection. No inbound ports, no webhook
URL, no public exposure. The Tailscale-only posture of office2 is fully
preserved.

---

## Constitutional Compliance

✅ **Security over convenience**: Baileys outbound connection preserves
Tailscale-only posture. No new ports opened.

✅ **No credentials in code**: Session credentials managed by OpenClaw
internally, not committed.

✅ **Documented exception**: Baileys use explicitly recorded in constitution
exception policy with rationale and scope.

✅ **Linux/office2 target**: OpenClaw already running on Ubuntu 24.04 LTS.

✅ **Docs adjacent**: Runbook and architecture docs updated alongside deployment.

---

## Risk Considerations

**Risk: WhatsApp session invalidation**
- WhatsApp can invalidate linked device sessions (e.g., "Log out of all
  devices", extended inactivity). Channel goes silent until re-paired.
- Mitigation: Re-pairing procedure documented in runbook. Daily heartbeat
  (F014) will serve as passive liveness check.

**Risk: Baileys account ban**
- WhatsApp could ban the account for using an unofficial client. Risk is low
  for personal single-user low-volume usage but non-zero.
- Mitigation: Risk accepted per constitution exception policy. If banned,
  recovery requires WhatsApp's appeal process or pairing a new number.

---

## Notes for Implementation

**Planning phase decisions:**
- Determine how OpenClaw's Baileys channel is configured and how `allowFrom`
  or equivalent DM filtering is set
- Determine where Baileys session credentials are stored and verify persistence
  across restarts
- Confirm how the QR code is surfaced to the user during the login flow

**Pairing:**
- Kent scans the QR code using his personal WhatsApp account
- WhatsApp path: Settings → Linked Devices → Link a Device
- QR codes expire — re-run login command if it times out

---

**END OF SPECIFICATION**
