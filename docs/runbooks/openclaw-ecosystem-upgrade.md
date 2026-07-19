---
title: OpenClaw Ecosystem Upgrade
doc_type: runbook
audience: agents_and_humans
status: approved
level: howto
created: 2026-07-19
last_validated: '2026-07-19'
last_updated: '2026-07-19'
updated_by: '#628; #653 PATH-shadow + plugins-update-verb gotchas (2026.7.1-2 apply)'
version: v1.1
owners: [kgale]
---

# OpenClaw Ecosystem Upgrade

How to keep the OpenClaw ecosystem on office2 current — **core** plus **every
channel plugin** — as a single lockstep operation, and how the weekly automated
detection that prompts an upgrade works.

> **Scope split.** *Detection* is automated (`felix-openclaw-updates`, weekly,
> silent-unless-findings). *Applying* an upgrade is a deliberate,
> **operator-attended** change performed by hand — the automation never upgrades
> anything. This runbook is the manual apply procedure the weekly digest points at.

## Why lockstep (the #588 / #617 lesson)

OpenClaw channels (`@openclaw/whatsapp`, …) are **external plugins**, installed
under `~/.openclaw/npm/projects/`, **not bundled with core and not auto-upgraded
when core is bumped.** Twice, a core upgrade left `@openclaw/whatsapp` behind on
an older version and Felix's WhatsApp DM-reply broke **silently** — the gateway
showed a typing indicator, then nothing, and cron announce-mode outbound kept
working so the break was masked (#588 initial, #617 recurrence). The rule that
prevents recurrence: **upgrade core and all channel plugins together, then
verify DM-reply end-to-end before walking away.**

## The weekly detection check (`felix-openclaw-updates`)

- **What:** a systemd-user timer on office2 (claude account), Monday 07:00 ET,
  running `python3 -m scripts.openclaw.check_ecosystem_updates --once`.
- **What it checks:** the `openclaw` core global package (`npm outdated -g
  openclaw`) plus each installed `@openclaw/*` channel plugin (enumerated from
  `~/.openclaw/npm/projects/*/node_modules/@openclaw/*` and compared against the
  npm registry `latest`).
- **Output discipline:** **silent** when everything is current (exit 0, no
  alert). When ≥1 update is available — or a component check failed — it emits a
  single WARN digest via the #701 felix-alert bus listing each component
  `name: current → latest`, and points here.
- **Liveness:** each completed pass rewrites
  `/data/services/felix-openclaw-updates/state/last-tick.json`; the Felix Canary
  freshness-monitors it (a silent weekly check must be provably *running*, not
  just quiet). A crashed run pages immediately via
  `felix-openclaw-updates-onfailure.service`.
- **It is detection-only.** It never calls `npm install`.

### Run the check by hand

```
ssh office2-claude 'cd kg-automation && python3 -m scripts.openclaw.check_ecosystem_updates --dry-run'
```

`--dry-run` prints the digest it *would* emit without paging or writing a tick.
`--self-check` verifies prerequisites (npm on PATH, projects dir readable, state
dir writable).

## Applying an upgrade (operator-attended)

Trigger: the weekly digest fired (or the dry-run above shows updates). The
running gateway is the OpenClaw core; upgrading it and restarting it briefly
interrupts WhatsApp DM handling. **This is an application-level change — treat it
with Tier-2 care (a recent Restic snapshot should exist) and perform it attended,
never autonomously.** The commands below run as the **claude** user (openclaw is a
user-local npm global under `/home/claude/.local`; no `sudo` is required). If any
step unexpectedly demands elevation, **stop** — that would be a Tier-0 action and
must be handed to Kent per the change-control hard lock.

> **⚠️ Use the absolute claude-space binary for every CLI command here.** The sole
> install lives in claude user-space at `/home/claude/.local/bin/openclaw` (#653
> relocated the core out of the root-owned `/usr/lib` and removed the root-global on
> 2026-07-19). The non-interactive ssh PATH — and the systemd-user / cron PATH — do
> **not** include `/home/claude/.local/bin`, so bare `openclaw` there is now
> `command not found` (before the removal it silently resolved to the *stale*
> root-global, reporting the wrong version — that false-negative is gone, replaced by
> a clean fail-loud). Either way, **run every openclaw CLI command in this section as
> `/home/claude/.local/bin/openclaw`**, and verify the *running* host with
> `openclaw gateway status --deep` (`Gateway version:`), not bare `openclaw --version`.
> The running gateway is unaffected regardless — its systemd `ExecStart` invokes the
> claude-space `dist/index.js` by absolute path. (Bare `openclaw` works only in a
> **login** shell, whose `.profile` puts `~/.local/bin` first — do not rely on that
> for scripted/systemd/cron callers; those must use the absolute path.)

1. **Snapshot precondition (Tier 2).** Confirm a Restic backup within 24h exists
   (see [`security-baseline-ops.md`](<./security-baseline-ops.md>) /
   [`deploy/discipline.md`](<./deploy/discipline.md>) for the backup story);
   trigger one first if stale.

2. **Record current versions** (so a rollback target is known — use the absolute
   claude-space binary per the PATH-shadow warning above):

   ```
   ssh office2-claude '/home/claude/.local/bin/openclaw --version && ls ~/.openclaw/npm/projects/'
   ```

3. **Upgrade core** (the `npm install -g` correctly targets the claude-space tree;
   verify with `gateway status --deep` after the restart, NOT bare
   `openclaw --version`, which is shadowed):

   ```
   ssh office2-claude 'npm install -g openclaw@latest && /home/claude/.local/bin/openclaw --version'
   ```

4. **Upgrade every channel plugin to match** (do NOT skip — this is the #588/#617
   guard). For each `@openclaw/<plugin>` the digest flagged, upgrade it through
   openclaw's own plugin mechanism so it lands under `~/.openclaw/npm/projects/`
   (NOT a bare `npm -g install`, which would put it in the wrong tree). The
   subcommand is **`plugins update`** (renamed from `plugins upgrade` in 2026.7.1)
   and needs the explicit `@latest` spec — the bare id refuses because the plugin
   is version-pinned. Dry-run first, then apply:

   ```
   ssh office2-claude '/home/claude/.local/bin/openclaw plugins update @openclaw/whatsapp@latest --dry-run'
   ssh office2-claude '/home/claude/.local/bin/openclaw plugins update @openclaw/whatsapp@latest'   # repeat per flagged plugin
   ```

   If `plugins update` is unavailable on the installed build, re-add the plugin at
   the target version via the same command used to install it originally (see
   [`openclaw-upgrade-gotchas`](<./openclaw-ops.md>) / memory
   `reference_openclaw_upgrade_gotchas`). Confirm the on-disk version:

   ```
   ssh office2-claude 'for p in ~/.openclaw/npm/projects/*/node_modules/@openclaw/*/package.json; do node -e "const x=require(\"$p\"); console.log(x.name, x.version)"; done'
   ```

5. **Restart the gateway** (rotation/upgrade wedges the live DM lane until a
   restart — deploy gotcha #11):

   ```
   ssh office2-claude '/home/claude/.local/bin/openclaw gateway restart'
   ```

   Confirm the *running* host is the new version (bare `openclaw --version` is
   shadowed; this reads the live process):

   ```
   ssh office2-claude '/home/claude/.local/bin/openclaw gateway status --deep 2>&1 | grep -iE "Gateway version|Runtime|Listening"'
   ```

6. **DM-reply smoke (mandatory — this is the #588/#617 verification).** Send a
   WhatsApp DM to Felix and confirm a real reply (not just a typing indicator).
   The canonical smoke procedure + the #588 signature are in
   [`reference_openclaw_dm_reply_lifecycle`] (memory) and
   [`openclaw-ops.md`](<./openclaw-ops.md>). **Do not consider the upgrade done
   until a DM round-trips.**

7. **Re-run the detection check** to confirm the ecosystem now reports current:

   ```
   ssh office2-claude 'cd kg-automation && python3 -m scripts.openclaw.check_ecosystem_updates --dry-run'
   ```

   Expect `openclaw ecosystem current — no updates available`.

8. **Rebaseline.** An openclaw core/plugin upgrade changes an audited surface
   (openclaw config / installed versions). Reset the security-monitor baselines
   per [`security-baseline-ops.md`](<./security-baseline-ops.md>) so the daily
   audit doesn't alert the expected drift.

## Rollback

If the DM smoke fails or the gateway misbehaves after the upgrade, reinstall the
recorded prior versions (step 2) for core and the affected plugin(s), restart the
gateway, and re-run the DM smoke. Escalate to Kent if a plugin/core version pin
cannot be resolved. See also
[`reference_openclaw_upgrade_gotchas`](<./openclaw-ops.md>) for known
version-pinning pitfalls.

## Related

- [`openclaw-agent-setup.md`](<./openclaw-agent-setup.md>) — H5 troubleshooting
  step (manual plugin-vs-core version check; this runbook is its automated
  sibling).
- [`openclaw-ops.md`](<./openclaw-ops.md>) — general OpenClaw operations.
- [`security-baseline-ops.md`](<./security-baseline-ops.md>) — rebaseline
  procedure.
- Issues: #628 (this capability), #617 / #588 (the breaks that motivated it).
