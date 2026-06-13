---
title: OpenClaw Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# OpenClaw Operations Runbook

This runbook covers operations for the OpenClaw gateway service on office2.

## Installed Version

- **Version**: OpenClaw 2026.6.5 (upgraded from 2026.3.24 on 2026-06-12)
- **Installation**: `sudo npm install -g openclaw@<version>` (global)
- **Binary**: `/usr/bin/openclaw` → symlink to `/usr/lib/node_modules/openclaw/openclaw.mjs`
- **Config**: `/home/claude/.openclaw/openclaw.json`
- **Per-agent auth (2026.6+)**: `~/.openclaw/agents/<id>/agent/openclaw-agent.sqlite`
  (replaces the legacy `auth-profiles.json` file-based store; see
  [Version Updates](<#version-updates>) for the migration step)

## Service Management

OpenClaw runs as a **user-level systemd service** for the claude user with lingering enabled.

**Service name**: `openclaw-gateway`

### Check status

```bash
# As claude user (no sudo required):
systemctl --user status openclaw-gateway
```

### Start / Stop / Restart

```bash
# As claude user (no sudo required for user-level service):
systemctl --user start openclaw-gateway
systemctl --user stop openclaw-gateway
systemctl --user restart openclaw-gateway
```

### View logs

```bash
journalctl --user -u openclaw-gateway -f              # follow live
journalctl --user -u openclaw-gateway --since "1 hour ago"
journalctl --user -u openclaw-gateway --since today
```

### Lingering

Lingering is enabled for the claude user, which means the service continues running after logout:

```bash
# Check lingering status:
ls /var/lib/systemd/linger/ | grep claude

# If lingering is lost (requires sudo — Kent runs):
sudo loginctl enable-linger claude
```

## Credentials

### API Key (Anthropic)

- **Storage**: OpenClaw native auth at `/home/claude/.openclaw/agents/main/agent/auth-profiles.json` (mode 600)
- **Backup copy**: `/data/services/openclaw/secrets/anthropic` (mode 600)
- **Rotation procedure**:
  1. Get new API key from https://console.anthropic.com/settings/keys
  2. Update the auth-profiles.json file (edit the `key` field)
  3. Update the backup copy in `/data/services/openclaw/secrets/anthropic`
  4. Restart: `systemctl --user restart openclaw-gateway`
  5. Verify logs show successful API connection

### Vikunja API Token

- **Storage**: `/data/services/openclaw/secrets/vikunja-api` (mode 600)
- **Token name in Vikunja**: `openclaw-agent`
- **Rotation procedure**:
  1. Generate new token in Vikunja UI (Settings → API Tokens)
  2. Revoke old token in Vikunja UI
  3. Update: `echo '<NEW_TOKEN>' > /data/services/openclaw/secrets/vikunja-api`
  4. Verify: `curl -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" http://100.92.197.90:3456/api/v1/info`

### Credential Store

```
/data/services/openclaw/secrets/    (mode 700, claude-owned)
├── anthropic                       (mode 600, backup of API key)
└── vikunja-api                     (mode 600, persistent Vikunja token)
```

## Version Updates

1. **Check release notes** for breaking changes — pay attention to auth
   storage, cron storage, plugin packaging, and any config schema changes.
   See [Known upgrade gotchas](<#known-upgrade-gotchas>) below.
2. **Verify a recent backup exists**: `restic snapshots --latest 1` (with correct env vars)
3. **Verify no missions are in flight**: `openclaw cron list` (no `error` state
   except known-stale displays) and any in-progress agent sessions are quiesced.
4. **Install new version** (Kent runs): `sudo npm install -g openclaw@<new-version>`
5. **Restart**: `systemctl --user restart openclaw-gateway`
6. **Run the post-upgrade migration sweep** (REQUIRED after every upgrade,
   even minor ones — `openclaw doctor` without `--fix` does NOT surface
   pending migrations, and `--post-upgrade` only reports plugin-compat
   findings):

   ```bash
   ssh office2-claude 'openclaw doctor --fix --non-interactive'
   ```

   This runs the file→SQLite auth migration (importing any per-agent
   `auth-profiles.json` into `openclaw-agent.sqlite`), normalizes legacy
   cron job storage, and applies any other safe migrations the new version
   knows about. Doctor preserves timestamped backups of every file it
   migrates (`*.sqlite-import.<ts>.bak`).
7. **Update the captured unit file** in `scripts/openclaw/openclaw-gateway.service` (version in Description)
8. **Verify**: `openclaw --version` and check logs
9. **Verify per-agent auth health** — manually run one cron job per
   isolated agent to exercise the openclaw-gateway → sub-agent → provider
   API path end-to-end:

   ```bash
   ssh office2-claude 'openclaw cron run <inbox-7am-id>'  # felix-admin-capture
   ssh office2-claude 'openclaw cron run <habits-morning-id>'  # felix-admin-habits
   # ...one per affected agent
   ssh office2-claude 'openclaw cron runs --id <id> --limit 1'  # confirm status=ok
   ```

   IMPORTANT: the `openclaw cron list` "Status" column shows the LAST
   scheduled run's outcome, not current health. Treat post-upgrade `error`
   rows as stale until you've manually rerun one job per affected agent.
10. **Commit** the version change to the repo
11. **Rebaseline** the security-monitor audited surfaces per
    [`docs/runbooks/security-baseline-ops.md`](<./security-baseline-ops.md>)
    if any audited surface changed.

### Known upgrade gotchas

- **2026.6.x — auth storage moved to per-agent SQLite.** The runtime now
  reads from `~/.openclaw/agents/<id>/agent/openclaw-agent.sqlite`. Until
  `openclaw doctor --fix` is run after the upgrade, sub-agents whose
  `auth-profiles.json` files are empty (the kg-automation pattern, where
  sub-agents inherit from `main`) will fail every cron job with
  `FailoverError: No API key found for provider "anthropic"`. The error
  message's hint to run `openclaw agents add <id>` is misleading — that
  command refuses to operate on existing agents. The actual fix is
  `openclaw doctor --fix`. (See: incident 2026-06-12, Felix outage of
  ~9 hours between gateway restart and rotation.)
- **2026.6.x — `openclaw auth set` is gone.** The CLI for writing an
  auth profile is now `openclaw models auth paste-api-key --provider <p>
  --profile-id <p>:<id> --agent <a>`. The
  [`anthropic-rotate.sh`](<../../scripts/security/anthropic-rotate.sh>)
  helper uses the new form.
- **Plugin packaging — channels may move to external plugins** between
  versions. Verify after upgrade: `openclaw channels list` should still
  show every channel you had before; `openclaw doctor` will flag missing
  ones if `plugins.allow` is not set.

### Per-agent auth-row shadow (post-`doctor --fix`)

**Symptom**: a sub-agent's cron jobs fail with `FailoverError: LLM error
authentication_error: invalid x-api-key` while sibling sub-agents continue
to work. WhatsApp escalations from `inbox-5pm` / `inbox-10pm` / `inbox-7am`
are the canonical signal.

**Cause**: `openclaw doctor --fix` migrates a sub-agent's pre-existing
`auth-profiles.json` into the per-agent SQLite store
(`~/.openclaw/agents/<id>/agent/openclaw-agent.sqlite`, tables
`auth_profile_store` + `auth_profile_state`). The migrated row OVERRIDES
the read-through inheritance from `main`. If the imported value is stale,
every LLM call routed through that sub-agent fails with `invalid x-api-key`.
Healthy state for any sub-agent is **zero rows** in both tables — the
sub-agent should inherit from `main` via read-through.

**Detection**: run `anthropic-verify --check` (see
[`scripts/security/anthropic-verify.sh`](<../../scripts/security/anthropic-verify.sh>)).
Exit code 2 = shadow detected; the finding names the affected agent
and the specific table.

**Remediation**:

```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --repair
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --check
```

The `--repair` mode writes a `.pre-repair.<unix-ts>.bak` sibling file
before clearing the rows. The final `--check` confirms the shadow is
gone (exit 0 = healthy).

**Reference**: `#596` (the post-incident write-up that uncovered this
failure mode), `#597` (this preventive surface — the verifier and the
two runbook addenda).

### Plaintext / SQLite drift

**Symptom**: `felix-doc-auditor-driver` or `felix-heartbeat-gate` ticks
emit `invalid x-api-key` errors while openclaw-gateway-routed agents
continue to work. The two consumer classes are on different keys.

**Cause**: `/data/services/openclaw/secrets/anthropic` (plaintext file
consumed by the non-openclaw Python drivers) has drifted from `main`'s
SQLite store. Usually triggered by an Anthropic key rotation that went
through `openclaw models auth paste-api-key` directly without going
through [`anthropic-rotate.sh`](<../../scripts/security/anthropic-rotate.sh>),
which updates both substrates atomically.

**Detection**: `anthropic-verify --check` reports a `drift` finding with
both sha256[:8] fingerprints. Exit code 3.

**Remediation**:

```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --repair
```

The `--repair` mode atomically rewrites the plaintext file from `main`'s
SQLite value via tmp-rename, preserving mode 0600. No gateway restart is
needed — the Python consumers re-read the file on their next tick.

**Reference**: `#597`.

### Post-`doctor --fix` and post-rotation gate (recommended)

Always run `anthropic-verify --check` after any of:

- `openclaw doctor --fix` (any invocation, including the post-upgrade
  migration sweep documented above).
- `anthropic-rotate.sh` (already invoked automatically at end-of-rotation
  as a fail-closed gate per `#597` FR-012 — operators do not need to
  re-run it).
- Manual edits to any of the three auth substrates: `main`'s SQLite
  (`/home/claude/.openclaw/agents/main/agent/openclaw-agent.sqlite`), the
  plaintext file (`/data/services/openclaw/secrets/anthropic`), or any
  sub-agent SQLite (`~/.openclaw/agents/<id>/agent/openclaw-agent.sqlite`).

Output is fingerprints (sha256[:8]) plus per-substrate verdicts. No key
values are printed.

### Rollback

1. `sudo npm install -g openclaw@<previous-version>`
2. `systemctl --user restart openclaw-gateway`
3. Verify service is healthy

## API Connectivity Check

```bash
# Verify no proxy in logs:
journalctl --user -u openclaw-gateway --since "1 hour ago" | grep -i "litellm\|proxy\|openai-compat"
# Expected: no output

# Verify gateway is responding:
curl -s http://127.0.0.1:18789/
```

## Skill Directory

Skills are managed by OpenClaw at `/home/claude/.openclaw/skills/`.
Skills committed to the kg-automation repo live at `scripts/openclaw/skills/`.

```bash
# List installed skills:
openclaw skills list

# Install a skill from the workspace:
openclaw skills install <skill-slug>

# Search ClawHub (public registry) for community skills:
openclaw skills search "<query>"
```

### ClawHub — Public Skill Registry

ClawHub (`clawhub.ai`) is the public registry for OpenClaw skills. It supports
discovery, versioning, and publishing. The kg-automation skills can be published
to ClawHub for backup and versioning using the `clawhub` CLI.

**Constitution policy**: Community skills from ClawHub must be read and reviewed
before installation. Never run `openclaw skills install <community-skill>` without
first reading the skill's SKILL.md and any supporting files. This is a hard
boundary — no exceptions.

**Publishing own skills** (backup/versioning — permitted):
```bash
# Install clawhub CLI (if needed):
npm i -g clawhub

# Publish a skill:
clawhub skill publish ./scripts/openclaw/skills/whisper \
  --slug kg-whisper --name "Whisper Transcription" --version 1.0.0 --tags latest

# Sync all skills:
clawhub sync --all
```

## Data and Backups

- **Workspace**: `/data/services/openclaw/data/` (in Restic backup scope)
- **Config**: `/home/claude/.openclaw/` (in Restic backup scope via `/home/claude/`)
- **Sessions**: `/home/claude/.openclaw/agents/main/sessions/`

## Security baseline trigger

OpenClaw changes that touch any of the audited surfaces (cron entries,
gateway service state, the contents of `~/.openclaw/`) require a
baseline reset afterwards. Triggers include:

- Initial OpenClaw install or version upgrade
- Adding or removing an OpenClaw agent or cron job
- Bulk agent-config sweeps that change `openclaw-config.txt` content

For the procedure, see [Security Baseline Operations](<./security-baseline-ops.md>).

## Gateway Access

- **Local URL**: `http://127.0.0.1:18789/`
- **Binding**: Loopback only (not exposed to network)
- **Gateway port**: 18789
- **Dashboard**: `openclaw dashboard --no-open` (prints URL with auth token)

## Governance

Felix agents operate under a formal governance framework established in F012.
All agents are registered, assigned an autonomy level, and bound by the
Felix Constitution.

### Key Documents

| Document | Path | Purpose |
|----------|------|---------|
| Felix Constitution | `docs/constitution/FELIX-CONSTITUTION.md` | Top-level governance — autonomy levels, principles, boundaries |
| Agent Registry (human-readable) | `docs/constitution/AGENT-REGISTRY.md` | Quick-reference agent list with current autonomy levels |
| Agent Registry (machine-readable) | `docs/constitution/agent-registry.json` | Authoritative agent state, transition history |
| Governance Runbook | `docs/runbooks/felix-governance.md` | Operational procedures for promotions, demotions, registration |

### Quick Reference

- All agents start at **Assisted (Level 1)** and require explicit promotion
- Each agent's `AGENTS.md` includes a governance preamble referencing the constitution
- The constitution is the tiebreaker when standing orders are ambiguous
- See the [Felix Governance Runbook](<./felix-governance.md>) for all procedures
