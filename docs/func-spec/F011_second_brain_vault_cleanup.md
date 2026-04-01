---
title: "F011: Second Brain Vault Cleanup — Remove Git Snapshot, Rename vault/Notes to notes"
doc_type: func-spec
status: draft
feature: F011
---

# F011: Second Brain Vault Cleanup

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure

---

## Executive Summary

F010 configured Obsidian Sync on office2 and, as part of that work,
implemented a daily git snapshot of the vault. That snapshot mechanism
is unnecessary and adds race condition risk. The vault is already
protected by two independent mechanisms: Obsidian Sync (live, with its
own version history) and Restic (nightly GFS encrypted backup to USB).
Git's role in the second-brain repo is to version non-vault content —
scripts, agent configs, assets — not the vault itself.

Additionally, the vault directory on office2 is named `vault/` while
the Mac vault root is `vault/Notes/`. This inconsistency should be
resolved to make the two environments parallel.

Current gaps:
- ❌ `vault-snapshot` cron job runs daily git commits on vault content —
  unnecessary, creates race condition risk with Obsidian Sync
- ❌ vault/ is tracked in git on office2 — should be .gitignored
- ❌ Server vault directory name (`vault/`) differs from Mac
  (`vault/Notes/`) — should be `notes/` on both to be parallel
- ❌ All agent path references and service configs point to the old
  path — must be updated atomically with the rename

This spec removes the git snapshot mechanism, adds vault to .gitignore,
renames the server vault directory to `notes/`, and updates all
downstream path references.

---

## Problem Statement

**Current State:**
```
office2 /home/kgale/second-brain/
├── vault/                    ← git-tracked, vault-snapshot cron commits here daily
│   └── Notes/                ← actual vault content (Obsidian Sync target)
├── agents/logs/              ← Felix agent logs
└── [other dirs]

Mac ~/second-brain/
└── notes/                    ← vault content (already renamed, Obsidian Sync source)

vault-snapshot service
└── ✅ Deployed by F010
└── ❌ Unnecessary — Obsidian Sync + Restic cover this
└── ❌ Race condition risk with Obsidian Sync writes

.gitignore on office2
└── ❌ vault/ is NOT excluded — vault content is tracked in git
```

**Target State:**
```
office2 /home/kgale/second-brain/
├── notes/                    ← renamed from vault/Notes/, .gitignored
│   ├── 00-Inbox/
│   ├── 01-Constitution/
│   └── [rest of vault]
├── agents/logs/
└── [other dirs]

Mac ~/second-brain/
└── notes/                    ← already restructured (matches server target)

vault-snapshot service
└── ❌ Removed — cron job and script deleted

.gitignore on office2
└── ✅ notes/ excluded from git tracking

All path references updated:
└── ✅ obsidian-sync.service — new path
└── ✅ felix-admin-capture TOOLS.md — new vault path
└── ✅ felix-admin-habits TOOLS.md — new vault path
└── ✅ service-inventory.json — updated paths and vault-snapshot removed
```

---

## Note on Mac Vault Path

The Mac vault has already been restructured to match the target server
path. The Mac vault is now at `~/second-brain/notes/` — the `vault/`
wrapper directory was removed and `Notes/` was renamed to `notes/` and
moved up a level. The office2 rename (FR-3) brings the server into
alignment with the Mac, not the other way around.

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read and understand:

1. **Every file that references the current vault path on office2**
   - `scripts/openclaw/agents/felix-admin-capture/TOOLS.md` — vault path
   - `scripts/openclaw/agents/felix-admin-habits/TOOLS.md` — vault path
   - The `obsidian-sync.service` systemd unit file on office2 — sync path
   - `docs/design/architecture/data/service-inventory.json` — data_path
     fields for obsidian-sync and vault-snapshot entries
   - Any other agent or script files that reference the vault path
   - Run a grep on office2 before starting: search for all references to
     `second-brain/vault` across agent workspaces and scripts

2. **The vault-snapshot service deployed by F010**
   - The script at `/home/kgale/helper-scripts/vault-snapshot.sh`
   - The systemd timer that schedules it
   - Both must be stopped, disabled, and removed

3. **The .gitignore on office2**
   - Current state of `/home/kgale/second-brain/.gitignore`
   - What is currently excluded and what needs to be added

4. **Restic backup configuration**
   - `docs/design/architecture/data/service-inventory.json` — restic entry
   - Verify `notes/` will still be captured (it's under `/home/kgale`
     which is in the backup scope — confirm this remains true after rename)

---

## Functional Requirements

### FR-1: Remove vault-snapshot Git Cron

**What it must do:**
- Stop and disable the vault-snapshot systemd timer on office2
- Delete the vault-snapshot script at
  `/home/kgale/helper-scripts/vault-snapshot.sh`
