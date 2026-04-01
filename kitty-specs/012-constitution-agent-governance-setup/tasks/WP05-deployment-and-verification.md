---
work_package_id: WP05
title: Deployment & Verification
lane: planned
dependencies: [WP01, WP02, WP03, WP04]
requirement_refs:
- FR-016
- FR-018
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning branch is main. Final merge target is main. Actual base_branch may differ for stacked WPs during implement.
subtasks: [T018, T019, T020, T021, T022]
history:
- date: '2026-04-01T22:12:34Z'
  event: created
  agent: claude
priority: P2
---

# WP05: Deployment & Verification

## Implementation Command

```bash
spec-kitty implement WP05 --base WP04
```

Depends on all previous WPs — deploys everything to office2.

## Objective

Deploy all F012 artifacts to office2 and verify the complete system works end-to-end: governance docs accessible, intelligence layer runs, digests appear in Obsidian, and agent workspaces are updated.

## Context

- **Spec**: FR-016 (deploy skill), FR-018 (deploy agent files)
- **Plan**: Implementation Sequence step 11
- **Quickstart**: `kitty-specs/012-constitution-agent-governance-setup/quickstart.md` (verification steps)
- **Constraint C-003**: All actions on office2 use the `claude` user account, never `kgale`

**SSH access**: `ssh office2-claude`

**Key paths on office2:**

| What | Path |
|------|------|
| OpenClaw skills | `/home/claude/.openclaw/skills/` |
| Agent workspaces | `/data/services/openclaw/inbox-agent/`, `/data/services/openclaw/habits-agent/` |
| Agent logs | `/home/kgale/second-brain/agents/logs/` |
| Obsidian vault notes | `/home/kgale/second-brain/notes/` |
| Constitution docs (deployed) | Where the agent workspaces or a shared location references them |

## Subtask T018: Deploy Governance Docs to office2

**Purpose**: Make the constitution, registry, and runbook available on office2 where agents can reference them.

**Files to deploy:**
- `docs/constitution/FELIX-CONSTITUTION.md`
- `docs/constitution/agent-registry.json`
- `docs/constitution/AGENT-REGISTRY.md`
- `docs/handbooks/felix-governance.md`

**Deployment approach:**
The repo is already cloned on office2. The simplest approach is to pull the latest from main on office2:

```bash
ssh office2-claude "cd /path/to/kg-automation && git pull origin main"
```

**Determine the repo path on office2** first by checking:
- The agent workspace configs reference the repo
- `service-inventory.json` may have the path
- Or check: `ssh office2-claude "find /home/claude -name 'kg-automation' -type d 2>/dev/null"`

**Validation**:
- [ ] Constitution file accessible on office2
- [ ] Registry JSON accessible and parseable on office2
- [ ] `ssh office2-claude "python3 -c \"import json; json.load(open('<path>/docs/constitution/agent-registry.json'))\""`

## Subtask T019: Deploy Skill-Authoring Skill and Updated Agent Workspaces

**Purpose**: Install the skill-authoring skill into OpenClaw's skill directory and update agent workspaces with the new AGENTS.md files.

**Skill deployment:**

```bash
# Option A: If OpenClaw has a skill install command
ssh office2-claude "openclaw skills install skill-author"

# Option B: Manual copy to skill directory
ssh office2-claude "cp -r /path/to/kg-automation/scripts/openclaw/skills/skill-author/ /home/claude/.openclaw/skills/skill-author/"
```

**Check which approach is correct** by reviewing `docs/handbooks/openclaw-ops.md` for the skill deployment procedure.

**Agent workspace deployment:**
The agent workspace files need to be synced to the deployed workspace directories. Check how previous features (F008, F009) deployed agent files:

```bash
# Likely approach — sync from repo to workspace
ssh office2-claude "cp scripts/openclaw/agents/felix-admin-capture/AGENTS.md /data/services/openclaw/inbox-agent/agent/AGENTS.md"
ssh office2-claude "cp scripts/openclaw/agents/felix-admin-habits/AGENTS.md /data/services/openclaw/habits-agent/agent/AGENTS.md"
```

**Important**: Verify the exact workspace structure before copying. The deployed workspace may have a different directory layout than the repo.

**Validation**:
- [ ] `ssh office2-claude "ls /home/claude/.openclaw/skills/skill-author/SKILL.md"` succeeds
- [ ] Both agents' AGENTS.md updated in their deployed workspaces
- [ ] Verify preamble is present: `ssh office2-claude "head -15 /data/services/openclaw/inbox-agent/agent/AGENTS.md"`

## Subtask T020: Set Up Intelligence Layer on office2

**Purpose**: Deploy the summarization script, configure cron, and create the Obsidian output directory.

**Step 1: Deploy the script**

```bash
# Create directory
ssh office2-claude "mkdir -p /data/services/openclaw/observation"

# Copy script and config
scp scripts/openclaw/observation/summarize.py office2-claude:/data/services/openclaw/observation/
scp scripts/openclaw/observation/config.py office2-claude:/data/services/openclaw/observation/
```

Or if using the repo pull approach from T018, the files are already on office2 at the repo path.

**Step 2: Create Obsidian output directory**

```bash
ssh office2-claude "mkdir -p /home/kgale/second-brain/notes/00-System/agent-activity"
```

**Note**: This directory is inside the Obsidian vault (`notes/`), which is within Obsidian Sync scope. Verify the claude user has write access (via the `secondbrain` group).

