# Research: Obsidian Sync on office2

**Feature**: F010 (010-obsidian-sync-office2)
**Date**: 2026-04-01

## R1: `ob` CLI Interface on office2

**Decision**: Use `ob` CLI v0.0.8 (already installed at `/usr/bin/ob`) for
headless Obsidian Sync.

**Findings**:

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `ob login` | Authenticate with Obsidian account | `--email`, `--password`, `--mfa` |
| `ob logout` | Clear stored credentials | — |
| `ob sync-list-remote` | List remote vaults (requires login) | — |
| `ob sync-list-local` | List locally configured vaults | — |
| `ob sync-setup` | Connect local vault to remote vault | `--vault`, `--path`, `--password` (e2ee), `--device-name`, `--config-dir` |
| `ob sync-config` | Configure sync behavior | `--mode`, `--conflict-strategy`, `--excluded-folders`, `--file-types`, `--device-name` |
| `ob sync-status` | Show sync status | `--path` |
| `ob sync` | Run sync | `--path`, `--continuous` |
| `ob sync-unlink` | Disconnect vault from sync | `--path` |

**Current state on office2**:
- Not logged in (`ob sync-list-remote` returns "No account logged in")
- No vaults configured (`ob sync-list-local` returns "No vaults configured")
- No existing `obsidian-sync.service` systemd unit file

**Rationale**: The CLI provides exactly the commands needed: headless login,
vault setup, continuous sync mode, and configuration for conflict strategy
and excluded folders.

**Alternatives considered**: Obsidian LiveSync (community plugin using
CouchDB) — rejected because Kent already has a working Obsidian Sync
subscription and the official CLI supports headless operation.

## R2: Authentication Flow

**Decision**: Kent must run `ob login` interactively as the `kgale` user on
office2. The `claude` user cannot perform this step.

**Findings**:
- `ob login` accepts `--email`, `--password`, and `--mfa` as CLI flags
- Credentials are stored locally after login (not in a config file we manage)
- The `claude` user does not own the vault directory and cannot sudo
- Initial login and `sync-setup` are one-time manual steps

**Rationale**: Security boundary — credentials should only be entered by
Kent. The automation (systemd service) runs after initial setup is complete.

## R3: Sync Configuration Options

**Decision**: Use bidirectional sync with merge conflict strategy and
exclude `02-Growth/_private/`.

**Findings**:
- `--mode bidirectional` (default) — both directions, appropriate since
  office2 agents write to vault notes (e.g., setting `status: processed`)
- `--conflict-strategy merge` — Obsidian's merge strategy (vs `conflict`
  which creates conflict files)
- `--excluded-folders "02-Growth/_private"` — respects the privacy boundary
- `--device-name "office2"` — identifies this device in sync version history

**Rationale**: Bidirectional is required because felix-admin-capture writes
status updates to vault notes. The privacy exclusion is a hard constitutional
boundary.

## R4: Vault Path Alignment

**Decision**: Sync target is `/home/kgale/second-brain/vault/` — confirmed
to match felix-admin-capture's configured path.

**Findings**:
- TOOLS.md: `Path on office2: /home/kgale/second-brain/vault/`
- TOOLS.md: `Inbox: /home/kgale/second-brain/vault/00-Inbox/`
- Vault directory listing confirms structure: `00-Inbox/`, `01-Constitution/`,
  `02-Growth/`, etc. directly under `vault/`
- `.obsidian/` config directory already exists in vault root
- The vault is inside a git repo at `/home/kgale/second-brain/`

**Note**: There is also a separate copy at `/home/claude/second-brain/vault/Notes/`
(the claude user's git clone). This is NOT the vault felix-admin-capture reads
from. F010 only targets the kgale vault.

## R5: Git Coexistence Strategy

**Decision**: Git operates as outbound-only daily snapshot at 2AM ET. Never
pulls or resets. Obsidian Sync is authoritative for live state.

**Findings**:
- The vault is inside git repo `/home/kgale/second-brain/` (has `.git/`)
- Git currently has only 1 commit ("Initial commit") — effectively unused
  for sync since initial clone
- `.gitignore` exists but needs review for Obsidian Sync metadata exclusions
- `ob sync` writes to `.obsidian/` directory — some of these files should
  be gitignored (sync metadata, workspace state)

**Implementation**:
- systemd timer or cron job at 2AM ET daily (as kgale user)
- Script: `git add -A && git commit -m "vault snapshot $(date +%Y-%m-%d)" && git push`
- Never runs `git pull`, `git reset`, or `git checkout`
- Schedule avoids inbox processing windows (7AM, 12PM, 6PM ET)
- `.gitignore` updated to exclude `.obsidian/workspace*.json` and sync
  metadata files

**Rationale**: Git provides backup and version history without competing
with Obsidian Sync for live state. The outbound-only constraint prevents
git from ever overwriting Obsidian Sync changes.

## R6: Systemd Service Design

**Decision**: User-level systemd unit running as `kgale`, executing
`ob sync --path /home/kgale/second-brain/vault --continuous`.

**Findings**:
- No existing `obsidian-sync.service` file on office2
- Service must run as `kgale` (vault owner), not root or claude
- `ob sync --continuous` is the persistent sync mode
- systemd user units live at `~/.config/systemd/user/` for the kgale user
- The `claude` user cannot create files under kgale's home — Kent must
  install the service file manually or we create it in the repo and Kent
  copies it

**Implementation**:
- Create service file in repo: `scripts/office2/obsidian-sync.service`
- Kent copies to `/home/kgale/.config/systemd/user/obsidian-sync.service`
- `systemctl --user enable --now obsidian-sync`
- Service configured with `Restart=on-failure`, `RestartSec=30`
- `WantedBy=default.target` for boot start
- `loginctl enable-linger kgale` required for user services to start at boot
  without login (Kent runs this with sudo)
