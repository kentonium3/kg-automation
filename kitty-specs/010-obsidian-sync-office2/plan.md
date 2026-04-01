# Implementation Plan: Obsidian Sync on office2

**Branch**: `main` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/010-obsidian-sync-office2/spec.md`

## Summary

Configure Obsidian Sync on office2 via the `ob` CLI (v0.0.8, headless) so
the vault at `/home/kgale/second-brain/vault/` stays current with Mac and
iPhone. Define a git coexistence strategy where Obsidian Sync owns live
state and git provides daily outbound-only snapshots at 2AM ET. Backfill
the stale vault (unchanged since 2026-03-22), update architecture docs,
and create an operations runbook. This unblocks the F008 inbox processor
(felix-admin-capture) which currently reads stale content.

## Technical Context

**Language/Version**: Bash scripts, systemd unit files
**Primary Dependencies**: `ob` CLI v0.0.8 (Obsidian headless client), systemd, git
**Storage**: Obsidian vault at `/home/kgale/second-brain/vault/` (filesystem)
**Testing**: Manual verification — sync latency tests, reboot persistence tests, git snapshot tests
**Target Platform**: office2 (Ubuntu 24.04 LTS)
**Project Type**: Infrastructure/configuration
**Performance Goals**: Sync latency < 5 minutes between any two devices
**Constraints**: `claude` user cannot sudo; `kgale` user owns vault and runs services; `02-Growth/_private/` excluded from all agent access
**Scale/Scope**: Single vault, single server, 3 devices total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| Security over convenience | PASS | Obsidian Sync credentials entered by Kent only, stored locally by `ob`, not in committed files |
| Tailscale-only posture | PASS | Obsidian Sync uses outbound HTTPS to Obsidian cloud — no inbound ports exposed |
| Privacy boundary (02-Growth/_private/) | PASS | `--excluded-folders "02-Growth/_private"` configured in sync-config |
| No credentials in code | PASS | Login is interactive; service file contains no secrets |
| Docs adjacent | PASS | Architecture docs and runbook updated as part of implementation |
| TEST_FIRST directive | PASS | Each WP includes verification steps before proceeding; sync latency tested before declaring success |
| Services run on office2 | PASS | All deployment targets office2 |
| CI validation | N/A | No Python code; no doc frontmatter changes that trigger CI |

**Post-design re-check**: All gates still pass. No new concerns from design.

## Project Structure

### Documentation (this feature)

```
kitty-specs/010-obsidian-sync-office2/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 output
├── quickstart.md        # Setup guide
└── tasks.md             # Phase 2 output (created by /spec-kitty.tasks)
```

### Source (repository root)

```
scripts/office2/
├── obsidian-sync.service     # systemd user unit for continuous sync
├── vault-snapshot.sh         # git snapshot script (outbound-only)
└── vault-snapshot.timer      # systemd timer for 2AM ET daily snapshot

docs/handbooks/
└── obsidian-sync-ops.md      # Operations runbook

docs/design/architecture/
├── data/
│   ├── service-inventory.json  # Updated: obsidian-sync entry
│   └── data-flows.json         # Updated: vault sync flow
├── service-inventory.md        # Updated narrative
└── data-flows.md               # Updated narrative
```

**Structure Decision**: No `src/` directory needed. This feature produces
systemd unit files, a Bash snapshot script, documentation, and architecture
updates. All artifacts live under `scripts/office2/` and `docs/`.

## Implementation Approach

### Manual steps (Kent must perform)

These steps require the `kgale` user on office2 and cannot be automated
by the `claude` user:

1. **Login**: `ob login --email <email>` (enter password and MFA when prompted)
2. **List remote vaults**: `ob sync-list-remote` (identify the vault name/ID)
3. **Setup sync**: `ob sync-setup --vault <vault-name> --path /home/kgale/second-brain/vault --device-name office2 --password <e2ee-password>`
4. **Configure sync**: `ob sync-config --path /home/kgale/second-brain/vault --mode bidirectional --conflict-strategy merge --excluded-folders "02-Growth/_private" --device-name office2`
5. **Install service file**: Copy `scripts/office2/obsidian-sync.service` to `~/.config/systemd/user/`
6. **Install timer**: Copy `scripts/office2/vault-snapshot.timer` and `vault-snapshot.sh` to appropriate locations
7. **Enable linger**: `sudo loginctl enable-linger kgale` (requires sudo)
8. **Enable and start**: `systemctl --user enable --now obsidian-sync` and `systemctl --user enable --now vault-snapshot.timer`

### Automated artifacts (created by implementation WPs)

- systemd service file (`obsidian-sync.service`)
- systemd timer file (`vault-snapshot.timer`)
- git snapshot script (`vault-snapshot.sh`)
- operations runbook
- architecture documentation updates
- setup quickstart guide with exact commands

### Verification sequence

1. After sync-setup: `ob sync-status --path /home/kgale/second-brain/vault`
2. After service start: `systemctl --user status obsidian-sync`
3. Sync latency test: Create a test note on Mac, verify it appears on office2 within 5 minutes
4. Reverse test: Modify a note on office2, verify it appears on Mac within 5 minutes
5. Reboot test: Reboot office2, verify service restarts and sync resumes
6. Snapshot test: Run `vault-snapshot.sh` manually, verify clean git commit and push
7. Backfill check: Verify inbox notes from March 22 onward are present on office2

### Git coexistence design

```
Obsidian Sync (live, continuous)
├── Direction: bidirectional
├── Authoritative for: live vault state
├── Runs: always (systemd service)
└── Conflict strategy: merge

Git snapshot (periodic, outbound-only)
├── Direction: outbound only (add → commit → push)
├── Authoritative for: version history and backup
├── Runs: 2AM ET daily (systemd timer)
├── Never: pulls, resets, or checks out
└── Avoids: 7AM, 12PM, 6PM ET (inbox processing windows)
```

**`.gitignore` additions** for the second-brain repo:
```
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/sync-*.json
```

### Excluded folder handling

`ob sync-config --excluded-folders "02-Growth/_private"` ensures the
privacy-protected directory is never synced to/from office2 via Obsidian
Sync. This is a constitutional hard boundary. The folder should also remain
in `.gitignore`.

## Complexity Tracking

No constitution violations. No complexity justifications needed.

## Work Package Outline (preliminary)

| WP | Focus | Dependencies |
|----|-------|-------------|
| WP01 | Create systemd service file, snapshot script, snapshot timer | None |
| WP02 | Create operations runbook | WP01 (references service and script) |
| WP03 | Update architecture documentation (JSON + markdown) | WP01 (references service config) |
| WP04 | Create quickstart guide with exact setup commands | WP01, WP02 |
| WP05 | Manual setup execution: login, sync-setup, service enable, backfill verification | WP01–WP04 (all artifacts ready) |

**Note**: WP05 is a manual step performed by Kent using the quickstart
guide. The implementation WPs (01–04) create all the artifacts Kent needs.

## Risk Mitigations

| Risk | Mitigation in this plan |
|------|------------------------|
| `ob` auth flow has undocumented requirements | Research captured exact CLI flags; quickstart guide provides step-by-step with expected output |
| Git snapshot conflicts with sync | Outbound-only design; never pulls; scheduled outside processing windows |
| Service doesn't survive reboot | `loginctl enable-linger` + `WantedBy=default.target`; reboot test in verification |
| Vault path mismatch | Confirmed path match: `/home/kgale/second-brain/vault/` in both TOOLS.md and `ob sync-setup` |
| Privacy folder synced by accident | `--excluded-folders "02-Growth/_private"` set during sync-config; verified in runbook |
