---
work_package_id: WP08
title: Deploy script and systemd unit update
dependencies:
- WP06
requirement_refs:
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T036
- T037
- T038
- T039
phase: Phase 4 — Verification
assignee: ''
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "25577"
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/office2/
execution_mode: code_change
owned_files:
- scripts/office2/felix-doc-auditor.service
- scripts/office2/felix-doc-auditor.timer
- scripts/office2/deploy/felix-doc-auditor-driver.sh
tags: []
---

# Work Package Prompt: WP08 — Deploy script and systemd unit update

## Objective

Update the systemd unit definition (ExecStart change from openclaw-agent invocation to direct Python driver invocation), and write the deploy script that lands the new driver on office2 + retires the old openclaw-agent definition. This is the operational tooling for WP09's cutover.

## Context

- Per `contracts/driver-invocation.contract.md`, the systemd unit's ExecStart shifts from `/usr/bin/openclaw agent --agent felix-doc-auditor ...` to `/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py`.
- Per spec FR-010, the old openclaw-agent registration is FULLY RETIRED at cutover — workspace files deleted, agent deregistered.
- Per spec C-007, the deploy is fail-forward. No automatic rollback. Each step in the deploy script is idempotent and reports clearly.
- Per research D10, the cutover sequence has 5 steps (pre-flight → merge → apply → verify → confirm soak). WP08 builds the tooling; WP09 executes it.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP08 --agent <name>`.

## Subtasks

### T036 — Update systemd unit ExecStart

**Purpose**: Change the systemd unit definition to invoke the new driver.

**Steps**:

1. Inspect the current unit file at `scripts/office2/felix-doc-auditor.service` (this is the source-in-repo per `service-inventory.json`):
   ```bash
   cat scripts/office2/felix-doc-auditor.service
   ```
   Compare to the deployed copy on office2 to ensure consistency before editing:
   ```bash
   ssh office2-claude 'cat ~/.config/systemd/user/felix-doc-auditor.service'
   ```

2. Edit `scripts/office2/felix-doc-auditor.service` per `contracts/driver-invocation.contract.md`:

   ```ini
   [Unit]
   Description=felix-doc-auditor driver — scripts-first audit processing
   After=network-online.target openclaw-gateway.service

   [Service]
   Type=oneshot
   TimeoutStartSec=30min
   ExecStart=/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py
   WorkingDirectory=/home/claude/kg-automation
   Environment=HOME=/home/claude

   [Install]
   WantedBy=default.target
   ```

   Key changes vs current:
   - `Description` updated to reflect the new driver
   - `ExecStart` changed from openclaw invocation to direct Python
   - `WorkingDirectory` set to repo root (in case driver needs it)
   - `Environment=HOME=/home/claude` preserved
   - All other fields preserved (`Type=oneshot`, `TimeoutStartSec=30min`, `After=` dependencies)

3. Verify `felix-doc-auditor.timer` does NOT need changes (it just references the .service by name, no ExecStart):
   ```bash
   cat scripts/office2/felix-doc-auditor.timer
   ```

4. Run `systemd-analyze verify` on the new unit file (locally or via SSH to office2):
   ```bash
   systemd-analyze verify scripts/office2/felix-doc-auditor.service
   # OR
   ssh office2-claude 'systemd-analyze verify /home/claude/kg-automation/scripts/office2/felix-doc-auditor.service'
   ```

**Files**:
- Modified: `scripts/office2/felix-doc-auditor.service`

**Validation**:
- [ ] `systemd-analyze verify` reports no errors
- [ ] ExecStart matches `contracts/driver-invocation.contract.md`
- [ ] TimeoutStartSec=30min preserved
- [ ] No accidental syntax change vs the contract

---

### T037 — Write deploy script `felix-doc-auditor-driver.sh`

**Purpose**: Single executable that lands the driver + retires the old openclaw-agent + tests deployment.

**Steps**:

1. Create `scripts/office2/deploy/felix-doc-auditor-driver.sh`. Reference `scripts/office2/deploy/felix-doc-auditor.sh` (existing deploy script for the old agent) for patterns.

2. CLI surface:
   ```
   felix-doc-auditor-driver.sh [--dry-run|--apply] [--backup-confirmed]

   --dry-run             Default. Print all intended operations; make no changes.
   --apply               Execute the deploy. Requires --backup-confirmed.
   --backup-confirmed    Operator's signoff that a Restic backup has run within
                         the last 24 hours (per Tier 2 change protocol). Refuse
                         to proceed in --apply mode without this flag.
   ```

3. Operations sequence (per research D10 step 3):

   ```bash
   #!/bin/bash
   set -euo pipefail

   # ... arg parsing ...

   echo "==> Step 1/8: Pre-flight checks"
   #   - Verify we're on office2 (uname/hostname)
   #   - Verify openclaw-gateway is running (systemctl is-active)
   #   - Verify Anthropic secret file is readable (NOT print contents)
   #   - Verify gh auth as kg-felix-bot

   echo "==> Step 2/8: rsync driver code from repo to /home/claude/kg-automation"
   #   - Driver code is committed to main; pull the repo
   #   - cd /home/claude/kg-automation && git pull --rebase

   echo "==> Step 3/8: Create driver directories"
   #   - mkdir -p /data/services/openclaw/felix-doc-auditor-driver/
   #   - chmod 755 ; chown claude:claude

   echo "==> Step 4/8: Install systemd unit"
   #   - cp scripts/office2/felix-doc-auditor.service ~/.config/systemd/user/
   #   - cp scripts/office2/felix-doc-auditor.timer ~/.config/systemd/user/  (if changed)
   #   - systemctl --user daemon-reload

   echo "==> Step 5/8: Retire old openclaw-agent definition"
   #   - openclaw agent unregister felix-doc-auditor  (or equivalent CLI)
   #   - Verify: openclaw agent list | grep felix-doc-auditor  → should be absent

   echo "==> Step 6/8: Delete old workspace files"
   #   - Verify nothing else is using /data/services/openclaw/felix-doc-auditor/
   #   - rm -rf /data/services/openclaw/felix-doc-auditor/

   echo "==> Step 7/8: Verify timer is enabled"
   #   - systemctl --user list-timers felix-doc-auditor.timer
   #   - systemctl --user is-enabled felix-doc-auditor.timer

   echo "==> Step 8/8: Done"
   #   - Print suggested follow-up: "Run a verification tick via:
   #     systemctl --user start --wait felix-doc-auditor.service"
   ```

4. **Critical**:
   - Each step prints what it's about to do BEFORE doing it (in --apply mode)
   - In --dry-run mode, prints the same but with [DRY-RUN] prefix and no actual change
   - All commands wrapped in error checks; on failure, print STEP FAILED and exit non-zero
   - Step 5 (retire openclaw): the openclaw CLI's deregister command may have specific syntax — research the exact command via `openclaw agent --help` before relying on a specific form
   - Step 6 (delete workspace): use `rm -rf` with explicit path verification (paranoid check before deletion)
   - Add a `--backup-confirmed` guard for step 6: this is Tier 2 (file deletion); refuse without it

5. Header comment in the script:
   - Purpose
   - Operator usage
   - Idempotency notes (running twice = no-op after first)
   - Rollback notes (none — fail-forward per C-007; refer to disaster recovery if needed)

**Files**:
- New: `scripts/office2/deploy/felix-doc-auditor-driver.sh` (~250 lines including comments)

**Validation**:
- [ ] `--dry-run` (default) prints all operations without executing
- [ ] `--apply` without `--backup-confirmed` refuses with clear message
- [ ] Each step is idempotent (re-running after success = no-op + clean exit)
- [ ] Failure at any step exits non-zero with the failed step's name

---

### T038 — Test deploy script in `--dry-run` mode

**Purpose**: Verify the deploy script does what it claims, without making any changes.

**Steps**:

1. From the Mac (or any non-office2 environment), invoke the dry-run mode against office2:
   ```bash
   ssh office2-claude 'bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor-driver.sh --dry-run'
   ```

2. Verify the output:
   - All 8 steps print with [DRY-RUN] prefix
   - No errors
   - No files modified on office2 (check `ls -la ~/.config/systemd/user/felix-doc-auditor.service` mtime — should be unchanged)

3. Capture the dry-run output as a fixture file `scripts/office2/deploy/felix-doc-auditor-driver.dry-run.expected.txt` (with timestamps and paths sanitized) so future deploys can be regression-checked.

4. Verify the script handles unexpected states cleanly:
   - If `/data/services/openclaw/felix-doc-auditor-driver/` already exists → step 3 reports "already exists, skipping" and continues
   - If the systemd unit is already installed and matches → step 4 reports "no change needed" and continues
   - If openclaw agent already deregistered → step 5 reports "already deregistered, skipping"
   - If workspace files already deleted → step 6 reports "already deleted, skipping"

**Files**:
- New: `scripts/office2/deploy/felix-doc-auditor-driver.dry-run.expected.txt` (optional reference fixture)

**Validation**:
- [ ] Dry-run output is sanity-checked end-to-end by reviewer
- [ ] No files on office2 are modified during dry-run
- [ ] Idempotency handles common pre-existing states cleanly

---

### T039 — Document deploy operation

**Purpose**: Make the deploy script self-documenting + cross-reference from the runbook (which is written in WP10).

**Steps**:

1. In `scripts/office2/deploy/felix-doc-auditor-driver.sh` HEADER, expand the comment block:
   ```bash
   #!/bin/bash
   # felix-doc-auditor scripts-first driver — deploy script
   #
   # Purpose:
   #   Lands the new driver code on office2, installs the systemd unit,
   #   retires the old openclaw-agent definition, and removes the legacy
   #   workspace files. Implements steps 3 of the cutover sequence
   #   documented in kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md D10.
   #
   # Operator usage:
   #   # Dry-run (default — preview only):
   #   bash scripts/office2/deploy/felix-doc-auditor-driver.sh
   #   # OR:
   #   bash scripts/office2/deploy/felix-doc-auditor-driver.sh --dry-run
   #
   #   # Apply (requires --backup-confirmed):
   #   bash scripts/office2/deploy/felix-doc-auditor-driver.sh --apply --backup-confirmed
   #
   # Pre-requisites:
   #   - Run on office2 as the claude user (ssh office2-claude)
   #   - Repo at /home/claude/kg-automation up to date with main
   #   - openclaw-gateway service running
   #   - Restic backup completed within last 24h
   #   - gh CLI authenticated as kg-felix-bot
   #   - Anthropic API key readable at /data/services/openclaw/secrets/anthropic
   #
   # Rollback:
   #   None — fail-forward posture per kitty-specs spec C-007.
   #   If the deploy fails partway, manually re-run after fixing the failure.
   #   The old openclaw-agent surface is irrecoverable from this script alone;
   #   restore from git (workspace files in scripts/openclaw/agents/felix-doc-auditor/)
   #   and re-register via openclaw CLI if needed.
   #
   # Idempotency:
   #   Re-running the script after a successful deploy is a no-op for steps
   #   3-7 (they check for existing state). Steps 1-2 are always re-run.
   #
   # See also:
   #   - kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md (D10 cutover sequence)
   #   - docs/runbooks/doc-auditor-driver-ops.md (operator runbook, written in WP10)
   ```

2. Ensure the script's `--help` output mirrors the header.

**Files**:
- Modified: `scripts/office2/deploy/felix-doc-auditor-driver.sh` (header expanded)

**Validation**:
- [ ] Header explains purpose, usage, prereqs, rollback, idempotency
- [ ] `--help` output mirrors header (or links to it)
- [ ] Cross-references to the runbook + research are present

---

## Definition of Done

- [ ] systemd unit `.service` file matches `contracts/driver-invocation.contract.md`
- [ ] Deploy script handles all 8 cutover steps
- [ ] Dry-run mode is non-destructive and informative
- [ ] Apply mode requires explicit `--backup-confirmed` guard
- [ ] Idempotency tested for common pre-existing states
- [ ] Script header is self-documenting

## Risks

| Risk | Mitigation |
|---|---|
| Deploy script's "retire openclaw" step uses wrong CLI syntax (openclaw CLI may have changed) | Verify `openclaw agent --help` or equivalent before relying on specific syntax; fall back to manual deregister if CLI lacks the command |
| Workspace deletion step (step 6) accidentally removes something else | Paranoid path check before `rm -rf` (verify exact path; refuse if pattern doesn't match expected) |
| systemd unit syntax error after edit | `systemd-analyze verify` catch in T036 |
| Deploy script tested in dry-run but not in apply (until WP09) | Acceptable — WP09 IS the first apply. Failure visible immediately. |

## Reviewer Guidance

- Confirm ExecStart matches contract exactly
- Confirm deploy script is `set -euo pipefail` at top (fail-fast)
- Confirm step 6 has paranoid path verification before deletion
- Confirm `--backup-confirmed` guard is present
- Confirm idempotency in 3-4 spot checks (re-run after step 4 → no-op; re-run after step 6 → no-op)

## Implementation Command

```bash
spec-kitty agent action implement WP08 --agent <name>
```

## Cross-references

- **Contract**: `contracts/driver-invocation.contract.md` (systemd unit shape)
- **Research**: D10 (cutover sequence)
- **Spec**: FR-010 (retire old agent), C-007 (fail-forward), C-004 (queue-drained at deploy)
- **Existing deploy patterns**: `scripts/office2/deploy/felix-doc-auditor.sh` (the old agent's deploy script — reference for style)

## Activity Log

- 2026-05-21T13:49:02Z – claude:opus-4.7:implementer:implementer – shell_pid=22287 – Started implementation via action command
- 2026-05-21T13:54:07Z – claude:opus-4.7:implementer:implementer – shell_pid=22287 – Ready for review: systemd unit ExecStart updated to driver entry; deploy script implements 8-step cutover with --dry-run default, --backup-confirmed Tier-2 gate, paranoid path check, and idempotent steps 3-7. Verified on office2: systemd-analyze verify passes; dry-run runs cleanly with all preflight checks green; --apply refuses without --backup-confirmed.
- 2026-05-21T13:54:39Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=23375 – Started review via action command
- 2026-05-21T13:57:55Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=23375 – Moved to planned
- 2026-05-21T13:59:18Z – claude:opus-4.7:implementer:implementer – shell_pid=24821 – Started implementation via action command
- 2026-05-21T14:02:58Z – claude:opus-4.7:implementer:implementer – shell_pid=24821 – Cycle 2: 3 findings addressed
- 2026-05-21T14:03:29Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=25577 – Started review via action command
