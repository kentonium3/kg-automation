#!/bin/bash
# Security audit script for office2
# Runs daily via cron at 3AM, alerts on changes from baseline
# Sends push notification via ntfy.sh when alerts are detected
#
# Setup:
#   1. NTFY_TOPIC is set below
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
ALERT=0

# ntfy topic — keep this private
NTFY_TOPIC="felix-office2-k9x4m2"

# --- Helpers ---
log()   { echo "[$(date '+%H:%M:%S')] $1" >> "$LOGFILE"; }
alert() { echo "[ALERT] $1" | tee -a "$ALERT_FILE" >> "$LOGFILE"; ALERT=1; }

check_baseline() {
    local name="$1" current="$2"
    if [ -f "$BASELINE_DIR/$name" ]; then
        local d
        d=$(diff "$BASELINE_DIR/$name" "$current" 2>/dev/null || true)
        if [ -n "$d" ]; then
            alert "$name changed since baseline: $d"
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
ss -tlnp 2>/dev/null | tail -n +2 | awk '{print $4}' \
    | grep -vE '^127\.0\.0\.1:[3-9][0-9]{4}$' \
    | grep -vE '^127\.0\.0\.1:[0-9]{6}$' \
    | grep -vE '^\[::1\]:[3-9][0-9]{4}$' \
    | grep -vE '^\[::1\]:[0-9]{6}$' \
    | sort > "$tmp"
check_baseline "listening-ports.txt" "$tmp"
rm -f "$tmp"

# 6. Systemd enabled services
log "Scanning systemd services..."
tmp=$(mktemp)
systemctl list-unit-files --type=service --state=enabled --no-pager 2>/dev/null \
    | grep enabled | awk '{print $1}' | sort > "$tmp"
check_baseline "enabled-services.txt" "$tmp"
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
ls -la /etc/cron.d/ >> "$tmp" 2>/dev/null || true
check_baseline "crontabs.txt" "$tmp"
rm -f "$tmp"

# --- Summary and notification ---
if [ "$ALERT" -eq 1 ]; then
    ALERT_COUNT=$(grep -c "^\[ALERT\]" "$ALERT_FILE" 2>/dev/null || echo "?")
    log "AUDIT COMPLETE: $ALERT_COUNT ALERT(S) FOUND"

    # Send ntfy push notification
    if [ -n "$NTFY_TOPIC" ] && [ "$NTFY_TOPIC" != "felix-office2-sec-CHANGEME" ]; then
        ALERT_SUMMARY=$(head -5 "$ALERT_FILE" | sed 's/\[ALERT\] //' | tr '\n' ' ')
        curl -s --max-time 10 -X POST \
            -H "Title: Felix Security Alert — office2" \
            -H "Priority: high" \
            -H "Tags: warning,rotating_light" \
            -d "${ALERT_COUNT} alert(s) on ${DATE}: ${ALERT_SUMMARY}" \
            "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null 2>&1 \
            && log "ntfy notification sent" \
            || log "ntfy notification failed (non-fatal, check connectivity)"
    else
        log "ntfy: skipped (NTFY_TOPIC not configured)"
    fi

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
