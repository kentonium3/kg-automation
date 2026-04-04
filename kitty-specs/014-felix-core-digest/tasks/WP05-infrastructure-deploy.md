---
work_package_id: WP05
title: Infrastructure and Deploy
dependencies: [WP03, WP04]
requirement_refs:
- FR-20
- FR-21
- FR-23
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 014-felix-core-digest-WP04
base_commit: 415450a05812b5684cbe16f034f7156f6ebea2ec
created_at: '2026-04-04T15:54:49.207256+00:00'
subtasks: [T022, T023, T024, T025]
shell_pid: '96267'
history:
- date: '2026-04-04'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/
execution_mode: code_change
feature: 014-felix-core-digest
owned_files:
- scripts/office2/felix-core-digest.timer
- scripts/office2/felix-core-digest.service
- scripts/deploy/deploy-f014.sh
---

# WP05: Infrastructure and Deploy

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP03 (summarize.py rewritten), WP04 (AGENTS.md updated)
- **Implementation command**: `spec-kitty implement WP05 --base WP04`
  (WP04 depends on WP02 which parallels WP03, so WP04 is the latest ancestor)

## Objective

Create the systemd timer/service for 15-minute digest generation on office2,
create the deployment script following the F013 pattern, and include the
gitignore update for the second-brain repo.

## Context

### Reference Pattern: second-brain-sync.timer

The 15-minute interval pattern is already established on office2:
```ini
# second-brain-sync.timer
[Unit]
Description=Second Brain sync timer (every 15 minutes)

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# second-brain-sync.service
[Unit]
Description=Second Brain bidirectional git sync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/home/kgale/helper-scripts/second-brain-sync.sh
Environment=HOME=/home/kgale
```

Felix-core-digest uses the same interval pattern but runs under the `claude`
user, not `kgale`.

### Reference Pattern: deploy-f013.sh

Located at `scripts/deploy/deploy-f013.sh`. Key patterns:
- `set -euo pipefail`
- `REPO_ROOT` relative path resolution
- Staged deployment with echo progress messages
- `scp` for file transfers to `office2-claude`
- `ssh office2-claude` for remote commands
- OpenClaw CLI for agent workspace deployment
- Built-in validation

### claude User on office2

- Home: `/home/claude`
- No sudo access
- User-level systemd available (`systemctl --user`)
- SSH alias: `office2-claude`

---

## Subtask T022: Create felix-core-digest.timer

**Purpose**: Systemd user timer that fires every 15 minutes.

