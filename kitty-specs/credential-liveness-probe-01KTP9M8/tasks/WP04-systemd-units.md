---
work_package_id: WP04
title: Systemd units + deploy script
dependencies:
- WP03
requirement_refs:
- FR-015
- FR-016
- FR-017
- C-005
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on the mission coordination branch per the rc41 #1777 workaround. During /spec-kitty.implement this WP gets its own lane worktree, computed by finalize-tasks to have WP03 code present in its base (deploy script smoke-tests the new CLI flag). Completed changes merge back into main as part of the mission's atomic merge.
subtasks:
- T019
- T020
- T021
- T022
agent: "claude"
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/office2/
execution_mode: code_change
mission_id: 01KTP9M86VF89TQM5SX7JVA83Z
mission_slug: credential-liveness-probe-01KTP9M8
owned_files:
- scripts/office2/credential-liveness-probe.service
- scripts/office2/credential-liveness-probe.timer
- scripts/office2/deploy/credential-liveness-probe.sh
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load implementer-ivan
```

Generic implementer posture for shell + config files. Mirror existing patterns rather than inventing new ones. Idempotency is the key invariant — the deploy script must be safe to re-run.

## Objective

Create the two systemd user unit files and an idempotent deploy script that mirrors the existing `credential-health-check.sh` pattern. After merge, operator runs the deploy script once on office2 to install + activate the 6h liveness probe timer.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Lane worktree: allocated per `lanes.json` after `finalize-tasks` runs. WP03 dependency means the lane base contains the `--liveness-only` CLI flag (so the deploy-script smoke-test works).

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) | FR-015, FR-016, FR-017, C-005 |
| [../plan.md](../plan.md) § IC-04 | Concern map; risks |
| [../research.md](../research.md) Decision 5 | Why separate timer vs extending existing |
| [../contracts/systemd-units.md](../contracts/systemd-units.md) | Full unit-file contracts + deploy-script template |
| `scripts/office2/credential-health-check.service` | Existing pattern to mirror |
| `scripts/office2/credential-health-check.timer` | Existing pattern to mirror |
| `scripts/office2/deploy/credential-health-check.sh` | Existing deploy pattern (idempotent shell) — adapt for liveness |

## Subtask Guidance

### T019 — Create `credential-liveness-probe.service`

**Probe first**:

```bash
cat scripts/office2/credential-health-check.service
```

Understand the existing unit's structure (After, Type, Environment, EnvironmentFile, PYTHONPATH, WorkingDirectory).

**Steps**:

Create `scripts/office2/credential-liveness-probe.service` with this content (per [../contracts/systemd-units.md](../contracts/systemd-units.md)):

```ini
[Unit]
Description=credential-liveness-probe — 6h OAuth liveness probe (kentonium3/kg-automation#572)
After=network-online.target openclaw-gateway.service
Wants=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=2min
ExecStart=/usr/bin/python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json --liveness-only
Environment=HOME=/home/claude
Environment=PYTHONPATH=/home/claude/kg-automation/scripts/security
Environment=GOG_KEYRING_BACKEND=file
EnvironmentFile=/data/services/openclaw/secrets/openclaw-gateway.env
WorkingDirectory=/home/claude
```

**Files**:
- `scripts/office2/credential-liveness-probe.service` (new, ~12 lines)

**Validation**:
- `systemd-analyze verify --user scripts/office2/credential-liveness-probe.service` (if available locally) — no errors.
- The unit's `ExecStart` exactly matches the documented invocation.
- `EnvironmentFile` points at the openclaw-gateway env file (same one the existing service uses).

---

### T020 — Create `credential-liveness-probe.timer`

**Steps**:

Create `scripts/office2/credential-liveness-probe.timer`:

```ini
[Unit]
Description=Timer: credential-liveness-probe (every 6 hours)

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
Persistent=true
Unit=credential-liveness-probe.service

[Install]
WantedBy=timers.target
```

**Files**:
- `scripts/office2/credential-liveness-probe.timer` (new, ~10 lines)

**Validation**:
- `systemd-analyze calendar "*-*-* 00,06,12,18:00:00"` — confirms the schedule (4 fires/day at 00:00, 06:00, 12:00, 18:00 UTC).
- `Persistent=true` is present (missed firings catch up).

---

### T021 — Create `deploy/credential-liveness-probe.sh`

**Probe first**:

```bash
cat scripts/office2/deploy/credential-health-check.sh
```

Mirror this script's structure. Adapt for the new service name and add a `liveness.py` presence check.

**Steps**:

Create `scripts/office2/deploy/credential-liveness-probe.sh`:

```bash
#!/usr/bin/env bash
# credential-liveness-probe.sh — Deploy or refresh the credential-liveness-probe
# systemd user timer + service on office2. Idempotent: safe to re-run.
#
# Why this exists: the OAuth app is in External + Testing publishing status,
# so Google issues 7-day refresh tokens. The new 6h liveness probe surfaces
# token death within ≤6h via a GitHub issue (vs waiting for user-facing failure).
# Tracking issue: kentonium3/kg-automation#572.
#
# Run from office2 as the claude user. No sudo required.
# Usage:
#   bash /home/claude/kg-automation/scripts/office2/deploy/credential-liveness-probe.sh

set -euo pipefail

REPO_ROOT="/home/claude/kg-automation"
SERVICE_NAME="credential-liveness-probe"
PACKAGE_REPO_PATH="${REPO_ROOT}/scripts/security/credential_health_check"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SYSTEMD_REPO_DIR="${REPO_ROOT}/scripts/office2"

echo ">>> Sanity check"
if [[ "$(whoami)" != "claude" ]]; then
  echo "ERROR: must run as the claude user (currently: $(whoami))" >&2
  exit 1
fi
if [[ ! -f "${PACKAGE_REPO_PATH}/liveness.py" ]]; then
  echo "ERROR: liveness.py not found at ${PACKAGE_REPO_PATH}/liveness.py" >&2
  echo "       Did 'git pull origin main' run successfully and is the merge complete?" >&2
  exit 1
fi
if [[ ! -x "/home/linuxbrew/.linuxbrew/bin/gog" ]]; then
  echo "ERROR: gog binary not found at /home/linuxbrew/.linuxbrew/bin/gog" >&2
  echo "       See docs/runbooks/google-workspace-ops.md for setup." >&2
  exit 1
fi
if [[ ! -f "/data/services/openclaw/secrets/openclaw-gateway.env" ]]; then
  echo "ERROR: openclaw-gateway env file missing at /data/services/openclaw/secrets/openclaw-gateway.env" >&2
  exit 1
fi

echo ">>> Pulling latest repo state"
git -C "${REPO_ROOT}" pull origin main

echo ">>> Installing systemd user timer + service"
mkdir -p "${SYSTEMD_USER_DIR}"
cp "${SYSTEMD_REPO_DIR}/${SERVICE_NAME}.timer" "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"
cp "${SYSTEMD_REPO_DIR}/${SERVICE_NAME}.service" "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.timer"

echo ">>> Verifying timer is active"
if systemctl --user is-active --quiet "${SERVICE_NAME}.timer"; then
  NEXT_FIRE=$(systemctl --user list-timers "${SERVICE_NAME}.timer" --no-pager 2>/dev/null | awk 'NR==2 {print $1, $2, $3, $4}')
  echo "    OK: ${SERVICE_NAME}.timer active. Next fire: ${NEXT_FIRE}"
else
  echo "    ERROR: ${SERVICE_NAME}.timer is not active after enable" >&2
  exit 1
fi

echo ">>> Smoke-test (dry-run, real probe call against current state)"
PYTHONPATH="${REPO_ROOT}/scripts/security" python3 -m credential_health_check \
  --manifest "${REPO_ROOT}/docs/design/architecture/data/credential-manifest.json" \
  --dry-run --liveness-only

echo ">>> Deploy complete."
echo "    Verify: systemctl --user status ${SERVICE_NAME}.timer"
echo "    Force a probe: systemctl --user start ${SERVICE_NAME}.service"
echo "    View logs: journalctl --user -u ${SERVICE_NAME}.service --since '1 hour ago'"
```

**Files**:
- `scripts/office2/deploy/credential-liveness-probe.sh` (new, ~80 lines)

**Validation**:
- `bash -n scripts/office2/deploy/credential-liveness-probe.sh` (syntax check) — no errors.
- Visual diff against `scripts/office2/deploy/credential-health-check.sh` — same structure, only specifics differ.
- `set -euo pipefail` is present (matches existing script).
- No `sudo` invocations anywhere (claude user has no sudo per CLAUDE.md).

---

### T022 — chmod +x on deploy script

**Steps**:

```bash
chmod 755 scripts/office2/deploy/credential-liveness-probe.sh
```

Then verify via `ls -l scripts/office2/deploy/credential-liveness-probe.sh` — should show `-rwxr-xr-x`.

**Files**:
- (mode change only)

**Validation**:
- `ls -l scripts/office2/deploy/credential-liveness-probe.sh` shows executable bits.
- Git tracks the mode change (run `git diff --stat` to confirm).

---

## Test Strategy

This WP's deliverables are configuration files + shell — no pytest coverage. Validation is by:

1. Syntax checks (`bash -n`, `systemd-analyze verify` if available).
2. Visual diff against the existing `credential-health-check` equivalents.
3. Smoke-test at deploy time (post-merge, when operator runs the script on office2).

## Definition of Done

- [ ] `scripts/office2/credential-liveness-probe.service` exists and matches the contract.
- [ ] `scripts/office2/credential-liveness-probe.timer` exists with `OnCalendar=*-*-* 00,06,12,18:00:00` and `Persistent=true`.
- [ ] `scripts/office2/deploy/credential-liveness-probe.sh` exists with shebang, `set -euo pipefail`, and the documented invariants (sanity checks, git pull, cp+enable, smoke-test).
- [ ] Deploy script is executable (`mode 0755`).
- [ ] Deploy script `bash -n` passes.
- [ ] Service unit's `EnvironmentFile` points at `/data/services/openclaw/secrets/openclaw-gateway.env`.
- [ ] No `sudo` invocations anywhere.
- [ ] Three new files appear under `scripts/office2/` (and `scripts/office2/deploy/`).

## Risks

- **`OnCalendar` syntax**: spaces and asterisks must be exact. `systemd-analyze calendar "..."` confirms parse.
- **Path absolutes**: the `ExecStart` and `WorkingDirectory` must be absolute paths (systemd requirement).
- **`EnvironmentFile` permissions**: the env file is `0600 claude:claude`; systemd user services run as claude so this works without sudo.
- **`PYTHONPATH` value**: must match the existing pattern `/home/claude/kg-automation/scripts/security` (not include trailing slash; not include the package name).
- **Deploy-script git pull**: `git -C "${REPO_ROOT}" pull origin main` requires the merge to be on main BEFORE the operator runs the deploy script. The mission's single-merge convention handles this.
- **Idempotency**: re-running the deploy script must produce identical state. `cp` overwrites; `daemon-reload` no-ops if no change; `enable --now` no-ops if already enabled. `Persistent=true` may catch up firings on re-run; that's intentional.

## Reviewer Guidance

- Open the existing `credential-health-check.{service,timer,sh}` side-by-side with the new files. They should differ ONLY in:
  - Service/unit names (`credential-liveness-probe` vs `credential-health-check`)
  - `ExecStart` (new `--liveness-only` flag)
  - `OnCalendar` cadence (6h vs daily)
  - `Description` line wording
  - Liveness-specific sanity checks in the deploy script (e.g., `liveness.py` presence)
- No structural deviations from the existing pattern should be present (e.g., don't add new fields like `Restart=` if the existing pattern doesn't use them).
- The deploy script's smoke-test MUST run with `--dry-run` so it doesn't file a real GitHub issue if the current token is dead.
