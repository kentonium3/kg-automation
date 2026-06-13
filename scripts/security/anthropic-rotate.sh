#!/usr/bin/env bash
# anthropic-rotate.sh — automate the lock-step Anthropic API key rotation.
#
# Why this exists: the Anthropic key has three independent consumers on office2
# (openclaw-gateway via OpenClaw's per-agent SQLite auth store, the
# felix-doc-auditor scripts-first driver, and the felix-heartbeat-gate — #490),
# so a manual rotation has to touch two storage paths in lock-step. Past
# rotations have hit copy-paste errors on multi-line shell snippets and
# version-drift on the OpenClaw CLI surface (auth set → models auth paste-api-key
# in 2026.6.x). Canonical procedure: docs/runbooks/credential-rotation-ops.md
# § `anthropic`.
#
# One interactive step remains (cannot be automated):
#   - Operator generates the new key in console.anthropic.com and pastes it.
#
# Everything else (file write + permissions, OpenClaw auth store update via
# the current CLI, gateway restart, liveness probe, post-rotation verify gate
# (WP03), old-key-revoke reminder) is handled here.
#
# Usage (on office2 as the claude user):
#   /home/claude/kg-automation/scripts/security/anthropic-rotate.sh
#
#   # Roll back a previously-completed rotation (WP03, FR-014):
#   /home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback <unix-ts>
#
# From Mac (one-shot, no manual ssh first):
#   ssh -t office2-claude /home/claude/kg-automation/scripts/security/anthropic-rotate.sh
#
# Environment overrides (intended for tests; defaults match office2 paths):
#   ANTHROPIC_ROTATE_PLAINTEXT_FILE  - path to the plaintext credential file
#   ANTHROPIC_VERIFY_BIN             - path to anthropic-verify.sh used in Step 6
#   ANTHROPIC_ROTATE_OPENCLAW_HOME   - directory holding openclaw.json + agents/
#                                      (defaults to ${HOME}/.openclaw)
#   ANTHROPIC_ROTATE_GATEWAY_RESTART_CMD - command run to restart the gateway
#                                      (defaults to: systemctl --user restart
#                                      openclaw-gateway.service)
#   ANTHROPIC_ROTATE_SKIP_SELF_UPDATE - non-empty to skip the git pull / re-exec
#                                      (set by tests; also auto-set when not a
#                                      git checkout)

set -euo pipefail

: "${ANTHROPIC_ROTATE_PLAINTEXT_FILE:=/data/services/openclaw/secrets/anthropic}"
: "${ANTHROPIC_VERIFY_BIN:=/home/claude/kg-automation/scripts/security/anthropic-verify.sh}"
: "${ANTHROPIC_ROTATE_OPENCLAW_HOME:=${HOME}/.openclaw}"
: "${ANTHROPIC_ROTATE_GATEWAY_RESTART_CMD:=systemctl --user restart openclaw-gateway.service}"

PLAINTEXT_FILE="${ANTHROPIC_ROTATE_PLAINTEXT_FILE}"
OPENCLAW_BIN="openclaw"
GATEWAY_UNIT="openclaw-gateway.service"
# Canonical liveness cron: inbox-7am on felix-admin-capture. Manual run is cheap
# and exercises the openclaw-gateway → sub-agent → anthropic API path end-to-end.
LIVENESS_CRON_ID="cc9977fa-e451-47e7-9a18-eb6d85775f26"
LIVENESS_CRON_NAME="inbox-7am"

# ---- argv ------------------------------------------------------------------

SKIP_LIVENESS=0
ROLLBACK_TS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-liveness) SKIP_LIVENESS=1; shift;;
    --rollback)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --rollback requires a timestamp argument" >&2
        exit 2
      fi
      ROLLBACK_TS="$2"
      shift 2;;
    -h|--help)
      cat <<EOF
Usage: $0 [--skip-liveness]
       $0 --rollback <unix-ts>

Rotates the Anthropic API key across all three consumers in lock-step:
  - $PLAINTEXT_FILE (file, 0600)
  - OpenClaw's per-agent SQLite auth store (anthropic:default on agent "main")
  - openclaw-gateway restarted to pick up the new key

After rotation, invokes ${ANTHROPIC_VERIFY_BIN} --check as a fail-closed
gate (WP03 / FR-012, FR-013). On verifier failure, prints the findings and a
copy-pasteable --rollback command and exits non-zero. Rotation is NOT
auto-undone.

  --skip-liveness     Skip the inbox-7am liveness probe at the end.
  --rollback <ts>     Restore the three rotation artifacts recorded in
                      ~/.cache/anthropic-rotate/manifest.<ts>.json. Refuses
                      partial rollback if any backup is missing.

