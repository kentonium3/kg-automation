# Feature Specification: WhatsApp Channel

**Feature Branch**: `004-whatsapp-channel`
**Created**: 2026-03-28
**Status**: Draft
**Input**: F004 func-spec — connect WhatsApp to OpenClaw via native Baileys channel

## Architecture Decision: Baileys via OpenClaw Native Channel

During planning research, it was discovered that OpenClaw's WhatsApp integration uses **Baileys** (an unofficial WhatsApp Web protocol library), not Meta Cloud API. OpenClaw has no Meta Cloud API channel at all.

**Decision**: Use OpenClaw's native Baileys-based WhatsApp channel. The original constraint C-002 ("official API only") has been **removed** based on the following risk acceptance:

- This is a personal single-user system with low message volume
- Baileys is OpenClaw's only WhatsApp path — there is no official API alternative within OpenClaw
- Account ban risk is acceptable; if Meta bans the number, a new number can be paired
- The dramatic simplification (no Tailscale Funnel, no Meta app, no webhook, no dedicated number registration) justifies the trade-off

**What this changes from the original func-spec**:
- No Meta Cloud API app needed
- No Tailscale Funnel needed (Baileys uses outbound WebSocket, not inbound webhook)
- No webhook verification challenge to handle
- No dedicated number registration with Meta Business Manager
- Authentication is via QR code scan, not API tokens
- Session credentials are managed by OpenClaw internally, not in the external credential store

## User Scenarios & Testing *(mandatory)*

### User Story 1 - WhatsApp Account Pairing (Priority: P0)

Kent needs the Google Voice WhatsApp account paired with OpenClaw so the system can send and receive messages on the dedicated number.

**Why this priority**: Without pairing, no messages can flow. This is the prerequisite for everything else.

**Independent Test**: `openclaw channels list` shows the WhatsApp channel as connected. A test message sent to the number reaches OpenClaw.

**Acceptance Scenarios**:

1. **Given** the Google Voice number (617) 564-0182 has an active WhatsApp account, **When** `openclaw channels login --channel whatsapp` is run, **Then** a QR code is displayed for Kent to scan.
2. **Given** Kent scans the QR code with the Google Voice WhatsApp app, **When** pairing completes, **Then** OpenClaw shows the channel as connected.
3. **Given** the channel is paired, **When** office2 reboots, **Then** the session reconnects automatically without re-scanning the QR code.

---

### User Story 2 - End-to-End Message Flow (Priority: P0)

Kent needs to send a WhatsApp message to the dedicated number and receive a reply from OpenClaw, confirming the full bidirectional communication path works.

**Why this priority**: This validates that OpenClaw's WhatsApp channel is functional end-to-end.

**Independent Test**: Send a text message from Kent's personal iPhone WhatsApp to (617) 564-0182. Receive a reply from OpenClaw.

**Acceptance Scenarios**:

1. **Given** the WhatsApp channel is paired and OpenClaw is running, **When** Kent sends "hello" to the dedicated number, **Then** the message reaches OpenClaw and a reply arrives on Kent's iPhone.
2. **Given** the channel is working, **When** Kent sends a voice note, **Then** the audio payload arrives at OpenClaw (transcription is F003 scope — here we verify arrival only).
3. **Given** OpenClaw is temporarily unavailable, **When** a message is sent, **Then** the Baileys session reconnects automatically when OpenClaw restarts and queued messages are delivered.

---

### User Story 3 - Channel Security Configuration (Priority: P1)

Kent needs the WhatsApp channel configured to only accept messages from his personal number and ignore all other senders, preventing unauthorized access to the system.

**Why this priority**: Without DM filtering, anyone who discovers the number could send commands to OpenClaw.

**Independent Test**: A message from an unknown number is ignored by OpenClaw. Only messages from Kent's personal number are processed.

**Acceptance Scenarios**:

1. **Given** `allowFrom` is configured with Kent's personal number, **When** a message arrives from an unknown number, **Then** OpenClaw ignores it.
2. **Given** `dmPolicy` is set appropriately, **When** Kent messages the number, **Then** OpenClaw processes the message normally.
3. **Given** `groupPolicy` is set to ignore, **When** the number is added to a group chat, **Then** OpenClaw does not respond to group messages.

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
- What if Meta bans the Google Voice number for using Baileys? → Pair a new number. The ban risk is accepted per the architecture decision above.
- What if OpenClaw's Baileys library version has a breaking change? → Pin OpenClaw version. Update only after testing.
- What if the Google Voice WhatsApp account is logged out on all devices? → The QR code pairing acts as a "linked device." If Kent logs out on the phone, the linked device session may be invalidated. Re-pair needed.
- What if multiple messages arrive while OpenClaw is restarting? → Baileys has reconnection with configurable backoff. Messages sent during downtime may be lost if the WebSocket disconnects. Document this limitation.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | WhatsApp channel addition | As Kent, I want the WhatsApp channel added to OpenClaw so it can send and receive messages. | High | Open |
| FR-002 | QR code pairing | As Kent, I want to pair the Google Voice WhatsApp account with OpenClaw via QR code so the channel is authenticated. | High | Open |
| FR-003 | DM filtering | As Kent, I want only my personal number accepted by OpenClaw so unauthorized senders are ignored. | High | Open |
| FR-004 | Group chat policy | As Kent, I want group messages ignored so OpenClaw only responds to direct messages. | High | Open |
| FR-005 | End-to-end text verification | As Kent, I want to verify that a text message sent from my iPhone reaches OpenClaw and a reply comes back. | High | Open |
| FR-006 | Voice note arrival verification | As Kent, I want to verify that a voice note sent from my iPhone arrives at OpenClaw (audio payload, not transcription). | High | Open |
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
| C-003 | Personal DM only | Only direct messages from Kent's personal number are processed — no group chats, no unknown senders | Security | High | Open |
| C-004 | Google Voice number | Use existing Google Voice number (617) 564-0182 — do not acquire a new number | Architecture | Medium | Open |
| C-005 | Baileys risk accepted | Baileys (unofficial WhatsApp Web protocol) is accepted for this personal system despite account-ban risk | Architecture | Medium | Open |

### Key Entities

- **Google Voice Number**: (617) 564-0182 — the dedicated system WhatsApp identity, distinct from Kent's personal number.
- **OpenClaw WhatsApp Channel**: OpenClaw's native Baileys-based WhatsApp integration, configured via `openclaw channels add/login`.
- **Baileys Session**: The WebSocket session credentials stored at `~/.openclaw/credentials/whatsapp/` on office2, maintaining the linked-device pairing.
- **OpenClaw Gateway**: The existing OpenClaw instance on `127.0.0.1:18789` that processes messages.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A WhatsApp text message sent from Kent's iPhone to (617) 564-0182 reaches OpenClaw and a reply arrives within 10 seconds.
- **SC-002**: A WhatsApp voice note sent to the number is received by OpenClaw (audio payload arrives, verified in logs).
- **SC-003**: The WhatsApp session survives an OpenClaw restart and reconnects within 30 seconds.
- **SC-004**: `ss -tlnp` on office2 shows no new publicly exposed inbound ports compared to pre-deployment baseline.
- **SC-005**: Messages from unknown numbers are ignored by OpenClaw (only Kent's personal number is accepted).
- **SC-006**: Runbook at `docs/handbooks/whatsapp-ops.md` passes CI validation and covers pairing, re-pairing, session management, and Baileys risk acceptance.
- **SC-007**: Architecture docs reflect the WhatsApp channel integration and Baileys risk acceptance.
