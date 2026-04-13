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
| Type | systemd **system** unit (runs as kgale) |
| Unit file | `/etc/systemd/system/obsidian-sync.service` |
| Restart policy | `Restart=always`, `RestartSec=10` |
| Vault path | `/home/kgale/second-brain/notes` |

**Note**: This is a system-level service, not a user unit. It requires `sudo` for management. A `.bak` file exists at the same path with an older vault path — do not use it.

### Commands

```bash
# All commands require kgale account (sudo access)
# Start the service
sudo systemctl start obsidian-sync

# Stop the service
sudo systemctl stop obsidian-sync

# Restart the service
sudo systemctl restart obsidian-sync

# Check service status
sudo systemctl status obsidian-sync
```

### Logs

```bash
# As kgale (needs adm or systemd-journal group):
sudo journalctl -u obsidian-sync -f

# The claude user CANNOT read these logs (no group membership).
# Use the heartbeat monitor instead for agent-accessible health checks.
```

### Boot Persistence

The service is a system unit with `WantedBy=multi-user.target`, so it starts automatically on boot without linger.

## Heartbeat Monitor

A cron-based heartbeat script detects silent sync failures — the scenario where the service is running but not actually pushing changes to cloud.

| Item | Value |
|---|---|
| Script | `scripts/obsidian/sync-heartbeat.py` |
| Cron | Every 30 minutes (claude user) |
| State file | `/tmp/sync-heartbeat-state.json` |
| Heartbeat file | `00-System/sync-heartbeat.md` (in vault) |
| Alert threshold | 3 consecutive failures |
| Alert channel | WhatsApp via `openclaw agent --deliver` |

### Manual check

```bash
python3 scripts/obsidian/sync-heartbeat.py --check-only
```

### What it monitors

1. **Process alive**: Is `ob sync --continuous` running?
2. **Heartbeat freshness**: Is the heartbeat file being updated?
3. **Consecutive failures**: After 3 consecutive checks where the heartbeat is missing or stale, sends a WhatsApp alert.

### Known limitation

The heartbeat monitor runs on office2 and writes to the local vault. It can detect if the process is dead or if the heartbeat file disappears, but it cannot independently verify office2→cloud propagation without a second device. The heartbeat file appearing on your Mac/phone is the visual confirmation that sync is working.

## Status Checks

### Service Status

```bash
sudo systemctl status obsidian-sync
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
systemctl --user list-timers 2>/dev/null | grep second-brain
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
   sudo systemctl restart obsidian-sync
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
   sudo systemctl status obsidian-sync
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
sudo journalctl -u obsidian-sync
```

### After Reboot

1. Verify linger is enabled:
   ```bash
   loginctl show-user kgale | grep Linger
   ```
2. Check the service auto-started:
   ```bash
   sudo systemctl status obsidian-sync
   ```

## Related Documentation

- Quickstart: `kitty-specs/010-obsidian-sync-office2/quickstart.md`
- Architecture: `docs/design/architecture/service-inventory.md`
- Inbox processor: `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`
