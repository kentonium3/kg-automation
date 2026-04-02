---
work_package_id: WP02
title: Operations Runbook
dependencies: [WP01]
requirement_refs:
- FR-13
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 010-obsidian-sync-office2-WP01
base_commit: 7b1144c895e92aec2a2af42d2314a157e02bd1d2
created_at: '2026-04-01T15:25:39.979178+00:00'
subtasks: [T006, T007, T008]
history:
- date: '2026-04-01T15:17:40Z'
  event: created
  actor: claude
authoritative_surface: ''
execution_mode: code_change
mission_id: 01KN5QX3WNQ7X8S386F2A0ME8Q
owned_files:
- docs/design/architecture/service-inventory.md
- docs/handbooks/**
- kitty-specs/010-obsidian-sync-office2/quickstart.md
wp_code: WP02
---

# WP02: Operations Runbook

## Implementation command

```bash
spec-kitty implement WP02 --base WP01
```

## Objective

Create `docs/handbooks/obsidian-sync-ops.md` — a comprehensive operations
runbook covering Obsidian Sync configuration on office2, status monitoring,
re-authentication, git coexistence strategy, and troubleshooting.

## Context

- **Output file**: `docs/handbooks/obsidian-sync-ops.md`
- **Existing handbook pattern**: Check `docs/handbooks/` for format conventions
- **kg-automation frontmatter**: Must include `title`, `doc_type`, `status` fields
- **Service files from WP01**: `scripts/office2/obsidian-sync.service`, `vault-snapshot.*`
- **Vault path**: `/home/kgale/second-brain/vault`
- **`ob` CLI**: `/usr/bin/ob` v0.0.8
- **Service user**: `kgale`
- **Inbox processing crons**: 7AM, 12PM, 6PM ET
- **Snapshot schedule**: 2AM ET daily

## Subtask guidance

### T006: Create runbook with standard frontmatter

**Purpose**: Create the runbook file with kg-automation-compliant frontmatter
and document structure.

**Steps**:
1. Create `docs/handbooks/obsidian-sync-ops.md`
2. Add frontmatter:
   ```yaml
   ---
   title: "Obsidian Sync Operations Runbook"
   doc_type: handbook
   status: approved
   ---
   ```
3. Structure the document with these sections:
   - Overview (what this runbook covers)
   - Architecture (sync topology diagram: Mac ↔ Obsidian Cloud ↔ office2 ↔ iPhone)
   - Service Configuration
   - Status Checks
   - Re-authentication
   - Git Coexistence Strategy
   - Manual Operations
   - Troubleshooting
   - Related Documentation

**Files**: `docs/handbooks/obsidian-sync-ops.md` (new, ~200 lines)

**Validation**:
- [ ] Frontmatter includes required fields (`title`, `doc_type`, `status`)
- [ ] All sections present

---

### T007: Document sync configuration, status checks, and re-authentication

**Purpose**: Cover the day-to-day operational commands Kent needs.

**Steps**:
1. **Service Configuration** section:
   - systemd service: `systemctl --user status obsidian-sync`
   - Service file location: `~/.config/systemd/user/obsidian-sync.service`
   - Start/stop/restart: `systemctl --user {start|stop|restart} obsidian-sync`
   - Logs: `journalctl --user -u obsidian-sync -f`
   - Boot persistence: requires `loginctl enable-linger kgale`

2. **Status Checks** section:
   - Service status: `systemctl --user status obsidian-sync`
   - Sync status: `ob sync-status --path /home/kgale/second-brain/vault`
   - Login status: `ob login` (shows status when already logged in)
   - Snapshot timer: `systemctl --user list-timers | grep vault`
   - Last snapshot: `cd /home/kgale/second-brain && git log --oneline -1`

3. **Re-authentication** section:
   - When: if `ob sync-status` shows authentication error
   - How: `ob login --email <email>` (password + MFA prompted)
   - After: restart service `systemctl --user restart obsidian-sync`
   - Note: must be run as `kgale` user (not `claude`)

**Validation**:
- [ ] All commands are correct and tested against `ob --help` output
- [ ] Commands specify correct vault path
- [ ] Re-auth procedure is complete (login, then restart service)

---

### T008: Document git coexistence strategy and troubleshooting

**Purpose**: Document the git snapshot strategy, schedule, and common
troubleshooting scenarios.

**Steps**:
1. **Git Coexistence Strategy** section:
   - Principle: Obsidian Sync is authoritative for live vault state
   - Git role: periodic snapshot for backup and version history
   - Direction: outbound-only (add → commit → push, never pulls)
   - Schedule: 2AM ET daily via systemd timer
   - Avoids: inbox processing windows (7AM, 12PM, 6PM ET)
   - Conflict resolution: if git and Obsidian Sync disagree, Obsidian Sync wins
   - `.gitignore`: workspace files and sync metadata excluded

2. **Manual Operations** section:
   - Trigger manual sync: `ob sync --path /home/kgale/second-brain/vault`
   - Trigger manual snapshot: `~/helper-scripts/vault-snapshot.sh`
   - Force re-sync: `ob sync-unlink --path ... && ob sync-setup ...` (last resort)

3. **Troubleshooting** section covering:
   - Note not appearing on office2: check service status, check sync status, check network
   - Sync conflict files: Obsidian Sync creates `.sync-conflict-*` files — check and resolve
   - Service won't start: check `journalctl --user -u obsidian-sync`
   - Git snapshot fails: check disk space, check git remote, check `.gitignore`
   - After office2 reboot: verify linger is enabled, check service auto-started

4. **Related Documentation** section:
   - Link to quickstart guide: `kitty-specs/010-obsidian-sync-office2/quickstart.md`
   - Link to architecture docs: `docs/design/architecture/service-inventory.md`
   - Link to felix-admin-capture: `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`

**Validation**:
- [ ] Git strategy section clearly states outbound-only, never pulls
- [ ] Troubleshooting covers the 5 most likely failure modes
- [ ] All file paths are absolute and correct

## Definition of Done

- [ ] `docs/handbooks/obsidian-sync-ops.md` exists with valid frontmatter
- [ ] All 8 sections documented (Overview through Related Documentation)
- [ ] Commands reference correct paths and user (`kgale`)
- [ ] Git coexistence strategy clearly documented
- [ ] Troubleshooting covers common failure scenarios
- [ ] No secrets or credentials in the document

## Risks

- `ob` CLI may have additional commands or behaviors not covered by `--help`. Mitigation: document what's known, update runbook as experience grows.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`

## Reviewer guidance

- Verify all `ob` commands match the CLI help output from research.md
- Verify vault path consistency (`/home/kgale/second-brain/vault`)
- Verify privacy boundary not referenced in any command examples
- Check that runbook passes `validate_docs.py` (frontmatter compliance)

## Activity Log

- 2026-04-01T15:25:40Z – claude-code – shell_pid=83022 – lane=doing – Assigned agent via workflow command
- 2026-04-01T15:28:43Z – claude-code – shell_pid=83022 – lane=for_review – Ready for review: operations runbook with all 9 sections
- 2026-04-01T15:29:09Z – claude-code – shell_pid=83022 – lane=approved – Review passed: runbook complete with all 9 sections, correct paths and commands
