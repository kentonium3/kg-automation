---
title: "F010: Obsidian Sync on office2"
doc_type: func-spec
status: draft
feature: F010
---

# F010: Obsidian Sync on office2

**Version**: 1.0
**Priority**: CRITICAL
**Type**: Infrastructure

---

## Executive Summary

F008 deployed the inbox processing agent on office2, but the agent is
processing stale vault content from March 22. The vault on office2 has
never been connected to Obsidian Sync — it was only populated via a
one-time git clone. Notes captured on Mac or iPhone via Wispr Flow never
reach office2. This means the inbox processor is effectively blind.

This feature is a prerequisite for F008 to function as designed.

Current gaps:
- ❌ office2 vault is stale — last updated March 22 via git clone
- ❌ Obsidian Sync not configured on office2
- ❌ Notes from Mac and iPhone never reach office2
- ❌ felix-admin-capture is processing nothing new
- ❌ Git is the current sync mechanism — incompatible with live Obsidian Sync

This spec delivers a properly configured Obsidian Sync connection on
office2 using the Obsidian CLI (headless), with a defined strategy for
how git and Obsidian Sync coexist without conflicts.

---

## Problem Statement

**Current State:**
```
iPhone / Mac
└── ✅ Obsidian Sync active (Mac ↔ iPhone ↔ Obsidian cloud)
└── ❌ office2 NOT in the Obsidian Sync loop

office2 vault
└── ❌ Contains only March 22 notes (git clone, never updated)
└── ❌ No live sync from Mac or iPhone
└── ❌ Obsidian CLI installed but sync not configured

felix-admin-capture (F008)
└── ✅ Deployed and scheduled 3× daily
└── ❌ Reading stale vault — no new inbox notes to process
```

