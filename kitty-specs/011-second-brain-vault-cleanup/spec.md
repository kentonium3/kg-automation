# F011: Second Brain Vault Cleanup

## Overview

Remove the redundant vault-snapshot git cron from office2, rename the vault
directory from `vault/` to `notes/` to match the Mac structure, initialize a
git repo for non-vault content with a bidirectional sync timer, and update all
downstream path references in agent files, service configs, and architecture
docs.

The vault is already protected by two independent mechanisms: Obsidian Sync
(live, with version history) and Restic (nightly GFS encrypted backup to USB).
The git snapshot strategy deployed by F010 is redundant and creates race
condition risk. Meanwhile, git's actual role in the second-brain directory
should be to version non-vault content — agent configs, skills, assets — and
keep that content synchronized between Mac (origin) and office2.

## Problem statement

The second-brain directory on office2 has several structural issues inherited
from F010:

1. **Redundant vault-snapshot cron** — A systemd timer runs daily git commits
   on vault content. This duplicates Obsidian Sync + Restic protection and
   risks race conditions with Obsidian Sync writes.

2. **Vault directory name mismatch** — office2 uses `vault/` while Mac uses
   `notes/` (renamed during the F010 post-mortem). Agent files and service
   configs reference the old path.

3. **No git repo for non-vault content** — The second-brain directory on
   office2 is not a git repository. Non-vault content (agent logs, configs,
   skills, assets) has no version control and no sync mechanism between Mac
   and server.

4. **Stale path references** — Agent workspace files, the obsidian-sync
   service unit, and architecture docs all reference `second-brain/vault`
   which will not exist after the rename.

## Actors

- **Kent** — vault owner. Authors non-vault content (agent configs, skills,
  assets) on Mac and pushes to origin.
- **office2** — Ubuntu 24.04 LTS server. Hosts the vault, inbox processor,
  and OpenClaw agents. Runs as `kgale` for vault and git operations, `claude`
  for agent operations.
- **felix-admin-capture** — F008 inbox processing agent on office2. Reads
  from the vault's inbox directory. Path references must be updated.
- **felix-admin-habits** — F009 daily habit agent on office2. Reads vault
  content. Path references must be updated.
- **Obsidian Sync** — Obsidian's cloud sync service. Syncs vault content
  across Mac, iPhone, and office2. Must be stopped during rename and
  restarted with the new path.
- **Bidirectional sync timer** — New systemd timer that pulls non-vault
  content from origin and pushes local changes (e.g., agent-created logs)
  every 15 minutes.

## User scenarios

### S1: Kent pushes config changes from Mac, office2 picks them up

Kent edits an agent config file or adds a new skill definition in
`~/second-brain/` on Mac. He commits and pushes to origin. Within 15 minutes,
the bidirectional sync timer on office2 pulls the change. The next agent run
uses the updated config.

### S2: Felix creates a log file, it syncs to origin

The felix-admin-capture agent processes inbox notes and writes a log to
`agents/logs/`. Within 15 minutes, the sync timer commits the new file and
pushes to origin. Kent can see the log by pulling on Mac.

### S3: Vault rename is transparent to Obsidian Sync

The vault directory is renamed from `vault/` to `notes/`. Obsidian Sync is
stopped before the rename and restarted with the updated path. Sync resumes
using the vault's internal ID — the rename does not affect sync identity.
A test note created on Mac appears on office2 within 5 minutes.

### S4: Inbox processing works after rename

After all path references are updated, felix-admin-capture processes inbox
notes from `notes/00-Inbox/`. A manual processing run completes cleanly with
no path-related errors.

### S5: office2 reboots, all services resume

After a reboot, the obsidian-sync service starts with the new vault path,
and the bidirectional git sync timer starts pulling/pushing non-vault content.
No manual intervention required.

## Functional requirements

