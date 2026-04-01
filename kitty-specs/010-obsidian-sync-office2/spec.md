# F010: Obsidian Sync on office2

## Overview

Connect office2 to Kent's existing Obsidian Sync loop so that the vault on
office2 stays current with Mac and iPhone. The vault at
`/home/kgale/second-brain/vault` is currently stale (last updated 2026-03-22
via git clone). Obsidian Sync is already active between Mac and iPhone but
office2 was never added. This means the F008 inbox processor
(felix-admin-capture) is reading stale content and processing nothing new.

This feature configures the `ob` CLI on office2 for headless Obsidian Sync,
defines a coexistence strategy so git and Obsidian Sync do not conflict,
backfills the stale vault, and updates architecture documentation.

## Problem statement

F008 deployed the inbox processing agent on office2, scheduled 3x daily. But
the agent reads from a vault that has not been updated since March 22. Notes
captured on Mac or iPhone via Wispr Flow never reach office2. The inbox
processor is effectively blind. The previous sync path (Cowork inbox processor
on Mac → Obsidian Sync to phone) was deleted on 2026-03-31, fully exposing
the gap. office2 must join the Obsidian Sync loop for the system to function.

## Actors

- **Kent** — vault owner. Captures notes on Mac and iPhone. Sole Obsidian
  Sync subscriber.
- **office2** — Ubuntu 24.04 LTS server. Hosts the vault, inbox processor,
  and OpenClaw agents. Runs as `kgale` user for vault operations, `claude`
  user for agent operations.
- **felix-admin-capture** — F008 inbox processing agent on office2. Reads
  from the vault's inbox directory. Depends on vault being current.
- **Obsidian Sync** — Obsidian's cloud sync service. Already syncing
  Mac ↔ iPhone ↔ Obsidian cloud. office2 must be added as a third device.

## User scenarios

### S1: Note captured on iPhone reaches office2

Kent dictates a note on iPhone via Wispr Flow. The note appears in the
vault's inbox on iPhone, syncs to Obsidian cloud, and arrives on office2
within 5 minutes. The next scheduled inbox processing run picks it up.

### S2: Inbox processor reads current content

felix-admin-capture runs at its scheduled time (7AM, 12PM, 6PM ET). It
reads the vault inbox on office2 and finds notes captured since the last
run. It processes them normally — no stale content, no missed notes.

### S3: office2 vault edit syncs outward

An agent on office2 writes a status update to a vault note (e.g., updating
an inbox note's frontmatter to `status: processed`). The change syncs to
Obsidian cloud and appears on Mac and iPhone within 5 minutes.

### S4: office2 reboots and sync resumes

office2 reboots (planned or unplanned). The obsidian-sync systemd service
starts automatically. Sync resumes and any notes captured during downtime
are pulled from Obsidian cloud.

### S5: Git snapshot runs without conflict

A scheduled git snapshot commits the current vault state for backup/version
history. The snapshot does not interfere with Obsidian Sync, does not
overwrite any files, and does not run during inbox processing windows.

### S6: Backfill after initial sync

After Obsidian Sync is first configured and connected, all notes from
Mac and iPhone that accumulated since March 22 flow to office2. A manual
inbox processing run is triggered to clear the backlog.

## Functional requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-01 | Configure the `ob` CLI on office2 to authenticate with Kent's Obsidian Sync account headlessly | proposed |
| FR-02 | Connect office2 to the same vault that Mac and iPhone sync to, targeting `/home/kgale/second-brain/vault` | proposed |
| FR-03 | Obsidian Sync must run continuously on office2, maintaining a live connection to the Obsidian cloud | proposed |
| FR-04 | The sync service must run as the `kgale` user (vault directory owner), not the `claude` user | proposed |
| FR-05 | Create or update `obsidian-sync.service` as a systemd user unit that starts on boot and restarts on failure | proposed |
| FR-06 | Notes created on Mac or iPhone must appear on office2 within 5 minutes of creation | proposed |
| FR-07 | Notes created or modified on office2 must appear on Mac and iPhone within 5 minutes | proposed |
| FR-08 | Define and implement a git coexistence strategy: Obsidian Sync owns live state, git provides periodic snapshot/backup | proposed |
| FR-09 | Git snapshot operates outbound-only (add, commit, push) — never pulls or resets vault files on office2 | proposed |
| FR-10 | Git snapshot schedule must not overlap with inbox processing cron windows (7AM, 12PM, 6PM ET) | proposed |
| FR-11 | After initial sync, backfill all notes accumulated since March 22 from Obsidian cloud to office2 | proposed |
| FR-12 | After backfill is confirmed, trigger a manual inbox processing run to clear backlogged unprocessed notes | proposed |
| FR-13 | Create or update `docs/handbooks/obsidian-sync-ops.md` covering sync configuration, status checks, re-authentication, git coexistence, manual sync, and troubleshooting | proposed |
| FR-14 | Update `docs/design/architecture/data/service-inventory.json` and `data/data-flows.json` to reflect Obsidian Sync as the live vault sync mechanism | proposed |
| FR-15 | Update corresponding architecture markdown files (`service-inventory.md`, `data-flows.md`) to match JSON updates | proposed |
| FR-16 | Obsidian Sync authentication credentials must be stored securely on office2 — not in committed files | proposed |

## Non-functional requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-01 | Sync latency for new notes between any two devices | Within 5 minutes | proposed |
| NFR-02 | obsidian-sync.service uptime after configuration | Survives reboots, restarts on failure within 30 seconds | proposed |
| NFR-03 | Git snapshot must complete without interfering with active Obsidian Sync | Zero sync errors during or after snapshot | proposed |

## Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-01 | Obsidian Sync is authoritative for live vault state — git must never overwrite Obsidian Sync changes | proposed |
| C-02 | The vault path on office2 is `/home/kgale/second-brain/vault` — must match the path felix-admin-capture reads from | proposed |
| C-03 | The `claude` user on office2 does not have sudo access — any sudo operations must be presented to Kent for manual execution | proposed |
| C-04 | `~/second-brain/vault/Notes/02-Growth/_private/` is never read, written, referenced, or logged by any agent or script | proposed |
| C-05 | The obsidian-sync service runs as `kgale` user, not `claude` | proposed |
| C-06 | All architecture JSON files updated by this feature must include `updated_by: "F010"` | proposed |

## Key entities

- **Vault** — the Obsidian vault at `/home/kgale/second-brain/vault` on
  office2, `~/second-brain/vault` on Mac
- **Obsidian Sync** — Obsidian's cloud sync service (paid subscription,
  already active for Mac and iPhone)
