#!/usr/bin/env bash
# Deploy entrypoint for agent-skill-sync (#775, WP03).
#
# HARD verify-before-enable gate (Codex #1 HIGH-1): an installed-but-not-running
# timer is exactly the stranded-edit failure this mission eliminates, so a failed
# smoke or enable FAILS THE DEPLOY LOUDLY (non-zero exit) rather than being
# marked applied. Mirrors the verify-before-enable pattern in
# scripts/deploy/deploy-felix-canary.py / deploy-habits-weekly-driver.py.
#
# Safe-deploy order (DIR-005): pre-flight -> place units -> daemon-reload ->
# real-unit smoke (assert freshness signal written) -> enable --now -> assert
# is-enabled + list-timers. No sudo anywhere (Tier-0 discipline).
#
# Runs on office2 as the claude user, invoked by felix-deployer from the checkout
# root. Idempotent: re-running re-copies units + re-asserts; enable --now on an
# already-enabled timer is a no-op.
set -euo pipefail

# systemctl --user needs the user session bus; a non-login context lacks it
# (units run under user-linger). Export XDG_RUNTIME_DIR like the precedent scripts.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo /home/claude/kg-automation)"
UNIT_SRC="${REPO_ROOT}/scripts/openclaw/deploy"
UNIT_DST="${HOME}/.config/systemd/user"
SERVICE_UNIT="agent-skill-sync.service"
TIMER_UNIT="agent-skill-sync.timer"
HELPER="scripts/openclaw/deploy/deploy_agent_skills.py"
SKILLS_SRC="${REPO_ROOT}/scripts/openclaw/skills"
FRESHNESS="/data/services/openclaw/deploy/skills-last-tick.json"

fail() { echo "DEPLOY FAILED: $*" >&2; echo "Recovery: systemctl --user disable --now ${TIMER_UNIT}; rm -f ${UNIT_DST}/agent-skill-sync.{service,timer}; systemctl --user daemon-reload" >&2; exit 1; }

echo "[skills-sync deploy] repo_root=${REPO_ROOT}"

# 1. Pre-flight — the code + units must already be in the checkout (they arrive
#    in the same merge commit; felix-deployer advances the checkout before apply).
[ -f "${REPO_ROOT}/${HELPER}" ] || fail "helper missing: ${HELPER}"
[ -f "${UNIT_SRC}/${SERVICE_UNIT}" ] || fail "unit missing: ${SERVICE_UNIT}"
[ -f "${UNIT_SRC}/${TIMER_UNIT}" ] || fail "unit missing: ${TIMER_UNIT}"
[ -d "${SKILLS_SRC}" ] || fail "skills source dir missing: ${SKILLS_SRC}"

# 2. Place unit files.
mkdir -p "${UNIT_DST}"
cp "${UNIT_SRC}/${SERVICE_UNIT}" "${UNIT_DST}/"
cp "${UNIT_SRC}/${TIMER_UNIT}" "${UNIT_DST}/"
echo "[skills-sync deploy] units placed in ${UNIT_DST}"

# 3. Reload the user manager.
systemctl --user daemon-reload || fail "daemon-reload failed (XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}?)"

# 4. SMOKE GATE — run the real unit once and prove it wrote the freshness signal.
#    A failed smoke fails the deploy (do NOT enable an unproven unit).
before="$(date +%s)"
systemctl --user start "${SERVICE_UNIT}" || fail "smoke: '${SERVICE_UNIT}' start failed"
# oneshot start blocks until the tick exits; give the fs a beat then assert.
if [ ! -f "${FRESHNESS}" ]; then
  fail "smoke: freshness signal ${FRESHNESS} not written by the tick"
fi
mtime="$(stat -c %Y "${FRESHNESS}" 2>/dev/null || echo 0)"
[ "${mtime}" -ge "${before}" ] || fail "smoke: freshness signal is stale (mtime ${mtime} < ${before}) — the tick did not run this deploy"
echo "[skills-sync deploy] smoke OK — freshness signal fresh"

# 5. Enable (only reached after a clean smoke).
systemctl --user enable --now "${TIMER_UNIT}" || fail "enable --now ${TIMER_UNIT} failed"

# 6. Assert the timer is enabled AND scheduled.
systemctl --user is-enabled "${TIMER_UNIT}" | grep -q enabled || fail "${TIMER_UNIT} not enabled after enable --now"
systemctl --user list-timers "${TIMER_UNIT}" --no-pager | grep -q "${TIMER_UNIT}" || fail "${TIMER_UNIT} not in list-timers"

echo "[skills-sync deploy] OK — ${TIMER_UNIT} enabled + scheduled; smoke green."