| ID | Requirement | Status |
| --- | --- | --- |
| FR-01 | Stop and disable the vault-snapshot systemd timer on office2 | proposed |
| FR-02 | Delete the vault-snapshot script at `/home/kgale/helper-scripts/vault-snapshot.sh` | proposed |
| FR-03 | Remove the vault-snapshot systemd timer and service unit files | proposed |
| FR-04 | Remove the vault-snapshot entry from `service-inventory.json` | proposed |
| FR-05 | Add `notes/` to `.gitignore` in the second-brain repo on office2 so vault content is excluded from git | proposed |
| FR-06 | Remove any currently-tracked vault files from the git index without deleting from disk (`git rm --cached`) | proposed |
| FR-07 | Stop obsidian-sync.service before rename | proposed |
| FR-08 | Rename `/home/kgale/second-brain/vault/` contents to `/home/kgale/second-brain/notes/` and remove the empty `vault/` directory | proposed |
| FR-09 | Update the obsidian-sync.service unit file to reference the new `notes/` path | proposed |
| FR-10 | Restart obsidian-sync.service with the new path and verify sync resumes | proposed |
| FR-11 | Update vault path references in `scripts/openclaw/agents/felix-admin-capture/TOOLS.md` | proposed |
| FR-12 | Update vault path references in `scripts/openclaw/agents/felix-admin-habits/TOOLS.md` | proposed |
| FR-13 | Update vault path in any other agent or script files discovered by a pre-implementation grep | proposed |
| FR-14 | Deploy updated agent workspace files to office2 | proposed |
| FR-15 | Initialize a git repository in `/home/kgale/second-brain/` on office2 with `notes/` gitignored | proposed |
| FR-16 | Connect the office2 repo to the existing GitHub origin remote | proposed |
| FR-17 | Create a bidirectional git sync script that pulls from origin, auto-commits any local changes, and pushes | proposed |
| FR-18 | Create a systemd user timer that runs the sync script every 15 minutes | proposed |
| FR-19 | The sync script must handle the no-changes case gracefully (no empty commits, no errors) | proposed |
| FR-20 | The sync timer must run as the `kgale` user (git repo owner) | proposed |
| FR-21 | Verify end-to-end: create a test note on Mac, confirm it appears in `notes/00-Inbox/` on office2, trigger manual inbox processing, confirm success | proposed |
| FR-22 | Update `docs/design/architecture/data/service-inventory.json`: remove vault-snapshot, update obsidian-sync `data_path`, add second-brain-sync service entry | proposed |
| FR-23 | Update `docs/handbooks/obsidian-sync-ops.md` to reflect new vault path and removal of git snapshot strategy | proposed |
| FR-24 | Update `docs/handbooks/inbox-ops.md` vault path references | proposed |
| FR-25 | Update corresponding architecture markdown files to match JSON updates | proposed |

## Non-functional requirements

| ID | Requirement | Threshold | Status |
| --- | --- | --- | --- |
| NFR-01 | Bidirectional sync latency for non-vault content | Within 15 minutes of change | proposed |
| NFR-02 | Obsidian Sync resumes after vault rename | Sync active within 5 minutes of service restart | proposed |
| NFR-03 | Sync timer survives office2 reboots | Starts automatically via systemd | proposed |
| NFR-04 | Sync script handles merge conflicts gracefully | Logs conflict, does not force-push or lose data | proposed |
| NFR-05 | All path updates applied atomically with the rename | No window where agents run with stale paths | proposed |

## Constraints

| ID | Constraint | Status |
| --- | --- | --- |
| C-01 | Obsidian Sync is authoritative for vault content — git must never track or modify vault files | proposed |
| C-02 | The `claude` user on office2 does not have sudo access — any sudo operations must be presented to Kent for manual execution | proposed |
| C-03 | `~/second-brain/notes/02-Growth/_private/` is never read, written, referenced, or logged by any agent or script | proposed |
| C-04 | The obsidian-sync service runs as `kgale` user, not `claude` | proposed |
| C-05 | The bidirectional sync timer runs as `kgale` user (git repo owner) | proposed |
| C-06 | The sync script must use `git pull --ff-only` to avoid creating merge commits from diverged history — if fast-forward fails, log the error and skip | proposed |
| C-07 | Auto-commit messages must follow a standard format (e.g., `chore: auto-sync second-brain from office2`) | proposed |
| C-08 | Vault-snapshot removal must happen before the vault rename to avoid a snapshot during the rename | proposed |
| C-09 | All architecture JSON files updated by this feature must include `updated_by: "F011"` | proposed |

## Key entities

- **Vault** — the Obsidian vault at `/home/kgale/second-brain/notes/` on
  office2 (renamed from `vault/`), `~/second-brain/notes/` on Mac
- **Obsidian Sync** — Obsidian's cloud sync service, managing vault content
  across all devices via internal vault ID `d9a7cf01fedcdfcb`
