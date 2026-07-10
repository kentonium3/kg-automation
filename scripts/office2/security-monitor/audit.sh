#!/bin/bash
# Security audit script for office2
# Runs daily via cron at 3AM, alerts on changes from baseline
# Sends push notification via the felix-alert bus (ntfy under the hood) when
# alerts are detected
#
# Coverage:
#   System: .pth files, pip packages, Docker images, brew packages + taps,
#           known IOCs, listening ports, system systemd enabled services,
#           SSH authorized_keys, /etc/hosts hash, system crontabs
#   User:   systemd user-scope enabled units + unit-file/drop-in inventory
#   Felix:  OpenClaw cron-job normalized config, openclaw.json content hash
#
# Setup:
#   1. Notifications go through the felix-alert bus shim
#      (scripts/common/alert_bus.sh), which sources the topic env-file at
#      /home/claude/.config/felix/alert-bus/env. No topic is hardcoded here.
#   2. Install the ntfy app on your phone: https://ntfy.sh
#   3. Subscribe to your topic in the app
#   4. On first run, baselines are created automatically
#   5. After intentional system changes, reset baselines:
#        sudo -u claude rm /data/services/security-monitor/baselines/*
#        sudo -u claude bash /data/services/security-monitor/scripts/audit.sh

# --- Configuration ---
BASE_DIR="/data/services/security-monitor"
BASELINE_DIR="$BASE_DIR/baselines"
LOG_DIR="$BASE_DIR/logs"
DATE=$(date +%Y-%m-%d)
LOGFILE="$LOG_DIR/audit-$DATE.log"
ALERT_FILE="$LOG_DIR/alerts-$DATE.log"
# Signal-driven doc-audit event stream (#278) — append-only JSONL
DRIFT_EVENTS_FILE="$LOG_DIR/drift-events.jsonl"
ALERT=0

# felix-alert bus shim — sources the topic env-file and delivers via the
# single Python ntfy source of truth. No hardcoded topic lives here anymore.
ALERT_BUS="/home/claude/kg-automation/scripts/common/alert_bus.sh"

# --- Helpers ---
log()   { echo "[$(date '+%H:%M:%S')] $1" >> "$LOGFILE"; }
alert() { echo "[ALERT] $1" | tee -a "$ALERT_FILE" >> "$LOGFILE"; ALERT=1; }

# Emit a structured drift event for felix-doc-auditor to consume.
# Diff is base64-encoded to avoid JSON-escaping multi-line content.
emit_drift_event() {
    local name="$1" diff_text="$2" event_type="${3:-baseline_drift}"
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local diff_b64
    diff_b64=$(printf '%s' "$diff_text" | base64 -w0)
    printf '{"timestamp":"%s","source":"audit.sh","event_type":"%s","baseline_name":"%s","diff_b64":"%s"}\n' \
        "$ts" "$event_type" "$name" "$diff_b64" >> "$DRIFT_EVENTS_FILE"
}

check_baseline() {
    local name="$1" current="$2"
    if [ -f "$BASELINE_DIR/$name" ]; then
        local d
        d=$(diff "$BASELINE_DIR/$name" "$current" 2>/dev/null || true)
        if [ -n "$d" ]; then
            alert "$name changed since baseline: $d"
            emit_drift_event "$name" "$d"
        else
            log "$name: no changes"
        fi
    else
        cp "$current" "$BASELINE_DIR/$name"
        log "$name: baseline created"
    fi
}

# --- Init ---
echo "=== Security Audit: $DATE ===" > "$LOGFILE"
> "$ALERT_FILE"

# 1. .pth file scan (Python startup hijack — litellm attack vector)
log "Scanning for .pth files..."
tmp=$(mktemp)
find /home /tmp /usr/local/lib /usr/lib/python3 -name "*.pth" 2>/dev/null | sort > "$tmp" || true
check_baseline "pth-files.txt" "$tmp"
rm -f "$tmp"

# 2. Pip packages
log "Scanning pip packages..."
tmp=$(mktemp)
python3 -m pip list --format=freeze > "$tmp" 2>/dev/null || echo "no-pip" > "$tmp"
check_baseline "pip-packages.txt" "$tmp"
rm -f "$tmp"

# 3. Docker images
log "Scanning Docker images..."
tmp=$(mktemp)
docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" 2>/dev/null | sort > "$tmp" || echo "no-docker" > "$tmp"
check_baseline "docker-images.txt" "$tmp"
rm -f "$tmp"

