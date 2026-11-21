---
title: office2 OS Maintenance (Ubuntu package updates)
doc_type: runbook
audience: agents_and_humans
status: approved
level: howto
created: 2026-07-19
last_validated: '2026-11-21'
last_updated: '2026-11-21'
updated_by: '#628 + #1120 (first full run 2026-11-21: tailscale session-drop warning, working OpenClaw check, security-monitor rebaseline step, Ubuntu Pro + Livepatch, kernel cleanup)'
version: v1.1
owners: [kgale]
---

# office2 OS Maintenance (Ubuntu package updates)

Keeping the office2 host (Ubuntu 24.04 LTS) patched. Like the OpenClaw ecosystem
check, the shape is **read-only detection → reminder → attended manual apply**.
Here the apply is a genuine **Tier-0 host change** that requires `sudo`, so
**Kent performs it** at the tty1 console or via `ssh office2-kgale`, never an
agent.

> **MVP.** Detection is currently driven by a **monthly recurring Vikunja task**
> ("Check office2 for OS/package updates (apt)", project **Felix-kg-automation**,
> id 16) rather than a systemd timer. The cadence is low and the apply is manual
> anyway. If this proves too easy to ignore, promote detection to an automated
> `apt list --upgradable` check with an ntfy digest (sibling to
> `felix-openclaw-updates`). That is tracked as a possible follow-up, not built
> here. Scheduled reboots after the nightly backup are tracked in #1121.

## What is automatic already

