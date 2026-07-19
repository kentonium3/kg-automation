---
title: office2 OS Maintenance (Ubuntu package updates)
doc_type: runbook
audience: agents_and_humans
status: approved
level: howto
created: 2026-07-19
last_validated: '2026-07-19'
last_updated: '2026-07-19'
updated_by: '#628'
version: v1.0
owners: [kgale]
---

# office2 OS Maintenance (Ubuntu package updates)

Keeping the office2 host (Ubuntu 24.04 LTS) patched. Like the OpenClaw ecosystem
check, the shape is **read-only detection → reminder → attended manual apply** —
but here the apply is a genuine **Tier-0 host change** requiring `sudo`, so it is
performed by **Kent via `ssh office2-kgale`**, never by an agent.

> **MVP.** Detection is currently driven by a **monthly recurring Vikunja task**
> ("Check office2 for OS/package updates (apt)", project **Felix-kg-automation**,
> id 16) rather than a systemd timer — the cadence is low and the apply is manual
> anyway. If this proves too easy to ignore, promote detection to an automated
> `apt list --upgradable` check with an ntfy digest (sibling to
> `felix-openclaw-updates`); tracked as a possible follow-up, not built here.

## Change-control tier (READ FIRST)

Applying system package updates (`sudo apt upgrade`) is a **Tier-0 host change**
(the change-control hard lock: host/foundational, requires `sudo`). **Claude Code
never runs it.** The agent may run the unprivileged *detection* commands below
and prepare the command list; **Kent runs the apply manually via
`ssh office2-kgale`.** This is absolute per `CLAUDE.md` → Change Control
Guardrails → Tier 0.

## Detection (unprivileged — agent-safe)

`apt` package lists are refreshed daily by `apt-daily.timer` (~06–08 UTC), so
`apt list --upgradable` is current enough without a manual `apt update`:

```
ssh office2-claude 'apt list --upgradable 2>/dev/null'
```

Check whether a prior upgrade left a pending reboot:

```
ssh office2-claude 'test -f /var/run/reboot-required && cat /var/run/reboot-required* || echo "no reboot required"'
```

Neither command needs `sudo`. Summarize the upgradable set for Kent, flagging
anything in the **blast-radius list** below.

## Blast-radius awareness

office2 runs the Felix stack (OpenClaw gateway, Vikunja, inbox processor) and
Docker. Take extra care when the upgradable set includes:

- **`containerd.io`, `docker-ce`, `docker-buildx-plugin`, `docker-compose-plugin`**
  — a containerd/docker upgrade can restart the Docker daemon and bounce the
  Vikunja stack. Verify the Vikunja containers come back healthy afterward.
- **`linux-*` / kernel packages** — imply a reboot (`/var/run/reboot-required`).
- **`openssh-server`** — a Tier-0 connectivity-sensitive package; do not let an
  sshd restart lock you out (keep an existing session open; Tailscale provides a
  second path).

## Apply (Tier-0 — Kent runs via `office2-kgale`)

Present this sequence to Kent; **do not run it as the agent.**

```
sudo apt update
sudo apt upgrade            # review the list; `-y` only if Kent is comfortable
sudo apt autoremove         # optional cleanup
```

If the upgrade touched Docker/containerd, verify the stacks:

```
ssh office2-claude 'sg docker -c "docker ps --format \"table {{.Names}}\t{{.Status}}\""'
```

Confirm OpenClaw + Vikunja health:

```
ssh office2-claude 'systemctl --user is-active felix-canary.timer felix-vikunja-sync.timer 2>/dev/null; openclaw --version'
```

## Reboot (if required)

If `/var/run/reboot-required` is present, Kent schedules a reboot via
`ssh office2-kgale` (`sudo reboot`) at a low-impact time. After reboot, confirm:

- office2 reachable over Tailscale (`ssh office2-claude 'uptime'`);
- Docker stacks up (Vikunja reachable);
- OpenClaw gateway up and DM-reply works (see
  [`openclaw-ecosystem-upgrade.md`](<./openclaw-ecosystem-upgrade.md>) DM smoke).

## Related

- [`openclaw-ecosystem-upgrade.md`](<./openclaw-ecosystem-upgrade.md>) — sibling
  update-discipline runbook for the OpenClaw layer (npm, not apt).
- `CLAUDE.md` → Change Control Guardrails → **Tier 0 hard lock** — why the agent
  never runs the apply.
- Issue: #628 (the update-visibility work this MVP is part of).
