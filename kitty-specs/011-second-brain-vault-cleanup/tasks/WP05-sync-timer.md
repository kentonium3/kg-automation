---
work_package_id: WP05
title: Bidirectional Git Sync Timer
lane: planned
dependencies: [WP01]
requirement_refs:
- FR-17
- FR-18
- FR-19
- FR-20
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T019, T020, T021, T022, T023, T024]
history:
- date: '2026-04-01T18:30:16Z'
  event: created
  actor: claude
---

# WP05: Bidirectional Git Sync Timer

## Implementation command

```bash
spec-kitty implement WP05 --base WP01
```

## Objective

Create the bidirectional git sync script and systemd timer, initialize the
git repo on office2, and deploy and enable the timer for 15-minute sync
cycles.

## Context

- **second-brain repo on Mac (origin)**: `~/second-brain/` → GitHub (kentonium3/second-brain)
- **second-brain on office2**: `/home/kgale/second-brain/` (NOT a git repo yet)
- **Service user**: `kgale` (C-05)
- **Sync frequency**: Every 15 minutes (NFR-01)
- **Pull strategy**: `git pull --ff-only` (C-06) — no merge commits
- **Auto-commit format**: `chore: auto-sync second-brain from office2` (C-07)
- **Vault excluded**: `notes/` in `.gitignore` (C-01)
- **kgale git credentials**: Set up by Kent in WP01 T003 (SSH key + .gitconfig)
- **Files created by agents**: `agents/logs/inbox-processing-*.md` owned by
  `claude:claude` with mode `rw-rw-r--` — kgale can read (world-readable)

## Subtask guidance

### T019: Create second-brain-sync.sh

**Purpose**: Bidirectional sync script that pulls, auto-commits local changes,
and pushes.

**File**: `scripts/office2/second-brain-sync.sh`

**Content**:
```bash
#!/bin/bash
# Bidirectional git sync for second-brain non-vault content
# Runs every 15 minutes via systemd timer as kgale user
# Vault (notes/) is gitignored — only syncs agent configs, logs, assets

set -euo pipefail

REPO_DIR="/home/kgale/second-brain"
LOG_TAG="second-brain-sync"

log() { logger -t "$LOG_TAG" "$1"; }

cd "$REPO_DIR" || { log "ERROR: Cannot cd to $REPO_DIR"; exit 0; }

# Pull from origin (ff-only to avoid merge commits)
if ! git pull --ff-only origin main 2>&1; then
    log "WARNING: pull --ff-only failed (diverged history?), skipping sync cycle"
    exit 0
fi

# Stage any local changes (respects .gitignore — notes/ excluded)
git add -A

# Commit if there are staged changes
if ! git diff --cached --quiet; then
    git commit -m "chore: auto-sync second-brain from office2"
    if ! git push origin main 2>&1; then
        log "WARNING: push failed, will retry next cycle"
        exit 0
    fi
    log "Synced: committed and pushed local changes"
else
    log "No local changes to sync"
fi
```

**Design decisions**:
- Always `exit 0` — systemd should not mark the unit as failed for transient
  git issues
- `logger` writes to syslog — can be viewed with `journalctl -t second-brain-sync`
- `git add -A` stages all untracked and modified files, but `.gitignore`
  ensures `notes/` is excluded
- `--ff-only` prevents merge commits; if history diverges, the cycle is
  skipped and will resolve on the next push from Mac

**Validation**:
- [ ] Script is syntactically valid: `bash -n scripts/office2/second-brain-sync.sh`
- [ ] Script is executable: check file mode includes `+x`

### T020: Create second-brain-sync.service

**Purpose**: Systemd oneshot unit that runs the sync script.

**File**: `scripts/office2/second-brain-sync.service`

**Content**:
```ini
[Unit]
Description=Second Brain bidirectional git sync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/home/kgale/helper-scripts/second-brain-sync.sh
Environment=HOME=/home/kgale
```

**Notes**:
- No `[Install]` section — the timer handles activation
- `Type=oneshot` — runs once and exits
- `Environment=HOME` ensures git finds `.gitconfig` and SSH keys

### T021: Create second-brain-sync.timer

**Purpose**: Systemd timer that triggers the sync service every 15 minutes.

**File**: `scripts/office2/second-brain-sync.timer`

