# Research: F011 Second Brain Vault Cleanup

**Date**: 2026-04-01
**Feature**: 011-second-brain-vault-cleanup

## R1: Vault-Snapshot Service State on office2

**Question**: What is the current state of the vault-snapshot infrastructure?

**Finding**: The vault-snapshot service, timer, and script **do not exist** on
office2. No systemd units, no script at `/home/kgale/helper-scripts/vault-snapshot.sh`.

**Decision**: FR-01 through FR-03 (stop/disable/delete vault-snapshot) become
**verification-only** — confirm absence rather than perform removal. FR-04
(remove from service-inventory.json) still applies since the entry exists in
the architecture docs.

**Rationale**: The vault-snapshot may have been removed during a prior session
or may never have been deployed. Either way, the on-server infrastructure is
already clean.

## R2: Obsidian-Sync Service State on office2

**Question**: Is obsidian-sync.service deployed on office2?

**Finding**: `obsidian-sync.service` does **not exist** as a systemd unit on
office2 (`Unit obsidian-sync.service could not be found`). The service file
exists in the repo at `scripts/office2/obsidian-sync.service` with path
`/home/kgale/second-brain/vault`.

**Decision**: The service file in the repo must be updated to use `notes/`
path, then deployed to office2 as a systemd user unit. This is a deploy task,
not just a path update.

**Current service file content**:
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

## R3: Git Credentials for kgale on office2

**Question**: Can kgale push/pull from GitHub on office2?

**Finding**: kgale has **no .gitconfig and no SSH keys** on office2. Git
operations require authentication setup.

**Decision**: Git auth setup for kgale on office2 is a **manual step** that
Kent must perform (SSH key generation, adding to GitHub, configuring
.gitconfig). The claude user cannot do this (no sudo, no access to kgale's
home directory for key generation). This must be a prerequisite or early WP
with manual steps.

**Alternatives considered**:
- HTTPS with token: Would work but less secure than SSH keys; token would
  need to be stored somewhere
- SSH key via claude user: Not possible — claude cannot write to
  `/home/kgale/.ssh/`
- Deploy key on the repo: Would limit to a single repo, which is fine, but
  still requires Kent to add to GitHub

**Recommendation**: SSH key pair, added to GitHub as a deploy key or to
Kent's account. Kent performs the setup manually.

## R4: Path References Inventory

**Question**: What files reference the old vault path?

### Actionable files (must be updated)

| File | Reference type |
| --- | --- |
| `scripts/office2/obsidian-sync.service` | `--path /home/kgale/second-brain/vault` |
| `scripts/office2/validate-obsidian-sync.sh` | Vault path in validation checks |
| `scripts/openclaw/agents/felix-admin-capture/TOOLS.md` | Vault root and inbox path |
| `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` | Vault path references |
| `scripts/openclaw/agents/felix-admin-habits/TOOLS.md` | Privacy boundary path |
| `docs/design/architecture/data/service-inventory.json` | `data_path` for obsidian-sync |
| `docs/design/architecture/data/data-flows.json` | Vault sync path |
| `docs/design/architecture/service-inventory.md` | Narrative vault path |
| `docs/design/architecture/data-flows.md` | Vault sync flow |
| `docs/design/architecture/glossary.md` | Vault definition |
| `docs/design/architecture/security-posture.md` | Privacy boundary path |
| `docs/design/architecture/backup-and-recovery.md` | Backup scope path |
| `docs/handbooks/obsidian-sync-ops.md` | Multiple vault path references |
| `docs/handbooks/inbox-ops.md` | Mac fallback path, troubleshooting |
| `CLAUDE.md` | Privacy boundary path |
| `ai-agents/claude-code-instructions.md` | Privacy boundary path |
| `ai-agents/claude-instructions.md` | Privacy boundary path |

### Deployed files on office2 (must be redeployed)

| File | Reference type |
| --- | --- |
| `/data/services/openclaw/inbox-agent/TOOLS.md` | Vault root and inbox path |
| `/data/services/openclaw/inbox-agent/AGENTS.md` | Vault path references |
| `/data/services/openclaw/habits-agent/TOOLS.md` | Privacy boundary path |

### Historical files (do NOT update — frozen records)

| File | Reason to leave |
| --- | --- |
| `docs/func-spec/F005_*.md` | Historical spec |
| `docs/func-spec/F008_*.md` | Historical spec |
| `docs/func-spec/F010_*.md` | Historical spec |
| `docs/func-spec/F011_*.md` | Input spec for this feature |
| `docs/archive/personal-ai-system-spec-v02.md` | Archived spec |
| `docs/design/personal-ai-system-spec-v03.md` | Design spec (references are contextual) |
| `docs/design/personal-ai-system-spec-v1.0.md` | Design spec |
| `docs/design/adversarial-analysis.md` | Analysis document |
| `docs/reports/second-brain-structure-audit-*.md` | Audit snapshot |
| `kitty-specs/005-*`, `006-*`, `008-*`, `009-*`, `010-*` | Completed feature specs |

## R5: Vault Directory State on office2

**Question**: What is the current vault structure?

**Finding**: Vault content is at `/home/kgale/second-brain/vault/` (numbered
folders directly under `vault/`, no `Notes/` subdirectory). The `notes/`
directory does not exist yet.

**Decision**: Rename is `vault/` → `notes/` (move contents, remove empty
`vault/`). No intermediate `Notes/` directory to deal with — the F011 spec's
FR-3 reference to `vault/Notes/` is outdated. The actual operation is simpler.

## R6: Second-Brain Repo on Mac (Origin)

**Question**: What is the state of the Mac second-brain for git initialization?

**Finding**: From the earlier audit session, the Mac second-brain `.git/` was
removed. A new git repo needs to be initialized on Mac, pushed to GitHub as
origin, then cloned/initialized on office2.

**Decision**: The Mac repo initialization is out of scope for F011 (per spec).
However, the office2 git init (FR-15/FR-16) depends on an origin existing.
This creates a dependency: either Mac repo init happens first (outside F011),
or F011 creates the GitHub repo and initializes both sides.

**Recommendation**: F011 should include creating the GitHub repo and
initializing on Mac as a prerequisite step, since the office2 sync timer
cannot function without an origin to push/pull from. This is a small addition
that unblocks the rest of the feature.
