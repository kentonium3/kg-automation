#!/usr/bin/env bash
# Deploy entrypoint for agent-skill-sync (#775, WP03 + post-merge Codex #2 fixes).
#
# The felix-deployer manifest applier (scripts/deploy/lib/apply.py) invokes this
# entrypoint TWICE: `<entrypoint> --dry-run` (must be non-mutating) then
# `<entrypoint> --apply` (does the work). It runs the whole apply inside the shared
# checkout `deploylock` (scripts/deploy/felix-deployer/_tick.py), so a smoke launched
# via `systemctl start` would run in a SEPARATE process, contend the same lock, and
# defer — an mtime-only smoke would then pass on a no-op (Codex #2 HIGH-1). We instead
# smoke with the helper's lock-free `--smoke` mode (real copies; the checkout lock does
# not protect the deployed skills dir) and assert it wrote status='smoke' (never
# 'deferred'), proving a REAL sync ran before the timer is enabled.
#
# HARD verify-before-enable gate: a failed smoke/enable FAILS THE DEPLOY LOUDLY.
# Safe-deploy order (DIR-005): preflight -> place -> daemon-reload -> real-copy smoke
# -> enable --now -> assert is-enabled/list-timers. No sudo (Tier-0 discipline).
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo /home/claude/kg-automation)"
UNIT_SRC="${REPO_ROOT}/scripts/openclaw/deploy"
UNIT_DST="${HOME}/.config/systemd/user"
SERVICE_UNIT="agent-skill-sync.service"
TIMER_UNIT="agent-skill-sync.timer"
HELPER="scripts/openclaw/deploy/deploy_agent_skills.py"
SKILLS_SRC="${REPO_ROOT}/scripts/openclaw/skills"
FRESHNESS="/data/services/openclaw/deploy/skills-last-tick.json"

MODE="${1:-}"

fail() { echo "DEPLOY FAILED: $*" >&2; echo "Recovery: systemctl --user disable --now ${TIMER_UNIT}; rm -f ${UNIT_DST}/agent-skill-sync.{service,timer}; systemctl --user daemon-reload" >&2; exit 1; }

preflight() {
  # The code + units must already be in the checkout (they arrive in the same
  # merge commit; felix-deployer advances the checkout before apply).
  [ -f "${REPO_ROOT}/${HELPER}" ] || fail "helper missing: ${HELPER}"
  [ -f "${UNIT_SRC}/${SERVICE_UNIT}" ] || fail "unit missing: ${SERVICE_UNIT}"
  [ -f "${UNIT_SRC}/${TIMER_UNIT}" ] || fail "unit missing: ${TIMER_UNIT}"
  [ -d "${SKILLS_SRC}" ] || fail "skills source dir missing: ${SKILLS_SRC}"
}

case "${MODE}" in
  --dry-run)
    # Non-mutating: validate inputs + print the planned steps. No side effects.
    preflight
    echo "[skills-sync deploy] DRY-RUN ok — would: place ${SERVICE_UNIT}+${TIMER_UNIT} in ${UNIT_DST}; daemon-reload; run '${HELPER} --smoke' (lock-free real-copy gate, assert status=smoke); enable --now ${TIMER_UNIT}; assert is-enabled + list-timers."
    exit 0
    ;;
  --apply)
    : # fall through to the apply body below
    ;;
  *)
    echo "usage: $0 --dry-run | --apply" >&2
    exit 2
    ;;
esac

# ----- --apply -----
echo "[skills-sync deploy] apply: repo_root=${REPO_ROOT}"
preflight

# 1. Place unit files.
mkdir -p "${UNIT_DST}"
cp "${UNIT_SRC}/${SERVICE_UNIT}" "${UNIT_DST}/"
cp "${UNIT_SRC}/${TIMER_UNIT}" "${UNIT_DST}/"
echo "[skills-sync deploy] units placed in ${UNIT_DST}"

# 2. Reload the user manager.
systemctl --user daemon-reload || fail "daemon-reload failed (XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}?)"

# 3. REAL-COPY SMOKE GATE (lock-free — felix-deployer holds the checkout lock).
#    Runs the helper's --smoke in-process (NOT via `systemctl start`, which would
#    defer under the held lock). It does real SKILL.md copies and writes
#    status='smoke'. A failed smoke fails the deploy (do NOT enable an unproven unit).
( cd "${REPO_ROOT}" && /usr/bin/python3 -m scripts.openclaw.deploy.deploy_agent_skills --smoke ) \
  || fail "smoke: real-copy tick (--smoke) returned non-zero"
[ -f "${FRESHNESS}" ] || fail "smoke: freshness signal ${FRESHNESS} not written"
smoke_status="$(/usr/bin/python3 -c "import json; print(json.load(open('${FRESHNESS}')).get('status',''))" 2>/dev/null || echo '')"
case "${smoke_status}" in
  smoke) echo "[skills-sync deploy] smoke OK — real-copy tick ran (status=smoke)";;
  smoke_partial) fail "smoke: a SKILL.md copy failed during the smoke tick (status=smoke_partial) — inspect the audit log";;
  *) fail "smoke: freshness status='${smoke_status}' is not 'smoke' — the real-copy tick did not run (a lock-defer or stale pointer would show here)";;
esac

# 4. Enable (only reached after a clean smoke). enable --now just schedules the
#    timer; the first real (locked) tick runs after felix-deployer releases the lock.
systemctl --user enable --now "${TIMER_UNIT}" || fail "enable --now ${TIMER_UNIT} failed"

# 5. Assert the timer is enabled AND scheduled.
systemctl --user is-enabled "${TIMER_UNIT}" | grep -q enabled || fail "${TIMER_UNIT} not enabled after enable --now"
systemctl --user list-timers "${TIMER_UNIT}" --no-pager | grep -q "${TIMER_UNIT}" || fail "${TIMER_UNIT} not in list-timers"

echo "[skills-sync deploy] OK — ${TIMER_UNIT} enabled + scheduled; real-copy smoke green."
