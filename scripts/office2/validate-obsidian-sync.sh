#!/usr/bin/env bash
# validate-obsidian-sync.sh — Post-setup validation for F010/F011
# Run as kgale user on office2 after completing quickstart guide.
set -euo pipefail

PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
        ((PASS++))
    else
        echo "  FAIL: $desc"
        ((FAIL++))
    fi
}

echo "=== F010 Obsidian Sync Validation ==="
echo ""

echo "--- ob CLI ---"
check "ob CLI installed" which ob
check "ob is logged in" ob sync-list-remote

echo ""
echo "--- Vault sync ---"
check "Vault configured for sync" ob sync-list-local
check "Sync status OK" ob sync-status --path /home/kgale/second-brain/notes

echo ""
echo "--- Systemd services ---"
check "obsidian-sync.service active" systemctl --user is-active obsidian-sync
check "second-brain-sync.timer active" systemctl --user is-active second-brain-sync.timer
check "Linger enabled for kgale" bash -c '[ "$(loginctl show-user kgale -p Linger --value 2>/dev/null)" = "yes" ]'

echo ""
echo "--- Vault content ---"
check "Vault directory exists" test -d /home/kgale/second-brain/notes
check ".obsidian directory exists" test -d /home/kgale/second-brain/notes/.obsidian
check "Inbox directory has files" bash -c 'test -n "$(ls /home/kgale/second-brain/notes/00-Inbox/ 2>/dev/null)"'

echo ""
echo "--- Git sync ---"
check "Git repo exists" test -d /home/kgale/second-brain/.git
check "Git remote configured" git -C /home/kgale/second-brain remote get-url origin
check "Sync script executable" test -x /home/kgale/helper-scripts/second-brain-sync.sh

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "See docs/handbooks/obsidian-sync-ops.md for troubleshooting."
    exit 1
fi