# 3b. Homebrew packages (gog CLI + transitive deps; Linuxbrew install path)
log "Scanning brew packages..."
tmp=$(mktemp)
BREW_BIN="/home/linuxbrew/.linuxbrew/bin/brew"
if [ -x "$BREW_BIN" ]; then
    "$BREW_BIN" list --versions 2>/dev/null | sort > "$tmp" || echo "brew-list-failed" > "$tmp"
else
    echo "no-brew" > "$tmp"
fi
check_baseline "brew-packages.txt" "$tmp"
rm -f "$tmp"

# 3c. Homebrew taps (supply-chain surface — non-default recipe repos)
log "Scanning brew taps..."
tmp=$(mktemp)
if [ -x "$BREW_BIN" ]; then
    "$BREW_BIN" tap 2>/dev/null | LC_ALL=C sort > "$tmp" || echo "brew-tap-failed" > "$tmp"
else
    echo "no-brew" > "$tmp"
fi
check_baseline "brew-taps.txt" "$tmp"
rm -f "$tmp"

# 4. Known IOCs (litellm supply chain attack indicators)
log "Checking known IOCs..."
[ -f "/tmp/pglog" ] && alert "IOC: /tmp/pglog exists (litellm indicator)"
systemctl is-active sysmon.service &>/dev/null && alert "IOC: sysmon.service running (litellm indicator)"
pc=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i "node-setup" || true)
[ -n "$pc" ] && alert "IOC: suspicious container: $pc"
log "IOC checks: done"

# 5. Listening ports
# Exclude ephemeral localhost ports (>32768) — these change on every reboot
# and are internal-only, not a security concern.
log "Scanning listening ports..."
tmp=$(mktemp)
# LC_ALL=C forces byte-collation so locale changes don't reorder lines
# (otherwise '[' vs digit ordering can drift and trip false-positive alerts).
ss -tlnp 2>/dev/null | tail -n +2 | awk '{print $4}' \
    | grep -vE '^127\.0\.0\.1:[3-9][0-9]{4}$' \
    | grep -vE '^127\.0\.0\.1:[0-9]{6}$' \
    | grep -vE '^\[::1\]:[3-9][0-9]{4}$' \
    | grep -vE '^\[::1\]:[0-9]{6}$' \
    | LC_ALL=C sort > "$tmp"
check_baseline "listening-ports.txt" "$tmp"
rm -f "$tmp"

# 6. Systemd enabled services (system scope)
log "Scanning systemd services..."
tmp=$(mktemp)
# LC_ALL=C forces byte-collation so case-mixed names (ModemManager vs systemd-*)
# sort in stable order across runs and locale changes.
systemctl list-unit-files --type=service --state=enabled --no-pager 2>/dev/null \
    | grep enabled | awk '{print $1}' | LC_ALL=C sort > "$tmp"
check_baseline "enabled-services.txt" "$tmp"
rm -f "$tmp"

# 6b. Systemd enabled units (user scope — claude)
# Uses explicit XDG_RUNTIME_DIR so it works under cron without a login session.
log "Scanning systemd user units (enabled)..."
tmp=$(mktemp)
XDG_RUNTIME_DIR="/run/user/$(id -u)" \
    systemctl --user list-unit-files --state=enabled --no-pager 2>/dev/null \
    | awk '$2 == "enabled" {print $1}' | LC_ALL=C sort > "$tmp" \
    || echo "no-user-systemd" > "$tmp"
check_baseline "systemd-user-units.txt" "$tmp"
rm -f "$tmp"

# 6c. Systemd user-scope unit files + drop-ins
# Captures unit files, *.conf drop-ins, and .wants/ symlinks (enabled state).
log "Scanning systemd user unit files..."
tmp=$(mktemp)
find "$HOME/.config/systemd/user" \( -type f -o -type l \) -printf '%P %y\n' 2>/dev/null \
    | LC_ALL=C sort > "$tmp"
check_baseline "systemd-user-dropins.txt" "$tmp"
rm -f "$tmp"

