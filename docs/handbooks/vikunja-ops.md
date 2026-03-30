---
title: Vikunja Operations Runbook
doc_type: handbook
status: draft
---

# Vikunja Operations Runbook

This runbook covers day-to-day operations for the Vikunja task management service running on office2.

## Service Management

Vikunja runs as a Docker container managed by systemd.

**Service name**: `vikunja`
**Container name**: `vikunja`
**Image**: `vikunja/vikunja:0.24.6`
**Port**: `100.92.197.90:3456` (Tailscale IP only)

### Check status

```bash
# As any user (no sudo required):
systemctl status vikunja
docker ps | grep vikunja
```

### Start / Stop / Restart

```bash
# Requires sudo (run as kgale, not claude):
sudo systemctl start vikunja
sudo systemctl stop vikunja
sudo systemctl restart vikunja
```

### View logs

```bash
# systemd journal (no sudo required):
journalctl -u vikunja -f              # follow live
journalctl -u vikunja --since "1 hour ago"
journalctl -u vikunja --since today

# Docker logs (no sudo required):
docker logs vikunja
docker logs vikunja --tail 50 --follow
```

## Data and Backups

### Database location

- **SQLite file**: `/data/services/vikunja/data/vikunja.db`
- **Data directory**: `/data/services/vikunja/data/`
- **Owner**: `kgale:root` (uid 1000:gid 0 — matches container runtime user)

### Backup

Vikunja data is automatically included in the nightly Restic backup because it resides under `/data/services/`, which is already in the backup scope.

- **Backup script**: `/data/services/backup/scripts/backup.sh`
- **Schedule**: Daily at 4AM UTC via claude user's crontab
- **No changes to backup config are needed** — the data path is already covered

### Verify backup

```bash
# List recent snapshots:
restic snapshots --latest 3

# Verify Vikunja data is in the latest snapshot:
restic ls latest /data/services/vikunja/

# Check specific file:
restic ls latest /data/services/vikunja/data/vikunja.db
```

### Manual backup trigger

```bash
# Run the backup script manually (as claude user):
/data/services/backup/scripts/backup.sh
```

## Version Updates

### Current version

The pinned Vikunja version is recorded in two places:

- `scripts/vikunja/vikunja.service` (the `ExecStart` line)
- `scripts/vikunja/deploy.sh` (the `VIKUNJA_IMAGE` variable)

### Update procedure

1. **Check release notes** at the Vikunja releases page for breaking changes
2. **Verify a recent backup exists**: `restic snapshots --latest 1`
3. **Update the version tag** in both `deploy.sh` and `vikunja.service`
4. **Pull the new image**:
   ```bash
   docker pull vikunja/vikunja:<new-version>
   ```
5. **Stop the service** (requires sudo — run as kgale):
   ```bash
   sudo systemctl stop vikunja
   ```
6. **Copy the updated service file** (requires sudo):
   ```bash
   sudo cp scripts/vikunja/vikunja.service /etc/systemd/system/vikunja.service
   sudo systemctl daemon-reload
   ```
7. **Start the service** (requires sudo):
   ```bash
   sudo systemctl start vikunja
   ```
8. **Verify**:
   ```bash
   systemctl status vikunja
   curl -s http://100.92.197.90:3456/api/v1/info | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])"
   ```
9. **Check data is intact** — log in to the web UI and verify tasks are present
10. **Commit and push the version change** to the kg-automation repo

### Rollback

If the new version has issues:

1. Revert the version tag in `deploy.sh` and `vikunja.service` to the previous version
2. Pull the old image: `docker pull vikunja/vikunja:<old-version>`
3. Repeat steps 5-9 above with the old version

## Access and Connectivity

### Web UI URLs

- **From any Tailscale device**: `http://office2:3456`
- **Using Tailscale IP directly**: `http://100.92.197.90:3456`

### Requirements

- Tailscale must be active on the accessing device
- office2 must be running and connected to Tailscale

### iPhone access

1. Ensure the Tailscale app is connected on iPhone
2. Open Safari to `http://100.92.197.90:3456`

### Troubleshooting connectivity

| Symptom | Check | Fix |
|---------|-------|-----|
| Page won't load | `systemctl status vikunja` on office2 | Start service if stopped |
| Connection refused | `ss -tlnp \| grep 3456` on office2 | Verify port binding to `100.92.197.90` |
| Hostname won't resolve | `tailscale status` on both devices | Ensure Tailscale is connected |
| Timeout from iPhone | Tailscale app on iPhone | Open Tailscale app, verify connection |
| Port bound to 0.0.0.0 | `ss -tlnp \| grep 3456` | **Security issue** — stop service, check vikunja.service bind address |

## Goals Project (F006)

The Goals project holds goal declarations — outcome statements with target dates
and evidence criteria. Goals are distinct from tasks: they are anchors, not actions.

### Project Structure

```
Goals                        ← Top-level project (id=11)
├── Intentional: $5K/month consulting income
├── Intentional: $2.5K/month consulting income by Q2
└── Personal: Complete Against the Tide 5K
```

### Identity Labels

| Label | Color | Created By |
| --- | --- | --- |
| personal | #2196f3 (blue) | F001 |
| intentional | #4caf50 (green) | F001 |
| metalcasework | #ff9800 (orange) | F006 |

Every goal task must have exactly one identity label.

### Saved Filters

| Filter | Expression | Sort | Created By |
| --- | --- | --- | --- |
| Today | `due_date >= now/d && due_date < now/d+1d && done = false` | due_date asc | F001 |
| Upcoming | `due_date > now/d && due_date <= now+14d && done = false` | due_date asc | F001 |
| Overdue | `due_date < now/d && done = false` | due_date asc | F001 |
| Goals | `project = 11 && done = false` | due_date asc | F006 |

### Setup Script

```bash
# Verify goals setup:
python3 scripts/vikunja/setup_goals.py --verify-only

# Re-run setup (idempotent):
python3 scripts/vikunja/setup_goals.py
```

See `docs/handbooks/goals-ops.md` for full goal lifecycle operations.

## Security Baseline Reset

After deploying or upgrading Vikunja, the security monitoring baselines on office2 need to be updated to reflect the new expected state.

### Why

The security monitor at `/data/services/security-monitor/` uses baselines to detect unexpected changes. A new or updated Docker container, systemd service, and port binding will trigger alerts unless baselines are refreshed.

### What changes

After a Vikunja deployment or upgrade, the following are new expected state:

- Docker container `vikunja` running
- systemd service `vikunja.service` enabled and active
- Port 3456 listening on `100.92.197.90`

### Baselines location

`/data/services/security-monitor/baselines/`

### Reset procedure

This step may require sudo. Run as kgale if needed:

```bash
# Check current baseline status:
ls -la /data/services/security-monitor/baselines/

# Regenerate baselines (exact command depends on the security monitor setup):
# If using the standard baseline script:
cd /data/services/security-monitor
./scripts/generate-baselines.sh

# Or if manual reset is needed, update the relevant baseline files
# to include the vikunja container, service, and port.
```

### When to reset

- After initial Vikunja deployment (F001)
- After any version update that changes the container image
- After any change to the systemd service file or port binding
