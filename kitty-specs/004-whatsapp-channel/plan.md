# Implementation Plan: WhatsApp Channel

**Branch**: `004-whatsapp-channel` | **Date**: 2026-03-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/004-whatsapp-channel/spec.md`

## Summary

Link the existing Google Voice WhatsApp account to OpenClaw via its native Baileys-based WhatsApp channel. Configure DM access control to accept only Kent's personal number, verify end-to-end messaging (text and voice note), confirm session persistence across restarts, and document the channel in runbook and architecture docs.

This feature is dramatically simpler than originally scoped. OpenClaw already has the WhatsApp channel added and enabled — only QR code linking and access control configuration remain.

## Technical Context

**Language/Version**: Bash (configuration commands), Markdown (runbook, architecture docs)
**Primary Dependencies**: OpenClaw 2026.3.24 (existing), Baileys (bundled with OpenClaw)
**Storage**: Session credentials at `~/.openclaw/credentials/whatsapp/` (managed by OpenClaw)
**Testing**: Manual verification — send messages, check logs, restart service
**Target Platform**: Ubuntu 24.04 LTS on office2
**Project Type**: Configuration + documentation
**Performance Goals**: Messages delivered within 5 seconds, session reconnects within 30 seconds
**Constraints**: No inbound ports, personal DM only, Baileys risk accepted
**Scale/Scope**: Single channel configuration + one runbook + architecture doc updates

## Research Findings

### OpenClaw WhatsApp Architecture (R-001, R-002)

- OpenClaw uses Baileys (outbound WebSocket), not Meta Cloud API
- WhatsApp channel already added and enabled: `not linked, enabled`
- Config already has `dmPolicy: "pairing"`, `groupPolicy: "allowlist"`, `mediaMaxMb: 50`
- Linking requires `openclaw channels login --channel whatsapp` → QR code → Kent scans
- Session persists via `~/.openclaw/credentials/whatsapp/`

### What Was Removed From Scope (R-004, R-006)

- Meta Cloud API app — not used by OpenClaw
- Tailscale Funnel — not needed (Baileys is outbound-only)
- Webhook verification — no webhooks involved
- External credential store entries — Baileys session managed internally by OpenClaw

### DM Access Control (R-003)

- `dmPolicy: "pairing"` already set — requires explicit pairing
- `groupPolicy: "allowlist"` — no group chats by default
- Implementation must configure `allowFrom` with Kent's personal number

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| No inbound ports | Pass | Baileys uses outbound WebSocket only |
| Agent traceability | Pass | `ssh office2-claude` only |
| Documentation adjacent | Pass | Runbook and architecture docs updated |
| No credentials in code | Pass | Baileys session managed by OpenClaw internally |
| Baileys risk accepted | Exception | Unofficial protocol accepted per Kent's decision — documented in spec |

## Project Structure

### Documentation (this feature)

```
kitty-specs/004-whatsapp-channel/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```
docs/handbooks/
└── whatsapp-ops.md      # Operations runbook
```

**Structure Decision**: Configuration-only feature. No scripts or deploy files needed — OpenClaw channel management is done via CLI commands on office2. Only deliverable files are the runbook and architecture doc updates.

## Dependency Graph

```
WP-01: WhatsApp channel linking + DM config + E2E verification (Kent interactive)
  └── WP-02: Ops runbook + architecture docs + session persistence verification
```

WP-01 must complete first (channel must be linked before documentation can capture the actual state). WP-02 follows.

**Key implementation note**: WP-01 requires Kent's interactive participation (QR code scanning). The agent cannot complete this step autonomously.
