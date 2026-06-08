# Quickstart: Agent Prompt Deploy Pipeline

**Mission**: `agent-prompt-deploy-pipeline-01KTMDDD`
**Audience**: Operator (Kent or any Felix operator on duty) doing first-time install or subsequent verification after a mission merge.
**Prereq**: Mission has merged to `main`; `~/kg-automation` on Mac is at the merge commit; office2 reachable via `ssh office2-claude`.

## First-time install (one-time, post-merge)

```bash
# 1. Ensure office2 git clone is current
ssh office2-claude
cd ~/kg-automation
git fetch origin main
git pull --ff-only origin main
git log -1 --oneline  # should match the merge commit on Mac

# 2. Copy the systemd unit files
mkdir -p ~/.config/systemd/user
cp scripts/openclaw/deploy/agent-prompt-sync.service ~/.config/systemd/user/
cp scripts/openclaw/deploy/agent-prompt-sync.timer ~/.config/systemd/user/

# 3. Reload the systemd user manager + enable the timer
systemctl --user daemon-reload
systemctl --user enable --now agent-prompt-sync.timer

# 4. Confirm the timer is scheduled
systemctl --user list-timers | grep agent-prompt-sync
```

Expected output of step 4:
```
NEXT                          LEFT    LAST  PASSED  UNIT                       ACTIVATES
Mon 2026-06-08 20:21:31 UTC   4m 30s  -     -       agent-prompt-sync.timer    agent-prompt-sync.service
```

## First-tick verification (within 5 minutes of install)

Wait up to 5 minutes for the first tick to fire (or trigger manually — see below). Then:

```bash
# Check the systemd journal for the most recent tick
journalctl --user -u agent-prompt-sync.service --since "10 min ago" --no-pager

# Check the audit log for per-file actions
tail -50 /data/services/openclaw/deploy/agent-prompt-sync.jsonl
```

Expected journal output: one line per tick showing exit status 0 and a duration <2s.

Expected audit-log output for the first tick post-#558/#561 deploy debt:
- One `copy` entry for `felix-admin-capture/AGENTS.md` (the stranded 1215-line update)
- One `copy` entry for `felix-admin-habits/AGENTS.md` (the stranded #561 Hard Rules)
- Skip entries for all other files
- One `tick_summary` entry showing `files_copied >= 2`

## Spot-check that prompts actually landed

```bash
# Compare repo MD5 to deployed MD5 for capture
md5sum /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-capture/AGENTS.md \
       /data/services/openclaw/inbox-agent/AGENTS.md

# Same for habits
md5sum /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-habits/AGENTS.md \
       /data/services/openclaw/habits-agent/AGENTS.md
```

Both md5s should match. If they differ, see Troubleshooting below.

## Manual trigger (without waiting for the timer)

```bash
# Run the helper directly (writes to audit log + makes real changes)
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts

# Or trigger the systemd service (functionally equivalent)
systemctl --user start agent-prompt-sync.service
```

## Dry-run (preview what WOULD change without modifying anything)

```bash
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts --dry-run
```

Expected output: zero `DRIFT` lines if everything is in sync; one `DRIFT` line per drifted file otherwise. Audit log is NOT written. Deployed files are NOT modified. `git pull` is NOT executed.

## Single-agent force-sync (incident response)

If you need to force-sync ONE agent without waiting for the timer (e.g., during a debug session):

```bash
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts --agent felix-admin-capture
```

Behavior is identical to a full tick but restricted to that agent.

## Troubleshooting

### Symptom: `systemctl --user list-timers` does not show agent-prompt-sync

The timer was not enabled. Re-run step 3 of the install (`systemctl --user enable --now agent-prompt-sync.timer`).

### Symptom: Audit log has `git_pull_failed` entries

`git fetch` or `git pull --ff-only` failed. Possible causes:
- **Network blip** (transient): next tick is a free retry; no action needed if subsequent ticks succeed.
- **Non-ff state** (e.g., manual commit on office2 clone): inspect with `cd ~/kg-automation && git status`. If there's a divergent commit, reconcile manually (commit + push OR reset + rebase). Helper does NOT auto-resolve divergence.
- **Authentication issue**: confirm `git fetch` works as the claude user; check `~/.ssh/config` for the `github-kg-automation` host alias.

### Symptom: Audit log has `error` entries for a specific file

The atomic copy raised an exception. Inspect the `error` and `error_class` fields. Common cases:
- `PermissionError`: helper running as wrong user, OR deploy dir got chowned. Confirm `/data/services/openclaw/<dir>/` is writable by `claude`.
- `OSError [Errno 28]`: disk full. Free space on `/data/`.
- `FileNotFoundError` on source: agent declared in service-inventory.json but `source_in_repo` path doesn't exist. Fix the JSON entry or add the missing dir.

### Symptom: Helper is running, but agent behavior hasn't changed

Agents read their prompts at session-init only. The next agent cron tick will pick up the new prompt:
- felix-admin-capture: next at 7am / noon / 5pm / 10pm ET
- felix-admin-habits: next at 7:05am ET (morning checkin) or Sunday 22:00 ET (weekly report)
- felix-admin-escalation: next at 8am ET
- felix-admin-tasker: triggered on delegation; force-trigger with a test delegation

The helper does NOT force-restart openclaw (per FR-017). If you need an agent to pick up a prompt change immediately, the operator must trigger that agent's cron entry manually.

### Symptom: HEARTBEAT.md disappeared from a deploy dir

The helper does NOT touch HEARTBEAT.md (C-002). If HEARTBEAT.md is missing, a different process (the heartbeat-gate) is responsible. See `docs/design/architecture/service-inventory.md` for the heartbeat surface owner.

## Rollback

If a deploy of agent prompts induces broken behavior (e.g., a new prompt has a typo that crashes openclaw session-init):

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

The revert lands as a fresh commit, which the helper picks up via its normal pull-and-sync flow.

If the helper itself is broken (e.g., a regression in deploy_agent_prompts.py):

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
