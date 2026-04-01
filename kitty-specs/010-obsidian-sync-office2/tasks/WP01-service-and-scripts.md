---
work_package_id: WP01
title: Systemd Service and Sync Scripts
lane: "doing"
dependencies: []
requirement_refs:
- FR-01
- FR-02
- FR-03
- FR-04
- FR-05
- FR-08
- FR-09
- FR-10
- FR-16
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: fed93f37768f5e4863964f90dd4d51b720aa3df8
created_at: '2026-04-01T15:23:53.181349+00:00'
subtasks: [T001, T002, T003, T004, T005]
agent: "claude-code"
shell_pid: "82860"
history:
- date: '2026-04-01T15:17:40Z'
  event: created
  actor: claude
---

# WP01: Systemd Service and Sync Scripts

## Implementation command

```bash
spec-kitty implement WP01
```

## Objective

Create all the systemd unit files and scripts needed for Obsidian Sync on
office2: the continuous sync service, the daily git snapshot script, and
the snapshot timer. These files are committed to the repo and later copied
to office2 by Kent during manual setup.

## Context

- **Target directory in repo**: `scripts/office2/`
- **Deploy target on office2**: Kent copies files to `~/.config/systemd/user/` and `~/helper-scripts/`
- **Vault path on office2**: `/home/kgale/second-brain/vault`
- **`ob` CLI**: `/usr/bin/ob` v0.0.8
- **User**: All services run as `kgale` (vault owner), not `claude` or root
- **Git repo on office2**: `/home/kgale/second-brain/` (contains `.git/`)
- **Inbox processing windows to avoid**: 7AM, 12PM, 6PM ET
- **Snapshot schedule**: 2AM ET daily

## Subtask guidance

### T001: Create `scripts/office2/obsidian-sync.service`

**Purpose**: Systemd user unit that runs `ob sync --continuous` to maintain
a persistent Obsidian Sync connection.

**Steps**:
1. Create `scripts/office2/obsidian-sync.service` with:
   ```ini
   [Unit]
   Description=Obsidian Sync (continuous)
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   ExecStart=/usr/bin/ob sync --path /home/kgale/second-brain/vault --continuous
   Restart=on-failure
   RestartSec=30
   Environment=HOME=/home/kgale

   [Install]
   WantedBy=default.target
   ```

2. Key design decisions:
   - `Type=simple` because `ob sync --continuous` runs in the foreground
   - `Restart=on-failure` with 30-second delay for transient network issues
   - `After=network-online.target` ensures network is ready before sync starts
   - `Environment=HOME=/home/kgale` ensures `ob` finds its auth credentials
   - `WantedBy=default.target` for automatic start on user login/linger

**Files**: `scripts/office2/obsidian-sync.service` (new, ~15 lines)

**Validation**:
- [ ] Unit file passes `systemd-analyze verify` syntax check
- [ ] ExecStart path matches installed `ob` location (`/usr/bin/ob`)
- [ ] Vault path matches felix-admin-capture's TOOLS.md (`/home/kgale/second-brain/vault`)

---

### T002: Create `scripts/office2/vault-snapshot.sh`

**Purpose**: Outbound-only git snapshot script that commits and pushes the
current vault state for backup/version history. Never pulls or resets.

**Steps**:
1. Create `scripts/office2/vault-snapshot.sh`:
   ```bash
   #!/usr/bin/env bash
   # vault-snapshot.sh — Daily git snapshot of Obsidian vault
   # Outbound-only: add, commit, push. NEVER pulls or resets.
   # Obsidian Sync is authoritative for live state.
   set -euo pipefail

   VAULT_REPO="/home/kgale/second-brain"
   cd "$VAULT_REPO"

   # Check for changes
   if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
       echo "No changes to snapshot."
       exit 0
   fi

   # Stage all changes (respects .gitignore)
   git add -A

   # Commit with date-stamped message
   git commit -m "vault snapshot $(date +%Y-%m-%d-%H%M)"

   # Push to origin
   git push origin main

   echo "Snapshot complete: $(git log --oneline -1)"
   ```

2. Mark executable: `chmod +x scripts/office2/vault-snapshot.sh`

