# Feature Specification: WhatsApp Channel

**Feature Branch**: `004-whatsapp-channel`
**Created**: 2026-03-28
**Status**: Draft
**Input**: F004 func-spec — connect WhatsApp to OpenClaw via native Baileys channel

## Architecture Decision: Baileys via OpenClaw Native Channel

During planning research, it was discovered that OpenClaw's WhatsApp integration uses **Baileys** (an unofficial WhatsApp Web protocol library), not Meta Cloud API. OpenClaw has no Meta Cloud API channel at all.

**Decision**: Use OpenClaw's native Baileys-based WhatsApp channel. The original constraint ("official API only") has been **removed** based on the following risk acceptance:

- This is a personal single-user system with low message volume
- Baileys is OpenClaw's only WhatsApp path — there is no official API alternative within OpenClaw
- Account ban risk is acceptable; if Meta bans the account, re-pair is straightforward
- The dramatic simplification (no Tailscale Funnel, no Meta app, no webhook, no separate number) justifies the trade-off

## Architecture Decision: Linked Device on Kent's Existing Number

OpenClaw links as a **linked device** on Kent's existing WhatsApp account (personal cell number). No separate dedicated number is needed.

**Rationale**: WhatsApp no longer accepts Google Voice (VoIP) numbers for registration. More importantly, a separate number was never architecturally required — OpenClaw's Baileys channel operates as a "linked device" on an existing WhatsApp account, just like WhatsApp Web or Desktop.

**What this means**:
- Kent's existing WhatsApp on his personal cell (617) 930-0916 is the account
- OpenClaw links as an additional device via QR code scan
- Messages Kent sends to himself (or that others send to Kent) can be processed by OpenClaw
- Kent interacts with OpenClaw by messaging himself (self-chat) or via a designated contact flow per OpenClaw's DM policy

## User Scenarios & Testing *(mandatory)*

### User Story 1 - WhatsApp Account Pairing (Priority: P0)

Kent needs his existing WhatsApp account linked to OpenClaw as a "linked device" so the system can send and receive messages.

**Why this priority**: Without pairing, no messages can flow. This is the prerequisite for everything else.

**Independent Test**: `openclaw channels list` shows the WhatsApp channel as connected.

**Acceptance Scenarios**:

1. **Given** Kent has WhatsApp on his iPhone with number (617) 930-0916, **When** `openclaw channels login --channel whatsapp` is run, **Then** a QR code is displayed for Kent to scan.
2. **Given** Kent scans the QR code from WhatsApp Linked Devices, **When** pairing completes, **Then** OpenClaw shows the channel as connected.
3. **Given** the channel is paired, **When** office2 reboots, **Then** the session reconnects automatically without re-scanning the QR code.

---

### User Story 2 - End-to-End Message Flow (Priority: P0)

Kent needs to send a WhatsApp message that reaches OpenClaw and receive a reply, confirming the full bidirectional communication path works.

**Why this priority**: This validates that OpenClaw's WhatsApp channel is functional end-to-end.

**Independent Test**: Send a message via WhatsApp that reaches OpenClaw. Receive a reply.

**Acceptance Scenarios**:

1. **Given** the WhatsApp channel is paired and OpenClaw is running, **When** Kent sends a message, **Then** the message reaches OpenClaw and a reply arrives.
2. **Given** the channel is working, **When** Kent sends a voice note, **Then** the audio payload arrives at OpenClaw (transcription is F003 scope — here we verify arrival only).
3. **Given** OpenClaw is temporarily unavailable, **When** a message is sent, **Then** the Baileys session reconnects automatically when OpenClaw restarts.

---

### User Story 3 - Channel Security Configuration (Priority: P1)

Kent needs the WhatsApp channel configured with appropriate DM and group policies so only authorized interactions are processed.

**Why this priority**: Proper access control prevents unintended message processing.

**Independent Test**: OpenClaw's DM policy restricts who can interact. Group messages are ignored.

**Acceptance Scenarios**:

1. **Given** `dmPolicy` is set to `pairing`, **When** an unknown contact messages Kent, **Then** OpenClaw does not process it as a command.
2. **Given** `groupPolicy` is set to `allowlist`, **When** a group message arrives, **Then** OpenClaw does not respond.

---

### User Story 4 - Managed and Documented Service (Priority: P2)

Kent or a future agent needs the channel documented and architecture docs updated so the WhatsApp integration is maintainable.

**Why this priority**: Operational documentation ensures the channel can be maintained without tribal knowledge.

**Independent Test**: A new agent session can follow the runbook to verify the channel, re-pair if needed, and troubleshoot common issues.

