# Feature Specification: WhatsApp Channel

**Feature Branch**: `004-whatsapp-channel`
**Created**: 2026-03-28
**Status**: Draft
**Input**: F004 func-spec — connect WhatsApp to OpenClaw via Meta Cloud API and Tailscale Funnel

## User Scenarios & Testing *(mandatory)*

### User Story 1 - WhatsApp Number Registration (Priority: P0)

Kent needs a dedicated WhatsApp number registered with Meta Cloud API so the system has an official, permanent communication channel distinct from his personal number.

**Why this priority**: Without a registered number, no messages can flow. This is the prerequisite for everything else.

**Independent Test**: Send an SMS to the Google Voice number and receive it. Meta Cloud API app shows the number as verified and active.

**Acceptance Scenarios**:

1. **Given** the Google Voice number (617) 564-0182 is active, **When** Meta registration is attempted, **Then** an OTP is received via SMS or voice call and registration completes successfully.
2. **Given** the number is registered with Meta, **When** the Meta Business Manager dashboard is checked, **Then** the number appears as active under the WhatsApp Business API.
3. **Given** Meta rejects the Google Voice number (VoIP restriction), **Then** stop and report the issue — a fallback PSTN number will be needed.

---

### User Story 2 - Webhook Endpoint via Tailscale Funnel (Priority: P0)

Kent needs the OpenClaw webhook endpoint on office2 to be reachable by Meta's servers without exposing office2 to the public internet, so that WhatsApp messages can be delivered.

**Why this priority**: Meta requires a publicly reachable HTTPS webhook URL. Without it, no messages are delivered.

**Independent Test**: `curl https://<tailscale-funnel-url>/health` (or equivalent webhook path) responds successfully from outside the Tailscale network.

**Acceptance Scenarios**:

1. **Given** Tailscale Funnel is configured on office2, **When** a request is sent from the public internet to the funnel URL, **Then** it reaches the OpenClaw gateway on `127.0.0.1:18789`.
2. **Given** Tailscale Funnel is running, **When** `ss -tlnp` is checked on office2, **Then** no new publicly exposed inbound ports appear.
3. **Given** Meta sends a GET webhook verification challenge, **Then** the endpoint responds correctly and Meta confirms the webhook.

---

### User Story 3 - End-to-End Message Flow (Priority: P1)

Kent needs to send a WhatsApp message to the dedicated number and receive a reply from OpenClaw, confirming the full bidirectional communication path works.

**Why this priority**: This validates that all infrastructure pieces (number, Meta API, Funnel, OpenClaw) work together.

**Independent Test**: Send a text message from Kent's iPhone WhatsApp to the dedicated number. Receive a reply from OpenClaw.

**Acceptance Scenarios**:

1. **Given** all infrastructure is configured, **When** Kent sends "hello" to the dedicated number, **Then** the message reaches OpenClaw and a reply arrives on Kent's iPhone.
2. **Given** the channel is working, **When** Kent sends a voice note, **Then** the audio payload arrives at OpenClaw (transcription is F003 scope — here we verify arrival only).
3. **Given** OpenClaw is temporarily unavailable, **When** a message is sent, **Then** no silent failure occurs — Meta's retry mechanism handles delivery, and the message arrives when OpenClaw recovers.

---

### User Story 4 - Managed and Documented Service (Priority: P2)

Kent or a future agent needs credentials securely stored, operations documented, and architecture docs updated so the WhatsApp channel is reproducible and maintainable.

**Why this priority**: Operational documentation ensures the channel can be maintained without tribal knowledge.

**Independent Test**: A new agent session can follow the runbook to verify the channel, rotate tokens, and troubleshoot common issues.

**Acceptance Scenarios**:

1. **Given** the runbook exists at `docs/handbooks/whatsapp-ops.md`, **When** an operator reads it, **Then** they can verify the channel, restart services, and rotate tokens.
2. **Given** credentials are in the credential store, **When** checked, **Then** `whatsapp-meta` and `whatsapp-webhook-token` exist with mode 600, claude-owned.

---

### Edge Cases

