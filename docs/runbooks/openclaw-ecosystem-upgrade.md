---
title: OpenClaw Ecosystem Upgrade
doc_type: runbook
audience: agents_and_humans
status: approved
level: howto
created: 2026-07-19
last_validated: '2026-11-23'
last_updated: '2026-11-23'
updated_by: '#628; #653 PATH-shadow + plugins-update-verb gotchas (2026.7.1-2 apply); #1122 Node-24 switch, target resolution, doctor-before-plugin order, npm allowScripts, selfChatMode, new DM smoke (2026.11.7 apply)'
version: v2.0
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
The one planned exception is step 1b, the Node major switch: it is a `sudo apt`
change, so **Kent runs it**.

Allow about an hour, attended, for a jump across several releases. The
2026-07 → 2026-11 jump (#1122) took 20 minutes of Felix downtime, and two traps
surfaced only during the window.

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
>
> **In code**, scripted callers resolve the binary through the seam
> [`scripts/common/openclaw_bin.py`](../../scripts/common/openclaw_bin.py)
> (`openclaw_bin()` / the `${OPENCLAW_BIN:=…}` shell convention), not a hardcoded
> literal (#811) — that is the single place to change on the next relocation. The
> interactive `ssh office2-claude '/home/claude/.local/bin/openclaw …'` commands
> below are one-off operator commands (no seam import available over ssh), so they
> use the absolute path directly.

0. **Resolve the targets by hand. Do not trust the digest's version numbers
   (#1123).** The checker reads core through `npm outdated`, which offers only
   the newest release the *installed* Node can run. It reads plugins from the
   registry `latest`, and never checks that the two are compatible. On
   2026-11-23 it paired core 2026.9.2 with plugin 2026.11.7, which needs core
   ≥2026.11.7. For the real targets:

   ```
   ssh office2-claude 'export PATH=/home/claude/.local/bin:$PATH; node --version; npm view openclaw dist-tags; npm view openclaw@latest engines.node; npm view @openclaw/whatsapp@latest peerDependencies.openclaw'
   ```

   - Pick **one version for core and every channel plugin**, and confirm each
     plugin's `peerDependencies.openclaw` accepts it.
   - If the target's `engines.node` excludes the installed Node, **the Node
     major line moves first** (step 1b). Otherwise skip 1b.

1. **Snapshot precondition (Tier 2).** Confirm a Restic backup under 24 h old
   (`/data/services/backup/state/last-backup.json`: `restic_exit_code` 0,
   `failure_reason` null). Then record the current versions and state, so the
   rollback target is known:

   ```
   ssh office2-claude '/home/claude/.local/bin/openclaw --version; for p in ~/.openclaw/npm/projects/*/node_modules/@openclaw/*/package.json; do node -e "const x=require(\"$p\"); console.log(x.name, x.version)"; done; /home/claude/.local/bin/openclaw cron list; sha256sum ~/.openclaw/openclaw.json'
   ```

1b. **Node major switch (Tier 0: Kent runs it, in `tmux` on office2).** Only
   when step 0 says so. NodeSource ships one apt source per major line:

   ```
   sudo sed -i 's#node_22.x#node_24.x#' /etc/apt/sources.list.d/nodesource.sources
   sudo apt update
   apt-cache policy nodejs        # candidate must be the new major
   sudo apt install nodejs
   ```

   ⚠ **This breaks native modules in other global npm packages.** A module
   compiled against the V8 ABI (not N-API) fails at its next restart with
   `ERR_DLOPEN_FAILED` / `NODE_MODULE_VERSION` mismatch. On 2026-11-23
   `obsidian-sync` crash-looped for 7 minutes on `better-sqlite3`. For each
   global package that ships a `.node` file under `/usr/lib/node_modules/*`
   or `~/.local/lib/node_modules/*`, rebuild it, then prove it **opens**.
   `require()` alone loads only the JavaScript and proves nothing:

   ```
   cd /usr/lib/node_modules/obsidian-headless && sudo npm rebuild better-sqlite3
   ssh office2-claude 'cd /tmp && node -e "const D=require(\"/usr/lib/node_modules/obsidian-headless/node_modules/better-sqlite3\"); new D(\":memory:\"); console.log(\"opens OK\")"'
   ```

   OpenClaw's own native modules (`node-pty`, `tree-sitter-bash`, the
   plugin's `sharp`) are N-API prebuilds and survive a Node switch. Then
   restart the gateway on the **old** OpenClaw and run the DM smoke (step 6)
   before touching OpenClaw, so a Node fault is not mistaken for an OpenClaw
   fault.

2. **Stop the gateway and copy `~/.openclaw`.** `doctor --fix` (step 4) applies
   **one-way** config and SQLite migrations, so reinstalling the old version
   is not a rollback on its own. Take the copy with the gateway **stopped**,
   or the SQLite files may be inconsistent:

   ```
   ssh office2-claude 'systemctl --user stop openclaw-gateway && cp -a ~/.openclaw /data/services/openclaw-preupgrade-$(date -u +%Y%m%dT%H%M%SZ)-stopped'
   ```

3. **Upgrade core, pinned to the step-0 version, not `@latest`:**

   ```
   ssh office2-claude 'export PATH=/home/claude/.local/bin:$PATH; npm install -g openclaw@<version> && /home/claude/.local/bin/openclaw --version'
   ```

   ⚠ **npm ≥11.19 skips install scripts not covered by `allowScripts`** and only
   warns. Read the warning. If `openclaw` is listed, run its postinstall once
   by hand; it prunes stale `dist` files and restores the `fs-safe` prebuild.
   Alternatively, reinstall with `--allow-scripts=openclaw`:

   ```
   ssh office2-claude 'cd /home/claude/.local/lib/node_modules/openclaw && node scripts/postinstall-bundled-plugins.mjs'
   ```

4. **Migrate with `doctor`: report first, then fix.** A new core can refuse
   plugin operations until its config and state migrations have run
   (2026.11.7: `agents.list moved to keyed agents.entries`, state DB
   `audit-events-v2`). So run doctor **before** the plugin update:

   ```
   ssh office2-claude '/home/claude/.local/bin/openclaw plugins update @openclaw/whatsapp@<version> --dry-run'   # lists the pending migrations
   ssh office2-claude '/home/claude/.local/bin/openclaw doctor --lint'                                             # read-only
   ssh office2-claude '/home/claude/.local/bin/openclaw doctor --fix --non-interactive > /data/services/openclaw-upgrade-$(date -u +%Y%m%d)-doctor-fix.txt 2>&1'
   ssh office2-claude '/home/claude/.local/bin/openclaw config validate'
   ```

   Review the migration list with Kent before `--fix`. Read the **whole** output
   afterwards, not just its exit code; look especially at the *Doctor
   changes*, *Cron* and *Heartbeat* sections. Known side effects (2026.11.7):

   - **doctor restarts the gateway itself** when it finishes, even though
     step 2 stopped it. The gateway then runs without any plugin that is
     still the old version.
   - It can **add automations**. On 2026-11-23 it migrated `HEARTBEAT.md` into
     a 30-minute "Proactive check (main)" job, and memory-core added "Memory
     Dreaming Promotion" at 03:00 UTC. Both appear as security-monitor cron
     drift, and neither is in `approved-crons.json`, so felix-trust-scan
     flags them.
     - Dreaming is **disabled on office2** (2026-11-23, #1122). Turn it off with
       `openclaw config set plugins.entries.memory-core.config.dreaming.enabled false`,
       not `cron rm`. memory-core owns the job and re-creates it; the config
       key makes it remove its own job.
     - The migrated "Proactive check" replaces OpenClaw's own heartbeat and
       is separate from felix-heartbeat-gate, which wakes the main session
       with `system event --mode now`. Deleting a provisioned check is
       permanent: doctor keeps a receipt and does not re-create it.
     - A plugin-managed job has no `agentId`, and on 2026-11-23 that
       crashed felix-trust-scan's `state_reconcile`. The scan reported
       `ok: false` and sent no alert. Check `journalctl --user -u
       felix-trust-scan` after any doctor run.
   - It will **not** rewrite our systemd unit while `~/.config` is
     group-writable. It leaves `openclaw-gateway.service.reconcile-*.bak` files
     in `~/.config/systemd/user/`, which appear as unit drift.

5. **Upgrade every channel plugin to the same version.** `plugins update` is
   **offline-only**: it refuses while the gateway runs. Stop the gateway first
   (doctor will have restarted it). This is the #588/#617 guard, so do not skip
   it:

   ```
   ssh office2-claude 'systemctl --user stop openclaw-gateway'
   ssh office2-claude '/home/claude/.local/bin/openclaw plugins update @openclaw/whatsapp@<version> --dry-run'
   ssh office2-claude '/home/claude/.local/bin/openclaw plugins update @openclaw/whatsapp@<version>'   # repeat per plugin
   ssh office2-claude 'for p in ~/.openclaw/npm/projects/*/node_modules/@openclaw/*/package.json; do node -e "const x=require(\"$p\"); console.log(x.name, x.version)"; done'
   ssh office2-claude 'systemctl --user start openclaw-gateway'
   ```

   The previous plugin generation stays on disk until the gateway's next
   start cleans it up. Confirm the *running* version:

   ```
   ssh office2-claude '/home/claude/.local/bin/openclaw gateway status --deep 2>&1 | grep -iE "Gateway version|Runtime|Listening"; /home/claude/.local/bin/openclaw channels status --probe | grep -i whatsapp'
   ```

   Expect WhatsApp `connected`, `health:healthy`, and `dm:allowlist` with the
   single allowed number.

6. **DM-reply smoke (mandatory; this is the #588/#617 verification).** Kent
   sends a WhatsApp DM to Felix and confirms a real reply, not just a typing
   indicator. Then count it, with `T0` set just before the DM:

   ```
   ssh office2-claude 'T0=<YYYY-MM-DDTHH:MM:SSZ> python3 - <<"EOF"
   import datetime, glob, json, os, sqlite3
   t0 = os.environ["T0"]
   ms = int(datetime.datetime.fromisoformat(t0.replace("Z", "+00:00")).timestamp() * 1000)
   inbound = 0
   for f in sorted(glob.glob(os.path.expanduser("~/.openclaw/logs/openclaw-*.log"))):
       for line in open(f):
           try: d = json.loads(line)
           except ValueError: continue
           if d.get("_meta", {}).get("date", "") >= t0 and d.get("2") == "inbound message":
               inbound += 1
   db = sqlite3.connect("file:" + os.path.expanduser("~/.openclaw/state/openclaw.sqlite") + "?mode=ro", uri=True)
   runs = dict(db.execute("select status, count(*) from audit_events where kind=? and action=? and occurred_at>=? and session_key like ? group by status", ("agent_run", "agent.run.finished", ms, "agent:%:whatsapp:direct:%")).fetchall())
   queued = db.execute("select count(*) from delivery_queue_entries").fetchone()[0]
   ok = runs.pop("succeeded", 0)
   print("inbound=%d runs_ok=%d runs_failed=%d delivery_queue=%d" % (inbound, ok, sum(runs.values()), queued))
   EOF'
   ```

   - **Healthy:** `inbound=N runs_ok=N runs_failed=0 delivery_queue=0`.
   - **`inbound=0` after a DM** means the channel layer dropped it, which
     2026.11.7 does silently: no log line, and the web heartbeat shows
     `messagesHandled: 0`. Check `channels.whatsapp.selfChatMode`, which
     **must be `true`** because Felix is linked to Kent's own number, and
     then the allowlist.
   - **Inbound present but `runs_ok=0`** means the agent turn failed or
     stalled. **`delivery_queue>0`** means a send is stuck or retrying.

   2026.11.7 no longer logs `Sending message` / `Sent message` at INFO, so the
   journal-based awk smoke in `openclaw-agent-setup.md` is valid only for
   ≤2026.7.x. **Do not consider the upgrade done until a DM round-trips.**

7. **Re-run the detection check.** Expect `openclaw ecosystem current — no
   updates available`:

   ```
   ssh office2-claude 'cd kg-automation && python3 -m scripts.openclaw.check_ecosystem_updates --dry-run'
   ```

8. **Rebaseline the security monitor.** The apply is out-of-band, so
   felix-deployer does not see it. Follow the manual reset in
   [`security-baseline-ops.md`](<./security-baseline-ops.md>):
   1. Archive the baselines to `/data`.
   2. Reset them.
   3. `diff -r` the archive against the new set and account for every line in
      the issue.

   Expected drift: `openclaw-config.txt` and `openclaw-cron.txt` (any
   doctor-added automations), and the unit files if doctor left `.bak` files.

## Rollback

If the DM smoke fails or the gateway misbehaves, take these steps in order:

1. Stop the gateway.
2. Move `~/.openclaw` aside and restore the step-2 `-stopped` copy.
3. Reinstall the recorded core version: `npm install -g openclaw@<old>`.
4. Reinstall the recorded plugin version: `plugins update
   @openclaw/<plugin>@<old>` (gateway stopped).
5. Start the gateway and re-run the DM smoke.

Reinstalling versions **without** restoring the copy leaves an old binary on
migrated config and state, which newer releases handle only partly. If the
Node major also moved and must be rolled back, do it **after** OpenClaw is
back on a release that supports the old Node. Kent switches the NodeSource
apt source back and installs the exact old `nodejs` version, then the native
modules from step 1b are rebuilt again. Escalate to Kent if a version pin
cannot be resolved. See also `reference_openclaw_upgrade_gotchas` (memory)
for the full list of known traps.

## Related

- [`openclaw-agent-setup.md`](<./openclaw-agent-setup.md>) — H5 troubleshooting
  step (manual plugin-vs-core version check; this runbook is its automated
  sibling).
- [`openclaw-ops.md`](<./openclaw-ops.md>) — general OpenClaw operations.
- [`security-baseline-ops.md`](<./security-baseline-ops.md>) — rebaseline
  procedure.
- Issues: #628 (this capability), #617 / #588 (the breaks that motivated it), #1122 (the 2026.11.7 apply and Node 24 switch that produced v2.0), #1123 (the checker's incompatible-pair defect).
