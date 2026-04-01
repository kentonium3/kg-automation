---
work_package_id: WP04
title: Quickstart Guide and Validation
lane: planned
dependencies: [WP01, WP02, WP03]
requirement_refs:
- FR-06
- FR-07
- FR-11
- FR-12
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T013, T014, T015]
history:
- date: '2026-04-01T15:17:40Z'
  event: created
  actor: claude
---

# WP04: Quickstart Guide and Validation

## Implementation command

```bash
spec-kitty implement WP04 --base WP03
```

## Objective

Finalize the quickstart setup guide with exact commands, expected outputs,
and a post-setup validation script. This is the document Kent follows to
perform the manual Obsidian Sync setup on office2.

## Context

- **Quickstart file**: `kitty-specs/010-obsidian-sync-office2/quickstart.md` (already exists as draft from planning phase — update it)
- **Validation script**: `scripts/office2/validate-obsidian-sync.sh` (new)
- **Depends on WP01 artifacts**: service files at `scripts/office2/`
- **Depends on WP02**: runbook at `docs/handbooks/obsidian-sync-ops.md` (for cross-references)
- **Depends on WP03**: architecture docs updated (for cross-references)
- **All manual steps run as `kgale` user on office2 via `ssh office2-kgale`**

## Subtask guidance

### T013: Finalize quickstart guide

**Purpose**: Update the draft quickstart guide with final file paths from
WP01–WP03, exact expected command outputs, and cross-references to the
runbook and architecture docs.

**Steps**:
1. Read the existing `kitty-specs/010-obsidian-sync-office2/quickstart.md`
2. Update all file paths to match the actual WP01 artifacts:
   - Service file: `scripts/office2/obsidian-sync.service`
   - Snapshot script: `scripts/office2/vault-snapshot.sh`
   - Snapshot timer: `scripts/office2/vault-snapshot.timer`
   - Snapshot service: `scripts/office2/vault-snapshot.service`
   - Gitignore additions: `scripts/office2/gitignore-additions.txt`
3. Add expected output for each command step (e.g., what `ob sync-list-remote`
   looks like on success, what `systemctl --user status` shows when active)
4. Add a section for installing the gitignore additions:
   ```bash
   cat ~/repos/kg-automation/scripts/office2/gitignore-additions.txt >> /home/kgale/second-brain/.gitignore
   ```
5. Add cross-references:
   - Operations runbook: `docs/handbooks/obsidian-sync-ops.md`
   - Architecture: `docs/design/architecture/service-inventory.md`
6. Ensure the guide is sequentially ordered and each step has a verification
   command

**Files**: `kitty-specs/010-obsidian-sync-office2/quickstart.md` (edit)

**Validation**:
- [ ] All file paths match actual WP01 artifact locations
- [ ] Each step has a verification command with expected output
- [ ] Steps are in correct dependency order
- [ ] Cross-references to runbook and architecture docs included

---

### T014: Create post-setup validation script

**Purpose**: A script Kent runs on office2 after completing the quickstart
steps to verify everything is configured correctly.

