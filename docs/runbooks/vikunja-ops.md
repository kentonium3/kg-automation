---
title: Vikunja Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# Vikunja Operations Runbook

This runbook covers day-to-day operations for the Vikunja task management service running on office2.

## Service Management

Vikunja runs as a Docker container managed by systemd.

**Service name**: `vikunja`
**Container name**: `vikunja`
**Image**: selected by `services/vikunja/docker-compose.yml`. It is `vikunja/vikunja:2.4.0` until the #1087 cutover, then `office2.local/vikunja:active` (see [Version Updates](#version-updates))
**Port**: `100.92.197.90:3456` (Tailscale IP only)

### Check status

```bash
# As any user (no sudo required):
systemctl status vikunja
docker ps | grep vikunja
```

### Start / Stop / Restart

**Kent only** (`sudo`, as `kgale` through `ssh office2-kgale`; agents never run these):

```bash
# Kent: requires sudo (run as kgale, not claude):
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

Rewritten 2026-10-30 for #1087. The earlier procedure edited the version
in `vikunja.service` and `deploy.sh`, pulled from Docker Hub and restarted
the service with `sudo`. None of that matches how the service runs now.

### Where the image is selected

- `vikunja.service` is a system oneshot (`User=claude`). Its start runs
  `docker compose -f /home/claude/kg-automation/services/vikunja/docker-compose.yml up -d`
  and its stop runs `... down`, with no `-p`. The unit does not name an
  image.
- The image is selected only by the `image:` line in
  `services/vikunja/docker-compose.yml`. The felix-deployer pulls `main`
  into `/home/claude/kg-automation`, so a merged Compose change is live in
  that file at once. The next start uses it.
- From the #1087 cutover onwards, Compose selects the local indirection tag
  `office2.local/vikunja:active` with `pull_policy: never`. The tag is
  moved only by the release entrypoints and the rollback helper. A missing
  tag makes `compose up -d` fail closed and never pull. Until the ACTIVATE
  merge, Compose still names `vikunja/vikunja:2.4.0`.
- The release being deployed is pinned, with every identity, in
  `services/vikunja/release.json`.

`scripts/vikunja/deploy.sh` is **legacy**. It always pulls a registry
image, cannot select an image archive, and has no dry-run/apply contract.
Do not use it to change the version.

### Upgrade route: STAGE, ACTIVATE, rollback

An image change goes through the manifest pipeline in two reviewed merges.
Each merge is Kent's.

The agent steps on office2, and the ingress, are run only by the Claude Code
session through its own account `ssh office2-claude`. Codex sessions only
review locally, and `office2-kgale` is for Kent's steps only.

1. **Ingress** (agent): `scripts/vikunja/stage_release_archive.py` copies
   the image archive and the rollback archive from office4 into a
   create-only, 0700 folder under `/data/services/vikunja/release-artifacts/`,
   through `ssh office2-claude`.
2. **STAGE** (Kent merges; the deployer applies): `deploys/queued/vikunja-release-stage.yaml`
   runs `scripts/deploy/deploy-vikunja-release-stage.py`. It loads and
   verifies the archive and tags the release. It also creates
   `office2.local/vikunja:active` pointing at the running image when that tag
   is absent. It is inert: no container or Compose change.
3. **ACTIVATE** (Kent's explicit go; the deployer applies): the Compose
   change plus `deploys/queued/vikunja-release-activate.yaml`. It runs
   `scripts/deploy/deploy-vikunja-release-activate.py` once, behind a durable
   marker. The run stops the service, takes the write-boundary DB snapshot,
   points `active` at the release, starts it and verifies it, all within a
   300 s outage deadline.
4. **Rollback** (only on failure): `scripts/vikunja/rollback_release.py`
   runs through `ssh office2-claude` in two phases, `--prepare` then
   `--finish`. Between them Kent restores the snapshot with `sudo` through
   `ssh office2-kgale`. The guard refuses to start the old image on a
   migrated DB.

The full procedure has every command, the expected output, the acceptance
step, the cancel and retry paths and the error codes. It is in
[Vikunja Release Cutover](<./vikunja-release-cutover.md>).

## Access and Connectivity

### Web UI URLs

- **Canonical URL (HTTPS)**: `https://office2.tail0f5f56.ts.net`
- **Tailscale Serve**: TLS terminated by Tailscale Serve on port 443, proxied to `http://100.92.197.90:3456`