- **unattended-upgrades** is enabled. It installs packages from the
  `noble-security` pocket nightly and, since Ubuntu Pro was attached
  (2026-11-21, #1120), the ESM origins too (`UbuntuESMApps`, `UbuntuESM`). What
  it does **not** do is restart anything. A patched library or kernel sits on
  disk until a restart or reboot, which is why `/var/run/reboot-required`
  accumulates.
- **Livepatch** (`canonical-livepatch`, via Ubuntu Pro) applies most kernel
  security fixes to the running kernel. Userspace fixes (libc6, systemd,
  openssl, …) and the occasional non-livepatchable kernel fix still need a
  reboot. So reboots get rarer but do not stop.

So a manual window is mostly about the **non-security `noble-updates` set**
(Docker, systemd, firmware, tailscale, nodejs, …) and **reboots**.

## Change-control tier (READ FIRST)

Applying system package updates (`sudo apt upgrade`) is a **Tier-0 host change**
(the change-control hard lock: host/foundational, requires `sudo`). **Claude Code
never runs it.** The agent may run the unprivileged *detection* and
*verification* commands below and prepare the command list. **Kent runs the
apply.** This is absolute per `CLAUDE.md` → Change Control Guardrails → Tier 0.

## Detection (unprivileged, agent-safe)

`apt` package lists are refreshed daily by `apt-daily.timer` (~06–08 UTC), so
`apt list --upgradable` is current enough without a manual `apt update`:

```
ssh office2-claude 'apt list --upgradable 2>/dev/null'
```

Check whether a prior upgrade left a pending reboot, and what the running kernel
is:

```
ssh office2-claude 'uname -r; uptime; test -f /var/run/reboot-required && cat /var/run/reboot-required.pkgs || echo "no reboot required"'
```

Neither command needs `sudo`. Summarize the upgradable set for Kent, flagging
anything in the **blast-radius list** below. A low count of `-security`
packages is normal: unattended-upgrades has usually installed those already.
The security exposure is then the **un-rebooted** kernel and libraries, not the
pending list.

## Pre-flight (agent, read-only)

- **Backup:** `/data/services/backup/state/last-backup.json` shows a snapshot
  under 24 h old with `restic_exit_code` 0 and `failure_reason: null`.
- **Health:** no failed units (`systemctl --failed`, `systemctl --user --failed`),
  and nothing in `deploys/queued/`.
- **`/boot` headroom:** check `df -h /boot`. Each kernel's initrd is about
  **255 MB** (NVIDIA firmware), and a new kernel needs about 300 MB free on the
  2 GB `/boot`.
- **Timing:** avoid the 03:00 (security audit) and 04:00 (backup) UTC crons.

## Blast-radius awareness

office2 runs the Felix stack (OpenClaw gateway, Vikunja, inbox processor) and
Docker. Take extra care when the upgradable set includes:

- **`tailscale`**: the upgrade **restarts `tailscaled` and drops every
  Tailscale-SSH session**, including `ssh office2-kgale`. Observed 2026-11-21:
  the session died mid-upgrade. **Run the apply inside `tmux` or at the tty1
  console** so dpkg is not killed with the session. If a session does drop,
  check `dpkg --audit` (empty = clean) and the `End-Date` in
  `/var/log/apt/history.log` before going on.
- **`containerd.io`, `docker-ce`, `docker-buildx-plugin`, `docker-compose-plugin`**:
  a containerd/docker upgrade restarts the Docker daemon and bounces `vikunja`
  and `transcribe-api`. Both restart automatically; verify them afterwards.
- **`linux-*` / kernel packages**: imply a reboot (`/var/run/reboot-required`).
  New `linux-modules-nvidia-*-server-<version>` packages arrive with the kernel.
  Check they match the running driver branch (`nvidia-smi`, currently 580).
- **`openssh-server`**: a Tier-0 connectivity-sensitive package. Do not let an
  sshd restart lock you out. Keep an existing session open; Tailscale and the
  console are second paths.
- **`nodejs`**: openclaw-gateway keeps the old binary until it restarts, so
  the reboot picks it up.

## Apply (Tier-0: Kent runs it, in tmux or at the console)

Present this sequence to Kent; **do not run it as the agent.** One command at a
time:

```
tmux new -s patch
sudo apt update
sudo apt upgrade            # review the list first; see below
```

Before answering `Y`, check the summary:

- **"to remove" must be 0.** If not, stop and review.
- **"kept back"** packages are named. A kept-back signature package for an
  old, non-running kernel is harmless.
- **NEW packages** for a kernel upgrade are expected: image, modules, headers,
  NVIDIA modules/signatures and the `linux-firmware-*` split packages.
- A **needrestart** dialog: restart nothing if a reboot follows.
- A **config-file prompt**: keep the local version (the default `N`) and note
  the file.

## Reboot (if required)

If `/var/run/reboot-required` is present, Kent reboots at a low-impact time,
from the console or `ssh office2-kgale`:

```
sudo reboot
```

Note the time, and any ntfy notifications or emails that arrive in the next
hour. That evidence feeds #1121.

## Post-reboot verification (agent, read-only)

```
ssh office2-claude 'uname -r; test -f /var/run/reboot-required && cat /var/run/reboot-required.pkgs || echo "no reboot required"; systemctl --failed --no-legend; systemctl --user --failed --no-legend; df -h /data /mnt/backups | tail -2; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader'
```

```
ssh office2-claude 'for u in docker containerd tailscaled obsidian-sync ssh.socket unattended-upgrades; do printf "%s=%s " $u $(systemctl is-active $u); done; echo; sg docker -c "docker ps --format \"{{.Names}}\t{{.Status}}\""; systemctl --user is-active openclaw-gateway; systemctl --user list-timers --no-legend | wc -l'
```

```
ssh office2-claude '/home/claude/.local/bin/openclaw --version; curl -s -m 5 -o /dev/null -w "vikunja %{http_code}\n" http://100.92.197.90:3456/api/v1/info'
```

Confirm all of the following:

- the new kernel is running and nothing failed;
- `/data` and `/mnt/backups` are mounted and the GPU answers;
- the containers are up (`vikunja.service` runs `compose down`/`up`, so they are
  *recreated* at boot by design);
- the gateway is active and the user timer count matches the pre-reboot count;
- Vikunja returns 200. It binds only the Tailscale IP, so `127.0.0.1` returns
  000 by design.

`openclaw` lives in `/home/claude/.local/bin`, which is not on the
non-interactive SSH `PATH`. A bare `openclaw --version` over `ssh` fails with
`command not found`, so use the full path.

Then run the DM-reply smoke check: Kent sends a DM, then the agent runs the
awk one-liner in
[`openclaw-agent-setup.md` § Operator smoke command](<./openclaw-agent-setup.md>).
One DM is enough for a post-reboot check. Also confirm the first post-boot
`felix-canary` run succeeded and the alert-bus ledger
(`/data/services/alert-bus/ledger/<date>.jsonl`) has no new entries.

## Security-monitor rebaseline (agent)

An apply through `sudo` is **out-of-band**: felix-deployer does not see it and
will not auto-rebaseline. Any host-state change the daily 03:00 audit
fingerprints will alert. Typical causes are a new enabled service (e.g. the
Livepatch daemon) or a changed Docker image set.

1. Replicate the audit's diffs read-only, without running `audit.sh`, which
   alerts. The generation commands are in
   `scripts/office2/security-monitor/audit.sh`. Diff each against
   `/data/services/security-monitor/baselines/`.
2. If anything drifted and every line is explained, follow the **manual reset**
   in [`security-baseline-ops.md`](<./security-baseline-ops.md>). **Archive to
   `/data`, not `/tmp`**, because `/tmp` is emptied at boot:

   ```
   ssh office2-claude 'cp -a /data/services/security-monitor/baselines /data/services/security-monitor/baselines-archive-$(date -u +%Y%m%dT%H%M%SZ)'
   ```

3. After the reset, `diff -r` the archive against the new set and account for
   **every** difference in the maintenance issue. A reset silently accepts
   anything that changed, including drift unrelated to the upgrade.

## Cleanup (Kent, after a clean boot)

```
sudo apt autoremove
```

The agent can preview it first with `apt-get -s autoremove` (no `sudo`). It keeps
the running and previous kernels. Older kernels whose NVIDIA signature packages
are still installed may not be offered. Investigate before purging them by hand,
because a manual purge can pull in replacement NVIDIA metapackages.

## Ubuntu Pro + Livepatch (set up 2026-11-21, #1120)

office2 is attached to Kent's **free personal** Ubuntu Pro subscription (up to
5 machines). The credential is recorded as `ubuntu-pro-machine-token` in
`docs/design/architecture/data/credential-manifest.json`, and the daemon as
`canonical-livepatch` in `service-inventory.json`.