- Remove the systemd timer and service unit files
- Remove the `vault-snapshot` entry from service-inventory.json

**Business rules:**
- The vault is backed up by Restic (nightly, GFS) and versioned by
  Obsidian Sync — git snapshots of vault content are redundant and risky
- Removal must happen before the vault rename to avoid a snapshot run
  during the rename operation

**Success criteria:**
- [ ] `systemctl --user status vault-snapshot.timer` shows not found
- [ ] vault-snapshot.sh does not exist on office2
- [ ] No cron or timer targeting vault git operations remains
- [ ] service-inventory.json updated to remove vault-snapshot entry

---

### FR-2: Add vault to .gitignore on office2

**What it must do:**
- Add the vault directory to `.gitignore` in the second-brain repo on
  office2 so vault content is never tracked in git
- After adding to .gitignore, remove any currently-tracked vault files
  from the git index without deleting them from disk (`git rm --cached`)

**Business rules:**
- The .gitignore entry must use the post-rename name (`notes/`) so it
  applies to the renamed directory
- Files must be removed from git tracking before the rename to avoid
  a large untracked-file diff after rename
- The `.obsidian/` metadata directory inside the vault must also be
  excluded — it contains per-device UI state that should never be
  committed

**Success criteria:**
- [ ] `notes/` present in `.gitignore`
- [ ] `.obsidian/` present in `.gitignore` (or covered by `notes/`)
- [ ] `git status` shows no vault files as tracked or modified
- [ ] Vault files still exist on disk after git rm --cached

---

### FR-3: Rename vault/Notes to notes on office2

**What it must do:**
- Rename `/home/kgale/second-brain/vault/Notes/` to
  `/home/kgale/second-brain/notes/`
- The `vault/` parent directory (which will be empty after the move)
  must also be removed
- The rename must be performed while Obsidian Sync is stopped to avoid
  sync conflicts during the operation

**Business rules:**
- Stop obsidian-sync.service before rename, restart after
- The rename must be atomic from Obsidian Sync's perspective —
  stop service, rename, update service config, restart service
- Do not rename on Mac — Mac vault path is managed by Obsidian

**Success criteria:**
- [ ] `/home/kgale/second-brain/notes/` exists with all vault content
- [ ] `/home/kgale/second-brain/vault/` no longer exists
- [ ] Obsidian Sync service restarted and syncing to new path
- [ ] A test note created on Mac appears in `notes/` within 5 minutes

---

### FR-4: Update All Path References

**What it must do:**
- Update every file that references the old vault path to use the new
  `notes/` path:
  - `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`
  - `scripts/openclaw/agents/felix-admin-habits/TOOLS.md`
  - The `obsidian-sync.service` unit file (both in repo and on office2)
  - Any other agent workspace files that reference the vault path
  - `docs/design/architecture/data/service-inventory.json` — data_path
    for the obsidian-sync entry
- Deploy updated agent workspace files to office2

**Business rules:**
- All path references must be updated before restarting Obsidian Sync
  and the OpenClaw agents — running agents with stale paths will cause
  silent failures
- The update to office2 agent workspace files must happen via the
  established deployment pattern (copy from repo to workspace)

**Success criteria:**
- [ ] No references to `second-brain/vault` remain in agent files,
  service files, or architecture docs
- [ ] felix-admin-capture processes inbox notes from `notes/00-Inbox/`
  after restart
- [ ] Obsidian Sync service config points to `notes/`

---

### FR-5: Verify End-to-End After Cleanup

**What it must do:**
- After all changes, verify the full pipeline works end-to-end:
  - Create a test inbox note on Mac
  - Confirm it appears in `notes/00-Inbox/` on office2
  - Trigger a manual inbox processing run
  - Confirm the note is processed and marked `status: processed`

**Success criteria:**
- [ ] Test note created on Mac appears on office2 within 5 minutes
- [ ] Manual inbox processing run completes successfully
- [ ] Processing log written to `agents/logs/`
- [ ] No errors related to vault paths in OpenClaw logs

---

### FR-6: Update Architecture Docs and Runbook

**What it must do:**
- Update `docs/design/architecture/data/service-inventory.json`:
  - Remove vault-snapshot service entry
  - Update obsidian-sync `data_path` to `notes/`
  - Set `updated_by: "F011"`
- Update `docs/handbooks/obsidian-sync-ops.md` to reflect:
  - New vault path (`notes/`)
  - Removal of git snapshot strategy
  - Restic as the sole backup mechanism for vault content
- Update `docs/handbooks/inbox-ops.md` vault path references

**Success criteria:**
- [ ] Architecture JSON files updated with `updated_by: "F011"`
- [ ] Runbooks reflect current paths and no git snapshot references
- [ ] No references to `vault-snapshot` or old vault path in docs

