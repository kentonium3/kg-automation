---
work_package_id: WP06
title: Architecture Docs and Handbooks
lane: "approved"
dependencies: [WP02]
requirement_refs:
- FR-04
- FR-22
- FR-23
- FR-24
- FR-25
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 011-second-brain-vault-cleanup-WP02
base_commit: 811a6d2ba4c590e0b8a098c939a613a01eb8fda4
created_at: '2026-04-01T19:32:55.435729+00:00'
subtasks: [T025, T026, T027, T028, T029, T030, T031, T032, T033]
agent: claude-code
shell_pid: '27623'
reviewed_by: "Kent Gale"
review_status: "approved"
history:
- date: '2026-04-01T18:30:16Z'
  event: created
  actor: claude
---

# WP06: Architecture Docs and Handbooks

## Implementation command

```bash
spec-kitty implement WP06 --base WP02
```

## Objective

Update architecture JSON files, their markdown narratives, and operational
handbooks to reflect: (1) vault-snapshot removal, (2) vault → notes rename,
(3) new second-brain-sync service entry.

## Context

- **Architecture docs root**: `docs/design/architecture/`
- **JSON files are authoritative**: Update JSON first, then update markdown
  narratives to match
- **updated_by requirement**: All JSON changes must include `"updated_by": "F011"` (C-09)
- **vault-snapshot**: Already absent from office2 but still referenced in docs
- **second-brain-sync**: New service to add (from WP05)
- **Handbooks**: `docs/handbooks/obsidian-sync-ops.md` and `docs/handbooks/inbox-ops.md`

## Subtask guidance

### T025: Update service-inventory.json [P]

**File**: `docs/design/architecture/data/service-inventory.json`

**Changes**:
1. **Remove** the `vault-snapshot` service entry entirely
2. **Update** the `obsidian-sync` entry:
   - Change `data_path` from `second-brain/vault` to `second-brain/notes`
   - Change `command` path reference from `vault` to `notes`
   - Set `"updated_by": "F011"`
3. **Add** a new `second-brain-sync` entry:
   ```json
   {
     "name": "second-brain-sync",
     "description": "Bidirectional git sync for non-vault second-brain content",
     "type": "timer",
     "schedule": "every 15 minutes",
     "user": "kgale",
     "command": "/home/kgale/helper-scripts/second-brain-sync.sh",
     "data_path": "/home/kgale/second-brain",
     "status": "active",
     "deployed_by": "F011",
     "updated_by": "F011"
   }
   ```

**Validation**:
- [ ] No `vault-snapshot` entry remains
- [ ] `obsidian-sync` entry references `notes` path
- [ ] `second-brain-sync` entry exists with correct fields
- [ ] JSON is valid (parse with `python3 -m json.tool`)

### T026: Update data-flows.json [P]

**File**: `docs/design/architecture/data/data-flows.json`

**Changes**:
1. Update vault sync flow path references from `vault` to `notes`
2. Remove any git snapshot flow reference
3. Add a bidirectional git sync flow for non-vault content:
   - Source: Mac (origin) ↔ office2 (clone)
   - Content: agent configs, logs, assets
   - Frequency: 15 minutes
   - Mechanism: git pull/push
4. Set `"updated_by": "F011"`

**Validation**:
- [ ] No `vault` path references remain
- [ ] Bidirectional sync flow documented
- [ ] JSON is valid

### T027: Update service-inventory.md [P]

**File**: `docs/design/architecture/service-inventory.md`

**Changes**:
1. Remove vault-snapshot service narrative
2. Update obsidian-sync section: path references from `vault` to `notes`
3. Add second-brain-sync service narrative describing the 15-minute
   bidirectional git sync

**Validation**:
- [ ] No vault-snapshot references
- [ ] obsidian-sync references `notes/` path
- [ ] second-brain-sync section added

### T028: Update data-flows.md [P]

**File**: `docs/design/architecture/data-flows.md`

**Changes**:
1. Update vault sync flow narrative: path references from `vault` to `notes`
2. Remove git snapshot from vault data flow description
3. Add bidirectional git sync flow description for non-vault content

**Validation**:
- [ ] No vault path references in active flow descriptions
- [ ] Git sync flow documented

### T029: Update glossary.md [P]

**File**: `docs/design/architecture/glossary.md`

**Changes**:
- Update the Vault definition: path references from `vault` to `notes`
- Update any references to `vault/Notes/` with `notes/`

**Validation**:
- [ ] Vault entry references `notes/` as the directory name

### T030: Update security-posture.md [P]

**File**: `docs/design/architecture/security-posture.md`

**Changes**:
- Update privacy boundary path from `vault/02-Growth/_private/` or
  `vault/Notes/02-Growth/_private/` to `notes/02-Growth/_private/`

**Validation**:
- [ ] Privacy boundary references `notes/02-Growth/_private/`

### T031: Update backup-and-recovery.md [P]

**File**: `docs/design/architecture/backup-and-recovery.md`

**Changes**:
- Update vault backup path references from `vault` to `notes`
- Remove any references to git snapshot as a backup mechanism for vault
  content (Restic + Obsidian Sync are the mechanisms)

**Validation**:
- [ ] Backup paths reference `notes/`
- [ ] No git snapshot references for vault backup

### T032: Update obsidian-sync-ops.md

**File**: `docs/handbooks/obsidian-sync-ops.md`

**Changes**:
1. Update all vault path references from `vault` to `notes` (7+ references)
2. Remove the "Git Coexistence" section or replace it with a note that
   git no longer tracks vault content
3. Remove vault-snapshot references
4. Add a note about the new directory name matching Mac

**Validation**:
- [ ] `grep 'vault' docs/handbooks/obsidian-sync-ops.md` returns no
  second-brain path matches
- [ ] No git snapshot references remain
- [ ] Handbook is internally consistent

### T033: Update inbox-ops.md

**File**: `docs/handbooks/inbox-ops.md`

**Changes**:
1. Update the Mac fallback path from `~/second-brain/vault/Notes/00-Inbox/`
   to `~/second-brain/notes/00-Inbox/`
2. Update any other vault path references
3. Update troubleshooting paths

**Validation**:
- [ ] `grep 'vault' docs/handbooks/inbox-ops.md` returns no second-brain
  path matches
- [ ] Mac and office2 paths are parallel (`notes/00-Inbox/` on both)

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`

## Definition of Done

- All 9 files updated
- JSON files are valid and include `updated_by: "F011"`
- vault-snapshot removed from all docs
- second-brain-sync added to service inventory
- All vault → notes path updates applied
- Handbooks reflect current state with no git snapshot references

## Risks

- **JSON structure changes**: When removing vault-snapshot and adding
  second-brain-sync, ensure the JSON array/object structure remains valid.
  Validate with `python3 -m json.tool` after each edit.
- **Markdown link integrity**: Ensure any cross-references between docs
  still resolve after edits.

## Activity Log

- 2026-04-01T19:32:55Z – claude-code – shell_pid=27623 – lane=doing – Assigned agent via workflow command
- 2026-04-01T19:49:19Z – claude-code – shell_pid=27623 – lane=approved – Review passed: All 9 files updated correctly. vault-snapshot removed, second-brain-sync added, all vault→notes path renames applied. JSON valid, updated_by F011 set. No stale vault references remain in architecture docs or handbooks.
