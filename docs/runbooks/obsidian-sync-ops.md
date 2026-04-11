---
title: "Obsidian Sync Operations Runbook"
doc_type: runbook
audience: agents
status: approved
---

# Obsidian Sync Operations Runbook

## Overview

This runbook covers the operation and maintenance of Obsidian Sync on office2, including the `ob` CLI for live sync management and the overall vault sync topology:

**Mac <-> Obsidian Cloud <-> office2 <-> iPhone**

All vault data flows through Obsidian Sync as the authoritative live sync mechanism. Non-vault content (agents/, logs/) is synced separately via `second-brain-sync.timer` (bidirectional git, every 15 min).

## Architecture

### Sync Topology

| Layer | Direction | Path |
|---|---|---|
| Obsidian Sync (live, bidirectional) | Mac <-> Obsidian Cloud <-> office2 <-> iPhone | Real-time vault synchronization |

### Consumer

- **felix-admin-capture** reads `/home/kgale/second-brain/notes/01-Inbox/` to process incoming notes and tasks. After processing, items move to `/home/kgale/second-brain/notes/02-Inbox-Processed/` (consumed by the inbox pre-scan helper planned in #149).

## Service Configuration

| Item | Value |
|---|---|
| Service | `obsidian-sync.service` |
| Type | systemd user unit (kgale) |
| Unit file | `~/.config/systemd/user/obsidian-sync.service` |

### Commands

```bash
# Start the service
systemctl --user start obsidian-sync

# Stop the service
systemctl --user stop obsidian-sync

# Restart the service
systemctl --user restart obsidian-sync

# Check service status
systemctl --user status obsidian-sync
```

### Logs

```bash
journalctl --user -u obsidian-sync -f
```

### Boot Persistence

The service must survive reboots without a login session. This requires linger to be enabled:

```bash
loginctl enable-linger kgale
```

## Status Checks

### Service Status

```bash
systemctl --user status obsidian-sync
```

### Sync Status

```bash
ob sync-status --path /home/kgale/second-brain/notes
```

### Login Status

```bash
ob login
```

Shows current authentication status when already logged in.

### Git Sync Timer Status

```bash
systemctl --user list-timers | grep second-brain
```

## Re-authentication

**When**: `ob sync-status` shows an authentication error.

**How**:

1. Log in again (must run as kgale user):
   ```bash
   ob login --email <email>
   ```
   Password and MFA will be prompted interactively.

2. Restart the sync service:
   ```bash
   systemctl --user restart obsidian-sync
   ```

3. Verify sync is healthy:
   ```bash
   ob sync-status --path /home/kgale/second-brain/notes
   ```

## Manual Operations

### Manual Sync

```bash
ob sync --path /home/kgale/second-brain/notes
```

### Force Re-sync (Last Resort)

If sync is in a broken state and normal restart does not resolve it:

```bash
ob sync-unlink --path /home/kgale/second-brain/notes
ob sync-setup --path /home/kgale/second-brain/notes
```

This unlinks and re-links the vault to Obsidian Sync. Use only when other troubleshooting steps have failed.

## Troubleshooting

### Note Not Appearing on office2

1. Check the service is running:
   ```bash
   systemctl --user status obsidian-sync
   ```
2. Check sync status for errors:
   ```bash
   ob sync-status --path /home/kgale/second-brain/notes
   ```
3. Check network connectivity from office2.

### Sync Conflict Files

Obsidian Sync may create `.sync-conflict-*` files when the same note is edited on multiple devices simultaneously. Check the vault for these files and resolve manually by comparing versions.

### Service Won't Start

Check the journal for error details:

```bash
journalctl --user -u obsidian-sync
```

### After Reboot

1. Verify linger is enabled:
   ```bash
   loginctl show-user kgale | grep Linger
   ```
2. Check the service auto-started:
   ```bash
   systemctl --user status obsidian-sync
   ```

## Related Documentation

- Quickstart: `kitty-specs/010-obsidian-sync-office2/quickstart.md`
- Architecture: `docs/design/architecture/service-inventory.md`
- Inbox processor: `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`