### Tailscale Serve Configuration

Tailscale Serve proxies HTTPS on port 443 to the Vikunja container. The proxy
target must be `http://100.92.197.90:3456` (Tailscale IP), **not** `localhost:3456`,
because the Docker container is bound to the Tailscale IP only — it does not
listen on localhost.

**Kent only.** These commands use `sudo` through `ssh office2-kgale`. Agents
never run them; an agent that needs the serve config changed asks Kent.

```bash
# Kent: view current serve config:
ssh office2-kgale 'sudo tailscale serve status'

# Kent: set or reset the proxy target:
ssh office2-kgale 'sudo tailscale serve --bg https+insecure://100.92.197.90:3456'
```

The UFW firewall must allow port 443 on the tailscale0 interface. This rule is
included in `scripts/office2/security-monitor/configure-ufw.sh`.

### Requirements

- Tailscale must be active on the accessing device
- office2 must be running and connected to Tailscale

### iPhone access

1. Ensure the Tailscale app is connected on iPhone
2. Open Safari to `https://office2.tail0f5f56.ts.net`

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

### Project Structure (F006 Goals project — RETIRED)

> The F006 Goals Vikunja project (formerly top-level id=11) was **deleted in the
> #717/#714 reorg**. The structure below is historical (F006 v1); the
> goal-declaration concept now lives in the separate steering-wheel design effort.

```
Goals                        ← Top-level project (id=11) — DELETED (#717)
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
| ~~Goals~~ (RETIRED #717) | ~~`project = 11 && done = false`~~ — project deleted | — | F006 |

### Setup Script

```bash
# Verify goals setup:
python3 scripts/vikunja/setup_goals.py --verify-only

# Re-run setup (idempotent):
python3 scripts/vikunja/setup_goals.py
```

See `docs/runbooks/goals-ops.md` for full goal lifecycle operations.

## Vikunja API Skill (F007)

The Vikunja API skill teaches OpenClaw agents how to interact with Vikunja's
REST API for task management.

### Skill Locations

- **Source in repo**: `scripts/openclaw/skills/vikunja-api/SKILL.md`
- **Deployed on office2**: `~/.openclaw/skills/vikunja-api/SKILL.md`
- **API base URL**: `https://office2.tail0f5f56.ts.net/api/v1`

### Update Skill on office2

After editing the SKILL.md in the repo, copy it to office2:

```bash
ssh office2-claude "cat > ~/.openclaw/skills/vikunja-api/SKILL.md" \
  < scripts/openclaw/skills/vikunja-api/SKILL.md
```

The skills watcher should pick up changes automatically. If not:

```bash
ssh office2-claude "openclaw gateway restart"
```

### Verify Skill

```bash
ssh office2-claude "openclaw skills list" | grep vikunja
ssh office2-claude "openclaw skills info vikunja_api"
```

### API Token

- **Token location**: `/data/services/openclaw/secrets/vikunja-api` (mode 600)
- **Token name in Vikunja**: `openclaw-agent`
- **Rotation**: See the API Token section in openclaw-ops.md

### Troubleshooting

| Symptom | Check | Fix |
| --- | --- | --- |
| Skill not in skills list | `ls ~/.openclaw/skills/vikunja-api/SKILL.md` | Re-deploy, restart gateway |
| 401 auth errors | Token file exists and is non-empty | Rotate token (see openclaw-ops.md) |
| Connection errors | Vikunja running? `systemctl status vikunja` | Start service |
| Wrong API URL | Check SKILL.md base URL | Should be `https://office2.tail0f5f56.ts.net/api/v1` |

## Security baseline trigger

A Vikunja change updates surfaces the audit watches, so the security
baselines on office2 need to be regenerated afterwards. What changes:

- Docker container `vikunja` running (or its image SHA after upgrade)
- systemd service `vikunja.service` enabled and active
- Port 3456 listening on `100.92.197.90`

Run the reset:

- After initial Vikunja deployment (F001)
- After any version update that changes the container image
- After any change to the systemd service file or port binding

For the procedure, see [Security Baseline Operations](<./security-baseline-ops.md>).