**Step 3: Configure cron**

```bash
# 7:00 PM ET = 23:00 UTC (EDT) or 00:00 UTC next day (EST)
# Use America/New_York timezone in cron
ssh office2-claude "crontab -l > /tmp/crontab.bak 2>/dev/null; echo '0 23 * * * cd /path/to/kg-automation && python3 scripts/openclaw/observation/summarize.py >> /tmp/observation-cron.log 2>&1' >> /tmp/crontab.bak && crontab /tmp/crontab.bak"
```

**Timezone note**: office2 may run in UTC. 7:00 PM ET is:
- 23:00 UTC during EDT (March-November)
- 00:00 UTC during EST (November-March)

Check office2's timezone: `ssh office2-claude "timedatectl"` and adjust the cron accordingly.

**Validation**:
- [ ] Script exists on office2: `ssh office2-claude "ls /data/services/openclaw/observation/summarize.py"`
- [ ] Output directory exists: `ssh office2-claude "ls -la /home/kgale/second-brain/notes/00-System/agent-activity/"`
- [ ] Cron entry exists: `ssh office2-claude "crontab -l | grep summarize"`

## Subtask T021: Run Dry-Run Test

**Purpose**: Verify the intelligence layer can parse existing logs and produce a digest without errors.

**Steps:**

```bash
# 1. Check for existing log files
ssh office2-claude "ls /home/kgale/second-brain/agents/logs/"

# 2. Run dry-run
ssh office2-claude "cd /path/to/kg-automation && python3 scripts/openclaw/observation/summarize.py --dry-run"
```

**Expected output**: The script should:
- Find and parse today's log files (or most recent available)
- Print the consolidated digest to stdout (dry-run = no file writes)
- Show no errors

**If no log files exist for today**: The script should output "No agent activity recorded today" (see T008 error handling). This is a valid test — it confirms the script handles the empty case gracefully.

**If errors occur**: Note them for debugging. Common issues:
- Registry path incorrect — adjust ObservationConfig
- Log directory path incorrect — verify path on office2
- Log format doesn't match parser expectations — compare actual logs to fixture format

**Validation**:
- [ ] Dry-run completes without errors
- [ ] Output is a valid digest format (or empty-day message)
- [ ] No Python tracebacks

## Subtask T022: Verify Obsidian Sync

**Purpose**: Confirm that digest files written to the vault on office2 appear in Obsidian on Mac (and eventually iPhone).

**Steps:**

1. **Run a real summarization** (not dry-run):
   ```bash
   ssh office2-claude "cd /path/to/kg-automation && python3 scripts/openclaw/observation/summarize.py"
   ```

2. **Check files exist on office2**:
   ```bash
   ssh office2-claude "ls -la /home/kgale/second-brain/notes/00-System/agent-activity/"
   ssh office2-claude "cat /home/kgale/second-brain/notes/00-System/agent-activity/overview.md"
   ```

3. **Wait for Obsidian Sync** (typically near real-time, up to a few minutes)

4. **Check local vault on Mac**:
   ```bash
   ls ~/second-brain/vault/Notes/00-System/agent-activity/
   cat ~/second-brain/vault/Notes/00-System/agent-activity/overview.md
   ```

**Note**: The local vault path may differ. Check the CLAUDE.md for the correct local Obsidian vault path (`~/second-brain/` or `~/second-brain/vault/Notes/`).

**If sync doesn't work**:
- Verify the `notes/00-System/` directory is within Obsidian Sync scope
- Check if the `ob` sync daemon is running on office2
- This is a known gap (see memory: Obsidian Sync gap) — office2 vault sync is git-based, not Obsidian Sync. If Obsidian Sync doesn't cover this path, the digest files will need to sync via git instead. Document this in the runbook.

**Validation**:
- [ ] Digest files written to office2 vault
- [ ] Files appear in local Obsidian (Mac) within reasonable time
- [ ] If Obsidian Sync doesn't cover this path, document the limitation and alternative access method

## Definition of Done

- [ ] Constitution and registry accessible on office2
- [ ] Skill-authoring skill deployed to OpenClaw skills directory
- [ ] Both agents' AGENTS.md updated in deployed workspaces on office2
- [ ] Intelligence layer script deployed on office2
- [ ] Cron job configured (7 PM ET daily)
- [ ] Agent-activity directory created in Obsidian vault
- [ ] Dry-run test passes
- [ ] Real run produces digest files in vault
- [ ] Obsidian Sync status documented (working or limitation noted)
- [ ] All deployment steps documented in commit message for reproducibility

## Risks

| Risk | Mitigation |
|------|-----------|
| SSH access fails | Verify `ssh office2-claude` works before starting any deployment |
| Cron timezone wrong | Check office2 timezone with timedatectl; convert 7 PM ET to correct UTC offset |
| Obsidian Sync doesn't cover `00-System/` | Document limitation; alternative is git-based sync or manual check |
| Agent workspace paths differ from expected | Read service-inventory.json for actual deployed paths before copying |
| Permission denied on vault writes | Verify claude user has secondbrain group membership |

## Reviewer Guidance

- Verify all SSH commands use `office2-claude` (never `office2-kgale`)
- Verify cron timezone is correct for the current DST state
- Check that dry-run produces valid output format
- If Obsidian Sync doesn't work for this path, verify the limitation is documented in felix-governance.md runbook
- Verify no `sudo` commands are used (C-003: claude user has no sudo access)