---

## Architecture Documentation Updates

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Remove vault-snapshot entry; update obsidian-sync data_path to `notes/`; set updated_by F011 |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Remove vault-snapshot; update obsidian-sync path |
| `data-flows.md` | Remove git snapshot from vault data flow; confirm Obsidian Sync + Restic are the documented mechanisms |
| `docs/handbooks/obsidian-sync-ops.md` | Update vault path, remove git coexistence section |
| `docs/handbooks/inbox-ops.md` | Update vault path references |

---

## Out of Scope

- ❌ Renaming the Mac vault — Obsidian manages this path; do not touch it
- ❌ Changing Restic backup configuration — `/home/kgale` is already in
  scope; the rename does not affect backup coverage
- ❌ Changing Obsidian Sync subscription or device configuration
- ❌ Any changes to vault content — this is a structural/path change only
- ❌ Adding git versioning back for any vault content — that decision is
  made; git tracks second-brain/ excluding notes/

---

## Success Criteria

**Complete when:**

### Removal
- [ ] vault-snapshot cron removed and verified gone
- [ ] notes/ in .gitignore, vault files untracked from git

### Rename
- [ ] notes/ exists on office2 with all vault content
- [ ] vault/ directory gone from office2
- [ ] Obsidian Sync running and syncing to notes/

### Path References
- [ ] No stale vault path references in any agent or service file
- [ ] felix-admin-capture reading from notes/00-Inbox/

### End-to-End
- [ ] Test note Mac → office2 confirmed within 5 minutes
- [ ] Manual inbox run completes cleanly

### Documentation
- [ ] Architecture docs updated with updated_by F011
- [ ] Runbooks reflect new paths

---

## Architecture Principles

### Restic + Obsidian Sync Is Sufficient

The vault has two independent protection mechanisms:
- **Obsidian Sync** — live sync with built-in conflict resolution and
  version history across all devices
- **Restic** — nightly GFS encrypted backup to USB with 7-day, 4-week,
  6-month, 1-year retention

Adding git as a third mechanism for the same content creates complexity
without meaningful additional protection. The git snapshot strategy was
a reasonable initial design that has since been superseded by the
confirmed adequacy of the existing two mechanisms.

### Git Tracks Code and Config, Not Content

The second-brain repo's appropriate scope is scripts, agent
configurations, assets, and structural files — things that benefit from
versioned change history with meaningful commit messages. Vault notes
are content, not code. Their history is managed by Obsidian Sync's own
versioning, which is purpose-built for that use case.

---

## Constitutional Compliance

✅ **Docs adjacent**: All path changes in agent files, service configs,
and architecture docs happen in the same PR as the operational changes.

✅ **No silent failures**: FR-5 requires end-to-end verification after
all changes before the feature is considered complete.

✅ **Restic backup unchanged**: Vault content remains in Restic scope
via `/home/kgale` — backup protection is not degraded by this change.

---

## Risk Considerations

**Risk: Obsidian Sync loses vault identity during rename**
- Obsidian Sync identifies vaults by internal ID stored in the vault's
  `.obsidian/` directory, not by filesystem path. The rename should not
  affect sync identity — but this must be verified after restart.
- Mitigation: Stop sync before rename, verify sync resumes correctly
  after restart with a test note before declaring success.

**Risk: Stale path reference causes silent agent failure**
- If any agent file retains the old `vault/Notes/` path after the
  rename, the agent will fail to find vault files and may fail silently.
- Mitigation: FR-1 requires a grep of all references before starting.
  FR-5 requires end-to-end verification before completion.

**Risk: git rm --cached removes files from disk**
- `git rm --cached` only removes from the index, not from disk — but
  this must be the exact command used. `git rm` without `--cached`
  deletes the files.
- Mitigation: Spec this command explicitly. Planning phase must use
  `--cached` flag only.

---

## Notes for Implementation

**Sequence matters — do in this order:**
1. Stop vault-snapshot timer first (eliminates race condition risk)
2. Stop obsidian-sync.service
3. Add notes/ to .gitignore and run git rm --cached on vault files
4. Rename vault/Notes/ to notes/
5. Remove empty vault/ directory
6. Update all path references in agent files and service configs
7. Deploy updated agent files to office2
8. Restart obsidian-sync.service with new path
9. Verify sync with a test note
10. Restart OpenClaw agents
11. Run end-to-end verification (FR-5)
12. Update architecture docs and commit

**Grep command for path audit (run on office2 before starting):**
- Planning phase should discover all references to the old vault path
  before making any changes — not prescribing the exact command, but
  a recursive search across `/home/kgale/` and `/data/services/openclaw/`
  for the string `second-brain/vault` will find them.

---

**END OF SPECIFICATION**
