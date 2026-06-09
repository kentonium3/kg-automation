# Contract: Systemd Units + Deploy Script

## File 1: `scripts/office2/credential-liveness-probe.service`

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

### Rationale

| Field | Value | Reason |
|---|---|---|
| `After=` | `network-online.target openclaw-gateway.service` | Probe needs network to call Google; openclaw-gateway ordering matches existing `credential-health-check.service` for unit-graph consistency |
| `Type=oneshot` | — | Matches existing pattern; the timer drives invocation cadence |
| `TimeoutStartSec=2min` | — | Generous upper bound for a full cycle (probe ≤15s × N credentials ≤ 60s). 2min is well above worst-case to avoid systemd-killed false errors |
| `EnvironmentFile=` | `/data/services/openclaw/secrets/openclaw-gateway.env` | Pulls `GOG_KEYRING_PASSWORD` (already in this env file). Same path the openclaw-gateway service uses |
| `Environment=GOG_KEYRING_BACKEND=file` | — | Required for headless gog use; per `docs/runbooks/google-workspace-ops.md` §2.6 |
| `PYTHONPATH=/home/claude/kg-automation/scripts/security` | — | Matches existing `credential-health-check.service` |

## File 2: `scripts/office2/credential-liveness-probe.timer`

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

### Rationale

| Field | Value | Reason |
|---|---|---|
| `OnCalendar=` | `*-*-* 00,06,12,18:00:00` | Per Decision 3 (6h cadence). UTC. |
| `Persistent=true` | — | Missed firings catch up after boot/maintenance |
| `Unit=` | `credential-liveness-probe.service` | Explicit linkage |
| `WantedBy=timers.target` | — | Standard activation point |

## File 3: `scripts/office2/deploy/credential-liveness-probe.sh`

Mirrors the structure of the existing `credential-health-check.sh` (which we read during planning):

```bash
#!/usr/bin/env bash
# credential-liveness-probe.sh — Deploy or refresh the credential-liveness-probe
# systemd user timer + service on office2. Idempotent.
#
# Run from office2 as the claude user. No sudo required.
# Usage: bash /home/claude/kg-automation/scripts/office2/deploy/credential-liveness-probe.sh

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
  echo "       Did 'git pull origin main' run successfully?" >&2
  exit 1
fi
if [[ ! -x "/home/linuxbrew/.linuxbrew/bin/gog" ]]; then
  echo "ERROR: gog binary not found at /home/linuxbrew/.linuxbrew/bin/gog" >&2
  echo "       See docs/runbooks/google-workspace-ops.md for setup." >&2
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

echo ">>> Smoke-test (dry-run, real probe call)"
PYTHONPATH="${REPO_ROOT}/scripts/security" python3 -m credential_health_check \
  --manifest "${REPO_ROOT}/docs/design/architecture/data/credential-manifest.json" \
  --dry-run --liveness-only

echo ">>> Deploy complete."
```

### Idempotency invariants

1. Running the script twice on the same day produces identical disk state (cp overwrites; daemon-reload no-ops if no change; enable --now no-ops if already enabled).
2. Smoke-test (dry-run) is run on every deploy — confirms the new code path doesn't crash on the current state.
3. Smoke-test does NOT file GitHub issues even if the credential is currently dead (per `--dry-run`).

### Failure modes

- Repo pull conflicts → exit 1, leaves systemd state unchanged.
- Missing `gog` binary → exit 1 BEFORE touching systemd.
- Missing `liveness.py` (deploy ran before merge landed) → exit 1.
- `systemctl --user enable --now` failure → exit 1, NEXT_FIRE check would also catch.
- Smoke-test crash → exit 1; systemd unit is enabled but the operator is alerted.

## Verification (manual, post-deploy)

```bash
# 1. Timer exists + active
systemctl --user status credential-liveness-probe.timer

# 2. Next-fire scheduled
systemctl --user list-timers credential-liveness-probe.timer

# 3. Manual fire — should log credential_alive (if token is currently valid)
systemctl --user start credential-liveness-probe.service
journalctl --user -u credential-liveness-probe.service --since "1 minute ago" | tail -20

# 4. Dry-run from any shell — should produce the same outcome
PYTHONPATH=/home/claude/kg-automation/scripts/security python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json --dry-run --liveness-only
```