**Content**:
```ini
[Unit]
Description=Second Brain sync timer (every 15 minutes)

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

**Notes**:
- `OnBootSec=2min` — first run 2 minutes after boot (allows network to settle)
- `OnUnitActiveSec=15min` — subsequent runs every 15 minutes
- `Persistent=true` — if office2 was off, run immediately on next boot

### T022: Initialize git repo on office2

**Purpose**: Set up the second-brain directory as a git clone on office2.

**IMPORTANT**: This requires Kent's git credentials from WP01 T003 to be
complete. If not done, STOP and wait.

**Steps** (present to Kent to run as kgale):
```bash
ssh office2-kgale
cd /home/kgale/second-brain

# Initialize and connect to origin
git init
git remote add origin git@github.com:kentonium3/second-brain.git

# Pull existing content from Mac (non-vault files)
git fetch origin
git reset --hard origin/main

# Verify
git status
git log --oneline -3
```

**Alternative** if the directory already has content that would conflict:
```bash
# Clone to a temp location, then move .git into existing dir
cd /tmp
git clone git@github.com:kentonium3/second-brain.git sb-temp
mv sb-temp/.git /home/kgale/second-brain/.git
rm -rf sb-temp
cd /home/kgale/second-brain
git checkout -- .
```

**Validation**:
- [ ] `git remote -v` shows origin pointing to kentonium3/second-brain
- [ ] `git status` shows clean or only untracked files in `notes/` (gitignored)

### T023: Create .gitignore on office2

**Purpose**: Ensure `notes/` is excluded from git tracking on office2.

**Note**: If the pull from origin in T022 already brought down the `.gitignore`
from Mac, this step may already be done. Verify first.

**File**: `/home/kgale/second-brain/.gitignore`

**Expected content** (should match Mac):
```
# Vault content — managed by Obsidian Sync, not git
notes/

# macOS
.DS_Store
**/.DS_Store
```

**Validation**:
- [ ] `.gitignore` exists and contains `notes/`
- [ ] `git status` does not show any files under `notes/` as untracked

### T024: Deploy sync script and timer, enable and start

**Purpose**: Copy the sync script and systemd units to office2 and activate.

**Steps**:
1. Copy files to office2:
   ```bash
   scp scripts/office2/second-brain-sync.sh office2-claude:/tmp/
   scp scripts/office2/second-brain-sync.service office2-claude:/tmp/
   scp scripts/office2/second-brain-sync.timer office2-claude:/tmp/
   ```

2. Present to Kent to run as kgale:
   ```bash
   ssh office2-kgale

   # Deploy script
   cp /tmp/second-brain-sync.sh ~/helper-scripts/
   chmod +x ~/helper-scripts/second-brain-sync.sh

   # Deploy systemd units
   cp /tmp/second-brain-sync.service ~/.config/systemd/user/
   cp /tmp/second-brain-sync.timer ~/.config/systemd/user/

   # Enable and start
   systemctl --user daemon-reload
   systemctl --user enable second-brain-sync.timer
   systemctl --user start second-brain-sync.timer

   # Verify
   systemctl --user status second-brain-sync.timer
   systemctl --user list-timers | grep second-brain
   ```

3. Trigger a manual run to verify:
   ```bash
   systemctl --user start second-brain-sync.service
   journalctl --user -u second-brain-sync.service --no-pager -n 20
   ```

**Validation**:
- [ ] Timer shows active (waiting)
- [ ] Manual run completes without errors
- [ ] `journalctl -t second-brain-sync` shows log messages

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`

## Definition of Done

- Sync script, service, and timer files created in the repo
- Git repo initialized on office2 with origin connected
- `notes/` excluded via `.gitignore` on office2
- Timer deployed, enabled, and running on office2
- Manual sync run completes successfully

## Risks

- **Git credentials not set up**: T022 depends on WP01 T003. If Kent hasn't
  completed the credential setup, this entire WP is blocked.
- **Existing files on office2 conflict with pull**: The `git reset --hard`
  approach overwrites local non-vault files with origin versions. If there
  are agent-created files not yet pushed, they'd be lost. Check for local
  changes first.
- **SSH key passphrase**: If Kent set a passphrase on the SSH key, the
  automated sync script won't be able to authenticate without an ssh-agent.
  Recommend no passphrase for the deploy key.