Runs entirely as the claude user. Requires interactive TTY (except for
--rollback, which is non-interactive).
EOF
      exit 0;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2;;
  esac
done

# ---- rollback branch (WP03, T012, FR-014) ---------------------------------

if [[ -n "$ROLLBACK_TS" ]]; then
  MANIFEST_DIR="${HOME}/.cache/anthropic-rotate"
  MANIFEST_FILE="${MANIFEST_DIR}/manifest.${ROLLBACK_TS}.json"
  if [[ ! -f "$MANIFEST_FILE" ]]; then
    echo "ERROR: manifest not found: $MANIFEST_FILE" >&2
    exit 1
  fi
  echo "==> anthropic-rotate --rollback ${ROLLBACK_TS}"
  echo "==> manifest: $MANIFEST_FILE"
  PLAINTEXT_BAK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['backups']['plaintext_file'])" "$MANIFEST_FILE")
  OPENCLAW_JSON_BAK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['backups']['openclaw_json'])" "$MANIFEST_FILE")
  SQLITE_IMPORT_BAK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['backups']['sqlite_import_bak'])" "$MANIFEST_FILE")
  # Verify all three backups exist before mutating anything (no partial rollback).
  MISSING=()
  for path in "$PLAINTEXT_BAK" "$OPENCLAW_JSON_BAK" "$SQLITE_IMPORT_BAK"; do
    [[ -f "$path" ]] || MISSING+=("$path")
  done
  if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "ERROR: backup(s) missing — refusing partial rollback:" >&2
    printf '  - %s\n' "${MISSING[@]}" >&2
    exit 1
  fi
  OPENCLAW_JSON_TARGET="${ANTHROPIC_ROTATE_OPENCLAW_HOME}/openclaw.json"
  SQLITE_AUTH_TARGET="${ANTHROPIC_ROTATE_OPENCLAW_HOME}/agents/main/agent/auth-profiles.json"
  echo "==> restoring openclaw.json..."
  cp "$OPENCLAW_JSON_BAK" "$OPENCLAW_JSON_TARGET"
  chmod 600 "$OPENCLAW_JSON_TARGET"
  echo "==> restoring SQLite import bak (triggers openclaw doctor --fix import)..."
  mkdir -p "$(dirname "$SQLITE_AUTH_TARGET")"
  cp "$SQLITE_IMPORT_BAK" "$SQLITE_AUTH_TARGET"
  if command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
    "$OPENCLAW_BIN" doctor --fix --non-interactive >/dev/null || true
  fi
  echo "==> restoring plaintext file (atomic)..."
  mkdir -p "$(dirname "$PLAINTEXT_FILE")"
  cp "$PLAINTEXT_BAK" "${PLAINTEXT_FILE}.tmp"
  chmod 600 "${PLAINTEXT_FILE}.tmp"
  mv "${PLAINTEXT_FILE}.tmp" "$PLAINTEXT_FILE"
  echo "==> restarting openclaw-gateway.service..."
  # ANTHROPIC_ROTATE_GATEWAY_RESTART_CMD is operator-injected for tests; safe
  # to word-split here on purpose. shellcheck disable=SC2086
  ${ANTHROPIC_ROTATE_GATEWAY_RESTART_CMD}
  echo "==> rollback complete. Run anthropic-verify --check to confirm."
  exit 0
fi

# ---- preconditions ---------------------------------------------------------

if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  echo "ERROR: openclaw not found on PATH" >&2
  exit 1
fi

if [[ -z "${ANTHROPIC_ROTATE_SKIP_TTY_CHECK:-}" && ! -t 0 ]]; then
  echo "ERROR: stdin is not a TTY — the key-paste prompt needs a real terminal." >&2
  echo "       From Mac, invoke with: ssh -t office2-claude $0" >&2
  exit 1
fi

# ---- self-update -----------------------------------------------------------

# Pull latest before running. Prevents the trap where a fix to this very
# script (e.g., a CLI-flag rename) doesn't take effect on the FIRST rotation
# because the previous version was on disk at invocation time.
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -z "${ANTHROPIC_ROTATE_SKIP_SELF_UPDATE:-}" && -d "${REPO_ROOT}/.git" ]]; then
  echo "==> Pulling latest anthropic-rotate.sh from main..."
  git -C "${REPO_ROOT}" fetch origin main --quiet
  git -C "${REPO_ROOT}" pull --ff-only origin main
  if [[ -z "${ANTHROPIC_ROTATE_REEXECED:-}" ]]; then
    export ANTHROPIC_ROTATE_REEXECED=1
    exec "${BASH_SOURCE[0]}" "$@"
  fi
fi

# ---- step 0: manifest write (WP03, T011, FR-013) ---------------------------
#
# Written BEFORE any rotation artifact is touched. Even a failed paste at
# Step 1 leaves the manifest discoverable for inspection / rollback planning.

