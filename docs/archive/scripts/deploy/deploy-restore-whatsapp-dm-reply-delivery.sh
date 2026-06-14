#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# deploy-restore-whatsapp-dm-reply-delivery.sh
#
# Mission: restore-whatsapp-dm-reply-delivery-01KTVVHH
# Issue:   kentonium3/kg-automation#588
# Path:    UPGRADE (openclaw 2026.5.28 -> 2026.6.5 per WP01 verdict H6)
# Tier:    2 (Application/State) per C-003; requires Restic <=24h pre-flight
#          and #557 audited-surface rebaseline post-deploy.
#
# References
#   WP01 investigation: docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md
#   Smoke contract:     kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/journal-event-assertions.md
#   Quickstart:         kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/quickstart.md (sections 4.6 + 4.7)
#   Upgrade gotchas:    memory reference_openclaw_upgrade_gotchas
#
# Order of operations
#   Stage 0 — Tier 2 pre-flight attestation gate (--backup-confirmed required)
#   Stage 1 — connectivity + pre-upgrade doctor capture
#   Stage 2 — backup current openclaw.json on office2
#   Stage 3 — OPERATOR-DRIVEN sudo upgrade via ssh office2-kgale (paused here)
#   Stage 4 — post-upgrade verification (gotchas checklist)
#   Stage 5 — restart openclaw-gateway, confirm active
#   Stage 6 — operator-driven 1-DM post-flight smoke (60s window) with
#             contract-aligned awk assertion and rollback instructions on fail
#
# Exit codes
#   0   success
#   1   stage failure (connectivity, verification, gateway, smoke, etc.)
#   64  missing --backup-confirmed flag (Tier 2 pre-flight attestation)

TARGET_VERSION="2026.6.5"
PRIOR_VERSION="2026.5.28"
REQUIRE_BACKUP_FLAG="--backup-confirmed"

TS="$(date -u +%Y%m%d-%H%M%S)"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Stage 0 — Tier 2 pre-flight attestation gate.
if [[ "${1:-}" != "$REQUIRE_BACKUP_FLAG" ]]; then
  cat <<EOF >&2
ERROR: this script requires the operator to attest the Tier 2 pre-flight.

Usage: $0 $REQUIRE_BACKUP_FLAG

Before running, verify a Restic snapshot <=24h via:
  ssh office2-kgale 'tail -1 /data/services/backup/logs/backup-\$(date +%Y-%m-%d).log'

If no snapshot exists within the last 24 hours, trigger one before deploy.
Repo root resolved: $REPO_ROOT
Run timestamp:      $TS
EOF
  exit 64
fi

echo "[deploy] repo_root=$REPO_ROOT ts=$TS target_version=$TARGET_VERSION"

echo "[deploy] === Stage 1: Pre-flight (connectivity + doctor capture) ==="
ssh -o ConnectTimeout=5 office2-claude 'echo ok' >/dev/null \
  || { echo "FAIL: office2-claude unreachable" >&2; exit 1; }
echo "[deploy]   + office2-claude reachable"

# shellcheck disable=SC2029  # $TS must expand locally so each run is timestamped on the deploy host.
ssh office2-claude "openclaw doctor --json > /tmp/openclaw-doctor.pre-upgrade-$TS.json 2>&1 || true; head -40 /tmp/openclaw-doctor.pre-upgrade-$TS.json" \
  || { echo "FAIL: pre-upgrade doctor capture failed" >&2; exit 1; }
echo "[deploy]   + pre-upgrade doctor snapshot at /tmp/openclaw-doctor.pre-upgrade-$TS.json"

PRE_VERSION="$(ssh office2-claude 'openclaw --version' || true)"
echo "[deploy]   + pre-upgrade version: $PRE_VERSION"

echo "[deploy] === Stage 2: Backup current openclaw.json ==="
# shellcheck disable=SC2029  # $TS must expand locally so the backup path matches the doctor snapshot above.
ssh office2-claude "cp /home/claude/.openclaw/openclaw.json /home/claude/.openclaw/openclaw.json.pre-upgrade-$TS" \
  || { echo "FAIL: openclaw.json backup failed" >&2; exit 1; }
echo "[deploy]   + backup: /home/claude/.openclaw/openclaw.json.pre-upgrade-$TS"

echo "[deploy] === Stage 3: openclaw upgrade (OPERATOR-DRIVEN sudo) ==="
cat <<EOF
[deploy]
[deploy]   OPERATOR ACTION REQUIRED — the claude user has no sudo.
[deploy]   Open a SECOND terminal and run EXACTLY:
[deploy]
[deploy]     ssh office2-kgale 'sudo npm install -g openclaw@${TARGET_VERSION}'
[deploy]
[deploy]   When the install completes successfully, return here and press Enter.
[deploy]   If the install fails, press Ctrl-C — no further stages have run on
[deploy]   the box, and the pre-upgrade backup at
[deploy]     /home/claude/.openclaw/openclaw.json.pre-upgrade-$TS
[deploy]   is untouched.
[deploy]
EOF
read -r _operator_ack
echo "[deploy]   + operator acknowledged upgrade complete"

echo "[deploy] === Stage 4: Post-upgrade verification (gotchas checklist) ==="