**Acceptance Scenarios**:

1. **Given** the runbook exists at `docs/handbooks/whatsapp-ops.md`, **When** an operator reads it, **Then** they can verify the channel status, re-pair if the session drops, and understand the Baileys risk acceptance.
2. **Given** architecture docs are updated, **When** checked, **Then** the WhatsApp channel and Baileys risk acceptance are documented.

---

### Edge Cases

- What if the Baileys session drops and can't reconnect? → Re-pair by running the QR code login flow again. Document in runbook.
- What if Meta bans the account for using Baileys? → Re-pair after any ban is lifted, or accept the limitation. The ban risk is accepted per the architecture decision above.
- What if OpenClaw's Baileys library version has a breaking change? → Pin OpenClaw version. Update only after testing.
- What if Kent unlinks OpenClaw from WhatsApp Linked Devices on his phone? → The linked device session is invalidated. Re-pair needed.
- What if multiple messages arrive while OpenClaw is restarting? → Baileys has reconnection with configurable backoff. Messages sent during downtime may be lost if the WebSocket disconnects. Document this limitation.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | WhatsApp channel linking | As Kent, I want OpenClaw linked as a device on my existing WhatsApp account so it can send and receive messages. | High | Open |
| FR-002 | QR code pairing | As Kent, I want to pair OpenClaw with my WhatsApp via QR code scan. | High | Open |
| FR-003 | DM policy configuration | As Kent, I want the DM policy configured so only authorized interactions are processed. | High | Open |
| FR-004 | Group chat policy | As Kent, I want group messages ignored so OpenClaw only responds to direct messages. | High | Open |
| FR-005 | End-to-end text verification | As Kent, I want to verify that a text message reaches OpenClaw and a reply comes back. | High | Open |
| FR-006 | Voice note arrival verification | As Kent, I want to verify that a voice note arrives at OpenClaw (audio payload, not transcription). | High | Open |
| FR-007 | Session persistence | As Kent, I want the WhatsApp session to survive OpenClaw restarts and office2 reboots without re-scanning the QR code. | High | Open |
| FR-008 | Operations runbook | As Kent, I want an ops runbook documenting the WhatsApp channel, re-pairing procedure, and Baileys risk acceptance. | Medium | Open |
| FR-009 | Architecture doc updates | As Kent, I want architecture documentation updated to reflect the WhatsApp channel integration. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Session reconnection | WhatsApp session reconnects automatically after OpenClaw restart within 30 seconds | Reliability | High | Open |
| NFR-002 | Message delivery latency | WhatsApp messages reach OpenClaw within 5 seconds of being sent | Performance | High | Open |
| NFR-003 | Credential security | Baileys session credentials stored by OpenClaw are not exposed in committed files or log output | Security | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | No inbound ports | office2 must not have any new publicly exposed inbound ports (Baileys uses outbound WebSocket only) | Security | High | Open |
| C-002 | Agent SSH identity | All commands via `ssh office2-claude`; sudo presented to Kent | Security | High | Open |
| C-003 | DM policy enforcement | DM and group policies must be configured to prevent unintended message processing | Security | High | Open |
| C-004 | Baileys risk accepted | Baileys (unofficial WhatsApp Web protocol) is accepted for this personal system despite account-ban risk | Architecture | Medium | Open |

### Key Entities

- **Kent's WhatsApp Account**: (617) 930-0916 — Kent's personal cell, existing WhatsApp account. OpenClaw links as an additional device.
- **OpenClaw WhatsApp Channel**: OpenClaw's native Baileys-based WhatsApp integration, configured via `openclaw channels add/login`.
- **Baileys Session**: The WebSocket session credentials stored at `~/.openclaw/credentials/whatsapp/` on office2, maintaining the linked-device pairing.
- **OpenClaw Gateway**: The existing OpenClaw instance on `127.0.0.1:18789` that processes messages.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A WhatsApp message reaches OpenClaw and a reply arrives within 10 seconds.
- **SC-002**: A WhatsApp voice note is received by OpenClaw (audio payload arrives, verified in logs).
- **SC-003**: The WhatsApp session survives an OpenClaw restart and reconnects within 30 seconds.
- **SC-004**: `ss -tlnp` on office2 shows no new publicly exposed inbound ports compared to pre-deployment baseline.
- **SC-005**: DM and group policies are configured per OpenClaw's channel settings.
- **SC-006**: Runbook at `docs/handbooks/whatsapp-ops.md` passes CI validation and covers pairing, re-pairing, session management, and Baileys risk acceptance.
- **SC-007**: Architecture docs reflect the WhatsApp channel integration and Baileys risk acceptance.