# 7. SSH authorized_keys
log "Scanning SSH authorized_keys..."
tmp=$(mktemp)
for d in /home/*/; do
    u=$(basename "$d")
    kf="$d.ssh/authorized_keys"
    if [ -f "$kf" ]; then
        echo "--- $u ---" >> "$tmp"
        ssh-keygen -l -f "$kf" >> "$tmp" 2>/dev/null || cat "$kf" >> "$tmp"
    fi
done
check_baseline "ssh-keys.txt" "$tmp"
rm -f "$tmp"

# 8. /etc/hosts integrity
log "Checking /etc/hosts..."
hh=$(sha256sum /etc/hosts | awk '{print $1}')
if [ -f "$BASELINE_DIR/hosts-hash.txt" ]; then
    bh=$(cat "$BASELINE_DIR/hosts-hash.txt")
    if [ "$hh" != "$bh" ]; then
        alert "/etc/hosts modified since baseline"
        emit_drift_event "hosts-hash.txt" "old:$bh new:$hh"
    else
        log "/etc/hosts: no changes"
    fi
else
    echo "$hh" > "$BASELINE_DIR/hosts-hash.txt"
    log "/etc/hosts: baseline recorded"
fi

# 9. Crontabs
log "Scanning crontabs..."
tmp=$(mktemp)
for u in claude kgale root; do
    t=$(crontab -u "$u" -l 2>/dev/null || true)
    if [ -n "$t" ]; then
        echo "--- $u ---" >> "$tmp"
        echo "$t" >> "$tmp"
    fi
done
# /etc/cron.d/ — record filename + size (detects add/remove and content change),
# not `ls -la` output (parent-dir mtime drift produced false positives).
echo "--- /etc/cron.d ---" >> "$tmp"
find /etc/cron.d -mindepth 1 -type f -printf '%f %s\n' 2>/dev/null | LC_ALL=C sort >> "$tmp" || true
check_baseline "crontabs.txt" "$tmp"
rm -f "$tmp"

# 10. OpenClaw cron jobs (normalized — captures Felix self-modifications like #273)
# Sorted by name and limited to stable security-relevant fields so cosmetic
# diffs (lastDelivered, nextRunAtMs, etc.) don't trigger false positives.
log "Scanning OpenClaw cron config..."
tmp=$(mktemp)
openclaw cron list --json 2>/dev/null \
    | jq -S '[.jobs[] | {name, enabled, agentId, schedule, timeoutSeconds: .payload.timeoutSeconds, deliveryMode: .delivery.mode, failureAlert: (.failureAlert // null)}] | sort_by(.name)' \
        > "$tmp" 2>/dev/null \
    || echo "no-openclaw" > "$tmp"
check_baseline "openclaw-cron.txt" "$tmp"
rm -f "$tmp"

# 11. OpenClaw main config (content-hash drift only — file may contain secrets)
log "Hashing OpenClaw config..."
tmp=$(mktemp)
sha256sum "$HOME/.openclaw/openclaw.json" 2>/dev/null | awk '{print $1}' > "$tmp" \
    || echo "no-openclaw-config" > "$tmp"
check_baseline "openclaw-config.txt" "$tmp"
rm -f "$tmp"

# --- Summary and notification ---
if [ "$ALERT" -eq 1 ]; then
    ALERT_COUNT=$(grep -c "^\[ALERT\]" "$ALERT_FILE" 2>/dev/null || echo "?")
    log "AUDIT COMPLETE: $ALERT_COUNT ALERT(S) FOUND"

    # Send push notification via the felix-alert bus shim.
    # Severity: always `error` (maps to ntfy Priority: high). The audit only
    # emits when count>0, i.e. real baseline drift or an IOC hit — every such
    # finding warrants the high-priority gradient, matching the old path which
    # always sent "Priority: high". No warn/error threshold branching: a single
    # drift is as security-relevant as many, so `error` is the floor for any
    # finding.
    ALERT_SUMMARY=$(head -5 "$ALERT_FILE" | sed 's/\[ALERT\] //' | tr '\n' ' ')
    SEVERITY="error"
    # Best-effort: the shim always exits 0, and `|| true` is belt-and-suspenders
    # so a notification failure can never fail the audit cron.
    "$ALERT_BUS" emit \
        --source "security-monitor/audit" \
        --severity "$SEVERITY" \
        --title "Felix Security Alert — office2" \
        --description "${ALERT_COUNT} alert(s) on ${DATE}" \
        --detail summary="${ALERT_SUMMARY}" \
        && log "felix-alert emit attempted (severity=$SEVERITY)" \
        || true

    echo "========================================="
    echo " SECURITY ALERTS DETECTED — $DATE"
    echo "========================================="
    cat "$ALERT_FILE"
    echo "========================================="
    exit 1
else
    log "AUDIT COMPLETE: All clear"
    rm -f "$ALERT_FILE"
    echo "Security audit $DATE: All clear"
    exit 0
fi
