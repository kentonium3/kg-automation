---
title: WhatsApp Channel Operations Runbook
doc_type: runbook
audience: agents_and_humans
status: draft
---

# WhatsApp Channel Operations Runbook

This runbook covers operations for the WhatsApp channel connected to OpenClaw on office2.

## Channel Overview

OpenClaw's WhatsApp integration uses **Baileys** (unofficial WhatsApp Web protocol). The channel operates as a "linked device" on Kent's existing WhatsApp account — the same mechanism as WhatsApp Web or Desktop.

**Account**: Kent's personal cell (617) 930-0916
**Protocol**: Baileys (outbound WebSocket — no inbound ports)
**Authentication**: QR code linked-device pairing
**Session storage**: `~/.openclaw/credentials/whatsapp/` on office2
**DM policy**: `pairing` — requires explicit pairing before DM accepted
**Group policy**: `allowlist` — no group chats by default
**Media max**: 50MB
**Deployed by**: F004

## Verify Channel Status

```bash
ssh office2-claude

# Quick check
openclaw channels list

# Detailed probe (checks gateway connectivity)
openclaw channels status --probe
```

Expected output when healthy: `WhatsApp default: enabled, configured, linked, running, connected, dm:pairing`

## Re-pairing (if session drops)

If the channel shows "not linked" or "disconnected":

```bash
# Start the QR code login flow
openclaw channels login --channel whatsapp
```

Kent must scan the QR code from WhatsApp on iPhone:
1. Open WhatsApp → Settings → Linked Devices → Link a Device
2. Scan the QR code displayed in the terminal
3. Verify: `openclaw channels list` shows "linked, enabled"

If the gateway doesn't pick up the new session immediately:
```bash
systemctl --user restart openclaw-gateway
```

## Session Management

- Sessions survive OpenClaw restarts automatically (credentials stored on disk)
- Session may drop if:
  - Kent unlinks the device from WhatsApp on iPhone (Settings → Linked Devices → remove)
  - Baileys library update in a new OpenClaw version
  - WhatsApp account ban (see Risk Acceptance below)
  - Extended network outage

To check session files:
```bash
ls -la ~/.openclaw/credentials/whatsapp/
```

## Log Viewing

```bash
# Follow live logs
journalctl --user -u openclaw-gateway -f

# WhatsApp-specific logs
journalctl --user -u openclaw-gateway --since "1 hour ago" | grep -i whatsapp

# Recent startup logs
journalctl --user -u openclaw-gateway --since "5 minutes ago"
```

## Configuration

Channel config is in `~/.openclaw/openclaw.json` under `channels.whatsapp`:

```json
{
  "enabled": true,
  "dmPolicy": "allowlist",
  "allowFrom": ["+16179300916"],
  "selfChatMode": true,
  "groupPolicy": "allowlist",
  "groupAllowFrom": ["+16179300916"],
  "mediaMaxMb": 50
}
```

(As deployed 2026-11-23, #1122. This block previously showed `dmPolicy:
"pairing"`, which was retired on 2026-03-31 because it sent pairing codes to
anyone who messaged the number.)

**`selfChatMode` must be `true`.** The linked account is Kent's own number, so
every Kent→Felix DM is a *from-me* message (`+16179300916 -> +16179300916`).

- **Why it was `false`:** it was set that way from the first WhatsApp mission
  to avoid echoes.
- **What changed:** `@openclaw/whatsapp` 2026.7.1 ignored it for same-number
  DMs, but 2026.11.7 enforces it. With `false`, every DM is dropped silently:
  the channel still reports connected and healthy, the web heartbeat shows
  `messagesHandled: 0`, and nothing is logged.
- **Echoes:** with `true`, Felix's own reply comes back once as an input and the
  session controller rejects it (`source-claim: failed`), so no loop occurs. If
  Felix ever starts answering its own messages, this setting is the first
  suspect.

To change a setting, use the CLI (it validates the value), then restart:

```bash
/home/claude/.local/bin/openclaw config set channels.whatsapp.<key> <value>
/home/claude/.local/bin/openclaw config validate
systemctl --user restart openclaw-gateway
```

This is an out-of-band change to `openclaw.json`, an audited surface. Rebaseline
`openclaw-config.txt` afterwards per
[`security-baseline-ops.md`](<./security-baseline-ops.md>).

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| Messages not arriving | `openclaw channels status --probe` | Re-pair if disconnected, restart gateway |
| Channel shows "not linked" | Session credentials missing | Re-run QR login flow |
| Channel shows "stopped" | Gateway may need restart | `systemctl --user restart openclaw-gateway` |
| Media not arriving | Check `mediaMaxMb` setting | Increase value in config if needed |
| Gateway not running | `systemctl --user status openclaw-gateway` | `systemctl --user start openclaw-gateway` |

## Baileys Risk Acceptance

OpenClaw uses Baileys (unofficial WhatsApp Web protocol). This is the **only** WhatsApp integration path available in OpenClaw — there is no Meta Cloud API channel.

**Accepted risks**:
- Meta could ban the account at any time for using unofficial clients
- Baileys protocol may break if WhatsApp changes their internal API

**Mitigations**:
- Personal single-user system at low message volume minimizes detection risk
- If banned: re-pair after any ban is lifted
- Pin OpenClaw version to avoid unexpected Baileys updates

**Policy exception**: Documented in `docs/design/architecture/security-posture.md` under Policy Exceptions.
