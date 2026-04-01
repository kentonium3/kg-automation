---
work_package_id: WP02
title: Vault Rename and Obsidian Sync Service Update
lane: done
dependencies: []
requirement_refs:
- FR-01
- FR-02
- FR-03
- FR-07
- FR-08
- FR-09
- FR-10
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: d4735d77fc92bc0aae076aeb356dbe9c818a459c
created_at: '2026-04-01T18:54:33.797605+00:00'
subtasks: [T004, T005, T006, T007, T008]
agent: claude-code
shell_pid: '23697'
reviewed_by: "Kent Gale"
review_status: "approved"
history:
- date: '2026-04-01T18:30:16Z'
  event: created
  actor: claude
---

# WP02: Vault Rename and Obsidian Sync Service Update

## Implementation command

```bash
spec-kitty implement WP02
```

## Objective

Rename the vault directory from `vault/` to `notes/` on office2, update and
deploy the obsidian-sync service with the new path, and verify Obsidian Sync
resumes correctly.

## Context

- **Current vault path on office2**: `/home/kgale/second-brain/vault/`
  (numbered folders directly under `vault/`, no `Notes/` subdirectory)
- **Target vault path**: `/home/kgale/second-brain/notes/`
- **obsidian-sync.service**: Exists in repo at `scripts/office2/obsidian-sync.service`
  but is NOT currently deployed on office2
- **vault-snapshot**: Already absent from office2 (no timer, service, or script)
- **ob CLI**: `/usr/bin/ob` on office2
- **Service user**: `kgale` (vault owner)
- **Vault ID**: `d9a7cf01fedcdfcb` (Obsidian Sync internal identifier)
- **SSH access**: Use `ssh office2-claude` for all commands. Present any
  commands requiring kgale or sudo to Kent.

## Subtask guidance

### T004: Verify vault-snapshot absence

**Purpose**: Confirm the vault-snapshot infrastructure does not exist on
office2 before proceeding with the rename.

**Steps** (run via `ssh office2-claude`):
1. `systemctl --user status vault-snapshot.timer 2>&1` — expect "could not be found"
2. `systemctl --user status vault-snapshot.service 2>&1` — expect "could not be found"
3. `ls /home/kgale/helper-scripts/vault-snapshot.sh 2>&1` — expect "No such file"
4. `ls ~/.config/systemd/user/vault-snapshot.* 2>&1` — expect "No such file" (check as kgale path)

**Validation**:
- [ ] All four checks confirm absence
- [ ] If any vault-snapshot component exists: STOP and report to Kent

### T005: Rename vault/ to notes/ on office2

**Purpose**: Move all vault content from `vault/` to `notes/` on office2.

**CRITICAL**: This is a filesystem operation that Kent must perform as kgale
(or the agent can do via `ssh office2-claude` if permissions allow — the
`secondbrain` group has write access to the directory).

**Steps**:
1. Verify current state: `ls -la /home/kgale/second-brain/vault/`
2. Rename: `mv /home/kgale/second-brain/vault /home/kgale/second-brain/notes`
3. Verify: `ls -la /home/kgale/second-brain/notes/`
4. Confirm vault/ is gone: `ls /home/kgale/second-brain/vault/ 2>&1` — expect "No such file"

**If the `mv` fails due to permissions**: Present the command to Kent to run
as kgale via `ssh office2-kgale`.

**Validation**:
- [ ] `/home/kgale/second-brain/notes/` exists with all numbered folders
- [ ] `/home/kgale/second-brain/vault/` does not exist
- [ ] `.obsidian/` directory is present in `notes/`

### T006: Update obsidian-sync.service in repo

**Purpose**: Update the vault path in the service unit file from `vault` to
`notes`.

**File**: `scripts/office2/obsidian-sync.service`

**Change**: In the `ExecStart` line:
```diff
-ExecStart=/usr/bin/ob sync --path /home/kgale/second-brain/vault --continuous
+ExecStart=/usr/bin/ob sync --path /home/kgale/second-brain/notes --continuous
```

**Validation**:
- [ ] `grep 'notes' scripts/office2/obsidian-sync.service` matches the updated path
- [ ] No references to `vault` remain in the file

### T007: Deploy obsidian-sync.service to office2

**Purpose**: Copy the updated service file to office2 and enable it.

**Steps**:
1. Copy to office2: `scp scripts/office2/obsidian-sync.service office2-claude:/tmp/`
2. Present these commands to Kent to run as kgale:
   ```bash
   ssh office2-kgale
   mkdir -p ~/.config/systemd/user/
   cp /tmp/obsidian-sync.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable obsidian-sync.service
   systemctl --user start obsidian-sync.service
   systemctl --user status obsidian-sync.service
   ```

**Validation**:
- [ ] `systemctl --user status obsidian-sync.service` shows active (running)
- [ ] `journalctl --user -u obsidian-sync.service --no-pager -n 10` shows sync activity

### T008: Verify Obsidian Sync resumes

**Purpose**: Confirm that Obsidian Sync recognizes the renamed vault and
syncs correctly using the vault's internal ID.

**Steps**:
1. Ask Kent to create a test note in Obsidian on Mac (a simple file in
   `00-Inbox/` like "Sync test F011")
2. Wait up to 5 minutes
3. Check on office2: `ls /home/kgale/second-brain/notes/00-Inbox/ | grep -i sync`
4. If the note appears: sync is working
5. If not after 5 minutes: check `journalctl --user -u obsidian-sync.service`
   for errors

**Validation**:
- [ ] Test note created on Mac appears on office2 within 5 minutes
- [ ] No errors in obsidian-sync journal logs

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`

## Definition of Done

- vault-snapshot verified absent from office2
- `vault/` renamed to `notes/` on office2
- obsidian-sync.service updated in repo and deployed to office2
- Obsidian Sync confirmed working with test note

## Risks

- **Obsidian Sync may not recognize the vault after rename**: The vault ID
  is stored in `.obsidian/` which moves with the rename, so this should work.
  If it doesn't, Kent may need to re-authenticate via `ob` CLI.
- **Permission issues on rename**: The `claude` user is in the `secondbrain`
  group but directory ownership is `kgale:secondbrain`. The `mv` should work
  if the parent directory has group write permission. If not, present to Kent.

## Activity Log

- 2026-04-01T18:54:34Z – claude-code – shell_pid=19966 – lane=doing – Assigned agent via workflow command
- 2026-04-01T19:14:58Z – claude-code – shell_pid=19966 – lane=for_review – Ready for review: vault renamed to notes on office2, obsidian-sync.service updated and deployed, sync verified with test note
- 2026-04-01T19:16:51Z – claude-code – shell_pid=23697 – lane=doing – Started review via workflow command
- 2026-04-01T19:18:02Z – claude-code – shell_pid=23697 – lane=approved – Review passed: vault renamed, obsidian-sync.service updated and running with new path, sync verified
