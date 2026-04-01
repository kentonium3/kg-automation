---
work_package_id: WP03
title: Architecture Documentation Updates
lane: "doing"
dependencies: [WP01]
requirement_refs:
- FR-14
- FR-15
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 010-obsidian-sync-office2-WP01
base_commit: 7b1144c895e92aec2a2af42d2314a157e02bd1d2
created_at: '2026-04-01T15:25:46.960507+00:00'
subtasks: [T009, T010, T011, T012]
shell_pid: "83167"
history:
- date: '2026-04-01T15:17:40Z'
  event: created
  actor: claude
---

# WP03: Architecture Documentation Updates

## Implementation command

```bash
spec-kitty implement WP03 --base WP01
```

## Objective

Update the architecture JSON files and their markdown narratives to reflect
the new vault sync topology: Obsidian Sync as the live mechanism, git as
the snapshot backup layer. All JSON files must include `updated_by: "F010"`.

## Context

- **Architecture docs root**: `docs/design/architecture/`
- **JSON data files**: `docs/design/architecture/data/`
- **Standing requirement**: Any feature that changes services, data flows, or
  network topology MUST update architecture docs (per CLAUDE.md)
- **Change control**: See `docs/design/architecture/change-control.md`
- **What changed**: vault sync mechanism shifted from git-only to Obsidian Sync
  (live) + git (snapshot backup)

**Read these files before making changes**:
- `docs/design/architecture/data/service-inventory.json`
- `docs/design/architecture/data/data-flows.json`
- `docs/design/architecture/service-inventory.md`
- `docs/design/architecture/data-flows.md`

## Subtask guidance

### T009: Update `data/service-inventory.json`

**Purpose**: Update the obsidian-sync service entry to reflect the actual
configuration after F010.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json`
2. Find the `obsidian-sync` entry (may exist from prior documentation)
3. Update or create the entry with:
   - `name`: "obsidian-sync"
   - `description`: "Continuous Obsidian vault sync via ob CLI"
   - `binary`: "/usr/bin/ob"
   - `version`: "0.0.8"
   - `command`: "ob sync --path /home/kgale/second-brain/vault --continuous"
   - `user`: "kgale"
   - `data_path`: "/home/kgale/second-brain/vault"
   - `systemd_unit`: "obsidian-sync.service (user unit)"
   - `auth_method`: "ob login (interactive, credentials stored locally by ob)"
   - `sync_direction`: "bidirectional"
   - `conflict_strategy`: "merge"
   - `excluded_folders`: ["02-Growth/_private"]
   - `status`: "active"
   - `updated_by`: "F010"
4. Also add or update a `vault-snapshot` entry:
   - `name`: "vault-snapshot"
   - `description`: "Daily git snapshot of vault for backup/version history"
   - `binary`: "/home/kgale/helper-scripts/vault-snapshot.sh"
   - `schedule`: "2AM ET daily (systemd timer)"
   - `user`: "kgale"
   - `data_path`: "/home/kgale/second-brain"
   - `direction`: "outbound-only (add, commit, push)"
   - `status`: "active"
   - `updated_by`: "F010"

**Files**: `docs/design/architecture/data/service-inventory.json` (edit)

**Validation**:
- [ ] `updated_by: "F010"` present on both entries
- [ ] JSON is valid (no syntax errors)
- [ ] Vault path is `/home/kgale/second-brain/vault` (not `/vault/Notes/`)
- [ ] User is `kgale` (not `claude` or `root`)

---

### T010: Update `data/data-flows.json`

**Purpose**: Update the vault sync data flow to show the new topology.

**Steps**:
1. Read `docs/design/architecture/data/data-flows.json`
2. Find the vault sync flow entry (may exist or need creation)
3. Update to reflect:
   - **Live sync**: Mac ↔ Obsidian Cloud ↔ office2 ↔ iPhone (via Obsidian Sync)
   - **Backup**: office2 vault → git → GitHub (outbound-only, 2AM ET daily)
   - **Consumer**: felix-admin-capture reads from `/home/kgale/second-brain/vault/00-Inbox/`
   - **Writer**: felix-admin-capture updates note frontmatter (status fields)
   - `updated_by`: "F010"
4. Remove or mark as deprecated any previous git-based live sync flow

**Files**: `docs/design/architecture/data/data-flows.json` (edit)

**Validation**:
- [ ] Flow shows Obsidian Sync as live mechanism (not git)
- [ ] Git role is clearly "backup/snapshot" not "sync"
- [ ] `updated_by: "F010"` present
- [ ] JSON is valid

---

### T011: Update `service-inventory.md`

**Purpose**: Update the narrative description of the obsidian-sync service
and add the vault-snapshot service.

**Steps**:
1. Read `docs/design/architecture/service-inventory.md`
2. Find the obsidian-sync section
3. Update narrative to describe:
   - Service runs `ob sync --continuous` as kgale user
   - Provides live bidirectional sync between office2, Mac, and iPhone
   - Authenticated via `ob login` (interactive, one-time setup)
   - Managed by `obsidian-sync.service` systemd user unit
   - Excludes `02-Growth/_private/` from sync
4. Add vault-snapshot service description:
   - Runs daily at 2AM ET via systemd timer
   - Outbound-only git snapshot (add, commit, push)
   - Provides version history and off-device backup
   - Never pulls or resets vault content

**Files**: `docs/design/architecture/service-inventory.md` (edit)

**Validation**:
- [ ] Both services documented
- [ ] Obsidian Sync described as live/authoritative
- [ ] Git described as backup/snapshot only
- [ ] Privacy exclusion mentioned

---

### T012: Update `data-flows.md`

**Purpose**: Update the narrative description of the vault sync data flow.

**Steps**:
1. Read `docs/design/architecture/data-flows.md`
2. Find the vault sync section
3. Update to describe the new topology:
   ```
   Capture → Obsidian Sync → office2 vault → felix-admin-capture

   Mac/iPhone (capture via Wispr Flow)
     ↕ Obsidian Sync (bidirectional, live)
   Obsidian Cloud
     ↕ Obsidian Sync (bidirectional, live)
   office2 vault (/home/kgale/second-brain/vault)
     → felix-admin-capture (reads 00-Inbox/)
     → git snapshot (2AM ET, outbound to GitHub)
   ```
4. Note that git is no longer the live sync mechanism — it serves as
   periodic backup only

**Files**: `docs/design/architecture/data-flows.md` (edit)

**Validation**:
- [ ] Topology accurately reflects three-device Obsidian Sync loop
- [ ] Git role clearly stated as backup, not live sync
- [ ] felix-admin-capture's read path documented

## Definition of Done

- [ ] `data/service-inventory.json` updated with both services, `updated_by: "F010"`
- [ ] `data/data-flows.json` updated with new sync topology, `updated_by: "F010"`
- [ ] `service-inventory.md` narrative updated for both services
- [ ] `data-flows.md` narrative updated with new topology
- [ ] All JSON files are valid (parseable)
- [ ] No references to git as a live sync mechanism

## Risks

- Existing JSON structure may have changed since the spec was written. Mitigation: read current files before editing.
- Data flow entries may reference other services that also need minor updates. Mitigation: only update vault-related flows, flag others for follow-up.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`

## Reviewer guidance

- Verify all JSON is valid (no trailing commas, proper escaping)
- Verify `updated_by: "F010"` on all modified entries
- Verify narrative matches JSON (no contradictions between files)
- Verify vault path consistency across all files
- Verify privacy boundary (`02-Growth/_private/`) mentioned in exclusions
