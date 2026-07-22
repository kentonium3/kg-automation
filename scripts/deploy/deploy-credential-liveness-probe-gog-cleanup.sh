#!/usr/bin/env bash
# Deploy entrypoint for credential-liveness-probe gog-decoupling (#846).
#
# The felix-deployer manifest applier (scripts/deploy/lib/apply.py) invokes this
# entrypoint TWICE: `<entrypoint> --dry-run` (must be non-mutating) then
# `<entrypoint> --apply` (does the work). It runs the apply inside the shared
# checkout deploylock, so the units in the checkout are already at the merged
# commit before apply.
#
# What it deploys: re-installs the cleaned credential-liveness-probe.service (and
# .timer, unchanged, for idempotency) into ~/.config/systemd/user/ and reloads the
# user manager so the running unit drops the removed gog-era env lines
# (Environment=GOG_KEYRING_BACKEND=file + EnvironmentFile=openclaw-gateway.env).
# The service is a oneshot fired by its timer; daemon-reload + enable --now is
# non-disruptive (no running probe is interrupted). No sudo (Tier-0 discipline).
#
# audited_surface: the systemd unit content changes -> the systemd-user-unit-contents
# baseline drifts. felix-deployer's deferred-confirm auto-rebaseline detects the
# repo-file signal (scripts/office2/*.service changed) and rebaselines automatically.
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo /home/claude/kg-automation)"
UNIT_SRC="${REPO_ROOT}/scripts/office2"
UNIT_DST="${HOME}/.config/systemd/user"
SERVICE_UNIT="credential-liveness-probe.service"
TIMER_UNIT="credential-liveness-probe.timer"

MODE="${1:-}"

fail() { echo "DEPLOY FAILED: $*" >&2; exit 1; }

preflight() {
  [ -f "${UNIT_SRC}/${SERVICE_UNIT}" ] || fail "unit missing in checkout: ${UNIT_SRC}/${SERVICE_UNIT}"
  [ -f "${UNIT_SRC}/${TIMER_UNIT}" ] || fail "unit missing in checkout: ${UNIT_SRC}/${TIMER_UNIT}"
  # Guard: the cleaned unit must NOT carry the removed gog-era env lines.
  if grep -qE 'GOG_KEYRING_BACKEND|openclaw-gateway[.]env' "${UNIT_SRC}/${SERVICE_UNIT}"; then
    fail "checkout ${SERVICE_UNIT} still contains gog-era env coupling — refusing to deploy an uncleaned unit"
  fi
}

case "${MODE}" in
  --dry-run)
    preflight
    echo "[liveness-probe gog-cleanup] DRY-RUN ok — would: cp ${SERVICE_UNIT}+${TIMER_UNIT} from ${UNIT_SRC} to ${UNIT_DST}; systemctl --user daemon-reload; enable --now ${TIMER_UNIT}; assert deployed ${SERVICE_UNIT} is gog-env-free + timer active."
    exit 0
    ;;
  --apply)
    : # fall through
    ;;
  *)
    echo "usage: $0 --dry-run | --apply" >&2
    exit 2
    ;;
esac

# ----- --apply -----
echo "[liveness-probe gog-cleanup] apply: repo_root=${REPO_ROOT}"
preflight

# 1. Place the (cleaned) unit files.
mkdir -p "${UNIT_DST}"
cp "${UNIT_SRC}/${SERVICE_UNIT}" "${UNIT_DST}/"
cp "${UNIT_SRC}/${TIMER_UNIT}" "${UNIT_DST}/"
echo "[liveness-probe gog-cleanup] units placed in ${UNIT_DST}"

# 2. Reload the user manager so the new unit definition takes effect.
systemctl --user daemon-reload || fail "daemon-reload failed (XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}?)"

# 3. Re-enable the timer (idempotent; non-disruptive to the oneshot service).
systemctl --user enable --now "${TIMER_UNIT}" || fail "enable --now ${TIMER_UNIT} failed"

# 4. Assert the deployed unit is now gog-env-free.
if grep -qE 'GOG_KEYRING_BACKEND|openclaw-gateway[.]env' "${UNIT_DST}/${SERVICE_UNIT}"; then
  fail "deployed ${SERVICE_UNIT} still contains gog-era env coupling after copy"
fi

# 5. Assert the timer is enabled AND scheduled.
systemctl --user is-enabled "${TIMER_UNIT}" | grep -q enabled || fail "${TIMER_UNIT} not enabled after enable --now"
systemctl --user list-timers "${TIMER_UNIT}" --no-pager | grep -q "${TIMER_UNIT}" || fail "${TIMER_UNIT} not in list-timers"

echo "[liveness-probe gog-cleanup] OK — deployed unit is gog-env-free; ${TIMER_UNIT} enabled + scheduled."
