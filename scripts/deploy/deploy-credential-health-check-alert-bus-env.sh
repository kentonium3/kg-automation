#!/usr/bin/env bash
# Deploy entrypoint for credential-health-check alert-bus env wiring (#852 Part 2).
#
# The felix-deployer manifest applier (scripts/deploy/lib/apply.py) invokes this
# entrypoint TWICE: `<entrypoint> --dry-run` (must be non-mutating) then
# `<entrypoint> --apply` (does the work). It runs the apply inside the shared
# checkout deploylock, so the unit in the checkout is already at the merged
# commit before apply.
#
# What it deploys: re-installs credential-health-check.service (and .timer,
# unchanged, for idempotency) into ~/.config/systemd/user/ and reloads the user
# manager so the running unit gains the EnvironmentFile that loads
# FELIX_ALERT_NTFY_TOPIC for the unified felix-alert bus (#701). Without it, the
# #852 ramping expiry-reminder ladder's emit() resolves NTFY_MISSING_TOPIC and
# never delivers. The service is a oneshot fired by its daily timer; daemon-reload
# + enable --now is non-disruptive. No sudo (Tier-0 discipline).
#
# audited_surface: the systemd unit content change -> the systemd-user-unit-contents
# baseline drifts. felix-deployer's deferred-confirm auto-rebaseline detects the
# repo-file signal (scripts/office2/*.service changed) and rebaselines automatically.
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo /home/claude/kg-automation)"
UNIT_SRC="${REPO_ROOT}/scripts/office2"
UNIT_DST="${HOME}/.config/systemd/user"
SERVICE_UNIT="credential-health-check.service"
TIMER_UNIT="credential-health-check.timer"
ENV_LINE_RE='^EnvironmentFile=-/home/claude/[.]config/felix/alert-bus/env'

MODE="${1:-}"

fail() { echo "DEPLOY FAILED: $*" >&2; exit 1; }

preflight() {
  [ -f "${UNIT_SRC}/${SERVICE_UNIT}" ] || fail "unit missing in checkout: ${UNIT_SRC}/${SERVICE_UNIT}"
  [ -f "${UNIT_SRC}/${TIMER_UNIT}" ] || fail "unit missing in checkout: ${UNIT_SRC}/${TIMER_UNIT}"
  # Guard: the checkout unit MUST carry the alert-bus EnvironmentFile line, else
  # deploying it would be a no-op that leaves the ladder inert.
  grep -qE "${ENV_LINE_RE}" "${UNIT_SRC}/${SERVICE_UNIT}" \
    || fail "checkout ${SERVICE_UNIT} is missing the alert-bus EnvironmentFile line"
}

case "${MODE}" in
  --dry-run)
    preflight
    echo "[cred-health alert-bus env] DRY-RUN ok — would: cp ${SERVICE_UNIT}+${TIMER_UNIT} from ${UNIT_SRC} to ${UNIT_DST}; systemctl --user daemon-reload; enable --now ${TIMER_UNIT}; assert deployed ${SERVICE_UNIT} carries the alert-bus EnvironmentFile + timer active."
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
echo "[cred-health alert-bus env] apply: repo_root=${REPO_ROOT}"
preflight

# 1. Place the unit files.
mkdir -p "${UNIT_DST}"
cp "${UNIT_SRC}/${SERVICE_UNIT}" "${UNIT_DST}/"
cp "${UNIT_SRC}/${TIMER_UNIT}" "${UNIT_DST}/"
echo "[cred-health alert-bus env] units placed in ${UNIT_DST}"

# 2. Reload the user manager so the new unit definition takes effect.
systemctl --user daemon-reload || fail "daemon-reload failed (XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}?)"

# 3. Re-enable the timer (idempotent; non-disruptive to the oneshot service).
systemctl --user enable --now "${TIMER_UNIT}" || fail "enable --now ${TIMER_UNIT} failed"

# 4. Assert the deployed unit now carries the alert-bus EnvironmentFile line.
grep -qE "${ENV_LINE_RE}" "${UNIT_DST}/${SERVICE_UNIT}" \
  || fail "deployed ${SERVICE_UNIT} is missing the alert-bus EnvironmentFile after copy"

# 5. Assert the timer is enabled AND scheduled.
systemctl --user is-enabled "${TIMER_UNIT}" | grep -q enabled || fail "${TIMER_UNIT} not enabled after enable --now"
systemctl --user list-timers "${TIMER_UNIT}" --no-pager | grep -q "${TIMER_UNIT}" || fail "${TIMER_UNIT} not in list-timers"

# 6. Deliverability guard: the whole point of this deploy is that the ladder can
# actually push. Assert the alert-bus env-file exists AND carries a non-empty
# FELIX_ALERT_NTFY_TOPIC (provisioned by the unified-alert-bus deploy, #701) —
# otherwise emit() would silently resolve NTFY_MISSING_TOPIC and never deliver,
# and this deploy would falsely report success.
ALERT_BUS_ENV="/home/claude/.config/felix/alert-bus/env"
grep -qE '^FELIX_ALERT_NTFY_TOPIC=.+' "${ALERT_BUS_ENV}" \
  || fail "alert-bus topic not provisioned: ${ALERT_BUS_ENV} missing a non-empty FELIX_ALERT_NTFY_TOPIC (deploy #701 should have set it)"

echo "[cred-health alert-bus env] OK — deployed unit carries the alert-bus EnvironmentFile; ${TIMER_UNIT} enabled + scheduled; ntfy topic provisioned."
