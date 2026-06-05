---
title: Deployment Runbook
doc_type: runbook
audience: agents_and_humans
status: approved
last_updated: '2026-06-05'
---

# Deployment Runbook

How Felix features are deployed to office2. Every feature that ships
code, agents, skills, or scheduled services follows this pattern.

---

## Prerequisites

### SSH host alias

All deploy scripts connect to office2 via the `office2-claude` SSH host
alias, running as the `claude` service account. This alias must be
configured in `~/.ssh/config` on your Mac before any deploy script will
work:

```
Host office2-claude
  HostName 100.92.197.90
  User claude
  IdentityFile ~/.ssh/id_ed25519
```

Confirm it works before running any deploy script:

```bash
ssh office2-claude "echo ok"
```

### Tailscale

office2 is only reachable over Tailscale. Ensure Tailscale is connected
on your Mac before deploying.

### Branch state

Deploy only from `main`. All feature work must be merged before
deploying. Never deploy from a feature branch.

```bash
git checkout main && git pull
```

### Risk tier and backup gate

Before deployment, classify the change using the canonical risk taxonomy in
`docs/design/architecture/data/change-risk-taxonomy.json`.

| Tier | Deployment gate |
|------|-----------------|
| 0 | Human executes manually; agent-authored scripts only |
| 1 | Connectivity pre-flight and post-change verification required |
| 2 | Recent backup or snapshot required before mutation |
| 3 | Standard deploy with dry-run or sandbox test where available |
| 4 | No deployment gate beyond normal validation |

Tier 0 and Tier 1 deployments must complete the pre-flight checklist in
`docs/runbooks/governance/pre-flight-checklist.md` before execution. Tier 0,
Tier 1, and Tier 2 deployments must complete post-change verification using
`docs/runbooks/governance/post-change-verification.md`.

For Tier 2 changes, confirm a successful backup or snapshot before deployment.
If no suitable backup exists, trigger the appropriate backup procedure and do
not deploy until it succeeds.

---

## Deploy script pattern

Every feature that touches office2 gets a deploy script at:

```
scripts/deploy/deploy-f{NNN}.sh
```

Note: Legacy deploy scripts use F-number naming (e.g., deploy-f013.sh).
New features use GitHub issue numbers. New deploy scripts should follow
the pattern: `scripts/deploy/deploy-<issue-number>.sh` or a descriptive
slug (e.g., `deploy-sysops-agent.sh`).

Deploy scripts are the authoritative deployment mechanism. There is no
CI-driven deployment to office2 — all deployments are triggered manually
by running the script from your Mac.

### Script structure

Each script follows this structure, adapted to the feature's deliverables:

```bash
#!/usr/bin/env bash
set -euo pipefail

# F0NN: Brief description of what this script deploys
#
# Prerequisites:
#   - All feature PRs merged to main
#   - SSH access to office2-claude configured
#   - Risk tier classified; required backup/pre-flight gate completed
#   - [Any other prerequisites specific to this feature]
#
# Usage: ./scripts/deploy/deploy-f0NN.sh

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "=== F0NN: [Step description] ==="
# ... deployment steps ...
echo "  Done"

echo ""
echo "=== F0NN: Deployment complete ==="
echo ""
echo "Manual validation steps:"
echo "  1. [First validation check]"
echo "  2. [Second validation check]"
```

Key conventions:
- `set -euo pipefail` — fail fast on any error
- `REPO_ROOT` resolved relative to the script, not assumed
- Each logical step announced with `=== F0NN: Step ===`
- Manual validation steps printed at the end — always

### Reference implementation

`scripts/deploy/deploy-f013.sh` is the most complete example. Read it
before authoring a new deploy script.

---

## What gets deployed where

### Agent workspaces

OpenClaw agent workspace files live on office2 at:
```
/data/services/openclaw/{agent-slug}/
```

Source files in the repo live at:
```
scripts/openclaw/agents/{agent-name}/
```

Deploy with `scp`:
```bash
for f in AGENTS.md SOUL.md USER.md IDENTITY.md TOOLS.md; do
  scp "$REPO_ROOT/scripts/openclaw/agents/{agent-name}/$f" \
    "office2-claude:/data/services/openclaw/{agent-slug}/$f"
done
```

Agent workspace directories must be created before first deploy:
```bash
ssh office2-claude "mkdir -p /data/services/openclaw/{agent-slug}"
```

### Skills