**Steps**:
1. Create `scripts/office2/felix-core-digest.timer`:
```ini
[Unit]
Description=Felix Core Digest — agent log summarization (every 15 minutes)

[Timer]
OnBootSec=3min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

2. Key decisions:
   - `OnBootSec=3min`: Slightly offset from second-brain-sync (2min) to avoid collision
   - `OnUnitActiveSec=15min`: Same interval as second-brain-sync
   - `Persistent=true`: Catch up if system was off at trigger time
   - User-level timer (no `[Install] WantedBy=multi-user.target`)

**Files**: `scripts/office2/felix-core-digest.timer` (new)

**Validation**:
- [ ] Timer unit file is valid systemd syntax
- [ ] No sudo-requiring directives
- [ ] Offset from other timers to avoid collision

---

## Subtask T023: Create felix-core-digest.service

**Purpose**: Systemd oneshot service that runs summarize.py.

**Steps**:
1. Create `scripts/office2/felix-core-digest.service`:
```ini
[Unit]
Description=Felix Core Digest — generate agent activity digests
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/observation/summarize.py
Environment=HOME=/home/claude
WorkingDirectory=/home/claude/repos/kg-automation
```

2. Key decisions:
   - `Type=oneshot`: Single execution per trigger
   - Full path to python3 (system Python on office2)
   - `HOME=/home/claude`: Ensures `~/second-brain/` resolves correctly
   - `WorkingDirectory`: Ensures relative paths in config.py resolve
   - No `[Install]` section: timer manages activation
   - Wants network: summarize.py doesn't need network, but consistent with pattern

**Files**: `scripts/office2/felix-core-digest.service` (new)

**Validation**:
- [ ] ExecStart path is correct for claude user on office2
- [ ] HOME environment set for tilde expansion
- [ ] WorkingDirectory enables config.py repo-root detection
- [ ] No sudo-requiring directives

---

## Subtask T024: Create deploy-f014.sh

**Purpose**: Deployment script following F013 pattern for all F014 artifacts.

**Steps**:
1. Create `scripts/deploy/deploy-f014.sh`
2. Read `scripts/deploy/deploy-f013.sh` as reference for structure
3. Implement deployment stages:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "=== F014: Felix Core Digest Deployment ==="

# Stage 1: Deploy log_action.py
echo "--- Stage 1: Deploy log_action.py ---"
scp "$REPO_ROOT/scripts/openclaw/observation/log_action.py" \
  office2-claude:~/repos/kg-automation/scripts/openclaw/observation/

# Stage 2: Deploy updated summarize.py
echo "--- Stage 2: Deploy summarize.py ---"
scp "$REPO_ROOT/scripts/openclaw/observation/summarize.py" \
  office2-claude:~/repos/kg-automation/scripts/openclaw/observation/

# Stage 3: Deploy updated config.py
echo "--- Stage 3: Deploy config.py ---"
scp "$REPO_ROOT/scripts/openclaw/observation/config.py" \
  office2-claude:~/repos/kg-automation/scripts/openclaw/observation/

# Stage 4: Deploy agent-registry.json
echo "--- Stage 4: Deploy agent-registry.json ---"
scp "$REPO_ROOT/docs/constitution/agent-registry.json" \
  office2-claude:~/repos/kg-automation/docs/constitution/

# Stage 5: Deploy AGENTS.md files
echo "--- Stage 5: Deploy AGENTS.md files ---"
for agent in felix-admin-capture felix-admin-habits felix-admin-tasker; do
  scp "$REPO_ROOT/scripts/openclaw/agents/$agent/AGENTS.md" \
    "office2-claude:~/repos/kg-automation/scripts/openclaw/agents/$agent/"
done

# Stage 6: Deploy systemd units
echo "--- Stage 6: Deploy systemd timer/service ---"
ssh office2-claude "mkdir -p ~/.config/systemd/user"
scp "$REPO_ROOT/scripts/office2/felix-core-digest.timer" \
  office2-claude:~/.config/systemd/user/
scp "$REPO_ROOT/scripts/office2/felix-core-digest.service" \
  office2-claude:~/.config/systemd/user/

# Stage 7: Enable and start timer
echo "--- Stage 7: Enable timer ---"
ssh office2-claude "systemctl --user daemon-reload && \
  systemctl --user enable felix-core-digest.timer && \
  systemctl --user start felix-core-digest.timer"

# Stage 8: Update second-brain .gitignore
echo "--- Stage 8: Update .gitignore ---"
ssh office2-claude 'grep -q "^agents/logs/" ~/second-brain/.gitignore || \
  echo "agents/logs/" >> ~/second-brain/.gitignore'

# Stage 9: Create log directories
echo "--- Stage 9: Create log directories ---"
ssh office2-claude "mkdir -p ~/second-brain/agents/logs/{felix-admin-capture,felix-admin-habits,felix-admin-tasker}"

# Stage 10: Validate
echo "--- Stage 10: Validation ---"
ssh office2-claude "systemctl --user status felix-core-digest.timer --no-pager"
ssh office2-claude "python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py --dry-run"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Manual verification checklist:"
echo "  [ ] Timer active: ssh office2-claude 'systemctl --user list-timers'"
echo "  [ ] Dry run clean: ssh office2-claude 'python3 ~/repos/.../summarize.py --dry-run'"
echo "  [ ] Test log write: ssh office2-claude 'python3 ~/repos/.../log_action.py --agent felix-admin-capture --category routine --action test_entry --target test --outcome completed'"
echo "  [ ] Wait 15 min, check: ssh office2-claude 'ls ~/second-brain/notes/Agent-Logs/'"
echo "  [ ] Verify in Obsidian on Mac"
```

4. Make executable: the file should have `#!/usr/bin/env bash` shebang

**Files**: `scripts/deploy/deploy-f014.sh` (new)

**Validation**:
- [ ] Script follows F013 structure (stages, progress messages)
- [ ] All F014 artifacts deployed
- [ ] Timer enabled and started
- [ ] Gitignore updated idempotently (grep before append)
- [ ] Validation step included
- [ ] Manual checklist at end

---

## Subtask T025: Add Gitignore Update and Validation

**Purpose**: Ensure the deploy script handles the gitignore update correctly
and includes comprehensive validation.

**Steps**:
1. The gitignore update in Stage 8 must be idempotent:
   - Check if `agents/logs/` already exists in `.gitignore`
   - Only append if missing
   - Use `grep -q` pattern (already in T024)
2. Validation in Stage 10 must verify:
   - Timer is active and scheduled
   - summarize.py runs without error in dry-run mode
   - log_action.py is callable from the deployed path
3. Add error handling for each SSH command (script uses `set -e`)
4. The deploy script must NOT attempt to run commands that require sudo

**Files**: `scripts/deploy/deploy-f014.sh` (updates to T024 content)

**Validation**:
- [ ] Gitignore update is idempotent (running twice doesn't duplicate)
- [ ] Validation covers timer, summarize.py, and log_action.py
- [ ] No sudo commands in script

---

## Definition of Done

- [ ] `felix-core-digest.timer` created with 15-min interval
- [ ] `felix-core-digest.service` created with correct paths for claude user
- [ ] `deploy-f014.sh` created following F013 pattern
- [ ] Deploy script covers all F014 artifacts
- [ ] Gitignore update is idempotent
- [ ] Validation steps included in deploy script

## Risks

- **User-level systemd**: The claude user must have lingering enabled
  (`loginctl enable-linger claude`) for user timers to run when not logged in.
  The deploy script should check for this and warn if not enabled.
- **Path differences**: Office2 paths (`/home/claude/repos/...`) differ from Mac
  paths (`/Users/kentgale/repos/...`). All paths in systemd units and deploy
  script must use office2 paths.

## Reviewer Guidance

1. Verify all paths use office2 conventions (`/home/claude/...`)
2. Verify timer offset from other timers
3. Check deploy script follows F013 pattern exactly
4. Confirm no sudo commands
5. Verify gitignore update is idempotent