- **Status (agent, no sudo):**
  `ssh office2-claude 'pro status; canonical-livepatch status --verbose'`.
  Expect `esm-apps`, `esm-infra` and `livepatch` enabled. For the running kernel
  expect `supported: supported` and `patchState` applied or nothing-to-apply.
  Note `upgradeRequiredDate`: Livepatch stops covering a kernel after that date.
- **Re-attach (Kent, e.g. after a rebuild):** run `sudo pro attach` with **no
  token argument**. It prints a code to approve at ubuntu.com/pro/attach, so the
  token never reaches a command line or shell history. Livepatch is enabled by
  default on attach; otherwise `sudo pro enable livepatch`.
- **Pending ESM fixes** appear in `apt list --upgradable` as `noble-apps-security`
  / `noble-infra-security`. unattended-upgrades applies them nightly.
- **Detach** before retiring or rebuilding office2: `sudo pro detach`.

## Related

- [`openclaw-ecosystem-upgrade.md`](<./openclaw-ecosystem-upgrade.md>): sibling
  update-discipline runbook for the OpenClaw layer (npm, not apt).
- [`security-baseline-ops.md`](<./security-baseline-ops.md>): baseline reset
  procedure.
- `CLAUDE.md` → Change Control Guardrails → **Tier 0 hard lock**: why the agent
  never runs the apply.
- Issues: #628 (the update-visibility work this MVP is part of); #1120 (first
  full run, 2026-11-21); #1121 (scheduled post-backup auto-reboot with alert
  mute).