OpenClaw skills live on office2 at:
```
/home/claude/.openclaw/skills/{skill-slug}/
```

Source files in the repo live at:
```
scripts/openclaw/skills/{skill-name}/
```

Deploy with `scp`:
```bash
ssh office2-claude "mkdir -p ~/.openclaw/skills/{skill-slug}"
scp "$REPO_ROOT/scripts/openclaw/skills/{skill-name}/SKILL.md" \
  "office2-claude:~/.openclaw/skills/{skill-slug}/SKILL.md"
```

### Python utilities and modules

Python scripts (observation module, helper utilities) live in the repo at
`scripts/openclaw/` and are deployed to a corresponding path on office2.
The planning phase for each feature determines the target path. Deploy
with `scp` following the same pattern as agent workspaces.

### Cron jobs (OpenClaw agents)

OpenClaw cron jobs are registered via the `openclaw cron add` command
over SSH:

```bash
ssh office2-claude 'openclaw cron add \
  --name "job-name" \
  --cron "0 */4 * * *" \
  --agent {agent-name} \
  --session isolated \
  --message '"'"'{"action": "..."}'"'"' \
  --no-deliver'
```

Verify after registration:
```bash
ssh office2-claude "openclaw cron list"
```

### Scheduled services (systemd timer)

Non-OpenClaw scheduled services (Python scripts, shell scripts) use
systemd timers following the pattern in:
```
scripts/office2/vault-snapshot.timer
scripts/office2/vault-snapshot.service
```

Copy unit files to office2 and enable:
```bash
scp scripts/office2/{service}.timer office2-claude:~/.config/systemd/user/
scp scripts/office2/{service}.service office2-claude:~/.config/systemd/user/
ssh office2-claude "systemctl --user daemon-reload && \
  systemctl --user enable --now {service}.timer"
```

---

## Authoring a new deploy script

1. Copy `scripts/deploy/deploy-f013.sh` as your starting point
2. Update the feature number, description, and prerequisites comment
3. Replace the deployment steps with what your feature actually deploys,
   following the patterns above
4. Write specific manual validation steps at the end — not generic ones
5. Test the script with a dry run by commenting out destructive steps
   and verifying the SSH connections and paths are correct before
   running for real

Commit the deploy script to the feature branch alongside the feature
code. It merges to main with the feature.

---

## After deployment

### Update architecture docs

Features that deploy new services, agents, or scheduled jobs must update
`docs/design/architecture/data/service-inventory.json` and the
corresponding Markdown view. This is part of the feature spec's
Architecture Documentation Updates section — not a separate step.

### Security baseline reset

After deploying new services or modifying existing ones, reset the
security audit baselines on office2. See
[Security Baseline Operations](<./security-baseline-ops.md>) for the
canonical procedure.

### Verify in Obsidian (for agent/digest changes)

If the feature produces output in the Obsidian vault (agent logs, digest
files, processed notes), verify the output appears on your Mac within
the expected sync window after deployment.

---

## Troubleshooting

**SSH connection refused**
- Confirm Tailscale is connected: `tailscale status`
- Confirm the claude account is reachable: `ping 100.92.197.90`

**Permission denied on office2**
- The `claude` account has scoped sudo for specific operations
- If a deploy step needs elevated permissions, check
  `docs/design/office2-backup-and-security.md` for what `claude` can sudo
- Operations requiring `kgale` permissions must be run manually by Kent

**OpenClaw cron job not appearing**
- Verify OpenClaw gateway is running:
  `ssh office2-claude "systemctl --user status openclaw-gateway"`
- Check cron registration: `ssh office2-claude "openclaw cron list"`

**Systemd timer not firing**
- Check timer status: `ssh office2-claude "systemctl --user list-timers"`
- Check service logs: `ssh office2-claude "journalctl --user -u {service} --since today"`

---

## Related documents

- `docs/runbooks/openclaw-ops.md` — OpenClaw service management
- `docs/design/office2-backup-and-security.md` — security baseline reset
- `docs/runbooks/maintenance.md` — branch and CI conventions
- `docs/design/architecture/change-control.md` — architecture doc update protocol and risk-tiered change control
- `docs/runbooks/governance/pre-flight-checklist.md` — Tier 0/1 deployment pre-flight
- `docs/runbooks/governance/post-change-verification.md` — Tier 0/1/2 post-change verification
- `scripts/deploy/deploy-f013.sh` — reference deploy script
