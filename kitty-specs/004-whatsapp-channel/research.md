# Research: WhatsApp Channel

**Feature**: 004-whatsapp-channel
**Date**: 2026-03-28

## R-001: OpenClaw WhatsApp Integration Architecture

**Decision**: Use OpenClaw's native Baileys-based WhatsApp channel.

**Discovery**: OpenClaw does NOT use Meta Cloud API for WhatsApp. It uses Baileys (unofficial WhatsApp Web protocol library). There is no Meta Cloud API channel available in OpenClaw. This was discovered by reading OpenClaw docs at `https://docs.openclaw.ai/channels/whatsapp`.

**Architecture**:
- Baileys maintains a persistent outbound WebSocket connection to WhatsApp's servers
- Messages arrive via this socket, not via inbound HTTP webhooks
- Authentication is via QR code scan (linked device pairing), not API tokens
- Session credentials stored at `~/.openclaw/credentials/whatsapp/<accountId>/creds.json`
- No inbound ports, no webhook, no Meta app needed

**Risk acceptance**: Baileys is unofficial. Meta could ban the account. This risk is accepted for a personal single-user system at low message volume.

## R-001b: Phone Number — Use Kent's Existing Cell

**Decision**: Use Kent's existing WhatsApp on his personal cell (617) 930-0916. No separate number needed.

**Discovery**: WhatsApp no longer accepts Google Voice (deprecated — not used) (VoIP) numbers for registration. More importantly, a separate number was never required — OpenClaw's Baileys channel links as a "linked device" on an existing WhatsApp account (like WhatsApp Web/Desktop). The original func-spec's assumption of a dedicated number was incorrect.

**Impact**: Removes Google Voice (deprecated — not used) dependency entirely. Kent simply scans the QR code from his existing WhatsApp to link OpenClaw as an additional device.

## R-002: Current OpenClaw WhatsApp Configuration

**Decision**: The WhatsApp channel is already added and enabled — only QR code linking is needed.

**Current state** (discovered via SSH to office2):
- OpenClaw version: 2026.3.24
- `openclaw channels list` shows: `WhatsApp default: not linked, enabled`
- Config at `~/.openclaw/openclaw.json` already has:
  ```json
  "channels": {
    "whatsapp": {
      "enabled": true,
      "dmPolicy": "pairing",
      "selfChatMode": false,
      "groupPolicy": "allowlist",
      "debounceMs": 0,
      "mediaMaxMb": 50
    }
  }
  ```

**What remains**: Run `openclaw channels login --channel whatsapp` to display QR code, Kent scans it, channel is linked.

## R-003: DM Policy and Access Control

**Decision**: Use `dmPolicy: "pairing"` (already configured) and `allowFrom` to restrict to Kent's number.

**OpenClaw DM policies** (from docs):
- `pairing` — requires an explicit pairing step before a user can DM the agent
- `allowlist` — only numbers in the allowlist can DM
- `open` — anyone can DM (not appropriate for personal system)

**Current config**: `dmPolicy: "pairing"` is already set. This means Kent will need to pair (first message initiates pairing, or explicit allowlist). The `groupPolicy: "allowlist"` means no group chats unless explicitly allowed.

**Recommendation**: After linking, configure `allowFrom` with Kent's personal number to lock down access. The exact config field needs to be confirmed via `openclaw channels add --help` or docs.

## R-004: Tailscale Funnel — Not Needed

**Decision**: Tailscale Funnel is NOT needed for F004.

**Rationale**: OpenClaw's Baileys-based WhatsApp channel uses outbound WebSocket connections. There is no inbound webhook that needs to be publicly reachable. Meta's servers never need to reach office2.

**Tailscale Funnel research** (for future reference): office2 runs Tailscale 1.96.2. Funnel is available via `tailscale funnel --bg <port>` and would provide `https://office2.<tailnet>.ts.net`. This may be useful for future features requiring inbound webhooks (e.g., GitHub webhooks).

## R-005: Session Persistence

**Decision**: Baileys sessions persist across OpenClaw restarts.

**How it works**: Baileys stores session credentials in `~/.openclaw/credentials/whatsapp/`. The OpenClaw gateway reconnects automatically on restart with configurable backoff. QR code re-scanning is only needed if the linked device is explicitly unlinked from the phone.

**Reconnection config** (from OpenClaw docs): `reconnect.initialMs` and `reconnect.maxMs` control backoff timing.

## R-006: Meta Cloud API — Removed from Scope

**Decision**: Meta Cloud API is not used. Original constraint C-002 ("official API only") has been removed.

**Original plan**: Register a dedicated number with Meta Business Manager, configure webhook, use Tailscale Funnel for Meta's webhook delivery.

**What changed**: OpenClaw has no Meta Cloud API integration. Baileys is the only WhatsApp path. The constraint was written without knowledge of OpenClaw's actual architecture.

**Credentials impact**: No `whatsapp-meta` or `whatsapp-webhook-token` needed in the external credential store. Baileys session credentials are managed internally by OpenClaw at `~/.openclaw/credentials/whatsapp/`.