- **`ob` CLI** — Obsidian's headless CLI tool, installed on office2
- **obsidian-sync.service** — systemd user unit managing continuous sync
- **Git snapshot** — scheduled outbound-only git commit of vault state
  for backup/version history

## Assumptions

- Kent's Obsidian Sync subscription supports adding office2 as a third
  device (no device limit encountered)
- The `ob` CLI supports headless authentication (confirmed by Kent)
- The `ob` CLI is already installed on office2 at `/usr/bin/ob`
- felix-admin-capture reads from `/home/kgale/second-brain/vault/Notes/`
  (to be verified during planning/research)
- The existing git repo at `/home/kgale/second-brain/` will retain its
  `.git` directory; Obsidian Sync operates alongside it

## Out of scope

- Vault restructuring (moving vault root path)
- Git hosting changes for the second-brain GitHub repo
- Obsidian Sync configuration changes on Mac or iPhone
- Obsidian Sync for the kg-automation repo (not a vault)
- Changes to felix-admin-capture's processing logic (F008 scope)

## Risk considerations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Git conflict on vault files during active sync | Low (if outbound-only) | Medium — could corrupt notes | Git snapshot is outbound-only; never pulls. Schedule outside processing windows. |
| `ob` CLI behavior differs from expectations | Low (headless auth confirmed) | Medium — may need different flags or config | Research phase verifies exact commands before implementation |
| Obsidian Sync credential expiry | Low | Medium — sync stops until re-auth | Runbook documents re-authentication procedure |
| Vault path mismatch with inbox processor | Low | High — processor still reads stale content | Planning phase verifies exact path alignment |

## Success criteria

- Notes captured on Mac or iPhone appear on office2 within 5 minutes
- Notes created or modified on office2 appear on Mac and iPhone within 5 minutes
- `systemctl --user status obsidian-sync` (as kgale) shows active and running
- obsidian-sync.service starts automatically after office2 reboot
- Git snapshot runs on schedule without Obsidian Sync errors
- office2 vault matches Mac vault content after initial sync
- Backlogged unprocessed inbox notes are processed successfully
- Operations runbook exists at `docs/handbooks/obsidian-sync-ops.md`
- Architecture docs updated with `updated_by: "F010"`

## Architecture documentation updates

| File | Change |
|------|--------|
| `data/service-inventory.json` | Update obsidian-sync entry: auth method, vault path, sync direction, correct status |
| `data/data-flows.json` | Update vault sync flow: Obsidian Sync as live mechanism, git as snapshot |
| `service-inventory.md` | Update obsidian-sync service narrative |
| `data-flows.md` | Update vault sync flow narrative |

## Constitutional compliance

- **Security over convenience**: Obsidian Sync credentials stored securely
  on office2, not in committed files
- **Tailscale-only posture**: Obsidian Sync uses outbound connections to
  Obsidian's cloud — no inbound ports exposed on office2
- **Docs adjacent**: Architecture docs and runbook updated alongside
  deployment
- **Private boundary**: `02-Growth/_private/` exclusion maintained
