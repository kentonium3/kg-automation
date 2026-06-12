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
# the current CLI, gateway restart, liveness probe, old-key-revoke reminder) is
# handled here.
#
# Usage (on office2 as the claude user):
#   /home/claude/kg-automation/scripts/security/anthropic-rotate.sh
#
# From Mac (one-shot, no manual ssh first):
#   ssh -t office2-claude /home/claude/kg-automation/scripts/security/anthropic-rotate.sh

set -euo pipefail

PLAINTEXT_FILE="/data/services/openclaw/secrets/anthropic"
OPENCLAW_BIN="openclaw"
GATEWAY_UNIT="openclaw-gateway.service"
# Canonical liveness cron: inbox-7am on felix-admin-capture. Manual run is cheap
# and exercises the openclaw-gateway → sub-agent → anthropic API path end-to-end.
LIVENESS_CRON_ID="cc9977fa-e451-47e7-9a18-eb6d85775f26"
LIVENESS_CRON_NAME="inbox-7am"

# ---- argv ------------------------------------------------------------------

SKIP_LIVENESS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-liveness) SKIP_LIVENESS=1; shift;;
    -h|--help)
      cat <<EOF
Usage: $0 [--skip-liveness]

Rotates the Anthropic API key across all three consumers in lock-step:
  - /data/services/openclaw/secrets/anthropic (file, 0600)
  - OpenClaw's per-agent SQLite auth store (anthropic:default on agent "main")
  - openclaw-gateway restarted to pick up the new key

  --skip-liveness   Skip the inbox-7am liveness probe at the end.

Runs entirely as the claude user. Requires interactive TTY.
EOF
      exit 0;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2;;
  esac
done

# ---- preconditions ---------------------------------------------------------

if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  echo "ERROR: openclaw not found on PATH" >&2
  exit 1
fi

if [[ ! -t 0 ]]; then
  echo "ERROR: stdin is not a TTY — the key-paste prompt needs a real terminal." >&2
  echo "       From Mac, invoke with: ssh -t office2-claude $0" >&2
  exit 1
fi

# ---- self-update -----------------------------------------------------------

# Pull latest before running. Prevents the trap where a fix to this very
# script (e.g., a CLI-flag rename) doesn't take effect on the FIRST rotation
# because the previous version was on disk at invocation time.
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -d "${REPO_ROOT}/.git" ]]; then
  echo "==> Pulling latest anthropic-rotate.sh from main..."
  git -C "${REPO_ROOT}" fetch origin main --quiet
  git -C "${REPO_ROOT}" pull --ff-only origin main
  if [[ -z "${ANTHROPIC_ROTATE_REEXECED:-}" ]]; then
    export ANTHROPIC_ROTATE_REEXECED=1
    exec "${BASH_SOURCE[0]}" "$@"
  fi
fi

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

echo "==> Step 2: writing $PLAINTEXT_FILE (mode 600)..."
printf '%s' "$NEW_KEY" > "$PLAINTEXT_FILE"
chmod 600 "$PLAINTEXT_FILE"
# Owner should already be claude:claude on office2; chown is a no-op then.
chown claude:claude "$PLAINTEXT_FILE" 2>/dev/null || true
stat -c "  %a %U:%G %n (%s bytes)" "$PLAINTEXT_FILE"

# ---- step 3: update OpenClaw's per-agent SQLite auth store -----------------

# OpenClaw 2026.6+ stores auth in agents/<id>/agent/openclaw-agent.sqlite.
# `openclaw models auth paste-api-key` is the current CLI for writing the
# anthropic:default profile on the main agent. (Pre-2026.6 was `openclaw auth set`.)
# Pipe via stdin to avoid a second key-paste prompt; the CLI reads from stdin
# when not on a TTY for the key value.
echo "==> Step 3: updating OpenClaw auth store (anthropic:default on agent 'main')..."
if ! printf '%s' "$NEW_KEY" | "$OPENCLAW_BIN" models auth paste-api-key \
      --provider anthropic --profile-id anthropic:default --agent main; then
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
for i in 1 2 3 4 5; do
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
  ENQUEUE_RESULT="$("$OPENCLAW_BIN" cron run "$LIVENESS_CRON_ID" 2>&1)"
  if ! echo "$ENQUEUE_RESULT" | grep -q '"ok": true'; then
    echo "ERROR: failed to enqueue liveness cron run." >&2
    echo "$ENQUEUE_RESULT" >&2
    exit 1
  fi
  # Poll for the run to finish. Manual runs typically complete in <30s.
  RUN_AT_MS=""
  for i in $(seq 1 30); do
    sleep 2
    LATEST="$("$OPENCLAW_BIN" cron runs --id "$LIVENESS_CRON_ID" --limit 1 2>&1 \
      | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    e = d.get('entries') or []
    if e:
        print(f\"{e[0].get('runAtMs',0)} {e[0].get('status','?')}\")
except Exception:
    pass
" 2>/dev/null)"
    if [[ -z "$LATEST" ]]; then continue; fi
    LATEST_RUN_AT_MS="${LATEST%% *}"
    LATEST_STATUS="${LATEST##* }"
    # Skip the historical entry; only the run we just enqueued (after script start) counts.
    if [[ "$LATEST_RUN_AT_MS" -gt "$(date -u +%s)000" ]] 2>/dev/null; then : ; fi
    # Anything younger than ~5 min is our run.
    AGE_MS=$(( $(date -u +%s)000 - LATEST_RUN_AT_MS ))
    if [[ "$AGE_MS" -lt 300000 ]]; then
      RUN_AT_MS="$LATEST_RUN_AT_MS"
      STATUS="$LATEST_STATUS"
      break
    fi
  done
  if [[ -z "$RUN_AT_MS" ]]; then
    echo "ERROR: liveness cron did not surface a fresh run within 60s." >&2
    exit 1
  fi
  if [[ "$STATUS" != "ok" ]]; then
    echo "ERROR: liveness probe failed (status=$STATUS)." >&2
    "$OPENCLAW_BIN" cron runs --id "$LIVENESS_CRON_ID" --limit 1 >&2
    exit 1
  fi
  echo "  $LIVENESS_CRON_NAME: ok"
fi

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
