---
title: "Obsidian Sync Operations Runbook"
doc_type: handbook
status: approved
---

# Obsidian Sync Operations Runbook

## Overview

This runbook covers the operation and maintenance of Obsidian Sync on office2, including the `ob` CLI for live sync management, git snapshot backup for version history, and the overall vault sync topology:

**Mac <-> Obsidian Cloud <-> office2 <-> iPhone**

All vault data flows through Obsidian Sync as the authoritative live sync mechanism. Git provides a complementary outbound-only snapshot for backup and version history.

## Architecture

### Sync Topology

| Layer | Direction | Path |
|---|---|---|
| Obsidian Sync (live, bidirectional) | Mac <-> Obsidian Cloud <-> office2 <-> iPhone | Real-time vault synchronization |
| Git snapshot (backup, outbound-only) | office2 -> GitHub | 2AM ET daily |

### Consumer

- **felix-admin-capture** reads `/home/kgale/second-brain/vault/00-Inbox/` to process incoming notes and tasks.

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
ob sync-status --path /home/kgale/second-brain/vault
```

### Login Status

```bash
ob login
```

Shows current authentication status when already logged in.

### Timer Status

```bash
systemctl --user list-timers | grep vault
```

### Last Git Snapshot

```bash
cd /home/kgale/second-brain && git log --oneline -1
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
   ob sync-status --path /home/kgale/second-brain/vault
   ```

## Git Coexistence Strategy

| Concern | Approach |
|---|---|
| Live vault state | Obsidian Sync is authoritative |
| Backup/version history | Git periodic snapshot |
| Direction | Outbound-only (add, commit, push — never pulls) |
| Schedule | 2AM ET daily via systemd timer |
| Conflict avoidance | Avoids inbox processing windows (7AM, 12PM, 6PM ET) |
| Exclusions | `.gitignore` excludes workspace and sync metadata |

The git snapshot is strictly one-way. It captures the current vault state and pushes to GitHub. It never pulls from the remote, which prevents git from interfering with Obsidian Sync's conflict resolution.

## Manual Operations

### Manual Sync

```bash
ob sync --path /home/kgale/second-brain/vault
```

### Manual Git Snapshot

```bash
~/helper-scripts/vault-snapshot.sh
```

### Force Re-sync (Last Resort)

If sync is in a broken state and normal restart does not resolve it:

```bash
ob sync-unlink --path /home/kgale/second-brain/vault
ob sync-setup --path /home/kgale/second-brain/vault
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
   ob sync-status --path /home/kgale/second-brain/vault
   ```
3. Check network connectivity from office2.

### Sync Conflict Files

Obsidian Sync may create `.sync-conflict-*` files when the same note is edited on multiple devices simultaneously. Check the vault for these files and resolve manually by comparing versions.

### Service Won't Start

Check the journal for error details:

```bash
journalctl --user -u obsidian-sync
```

### Git Snapshot Fails

- Check available disk space: `df -h /home/kgale/second-brain`
- Check git remote is reachable: `cd /home/kgale/second-brain && git remote -v`
- Check `.gitignore` is not excluding expected files

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