- What if Meta rejects the Google Voice number? → Stop and report. A fallback PSTN number is needed. Do not attempt workarounds.
- What if Tailscale Funnel is not available on the current Tailscale plan? → Stop and report. Research alternative approaches.
- What if Meta's webhook verification challenge fails? → Check that the funnel URL is correct, that OpenClaw handles the GET challenge, and that the verify token matches.
- What if the Tailscale Funnel URL changes? → The URL is based on the machine's Tailscale hostname and is stable. Document it in the runbook and in `network-topology.json`.
- What if Meta disables the app or webhook? → Follow recovery procedure in the runbook. Re-verify the webhook URL and credentials.
- What if OpenClaw doesn't natively handle Meta's webhook verification? → Planning phase must determine this. If not, a lightweight verification handler may be needed.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | WhatsApp number registration | As Kent, I want the Google Voice number registered with Meta Cloud API so the system has a dedicated WhatsApp identity. | High | Open |
| FR-002 | Meta Cloud API app configuration | As Kent, I want the Meta developer app configured with webhook URL, verify token, and message subscriptions so messages are delivered. | High | Open |
| FR-003 | Credential store entries | As Kent, I want WhatsApp credentials stored securely in the existing credential store (mode 600, claude-owned) so no secrets are in code. | High | Open |
| FR-004 | Tailscale Funnel configuration | As Kent, I want Tailscale Funnel configured on office2 to expose the OpenClaw webhook endpoint publicly without opening inbound ports. | High | Open |
| FR-005 | OpenClaw WhatsApp integration | As Kent, I want OpenClaw configured with the WhatsApp channel so it receives inbound messages and can send replies. | High | Open |
| FR-006 | End-to-end verification | As Kent, I want to verify that a text message and voice note sent from my iPhone reach OpenClaw and a reply comes back. | High | Open |
| FR-007 | Operations runbook | As Kent, I want an ops runbook documenting the WhatsApp channel, Tailscale Funnel, token rotation, and troubleshooting. | Medium | Open |
| FR-008 | Architecture doc updates | As Kent, I want architecture documentation updated to reflect the new Tailscale Funnel ingress pattern and WhatsApp credentials. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Funnel availability | Tailscale Funnel remains available across office2 reboots without manual intervention | Reliability | High | Open |
| NFR-002 | Message delivery latency | WhatsApp messages reach OpenClaw within 5 seconds of being sent (excluding Meta's own delivery latency) | Performance | High | Open |
| NFR-003 | Credential security | No WhatsApp API tokens, verify tokens, or secrets appear in any committed file or log output | Security | High | Open |
| NFR-004 | Webhook response time | Webhook endpoint responds to Meta's verification challenges and message deliveries within 3 seconds | Performance | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | No inbound ports | office2 must not have any new publicly exposed inbound ports after deployment | Security | High | Open |
| C-002 | Official API only | Only Meta Cloud API for WhatsApp integration — no unofficial bridges (whatsapp-web.js, Baileys, etc.) | Security | High | Open |
| C-003 | Agent SSH identity | All commands via `ssh office2-claude`; sudo presented to Kent | Security | High | Open |
| C-004 | Tailscale Funnel ingress | Use Tailscale Funnel for public webhook exposure — no Cloudflare Tunnel, no ngrok, no 0.0.0.0 binding | Architecture | High | Open |
| C-005 | Credential store pattern | Follow F002 credential store pattern at `/data/services/openclaw/secrets/` | Security | High | Open |
| C-006 | Google Voice number | Use existing Google Voice number (617) 564-0182 — do not acquire a new number | Architecture | Medium | Open |

### Key Entities

- **Google Voice Number**: (617) 564-0182 — the dedicated system WhatsApp identity, distinct from Kent's personal number.
- **Meta Cloud API App**: The Meta developer app providing WhatsApp Business API access, webhook configuration, and access tokens.
- **Tailscale Funnel**: Tailscale's built-in feature that serves content from a Tailscale node to the public internet via HTTPS. No additional services or domains needed.
- **OpenClaw Gateway**: The existing OpenClaw instance on `127.0.0.1:18789` that receives webhook messages.
- **Credential Store**: `/data/services/openclaw/secrets/` — existing store from F002, extended with `whatsapp-meta` and `whatsapp-webhook-token`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A WhatsApp text message sent from Kent's iPhone to (617) 564-0182 reaches OpenClaw and a reply arrives within 10 seconds.
- **SC-002**: A WhatsApp voice note sent to the number is received by OpenClaw (audio payload arrives, verified in logs).
- **SC-003**: The Tailscale Funnel URL is reachable from the public internet and responds to requests.
- **SC-004**: `ss -tlnp` on office2 shows no new publicly exposed inbound ports compared to pre-deployment baseline.
- **SC-005**: All WhatsApp credentials exist in the credential store with mode 600, claude-owned, and no secrets in any committed file.
- **SC-006**: Runbook at `docs/handbooks/whatsapp-ops.md` passes CI validation and covers number, Funnel, token rotation, and troubleshooting.
- **SC-007**: Architecture docs reflect Tailscale Funnel as the approved external ingress pattern.