**Steps**:
1. Create `scripts/office2/validate-obsidian-sync.sh`:
   ```bash
   #!/usr/bin/env bash
   # validate-obsidian-sync.sh — Post-setup validation for F010
   # Run as kgale user on office2 after completing quickstart guide
   set -euo pipefail

   PASS=0
   FAIL=0

   check() {
       local desc="$1"
       shift
       if "$@" >/dev/null 2>&1; then
           echo "  PASS: $desc"
           ((PASS++))
       else
           echo "  FAIL: $desc"
           ((FAIL++))
       fi
   }

   echo "=== F010 Obsidian Sync Validation ==="
   echo ""

   echo "--- ob CLI ---"
   check "ob CLI installed" which ob
   check "ob is logged in" ob sync-list-remote

   echo ""
   echo "--- Vault sync ---"
   check "Vault configured for sync" ob sync-list-local
   check "Sync status OK" ob sync-status --path /home/kgale/second-brain/vault

   echo ""
   echo "--- Systemd services ---"
   check "obsidian-sync.service active" systemctl --user is-active obsidian-sync
   check "vault-snapshot.timer active" systemctl --user is-active vault-snapshot.timer
   check "Linger enabled for kgale" loginctl show-user kgale -p Linger --value

   echo ""
   echo "--- Vault content ---"
   check "Vault directory exists" test -d /home/kgale/second-brain/vault
   check ".obsidian directory exists" test -d /home/kgale/second-brain/vault/.obsidian
   check "Inbox directory has files" test -n "$(ls /home/kgale/second-brain/vault/00-Inbox/ 2>/dev/null)"

   echo ""
   echo "--- Git snapshot ---"
   check "Git repo exists" test -d /home/kgale/second-brain/.git
   check "Git remote configured" git -C /home/kgale/second-brain remote get-url origin
   check "Snapshot script executable" test -x /home/kgale/helper-scripts/vault-snapshot.sh

   echo ""
   echo "=== Results: $PASS passed, $FAIL failed ==="
   if [ "$FAIL" -gt 0 ]; then
       echo "See docs/handbooks/obsidian-sync-ops.md for troubleshooting."
       exit 1
   fi
   ```

2. Mark executable: `chmod +x scripts/office2/validate-obsidian-sync.sh`

**Files**: `scripts/office2/validate-obsidian-sync.sh` (new, ~55 lines)

**Validation**:
- [ ] Script is executable
- [ ] Covers all critical checks: ob login, sync status, services, vault content, git
- [ ] Provides clear PASS/FAIL output
- [ ] References troubleshooting runbook on failure
- [ ] Does not require sudo (runs as kgale user)

---

### T015: Add backfill verification and inbox processing trigger

**Purpose**: Add instructions for verifying the vault backfill and
triggering the first inbox processing run after sync is current.

**Steps**:
1. Add to quickstart guide after sync verification:
   - **Backfill check**: Compare inbox file count on office2 vs Mac
     ```bash
     ls /home/kgale/second-brain/vault/00-Inbox/ | wc -l
     ```
   - Compare with Mac: `ls ~/second-brain/vault/Notes/00-Inbox/ | wc -l`
   - Note: counts should match (or be very close, within sync latency)

2. Add inbox processing trigger:
   ```bash
   # Run from office2 as claude user (ssh office2-claude)
   openclaw agent --agent felix-admin-capture \
     --message "Process the inbox now. Read all unprocessed files in 00-Inbox/, classify and route content per your standing orders, create Vikunja tasks for action items and research requests, route valid goal declarations, and write the processing log." \
     --json --timeout 300
   ```

3. Add verification:
   ```bash
   # Check processing log
   ls -t /home/kgale/second-brain/agents/logs/inbox-processing-*.md | head -1
   ```

**Files**: `kitty-specs/010-obsidian-sync-office2/quickstart.md` (edit)

**Validation**:
- [ ] Backfill verification compares office2 and Mac vault content
- [ ] Inbox processing command matches the pattern in `scripts/openclaw/agents/main-patches/inbox-delegation.md`
- [ ] Processing log check included

## Definition of Done

- [ ] `quickstart.md` updated with final paths, expected outputs, and cross-references
- [ ] `scripts/office2/validate-obsidian-sync.sh` exists and is executable
- [ ] Backfill verification steps documented
- [ ] Inbox processing trigger documented with correct command
- [ ] All cross-references to WP01–WP03 artifacts are correct

## Risks

- Quickstart guide references WP01 artifacts that may have changed during implementation. Mitigation: read actual files from `scripts/office2/` before updating paths.
- `openclaw agent` command syntax may have changed since F008. Mitigation: verify against `scripts/openclaw/agents/main-patches/inbox-delegation.md`.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`

## Reviewer guidance

- Walk through the quickstart guide step by step — does it make sense as a sequential checklist?
- Verify the validation script covers all success criteria from the spec
- Verify inbox processing command matches existing patterns
- Check that no step requires the `claude` user to do something that needs `kgale` access (or vice versa)
