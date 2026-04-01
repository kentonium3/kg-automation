# Implementation Plan: Second Brain Vault Cleanup

**Branch**: `main` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/011-second-brain-vault-cleanup/spec.md`

## Summary

Remove the redundant vault-snapshot references from architecture docs, rename
the vault directory from `vault/` to `notes/` on office2, update all path
references in agent files and service configs, initialize a git repo for
non-vault content with a bidirectional 15-minute sync timer, and verify
end-to-end.

Research revealed that the vault-snapshot service was already removed from
office2 (no timer, service, or script exists), the obsidian-sync service is
not deployed, and kgale has no git credentials on office2. The plan accounts
for these findings.

## Technical Context

**Language/Version**: Bash (scripts, systemd units), JSON/Markdown (docs)
**Primary Dependencies**: git, systemd, `ob` CLI (Obsidian headless sync)
**Storage**: Filesystem (second-brain directory tree)
**Testing**: Manual verification (end-to-end sync tests, path grep audits)
**Target Platform**: office2 (Ubuntu 24.04 LTS) + Mac (authoring)
**Project Type**: Infrastructure/operations
**Performance Goals**: Sync latency within 15 minutes (git), 5 minutes (Obsidian)
**Constraints**: claude user has no sudo; kgale user performs privileged ops
**Scale/Scope**: Single server, single repo, ~20 files to update

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
| --- | --- | --- |
| Test-first paradigm | Pass | Manual verification steps defined for each WP; automated tests not applicable to infrastructure/path changes |
| CI validation | Pass | validate_docs.py runs on push; updated docs must pass frontmatter checks |
| Privacy boundary | Pass | `notes/02-Growth/_private/` exclusion maintained in all updated files (C-03) |
| No credentials in code | Pass | Git SSH keys configured manually by Kent, not committed |
| Tailscale-only posture | Pass | No new inbound ports; git uses SSH outbound |
| Docs adjacent | Pass | Architecture docs and runbooks updated in same WPs as operational changes |
| Deployment target | Pass | All scripts/services target Linux (office2) |

## Project Structure

### Documentation (this feature)

```
kitty-specs/011-second-brain-vault-cleanup/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── spec.md              # Feature specification
├── meta.json            # Feature metadata
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks/               # Phase 2 output (created by /spec-kitty.tasks)
```

### Source Code (repository root)

```
scripts/
├── office2/
│   ├── obsidian-sync.service        # Updated: vault → notes path
│   ├── validate-obsidian-sync.sh    # Updated: vault → notes path
│   └── second-brain-sync.sh         # NEW: bidirectional git sync script
│   └── second-brain-sync.timer      # NEW: 15-minute systemd timer
├── openclaw/agents/
│   ├── felix-admin-capture/
│   │   ├── TOOLS.md                 # Updated: vault → notes path
│   │   └── AGENTS.md                # Updated: vault → notes path
│   └── felix-admin-habits/
│       └── TOOLS.md                 # Updated: vault → notes path

docs/
├── design/architecture/
│   ├── data/
│   │   ├── service-inventory.json   # Updated: remove vault-snapshot, update paths, add sync
│   │   └── data-flows.json          # Updated: vault → notes path
│   ├── service-inventory.md         # Updated: narrative
│   ├── data-flows.md                # Updated: narrative
│   ├── glossary.md                  # Updated: vault → notes
│   ├── security-posture.md          # Updated: privacy path
│   └── backup-and-recovery.md       # Updated: backup path
├── handbooks/
│   ├── obsidian-sync-ops.md         # Updated: vault → notes, remove git snapshot refs
│   └── inbox-ops.md                 # Updated: vault → notes

ai-agents/
├── claude-code-instructions.md      # Updated: privacy path
└── claude-instructions.md           # Updated: privacy path

CLAUDE.md                            # Updated: privacy path
```

**Structure Decision**: No new source directories. Changes are path updates
in existing files plus two new scripts/units for the sync timer.

## Key Design Decisions

### D1: Vault-Snapshot Removal Is Verification-Only

Research found no vault-snapshot infrastructure on office2. The service,
timer, and script do not exist. FR-01 through FR-03 become verification
steps rather than removal steps. FR-04 (remove from service-inventory.json)
still applies since the architecture docs still reference it.

### D2: Obsidian-Sync Service Must Be Deployed

The obsidian-sync service file exists in the repo but is not deployed on
office2. The path update and deployment happen together in the same WP.

### D3: Git Credentials Require Manual Setup by Kent

kgale has no .gitconfig or SSH keys on office2. Kent must:
1. Generate an SSH key pair on office2 (as kgale)
2. Add the public key to GitHub (deploy key or account key)
3. Configure .gitconfig with name and email

This is a manual prerequisite step presented to Kent with exact commands.

### D4: Mac Second-Brain Git Repo Initialization

The Mac second-brain `.git/` was removed during cleanup. A new repo must be
initialized on Mac and pushed to GitHub before office2 can clone/pull. This
is included in F011 as a prerequisite WP since the bidirectional sync timer
depends on it.

### D5: Bidirectional Sync Script Design

```
second-brain-sync.sh:
  1. cd /home/kgale/second-brain
  2. git pull --ff-only origin main
     - If fails: log "pull failed, skipping sync cycle" and exit 0
  3. git add -A (stages agent-created files)
     - Respects .gitignore (notes/ excluded)
  4. If changes staged:
     - git commit -m "chore: auto-sync second-brain from office2"
     - git push origin main
     - If push fails: log "push failed" and exit 0
  5. Exit 0 (always succeed for systemd — failures are logged, not fatal)
```

### D6: Path Update Scope

17 actionable files in the repo + 3 deployed files on office2. Historical
docs (completed feature specs, archived specs, audit reports) are NOT
updated — they are frozen records of past state.

### D7: Vault Rename Is Direct

The office2 vault is at `vault/` with numbered folders directly inside
(no `Notes/` subdirectory). The rename is `vault/` → `notes/` by moving
all contents, then removing the empty `vault/` directory.

## Sequencing

The implementation must follow this order (from spec):

1. **Verify** vault-snapshot absence on office2
2. **Initialize** Mac git repo, push to GitHub (prerequisite for office2)
3. **Rename** vault → notes on office2 (stop obsidian-sync first if running)
4. **Update** all path references in repo files
5. **Deploy** updated agent files and obsidian-sync service to office2
6. **Setup** git on office2 (credentials, clone/init, .gitignore)
7. **Create** and deploy bidirectional sync timer
8. **Restart** obsidian-sync and OpenClaw agents
9. **Verify** end-to-end (Obsidian Sync + inbox processing + git sync)
10. **Update** architecture docs and commit

## Complexity Tracking

No constitution violations to justify.