POST_VERSION="$(ssh office2-claude 'openclaw --version' || true)"
echo "[deploy]   post-upgrade version: $POST_VERSION"
if ! echo "$POST_VERSION" | grep -q "$TARGET_VERSION"; then
  echo "FAIL: version mismatch post-upgrade (expected $TARGET_VERSION, got $POST_VERSION)" >&2
  exit 1
fi
echo "[deploy]   + version reports $TARGET_VERSION"

if ! ssh office2-claude 'openclaw doctor --json' | jq -e '.success == true' >/dev/null; then
  echo "FAIL: openclaw doctor reports failure post-upgrade" >&2
  ssh office2-claude 'openclaw doctor --json' | head -40 >&2 || true
  exit 1
fi
echo "[deploy]   + openclaw doctor reports success"

if ! ssh office2-claude 'jq ".models.providers.anthropic.models | length > 0" /home/claude/.openclaw/openclaw.json' | grep -q true; then
  echo "FAIL: models.providers.anthropic.models[] missing or empty (regression of #557-class config drift)" >&2
  exit 1
fi
echo "[deploy]   + models.providers.anthropic.models[] populated"

if ! ssh office2-claude 'jq ".plugins.entries.whatsapp.enabled" /home/claude/.openclaw/openclaw.json' | grep -q true; then
  echo "FAIL: @openclaw/whatsapp plugin not enabled in deployed config" >&2
  exit 1
fi
echo "[deploy]   + @openclaw/whatsapp external plugin enabled"

echo "[deploy] === Stage 5: Restart openclaw-gateway ==="
ssh office2-claude 'systemctl --user restart openclaw-gateway.service' \
  || { echo "FAIL: gateway restart command failed" >&2; exit 1; }
sleep 10
if ! ssh office2-claude 'systemctl --user is-active openclaw-gateway.service' | grep -q '^active$'; then
  echo "FAIL: openclaw-gateway not active post-restart" >&2
  ssh office2-claude 'systemctl --user status openclaw-gateway.service | head -20' >&2 || true
  exit 1
fi
echo "[deploy]   + openclaw-gateway active"

echo "[deploy] === Stage 6: Post-flight 1-DM smoke (operator-driven) ==="
cat <<EOF
[deploy]
[deploy]   OPERATOR ACTION REQUIRED:
[deploy]   Send ONE WhatsApp DM to +16179300916 (any short message).
[deploy]   You have 60 seconds. The smoke window starts now.
[deploy]
EOF
SMOKE_TS="$(date -u +"%Y-%m-%d %H:%M:%S")"
echo "[deploy]   smoke window opens at: $SMOKE_TS (UTC)"
sleep 60

# Awk pattern aligned byte-for-byte with the canonical operator command in
# contracts/journal-event-assertions.md (resolve_fail_current= and trunc_main=
# field names; trunc_main asserts SC-006 / FR-006 regression).
# shellcheck disable=SC2029  # $SMOKE_TS must expand locally so the journal window matches the operator prompt above.
RESULTS="$(ssh office2-claude "journalctl --user -u openclaw-gateway --since '$SMOKE_TS' 2>/dev/null | awk '/\\[whatsapp\\] Inbound message/{i++} /\\[whatsapp\\] Sending message ->/{s++} /\\[whatsapp\\] Sent message /{sent++} /\\[diagnostic\\] stalled session/{stall++} /\\[diagnostic\\] stuck session recovery/{rec++} /sessions\\.resolve.*INVALID_REQUEST.*current/{rf++} /truncating in injected context.*sessionKey=agent:main:/{trunc++} END{print \"inbound=\"i\" send=\"s\" sent=\"sent\" stall=\"stall\" recovery=\"rec\" resolve_fail_current=\"rf\" trunc_main=\"trunc}'")"
echo "[deploy]   smoke results: $RESULTS"

EXPECTED="inbound=1 send=1 sent=1 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0"
if ! echo "$RESULTS" | grep -q "$EXPECTED"; then
  cat <<EOF >&2
[deploy] FAIL: post-flight smoke did not match expected pattern.
[deploy]   expected: $EXPECTED
[deploy]   actual:   $RESULTS
[deploy]
[deploy] ROLLBACK INSTRUCTIONS (operator):
[deploy]   1. Reinstall prior runtime (requires sudo):
[deploy]        ssh office2-kgale 'sudo npm install -g openclaw@${PRIOR_VERSION}'
[deploy]   2. Restore pre-upgrade openclaw.json + restart gateway:
[deploy]        ssh office2-claude 'cp /home/claude/.openclaw/openclaw.json.pre-upgrade-$TS /home/claude/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway.service'
[deploy]   3. Verify rollback:
[deploy]        ssh office2-claude 'openclaw --version'  # expect $PRIOR_VERSION
EOF
  exit 1
fi

echo "[deploy] === SUCCESS ==="
cat <<EOF
[deploy] post-flight 1-DM smoke passed; openclaw upgraded to $TARGET_VERSION
[deploy]
[deploy] NEXT STEPS (operator) — see quickstart.md sections 4.6 + 4.7:
[deploy]   1. WP05 will execute the full 5-DM acceptance smoke covering
[deploy]      SC-001 through SC-007.
[deploy]   2. After the full smoke passes, run the #557 audited-surface
[deploy]      rebaseline reset on office2:
[deploy]        ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
[deploy]   3. Record the rebaseline timestamp in the merge-commit trailer:
[deploy]        Rebaseline: completed at <ISO 8601 UTC>
EOF