ROTATION_TS=$(date +%s)
MANIFEST_DIR="${HOME}/.cache/anthropic-rotate"
MANIFEST_FILE="${MANIFEST_DIR}/manifest.${ROTATION_TS}.json"
mkdir -p "$MANIFEST_DIR"

# Compute the three backup paths up front so the manifest names them before
# any artifact is mutated. These are the paths the --rollback <ts> branch
# above will read back.
PLAINTEXT_BAK="${PLAINTEXT_FILE}.pre-rotate.${ROTATION_TS}.bak"
OPENCLAW_JSON="${ANTHROPIC_ROTATE_OPENCLAW_HOME}/openclaw.json"
OPENCLAW_JSON_BAK="${OPENCLAW_JSON}.bak"   # written by `openclaw models auth paste-api-key`
SQLITE_IMPORT_BAK="${ANTHROPIC_ROTATE_OPENCLAW_HOME}/agents/main/agent/auth-profiles.json.sqlite-import.${ROTATION_TS}.bak"

cat > "$MANIFEST_FILE" <<MANIFEST
{
  "rotation_ts": ${ROTATION_TS},
  "started_at_iso": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backups": {
    "plaintext_file": "${PLAINTEXT_BAK}",
    "openclaw_json": "${OPENCLAW_JSON_BAK}",
    "sqlite_import_bak": "${SQLITE_IMPORT_BAK}"
  },
  "rotation_completed_at_iso": null,
  "verify_outcome": null
}
MANIFEST
chmod 600 "$MANIFEST_FILE"
echo "==> manifest: $MANIFEST_FILE"

# ---- step 1: operator generates + pastes new key ---------------------------

cat <<EOF

==> anthropic-rotate

==> Step 1: browser-side steps
    1. Open https://console.anthropic.com/settings/keys
    2. Click "Create Key" — name it something traceable (e.g., office2-felix-YYYY-MM-DD)
    3. Copy the key value immediately (you cannot read it again later)

==> Paste the new API key below (input is hidden), then press Enter:
EOF

read -rs NEW_KEY
echo

if [[ -z "$NEW_KEY" ]]; then
  echo "ERROR: empty key — aborting." >&2
  exit 1
fi

# Cheap shape check. Anthropic keys are sk-ant-... — refuse anything obviously wrong.
if [[ "$NEW_KEY" != sk-ant-* ]]; then
  echo "ERROR: key does not start with sk-ant- — refusing to deploy a malformed value." >&2
  echo "       If Anthropic has changed the key prefix, update this check in the script." >&2
  exit 1
fi

# ---- step 2: write plaintext file (consumed by doc-auditor + heartbeat-gate) ----
#
# Back up the existing plaintext file before overwriting (WP03, T011).
# The backup path is the one recorded in the manifest above so --rollback can find it.

echo "==> Step 2: writing $PLAINTEXT_FILE (mode 600)..."
if [[ -f "$PLAINTEXT_FILE" ]]; then
  cp "$PLAINTEXT_FILE" "$PLAINTEXT_BAK"
  chmod 600 "$PLAINTEXT_BAK"
  echo "  backup: $PLAINTEXT_BAK"
fi
printf '%s' "$NEW_KEY" > "$PLAINTEXT_FILE"
chmod 600 "$PLAINTEXT_FILE"
# Owner should already be claude:claude on office2; chown is a no-op then.
chown claude:claude "$PLAINTEXT_FILE" 2>/dev/null || true
# stat -c is GNU; macOS uses BSD `stat -f`. This is diagnostic only — failure
# here must not abort rotation when running cross-platform tests.
stat -c "  %a %U:%G %n (%s bytes)" "$PLAINTEXT_FILE" 2>/dev/null || true

# ---- step 3: update OpenClaw's per-agent SQLite auth store -----------------

# OpenClaw 2026.6+ stores auth in agents/<id>/agent/openclaw-agent.sqlite.
# `openclaw models auth paste-api-key` is the current CLI for writing the
# anthropic:default profile on the main agent. (Pre-2026.6 was `openclaw auth set`.)
# IMPORTANT: --agent is an option on the `models auth` parent command, NOT on
# `paste-api-key`. It must appear BEFORE the subcommand. Pipe via stdin to
# avoid a second key-paste prompt; the CLI reads from stdin when not on a TTY.
echo "==> Step 3: updating OpenClaw auth store (anthropic:default on agent 'main')..."
if ! printf '%s' "$NEW_KEY" | "$OPENCLAW_BIN" models auth --agent main paste-api-key \
      --provider anthropic --profile-id anthropic:default; then
  echo "ERROR: openclaw models auth paste-api-key failed." >&2
  echo "       The plaintext file at $PLAINTEXT_FILE was already updated." >&2
  echo "       Remediate manually before continuing — gateway is on stale auth." >&2
  exit 1
