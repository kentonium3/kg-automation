# Quickstart: WhatsApp Channel

**Feature**: 004-whatsapp-channel
**Date**: 2026-03-28

## Prerequisites

- office2 running with OpenClaw 2026.3.24 (F002 complete)
- Google Voice number (617) 564-0182 with active WhatsApp account
- Kent available to scan QR code from WhatsApp on iPhone
- SSH access via `ssh office2-claude`

## Steps

### 1. Verify OpenClaw WhatsApp Channel Status

```bash
ssh office2-claude
openclaw channels list
# Expected: "WhatsApp default: not linked, enabled"
openclaw channels status
```

### 2. Configure DM Access Control

```bash
# Update config to restrict access to Kent's personal number
# Exact config field TBD during implementation — check openclaw channels add --help
```

### 3. Link WhatsApp Account (Kent Interactive)

```bash
# This displays a QR code — Kent scans it from WhatsApp on iPhone
openclaw channels login --channel whatsapp
```

### 4. Verify Pairing

```bash
openclaw channels list
# Expected: "WhatsApp default: linked, enabled"
openclaw channels status --deep
```

### 5. End-to-End Test

- [ ] Kent sends "hello" from personal WhatsApp to (617) 564-0182
- [ ] OpenClaw receives the message (check logs)
- [ ] OpenClaw sends a reply
- [ ] Kent receives the reply on iPhone
- [ ] Kent sends a voice note
- [ ] OpenClaw receives the audio payload (check logs)

### 6. Verify Session Persistence

```bash
# Restart OpenClaw and confirm reconnection
systemctl --user restart openclaw-gateway
# Wait 30 seconds
openclaw channels status --deep
# Expected: still linked
```

### 7. Verify No New Ports

```bash
ss -tlnp | grep -E '(3456|18789|8787)'
# All three should show same bindings as before — no new ports
```
