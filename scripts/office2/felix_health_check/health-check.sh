#!/bin/bash
# Service-level health checks for office2 (systemd units, Vikunja API, OpenClaw
# gateway). Run by scripts/office2/felix_health_check/run.py from the deployed
# checkout (felix-health-check.timer, #676), which combines this output with
# the coverage checks on felix-canary and restic-backup (#1063). Version-
# controlled since #1063; previously an untracked copy in ~/helper-scripts/.
# Output contract (do not change without run.py): ALL_HEALTHY, or
# FAILURES_DETECTED followed by one DOWN: line per failure.

FAILURES=""

# System-level services
for unit in obsidian-sync.service vikunja.service; do
    status=$(systemctl is-active $unit 2>/dev/null)
    if [ "$status" != "active" ]; then
        FAILURES="${FAILURES}DOWN: ${unit} (${status})\n"
    fi
done

# User-level services (claude)
# NOTE: is-active on a .timer reports "active" even for a timer stuck in the
# #1062 dormant state (active, elapsed), so this cannot see a timer that never
# fires again. Follow-up: kentonium3/kg-automation#1068.
for unit in openclaw-gateway.service felix-core-digest.timer; do
    status=$(systemctl --user is-active $unit 2>/dev/null)
    if [ "$status" != "active" ]; then
        FAILURES="${FAILURES}DOWN: ${unit} (${status})\n"
    fi
done

# Vikunja API health
HTTP=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://100.92.197.90:3456/api/v1/info 2>/dev/null)
if [ "$HTTP" != "200" ]; then
    FAILURES="${FAILURES}DOWN: vikunja-api (HTTP ${HTTP})\n"
fi

# OpenClaw gateway health
HTTP=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://127.0.0.1:18789/ 2>/dev/null)
if [ "$HTTP" = "000" ]; then
    FAILURES="${FAILURES}DOWN: openclaw-gateway-http (unreachable)\n"
fi

if [ -z "$FAILURES" ]; then
    echo "ALL_HEALTHY"
else
    echo "FAILURES_DETECTED"
    echo -e "$FAILURES"
fi