fi

# Safety: ensure the new key is reflected in openclaw-agent.sqlite (idempotent).
# In a clean 2026.6+ environment paste-api-key writes directly to SQLite, but
# doctor --fix re-imports any legacy auth-profiles.json files that may have
# been touched. Idempotent and cheap.
echo "==> Step 3b: openclaw doctor --fix --non-interactive (safety sweep)..."
"$OPENCLAW_BIN" doctor --fix --non-interactive >/dev/null

# ---- step 4: restart gateway -----------------------------------------------

echo "==> Step 4: restarting $GATEWAY_UNIT..."
systemctl --user restart "$GATEWAY_UNIT"
# Give the gateway a moment to come up before probing.
for _ in 1 2 3 4 5; do
  if systemctl --user is-active --quiet "$GATEWAY_UNIT"; then
    break
  fi
  sleep 1
done
if ! systemctl --user is-active --quiet "$GATEWAY_UNIT"; then
  echo "ERROR: gateway did not become active within 5s." >&2
  systemctl --user status "$GATEWAY_UNIT" --no-pager | head -20 >&2
  exit 1
fi
echo "  $GATEWAY_UNIT: active"

# ---- step 5: liveness probe ------------------------------------------------

if [[ "$SKIP_LIVENESS" -eq 1 ]]; then
  echo "==> Step 5: liveness probe skipped (--skip-liveness)"
else
  echo "==> Step 5: liveness probe — running cron job '$LIVENESS_CRON_NAME'..."
  # `cron run --wait` is synchronous and returns a JSON envelope with a
  # top-level `status` field. Simpler and bug-free vs polling cron runs.
  PROBE_JSON="$("$OPENCLAW_BIN" cron run --wait --wait-timeout 90s "$LIVENESS_CRON_ID" 2>&1)" || {
    echo "ERROR: liveness probe call failed." >&2
    echo "$PROBE_JSON" >&2
    exit 1
  }
  PROBE_STATUS="$(echo "$PROBE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)"
  if [[ "$PROBE_STATUS" != "ok" ]]; then
    echo "ERROR: liveness probe returned status=$PROBE_STATUS (expected ok)." >&2
    echo "$PROBE_JSON" >&2
    exit 1
  fi
  echo "  $LIVENESS_CRON_NAME: ok"
fi

# ---- step 6: verify (fail-closed gate; WP03, T011, FR-012/FR-013/NFR-006) --

echo "==> Step 6: anthropic-verify --check (fail-closed gate)..."
if VERIFY_OUTPUT=$("$ANTHROPIC_VERIFY_BIN" --check 2>&1); then
  VERIFY_EXIT=0
else
  VERIFY_EXIT=$?
fi

if [[ "$VERIFY_EXIT" -ne 0 ]]; then
  echo "$VERIFY_OUTPUT" >&2
  cat <<EOF >&2

==> ROTATION VERIFY FAILED (exit ${VERIFY_EXIT} after rotation).
==> Rotation artifacts ARE in place but verifier flagged a finding above.
==> Inspect the finding, then EITHER remediate forward (e.g., anthropic-verify --repair if shadow)
==> OR roll back this rotation:

    /home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback ${ROTATION_TS}

==> The rollback restores the plaintext file, openclaw.json, and the SQLite import-bak
==> from the per-step backups recorded at rotation start.
EOF
  python3 - "$MANIFEST_FILE" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text())
d['verify_outcome'] = 'failed'
d['rotation_completed_at_iso'] = None
p.write_text(json.dumps(d, indent=2))
PY
  exit "$VERIFY_EXIT"
fi

echo "  verify: green"

python3 - "$MANIFEST_FILE" <<'PY'
import json, pathlib, sys
from datetime import datetime, timezone
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text())
d['verify_outcome'] = 'passed'
d['rotation_completed_at_iso'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
p.write_text(json.dumps(d, indent=2))
PY

# ---- closing summary -------------------------------------------------------

cat <<EOF

==> anthropic-rotate complete.

    All three consumers (openclaw-gateway, felix-doc-auditor-driver,
    felix-heartbeat-gate) now read the new key.

==> Manual follow-up (you do this — script can't):
    1. Revoke the OLD key at https://console.anthropic.com/settings/keys
       (do this AFTER you've confirmed the next felix-doc-auditor and
       felix-heartbeat-gate ticks come back ok — see verification in
       docs/runbooks/credential-rotation-ops.md § \`anthropic\`).
    2. Update credential-manifest.json last_updated date if rotating
       proactively rather than in response to an incident.
EOF