- **vault-snapshot** — the systemd timer + script deployed by F010 for daily
  git commits of vault content; to be removed by this feature
- **obsidian-sync.service** — systemd user unit managing continuous vault
  sync on office2; path must be updated
- **second-brain-sync** — new systemd timer + script for bidirectional git
  sync of non-vault content between office2 and GitHub origin
- **second-brain repo** — the git repository at `~/second-brain/` on Mac
  (origin on GitHub) and `/home/kgale/second-brain/` on office2 (clone)

## Assumptions

- The Mac second-brain vault has already been renamed to `notes/` and the
  old `vault/` directory removed (completed before this feature)
- The Mac second-brain git repo (`.git/`) has been removed (completed
  before this feature; will be reinitialized on Mac separately if needed)
- The `kgale` user on office2 has SSH or HTTPS access to the GitHub remote
  for git push/pull operations
- The vault-snapshot timer and script exist on office2 as deployed by F010
- Obsidian Sync identifies vaults by internal ID, not filesystem path —
  the rename will not break sync identity

## Out of scope

- Renaming the Mac vault — already completed
- Changing Restic backup configuration — `/home/kgale` remains in backup
  scope; rename does not affect coverage
- Changing Obsidian Sync subscription or device configuration
- Any changes to vault content — this is structural/path changes only
- Reinitializing the Mac second-brain git repo (separate concern)
- Adding intelligence/, scripts/, or other previously-removed scaffolding

## Risk considerations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Obsidian Sync loses vault identity during rename | Low | High — sync breaks until reconfigured | Stop sync before rename; verify resume with test note |
| Stale path reference causes silent agent failure | Medium | High — agent reads from nonexistent path | Pre-implementation grep for all references; end-to-end verification |
| `git rm --cached` accidentally deletes files from disk | Low | Critical — vault content lost | Spec explicitly requires `--cached` flag; verify files exist after operation |
| Bidirectional sync creates merge conflict | Low | Low — sync pauses until resolved | `git pull --ff-only` avoids merge commits; conflict logged, no force-push |
| Vault-snapshot runs during rename operation | Low | Medium — commits partial state | Remove vault-snapshot before starting rename |

## Success criteria

- vault-snapshot timer removed and verified gone on office2
- `notes/` in `.gitignore`, vault files untracked from git
- `/home/kgale/second-brain/notes/` exists with all vault content
- `/home/kgale/second-brain/vault/` no longer exists
- Obsidian Sync running and syncing to `notes/`
- No references to `second-brain/vault` in any agent file, service file,
  or architecture doc
- felix-admin-capture reads from `notes/00-Inbox/` after restart
- Test note created on Mac appears on office2 within 5 minutes
- Manual inbox processing run completes cleanly
- Git repo initialized on office2 with `notes/` gitignored
- Bidirectional sync timer running every 15 minutes
- Non-vault content pushed from Mac reaches office2 within 15 minutes
- Agent-created files on office2 appear in origin within 15 minutes
- Architecture docs updated with `updated_by: "F011"`
- Runbooks reflect new paths and no git-snapshot references

## Architecture documentation updates

| File | Change |
| --- | --- |
| `data/service-inventory.json` | Remove vault-snapshot entry; update obsidian-sync `data_path` to `notes/`; add second-brain-sync entry; set `updated_by: "F011"` |
| `service-inventory.md` | Remove vault-snapshot; update obsidian-sync path; add second-brain-sync narrative |
| `data-flows.md` | Remove git snapshot from vault data flow; add bidirectional git sync flow for non-vault content |
| `docs/handbooks/obsidian-sync-ops.md` | Update vault path to `notes/`; remove git coexistence section |
| `docs/handbooks/inbox-ops.md` | Update vault path references |

## Constitutional compliance

- **Docs adjacent**: All path changes in agent files, service configs, and
  architecture docs happen in the same implementation as the operational
  changes
- **No silent failures**: FR-21 requires end-to-end verification after all
  changes before the feature is considered complete
- **Restic backup unchanged**: Vault content remains in Restic scope via
  `/home/kgale` — backup protection is not degraded by this change
- **Private boundary**: `notes/02-Growth/_private/` exclusion maintained (C-03)
- **Security over convenience**: Git sync uses existing SSH/HTTPS auth; no
  new credentials stored in committed files
