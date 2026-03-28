# Data Model: WhatsApp Channel

**Feature**: 004-whatsapp-channel
**Date**: 2026-03-28

## Overview

No new data models created. This feature configures an existing OpenClaw channel and manages its session state.

## OpenClaw WhatsApp Channel Entities (existing, documented for reference)

### Channel Configuration

Stored in `~/.openclaw/openclaw.json` under `channels.whatsapp`:

| Field | Type | Current Value | Description |
|-------|------|---------------|-------------|
| enabled | boolean | true | Channel is active |
| dmPolicy | string | "pairing" | Requires explicit pairing before DM accepted |
| selfChatMode | boolean | false | Don't respond to messages from self |
| groupPolicy | string | "allowlist" | Only respond in explicitly allowed groups |
| debounceMs | number | 0 | No message debouncing |
| mediaMaxMb | number | 50 | Maximum media file size in MB |

### Session Credentials

Stored at `~/.openclaw/credentials/whatsapp/<accountId>/creds.json` (managed by OpenClaw, not the external credential store):

| Field | Type | Description |
|-------|------|-------------|
| Session keys | object | Baileys WebSocket session keys |
| Account ID | string | WhatsApp account identifier |
| Phone number | string | Paired phone number |

### File System Artifacts

```
/home/claude/.openclaw/
├── openclaw.json                          # Channel config (already exists)
└── credentials/
    └── whatsapp/
        └── <accountId>/
            └── creds.json                 # Baileys session (created during pairing)
```