**Key design decisions**:
- No `git pull` or `git fetch` — outbound only
- `git add -A` respects `.gitignore` (Obsidian metadata excluded)
- Exit 0 on no changes (don't fail the timer)
- Simple date-stamped commit message for easy log scanning

**Files**: `scripts/office2/vault-snapshot.sh` (new, ~25 lines)

**Validation**:
- [ ] Script is executable
- [ ] No `git pull`, `git fetch`, `git reset`, or `git checkout` commands present
- [ ] Handles "no changes" case gracefully (exit 0)

---

### T003: Create `scripts/office2/vault-snapshot.service`

**Purpose**: Systemd service unit that runs the snapshot script. Paired with
the timer in T004.

**Steps**:
1. Create `scripts/office2/vault-snapshot.service`:
   ```ini
   [Unit]
   Description=Obsidian Vault Git Snapshot
   After=network-online.target

   [Service]
   Type=oneshot
   ExecStart=/home/kgale/helper-scripts/vault-snapshot.sh
   Environment=HOME=/home/kgale
   ```

2. Key design decisions:
   - `Type=oneshot` because the script runs and exits
   - No `[Install]` section — activated by the timer only
   - `Environment=HOME` for git config access

**Files**: `scripts/office2/vault-snapshot.service` (new, ~10 lines)

**Validation**:
- [ ] ExecStart path matches where Kent will copy the script (`~/helper-scripts/`)
- [ ] Type is `oneshot` (appropriate for timer-triggered scripts)

---

### T004: Create `scripts/office2/vault-snapshot.timer`

**Purpose**: Systemd timer that triggers the snapshot service daily at 2AM ET.

**Steps**:
1. Create `scripts/office2/vault-snapshot.timer`:
   ```ini
   [Unit]
   Description=Daily Obsidian Vault Git Snapshot (2AM ET)

   [Timer]
   OnCalendar=*-*-* 02:00:00 America/New_York
   Persistent=true
   RandomizedDelaySec=300

   [Install]
   WantedBy=timers.target
   ```

2. Key design decisions:
   - `OnCalendar` with timezone ensures correct ET scheduling regardless of server TZ
   - `Persistent=true` means if office2 was off at 2AM, it runs on next boot
   - `RandomizedDelaySec=300` (5 min) adds jitter to avoid exact-second contention
   - 2AM ET is well outside inbox processing windows (7AM, 12PM, 6PM ET)

**Files**: `scripts/office2/vault-snapshot.timer` (new, ~12 lines)

**Validation**:
- [ ] Timer fires at 2AM ET (not UTC)
- [ ] Schedule does not overlap with inbox processing crons (7AM, 12PM, 6PM ET)
- [ ] `Persistent=true` set for catch-up after downtime

---

### T005: Create `scripts/office2/gitignore-additions.txt`

**Purpose**: Document the `.gitignore` additions needed for the second-brain
repo to exclude Obsidian Sync metadata files from git snapshots.

**Steps**:
1. Create `scripts/office2/gitignore-additions.txt` with:
   ```
   # Obsidian workspace state (device-specific, changes constantly)
   .obsidian/workspace.json
   .obsidian/workspace-mobile.json

   # Obsidian Sync internal metadata
   .obsidian/sync-*.json

   # Privacy boundary (constitutional hard boundary)
   02-Growth/_private/
   ```

2. This is a reference file. Kent appends these entries to
   `/home/kgale/second-brain/.gitignore` during manual setup.

**Files**: `scripts/office2/gitignore-additions.txt` (new, ~10 lines)

**Validation**:
- [ ] Excludes workspace files that change on every Obsidian open
- [ ] Excludes sync metadata that is Obsidian Sync internal state
- [ ] Includes privacy boundary exclusion

## Definition of Done

- [ ] `scripts/office2/obsidian-sync.service` exists and is syntactically valid
- [ ] `scripts/office2/vault-snapshot.sh` exists and is executable
- [ ] `scripts/office2/vault-snapshot.service` exists and is syntactically valid
- [ ] `scripts/office2/vault-snapshot.timer` exists with 2AM ET schedule
- [ ] `scripts/office2/gitignore-additions.txt` documents required `.gitignore` entries
- [ ] No secrets or credentials in any committed file
- [ ] All files reference correct vault path (`/home/kgale/second-brain/vault`)

## Risks

- `ob sync --continuous` may require additional flags not visible in `--help` (e.g., for reconnection). Mitigation: test manually before enabling service.
- systemd timezone support for `OnCalendar` varies by version. Ubuntu 24.04's systemd should support `America/New_York`. Verify during manual setup.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`

## Reviewer guidance

- Verify no `git pull` or `git reset` in snapshot script
- Verify vault path consistency across all files
- Verify timer schedule avoids inbox processing windows
- Verify privacy boundary (`02-Growth/_private/`) in gitignore additions

## Activity Log

- 2026-04-01T15:23:53Z – claude-code – shell_pid=82396 – lane=doing – Assigned agent via workflow command
- 2026-04-01T15:24:43Z – claude-code – shell_pid=82396 – lane=for_review – Ready for review: systemd service, snapshot script/timer, gitignore additions
- 2026-04-01T15:25:09Z – claude-code – shell_pid=82860 – lane=doing – Started review via workflow command
