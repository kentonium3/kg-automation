---
id: agent-prompt-sync-ops
doc_type: runbook
title: Agent prompt sync — operator runbook
status: active
level: howto
owners: ["kgale"]
last_validated: 2026-06-08
version: 1.0
---

# Agent prompt sync — operator runbook

Operator-facing runbook for the agent-prompt deploy pipeline (`agent-prompt-sync`).
Mission: `agent-prompt-deploy-pipeline-01KTMDDD` (closes #567).

## What this pipeline does

Every 5 minutes on office2, a user-level systemd timer fires a Python helper
that:

1. Runs `git fetch && git pull --ff-only origin main` inside `/home/claude/kg-automation`
2. Reads `docs/design/architecture/data/service-inventory.json` to discover Felix agents
3. For each in-scope agent file (`AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`), MD5-compares the repo source against the deployed copy under `/data/services/openclaw/<deploy-dir>/`
4. Atomically copies any drifted file (preserving mode)
5. Appends structured audit records to `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`

No openclaw restart is triggered. Running agents pick up the new prompt at
their next session-init (next cron tick).

## First-time install (one-time, post-mission-merge)

```bash
ssh office2-claude
cd ~/kg-automation
git pull --ff-only origin main
git log -1 --oneline  # should match the merge commit on Mac

mkdir -p ~/.config/systemd/user
cp scripts/openclaw/deploy/agent-prompt-sync.service ~/.config/systemd/user/
cp scripts/openclaw/deploy/agent-prompt-sync.timer   ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now agent-prompt-sync.timer
systemctl --user list-timers | grep agent-prompt-sync
```

Expected output of the last command:

```
NEXT                          LEFT    LAST  PASSED  UNIT                       ACTIVATES
Mon 2026-06-08 20:21:31 UTC   4m 30s  -     -       agent-prompt-sync.timer    agent-prompt-sync.service
```

## Verify first tick (within 5 minutes of install)

```bash
journalctl --user -u agent-prompt-sync.service --since "10 min ago" --no-pager
tail -50 /data/services/openclaw/deploy/agent-prompt-sync.jsonl
```

Expected journal: one line per tick showing exit status 0 and duration <2s.

Expected audit-log content for the first tick post-#558/#561 deploy debt:

- One `copy` entry for `felix-admin-capture/AGENTS.md` (the stranded 1215-line update from `inbox-calendar-and-aspiration-routing-01KTHHXS`)
- One `copy` entry for `felix-admin-habits/AGENTS.md` (the stranded #561 Hard Rules)
- `skip` entries for all other files
- One `tick_summary` entry showing `files_copied >= 2`

Spot-check deployed files match repo:

```bash
md5sum /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-capture/AGENTS.md \
       /data/services/openclaw/inbox-agent/AGENTS.md

md5sum /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-habits/AGENTS.md \
       /data/services/openclaw/habits-agent/AGENTS.md
```

Both md5s should match. If they differ, see Troubleshooting below.

## Operator actions

### Manual trigger (skip the timer wait)

```bash
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts
```

Or trigger via systemd (functionally equivalent):

```bash
systemctl --user start agent-prompt-sync.service
```

### Dry-run (preview drift without modifying anything)

```bash
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts --dry-run
```

Prints one `DRIFT <slug> <filename> src_md5=<hex> dst_md5=<hex|absent>` line
per drift-candidate file. Zero output = everything is in sync. Audit log is
NOT written. Deployed files are NOT modified. `git pull` is NOT executed.

### Single-agent force-sync (incident response)

```bash
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts --agent felix-admin-capture
```

Behavior is identical to a full tick but restricted to that agent. Useful
for forcing a sync during incident response without affecting other agents.

## Troubleshooting

### Symptom: `systemctl --user list-timers` does not show agent-prompt-sync

The timer was not enabled. Re-run `systemctl --user enable --now agent-prompt-sync.timer`.

### Symptom: Audit log has `git_pull_failed` entries

`git fetch` or `git pull --ff-only` failed. Possible causes:

- **Network blip** (transient): next tick is a free retry; no action needed if subsequent ticks succeed
- **Non-ff state** (e.g., manual commit on office2 clone): inspect with `cd ~/kg-automation && git status`. If there's a divergent commit, reconcile manually (commit + push OR reset + rebase). Helper does NOT auto-resolve divergence
- **Authentication issue**: confirm `git fetch` works as the claude user; check `~/.ssh/config` for the `github-kg-automation` host alias

### Symptom: Audit log has `error` entries for a specific file

The atomic copy raised an exception. Inspect the `error` and `error_class`
fields. Common cases:

- `PermissionError`: helper running as wrong user, OR deploy dir got chowned. Confirm `/data/services/openclaw/<dir>/` is writable by `claude`
- `OSError [Errno 28]`: disk full on `/data/`. Free space
- `FileNotFoundError` on source: agent declared in `service-inventory.json` but `source_in_repo` path doesn't exist. Fix the JSON entry or restore the missing dir

### Symptom: Helper is running, but agent behavior hasn't changed

Agents read their prompts at session-init only. The next agent cron tick will
pick up the new prompt:

- `felix-admin-capture`: next at 7am / noon / 5pm / 10pm ET
- `felix-admin-habits`: next at 7:05am ET (morning) or Sunday 22:00 ET (weekly)
- `felix-admin-escalation`: next at 8am ET
- `felix-admin-tasker`: triggered on delegation; force-trigger with a test delegation

The helper does NOT force-restart openclaw (per spec FR-017). If you need an
agent to pick up a prompt change immediately, trigger that agent's cron entry
manually.

### Symptom: HEARTBEAT.md disappeared from a deploy dir

The helper does NOT touch `HEARTBEAT.md` (per spec C-002). If `HEARTBEAT.md`
is missing, a different process (the heartbeat-gate) is responsible. See
`docs/design/architecture/service-inventory.md` for the heartbeat surface
owner.

### Symptom: deployed file ownership changed from `claude:felix` to `claude:claude`

Expected. The helper preserves file MODE but not OWNERSHIP — temp files are
created with the helper user's identity (`claude:claude`), and `os.replace`
keeps that ownership at the destination. Operationally fine because deployed
prompt files have mode `rw-r--r--` (world-readable) and openclaw runs as
`claude` (can read claude-owned files regardless of group). Not a concern.

## Rollback

If a deployed prompt induces broken behavior (e.g., a new prompt has a typo
that crashes openclaw session-init):

```bash
# 1. Revert the offending commit on Mac and push
cd ~/repos/kg-automation
git revert <bad-sha>
git push origin main

# 2. Wait <=5 min for the next tick, OR force a tick:
ssh office2-claude
cd ~/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts
```

The revert lands as a fresh commit, which the helper picks up via its normal
pull-and-sync flow.

If the helper itself is broken (regression in `deploy_agent_prompts.py`):

```bash
# Stop the timer to halt sync
ssh office2-claude
systemctl --user stop agent-prompt-sync.timer
systemctl --user disable agent-prompt-sync.timer

# Manual file copy for any deploy needed in the interim
scp ~/repos/kg-automation/scripts/openclaw/agents/felix-admin-capture/AGENTS.md \
    office2-claude:/data/services/openclaw/inbox-agent/AGENTS.md
```

After the fix lands and a fresh `git pull` is done on office2, re-enable:

```bash
systemctl --user enable --now agent-prompt-sync.timer
```

## Observability

| Surface | What to check | Frequency |
|---|---|---|
| `systemctl --user list-timers` | Timer is scheduled, last tick passed recently | Ad-hoc / weekly |
| `journalctl --user -u agent-prompt-sync.service --since "1 day ago"` | No failed service starts | Weekly |
| `/data/services/openclaw/deploy/agent-prompt-sync.jsonl` (last 100 lines) | Per-file actions look sane | After any mission merge that touched an agent prompt |
| MD5 comparison (repo vs deployed) | Match on all expected files | After any mission merge that touched an agent prompt; spot-check during incident response |

## References

- Mission spec: `kitty-specs/agent-prompt-deploy-pipeline-01KTMDDD/spec.md`
- Helper source: `scripts/openclaw/deploy/deploy_agent_prompts.py`
- Systemd units: `scripts/openclaw/deploy/agent-prompt-sync.{service,timer}`
- Service inventory entry: `docs/design/architecture/data/service-inventory.json` → `services[name=agent-prompt-sync]`
- Audit log JSONL contract: 5 record kinds (`copy`, `skip`, `error`, `git_pull_failed`, `warning`) plus per-tick `tick_summary`
