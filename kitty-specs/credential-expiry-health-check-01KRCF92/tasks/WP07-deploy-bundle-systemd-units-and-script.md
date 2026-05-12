---
work_package_id: WP07
title: Deploy bundle — systemd units + deploy script
dependencies:
- WP06
requirement_refs:
- C-001
- C-004
- FR-009
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T030
- T031
- T032
agent: "claude"
shell_pid: "49962"
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: scripts/office2/credential-health-check
execution_mode: code_change
owned_files:
- scripts/office2/credential-health-check.timer
- scripts/office2/credential-health-check.service
- scripts/office2/deploy/credential-health-check.sh
tags: []
---

# WP07 — Deploy bundle

## Objective

Package the runtime: systemd user timer + oneshot service + a deploy script that copies units and arms the timer. All artefacts mirror the `felix-doc-auditor.{timer,service}` pattern delivered in #223.

## Context

- **Spec** anchors: FR-009 (once per UTC day), FR-010 (`claude` user on office2), C-004 (systemd user timer pattern).
- **Research** anchors: R-002 (logs to systemd journal); R-009 (schedule = 13:00 UTC); R-010 (naming conventions).
- **Prior art**: `scripts/office2/felix-doc-auditor.{timer,service}` and `scripts/office2/deploy/felix-doc-auditor.sh`. Use them as templates verbatim, changing only names + ExecStart + schedule + timeout.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree; merges to `main`.

## Subtasks

### T030 — `credential-health-check.timer`

**Purpose**: Daily 13:00 UTC trigger.

**Steps**:

1. Create `scripts/office2/credential-health-check.timer`:
   ```ini
   [Unit]
   Description=credential-health-check — daily credential expiry/cadence audit

   [Timer]
   OnCalendar=*-*-* 13:00:00
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```
2. `Persistent=true` ensures a missed tick during downtime fires on next boot.
3. `OnCalendar=*-*-* 13:00:00` is interpreted in UTC by user-session systemd by default (Ubuntu 24.04). No timezone qualifier needed.

**Files**: `scripts/office2/credential-health-check.timer` (create).

---

### T031 — `credential-health-check.service`

**Purpose**: One-shot service invoked by the timer.

**Steps**:

1. Create `scripts/office2/credential-health-check.service`:
   ```ini
   [Unit]
   Description=credential-health-check — process credential cadence + activity signals
   After=network-online.target openclaw-gateway.service
   Wants=network-online.target

   [Service]
   Type=oneshot
   TimeoutStartSec=10min
   ExecStart=/usr/bin/python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json
   Environment=HOME=/home/claude
   Environment=PYTHONPATH=/home/claude/kg-automation/scripts/security
   WorkingDirectory=/home/claude
   ```
2. `PYTHONPATH=/home/claude/kg-automation/scripts/security` lets `python3 -m credential_health_check` resolve the package without installing it into site-packages.
3. `TimeoutStartSec=10min` is comfortably above the expected ~10-second cycle (NFR-001) and well below the WP01–WP06 budgets.

**Files**: `scripts/office2/credential-health-check.service` (create).

---

### T032 — `deploy/credential-health-check.sh`

**Purpose**: Idempotent deploy from a freshly-pulled repo on office2.

**Steps**:

1. Create `scripts/office2/deploy/credential-health-check.sh`. Model on `scripts/office2/deploy/felix-doc-auditor.sh` (read that file first).
2. Script outline:
   ```bash
   #!/usr/bin/env bash
   # Deploy credential-health-check systemd user units on office2.
   # Run as the claude user from /home/claude/kg-automation. No sudo required.
   set -euo pipefail

   REPO_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
   USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

   echo "=== credential-health-check deploy ==="

   # Sanity checks
   if [[ "$(whoami)" != "claude" ]]; then
       echo "ERROR: must run as the claude user (currently: $(whoami))" >&2
       exit 1
   fi
   if [[ ! -f "$REPO_DIR/scripts/security/credential_health_check/__main__.py" ]]; then
       echo "ERROR: package not found at $REPO_DIR/scripts/security/credential_health_check/" >&2
       exit 1
   fi

   mkdir -p "$USER_SYSTEMD_DIR"

   echo "Copying unit files..."
   cp "$REPO_DIR/scripts/office2/credential-health-check.timer" "$USER_SYSTEMD_DIR/"
   cp "$REPO_DIR/scripts/office2/credential-health-check.service" "$USER_SYSTEMD_DIR/"

   echo "Reloading systemd..."
   systemctl --user daemon-reload

   echo "Enabling + starting timer..."
   systemctl --user enable --now credential-health-check.timer

   echo ""
   echo "=== Deploy complete ==="
   echo "Verify with:"
   echo "  systemctl --user list-timers --all | grep credential-health-check"
   echo "  journalctl --user -u credential-health-check.service -n 50 --no-pager"
   ```
3. Make the script executable (`chmod +x` in the filesystem). Git tracks this via the executable bit.

**Files**: `scripts/office2/deploy/credential-health-check.sh` (create, executable).

---

## Definition of Done

- All three files exist with the documented content.
- `chmod +x scripts/office2/deploy/credential-health-check.sh` was applied (verify via `git ls-files --stage scripts/office2/deploy/credential-health-check.sh` shows mode `100755`).
- The unit files validate (syntactically) via `systemd-analyze verify --user scripts/office2/credential-health-check.{timer,service}` on a Linux host. (Optional but a great catch — skip if no Linux available during implementation.)
- Commit prefix: `feat(security):` or `feat(WP07):` referencing #115.

## Risks

- **PYTHONPATH**: setting it via the unit's `Environment=` directive is the simplest path. Alternative would be `pip install -e .` of the package, but that requires a `pyproject.toml` (not in scope here). Stick with `PYTHONPATH`.
- **Timer drift**: `OnCalendar=*-*-* 13:00:00` is precise; combined with `Persistent=true`, missed ticks (downtime) fire on next boot. No drift concerns.
- **Deploy script must be runnable as `claude`, no sudo**: enforced by C-001. The `whoami != claude` check at the top catches accidental misuse.

## Reviewer guidance

- Verify: timer schedule matches `OnCalendar=*-*-* 13:00:00` (UTC); not `OnCalendar=daily` (which is 00:00).
- Verify: service `Type=oneshot` and `TimeoutStartSec=10min`.
- Verify: ExecStart uses absolute `/usr/bin/python3` (not bare `python3` — systemd doesn't search PATH the same way shells do).
- Verify: `PYTHONPATH=/home/claude/kg-automation/scripts/security` is set so `-m credential_health_check` resolves.
- Verify: deploy script aborts early on `whoami != claude`.
- Verify: deploy script uses `cp` (clobbers prior version) — re-running redeploys cleanly.

## Suggested implement command

```bash
spec-kitty agent action implement WP07 --agent <name>
```

## Activity Log

- 2026-05-12T01:35:11Z – claude – shell_pid=49784 – Started implementation via action command
- 2026-05-12T01:36:07Z – claude – shell_pid=49784 – Deploy bundle present; mirrors felix-doc-auditor pattern; deploy script idempotent + dry-run smoke.
- 2026-05-12T01:36:11Z – claude – shell_pid=49962 – Started review via action command
- 2026-05-12T01:36:15Z – claude – shell_pid=49962 – Review passed: timer schedule, service file structure, deploy script all consistent with felix-doc-auditor precedent.