**Target State:**
```
iPhone / Mac / office2
└── ✅ All three devices in Obsidian Sync loop
└── ✅ Notes captured on any device reach office2 within minutes

office2 vault
└── ✅ Live and current via Obsidian Sync (headless via Obsidian CLI)
└── ✅ obsidian-sync.service running and maintaining connection

felix-admin-capture (F008)
└── ✅ Reads current vault content
└── ✅ Processes inbox notes as Kent captures them
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Current vault and sync state on office2**
   - `docs/design/architecture/data/service-inventory.json` — obsidian-sync
     service entry shows `data_path: /home/kgale/second-brain/vault` and
     `binary: /usr/bin/ob`. The service is listed as running but the vault
     content shows it is not actually syncing.
   - SSH to office2 and verify the actual state:
     - Is `obsidian-sync.service` active? (`systemctl --user status obsidian-sync`)
     - What does `ob sync --help` show for available commands and auth options?
     - Is there an existing Obsidian Sync credential or session on office2?

2. **Obsidian CLI documentation**
   - Research the `ob` CLI tool to understand:
     - How Obsidian Sync authentication works in headless mode
     - How to specify which vault to sync
     - How continuous sync is configured vs. one-shot sync
     - Whether it requires a GUI for initial auth or can be done headlessly

3. **Git and Obsidian Sync conflict risk**
   - `docs/design/architecture/data/service-inventory.json` — obsidian-sync
     service entry and the second-brain repo structure
   - The vault at `/home/kgale/second-brain/vault` is inside a git repo
     (`/home/kgale/second-brain/`). Simultaneous Obsidian Sync writes and
     git operations on the same files will cause conflicts.
   - Planning phase must design a coexistence strategy before implementation.

4. **F008 inbox processor vault path**
   - `scripts/openclaw/agents/felix-admin-capture/TOOLS.md` (or equivalent)
     — verify the exact vault path the inbox processor reads from so F010
     syncs to the correct location.

---

## Functional Requirements

### FR-1: Obsidian Sync Configured on office2

**What it must do:**
- Configure the Obsidian CLI (`ob`) on office2 to sync Kent's vault to
  `/home/kgale/second-brain/vault/Notes/` continuously
- The sync must use Kent's existing Obsidian Sync subscription and vault —
  the same vault already syncing between Mac and iPhone
- Once configured, new notes captured on Mac or iPhone must appear on
  office2 within a reasonable time (target: within 5 minutes of creation)

**Business rules:**
- The sync must run as the `kgale` user (who owns the vault directory),
  not the `claude` user
- Authentication credentials for Obsidian Sync must be stored securely —
  not in committed files
- The sync must survive office2 reboots — managed via systemd

**Success criteria:**
- [ ] `ob sync` authenticated with Kent's Obsidian account on office2
- [ ] A note created on Mac or iPhone appears on office2 within 5 minutes
- [ ] A note created on office2 appears on Mac and iPhone within 5 minutes
- [ ] Sync survives office2 reboot (systemd service)

---

### FR-2: Git and Obsidian Sync Coexistence Strategy

**What it must do:**
- Define and implement a strategy that allows both Obsidian Sync (live,
  continuous) and git (periodic snapshot/backup) to operate on the vault
  without conflicts or race conditions
- Obsidian Sync is authoritative for live vault state — git must not
  overwrite Obsidian Sync changes
- Git continues to provide version history and backup for the vault

**Recommended strategy (planning phase to validate and implement):**
- Obsidian Sync owns live read/write of all vault files
- Git operates as a scheduled snapshot — a daily or weekly `git add`,
  `git commit`, `git push` that captures current vault state as a point
  in time
- Git never pulls or resets vault files on office2 — it only commits
  outward
- `.gitignore` additions may be needed to exclude Obsidian Sync metadata
  files that should not be committed

**Business rules:**
- Obsidian Sync always wins for live content — git must not interfere
  with sync operations
- The git snapshot schedule must not run during the inbox processing
  cron windows (7AM, 12PM, 6PM ET) to avoid file contention
- If git and Obsidian Sync ever conflict on a file, Obsidian Sync's
  version is the correct one

**Success criteria:**
- [ ] Obsidian Sync and git can both operate on the vault without errors
- [ ] A vault file updated by Obsidian Sync is not overwritten by git pull
- [ ] Git snapshot schedule does not overlap with inbox processing crons
- [ ] Coexistence strategy documented in runbook

---

### FR-3: Vault Backfill

**What it must do:**
- After Obsidian Sync is configured and running, the vault on office2
  must be brought fully current — all notes from Mac and iPhone that
  accumulated since March 22 must be present
- The inbox processor must then process any notes with `status: unprocessed`
  that have not yet been seen by office2

**Business rules:**
- The backfill happens automatically once Obsidian Sync is connected —
  Obsidian Sync will pull all missing content from the cloud
- Do not manually copy files — let Obsidian Sync do the reconciliation
- After sync is confirmed current, trigger a manual inbox processing run
  to process any backlogged unprocessed notes

**Success criteria:**
- [ ] After sync, office2 vault matches Mac vault content
- [ ] Inbox notes from March 22 onward that are `status: unprocessed`
  are visible on office2
- [ ] Manual inbox processing run triggered and completes successfully

---

### FR-4: Updated obsidian-sync.service

**What it must do:**
- Update or replace the existing `obsidian-sync.service` systemd unit to
  use the correct `ob sync` command with the configured vault
- Service must start on boot, restart on failure, and run as `kgale` user
- The existing service entry in the architecture docs must be updated to
  reflect the correct configuration

**Success criteria:**
- [ ] `systemctl --user status obsidian-sync` shows active and running
  (as kgale user)
- [ ] Service starts automatically on boot
- [ ] `ob` CLI authenticated and syncing the correct vault

---

### FR-5: Operations Runbook

**What it must do:**
- Create or update `docs/handbooks/obsidian-sync-ops.md` covering:
  - How Obsidian Sync is configured on office2
  - How to check sync status
  - How to re-authenticate if credentials expire
  - The git coexistence strategy and schedule
  - How to trigger a manual sync
  - Troubleshooting: note not appearing on office2, sync conflicts

**Success criteria:**
- [ ] Runbook exists and covers all topics
- [ ] Passes doc validation (frontmatter compliant)

---

## Architecture Documentation Updates

F010 changes the vault sync mechanism — a significant data flow change.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Update obsidian-sync entry to reflect actual configuration (auth method, vault path, sync direction); update `updated_by` to F010 |
| `data/data-flows.json` | Update vault sync data flow to reflect Obsidian Sync as live mechanism and git as snapshot |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Update obsidian-sync service details |
| `data-flows.md` | Update vault sync flow description |

**Success criteria:**
- [ ] All modified JSON files have `updated_by: "F010"`
- [ ] Architecture docs accurately reflect the sync mechanism

---

## Out of Scope

- ❌ Vault restructuring (moving vault root from vault/Notes to vault) —
  a separate decision; this spec syncs the existing vault structure
- ❌ Git hosting changes — the second-brain GitHub repo remains as-is
- ❌ Obsidian Sync for the kg-automation repo — that is a separate repo,
  not a vault
- ❌ iPhone or Mac Obsidian Sync configuration — already working; this
  spec only adds office2

---

## Success Criteria

**Complete when:**

### Sync Working
- [ ] office2 vault receives notes from Mac/iPhone within 5 minutes
- [ ] Notes from office2 appear on Mac/iPhone within 5 minutes
- [ ] obsidian-sync.service active and persists across reboots

### Coexistence
- [ ] Git snapshot strategy implemented and scheduled
- [ ] No conflicts between Obsidian Sync and git operations documented

### Backfill
- [ ] office2 vault current with Mac/iPhone content
- [ ] Backlogged unprocessed inbox notes processed

### Documentation
- [ ] `docs/handbooks/obsidian-sync-ops.md` complete and CI-passing
- [ ] Architecture docs updated

---

## Architecture Principles

### Obsidian Sync Is Authoritative for Live State

Obsidian Sync is designed to be the authoritative sync mechanism for
Obsidian vaults. It handles conflict resolution, metadata, and real-time
propagation. Git should not compete with it — it should complement it
as a versioning and backup layer. This separation of concerns prevents
the race conditions that would occur if both tried to own live sync.

### The Inbox Processor Depends on This

F008's felix-admin-capture is currently deployed but not functional
because it has no current content to process. F010 is not optional
infrastructure — it is the prerequisite that makes F008 actually work.
Every subsequent feature that reads from or writes to the vault also
depends on this being correct.

---

## Constitutional Compliance

✅ **Security over convenience**: Obsidian Sync credentials stored
securely on office2, not committed to git.

✅ **Tailscale-only posture**: Obsidian Sync uses Obsidian's cloud
service for sync — this is an outbound connection from office2, not
an inbound one. The Tailscale-only constraint applies to services
exposed on office2, not outbound connections to external services.

✅ **Docs adjacent**: Architecture docs and runbook updated alongside
deployment.

---

## Risk Considerations

**Risk: Obsidian CLI headless auth is difficult or unsupported**
- The `ob` CLI may require a GUI for initial authentication.
- Mitigation: Planning phase verifies headless auth capability before
  implementation. If `ob` cannot authenticate headlessly, research
  alternatives (rclone with WebDAV, or Obsidian LiveSync as an
  alternative sync plugin).

**Risk: Git conflict on vault files during sync**
- Mitigation: Git snapshot is outbound-only (commit + push, never pull).
  Schedule snapshot outside inbox processing windows.

**Risk: Obsidian Sync device limit**
- Adding office2 as a third device may require plan verification.
- Mitigation: Planning phase verifies subscription supports 3+ devices
  before proceeding.

---

## Notes for Implementation

**First discovery step**: SSH to office2 and run `ob --version` and
`ob sync --help` to understand what the CLI supports before planning
anything. The capabilities of the installed version determine the
implementation approach.

**If headless auth is blocked**: Research Obsidian LiveSync (a
community plugin) as an alternative — it uses CouchDB or S3 as a sync
backend and is designed for server deployments.

**Vault path alignment**: Verify the exact path felix-admin-capture
reads from and ensure F010 syncs to the same location.

---

**END OF SPECIFICATION**
