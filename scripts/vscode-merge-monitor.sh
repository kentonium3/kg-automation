#!/usr/bin/env bash
# vscode-merge-monitor.sh — Run in an EXTERNAL terminal before spec-kitty merge
# Captures diagnostics to help identify what triggers VS Code crashes
# during worktree removal.
#
# Usage: ./scripts/vscode-merge-monitor.sh
# Stop: Ctrl+C (cleans up background processes)
set -euo pipefail

LOGDIR="/tmp/vscode-merge-diagnostics-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOGDIR"

echo "=== VS Code Merge Monitor ==="
echo "Log directory: $LOGDIR"
echo ""

# Find the active VS Code log session
VSCODE_LOGS="$HOME/Library/Application Support/Code/logs"
LATEST_SESSION=$(ls -td "$VSCODE_LOGS"/*/ 2>/dev/null | head -1)

if [ -z "$LATEST_SESSION" ]; then
    echo "WARNING: No VS Code log session found. Is VS Code running?"
else
    echo "Active VS Code session: $(basename "$LATEST_SESSION")"
fi

# Cleanup on exit
PIDS=()
cleanup() {
    echo ""
    echo "--- Stopping monitors ---"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo ""
    echo "=== Diagnostics saved to: $LOGDIR ==="
    echo "Files:"
    ls -la "$LOGDIR/"
    echo ""
    echo "To review after a crash:"
    echo "  cat $LOGDIR/system-errors.log     # macOS-level errors"
    echo "  cat $LOGDIR/git-extension.log     # Git extension activity"
    echo "  cat $LOGDIR/process-count.log     # Code Helper process count"
    echo "  ls $LOGDIR/crash-reports/         # macOS crash reports (if any)"
}
trap cleanup EXIT

# Monitor 1: macOS system log for VS Code/Electron errors
echo "Starting: macOS system log monitor..."
log stream --predicate 'process CONTAINS "Code" OR process CONTAINS "Electron"' \
    --level error \
    > "$LOGDIR/system-errors.log" 2>&1 &
PIDS+=($!)

# Monitor 2: VS Code Git extension log
if [ -n "$LATEST_SESSION" ]; then
    GIT_LOG="${LATEST_SESSION}window1/exthost/vscode.git/Git.log"
    if [ -f "$GIT_LOG" ]; then
        echo "Starting: Git extension log tail..."
        tail -f "$GIT_LOG" > "$LOGDIR/git-extension.log" 2>&1 &
        PIDS+=($!)
    else
        echo "WARNING: Git.log not found at $GIT_LOG"
    fi
fi

# Monitor 3: File watcher log
if [ -n "$LATEST_SESSION" ]; then
    FW_LOG="${LATEST_SESSION}window1/fileWatcher.log"
    if [ -f "$FW_LOG" ]; then
        echo "Starting: File watcher log tail..."
        tail -f "$FW_LOG" > "$LOGDIR/file-watcher.log" 2>&1 &
        PIDS+=($!)
    fi
fi

# Monitor 4: Crash report watcher (polls every 2s for new files)
mkdir -p "$LOGDIR/crash-reports"
echo "Starting: Crash report watcher..."
(
    # Snapshot existing crash reports
    BEFORE=$(mktemp)
    for dir in "$HOME/Library/Logs/DiagReports" "/Library/Logs/DiagReports"; do
        ls "$dir" 2>/dev/null >> "$BEFORE" || true
    done
    while true; do
        AFTER=$(mktemp)
        for dir in "$HOME/Library/Logs/DiagReports" "/Library/Logs/DiagReports"; do
            ls "$dir" 2>/dev/null >> "$AFTER" || true
        done
        NEW=$(comm -13 <(sort "$BEFORE") <(sort "$AFTER"))
        if [ -n "$NEW" ]; then
            echo "$NEW" | while read -r file; do
                echo "$(date +%H:%M:%S) CRASH REPORT: $file" | tee -a "$LOGDIR/crash-events.log"
                for dir in "$HOME/Library/Logs/DiagReports" "/Library/Logs/DiagReports"; do
                    cp "$dir/$file" "$LOGDIR/crash-reports/" 2>/dev/null || true
                done
            done
            cp "$AFTER" "$BEFORE"
        fi
        rm -f "$AFTER"
        sleep 2
    done
) &
PIDS+=($!)

# Monitor 5: Code Helper process count (detect sudden drops)
echo "Starting: Process count monitor..."
(
    PREV_COUNT=0
    while true; do
        COUNT=$(pgrep -f "Code Helper" 2>/dev/null | wc -l | tr -d ' ')
        TIMESTAMP=$(date +%H:%M:%S)
        if [ "$COUNT" != "$PREV_COUNT" ]; then
            echo "$TIMESTAMP  Code Helper processes: $PREV_COUNT -> $COUNT" | tee -a "$LOGDIR/process-count.log"
            if [ "$COUNT" -lt "$PREV_COUNT" ] && [ "$PREV_COUNT" -gt 0 ]; then
                DROPPED=$((PREV_COUNT - COUNT))
                echo "$TIMESTAMP  *** $DROPPED Code Helper process(es) DIED ***" | tee -a "$LOGDIR/process-count.log"
            fi
        fi
        PREV_COUNT=$COUNT
        sleep 1
    done
) &
PIDS+=($!)

echo ""
echo "=== All monitors running ==="
echo "Now run the merge from VS Code integrated terminal."
echo "Press Ctrl+C here when done (or after crash)."
echo ""

# Keep running until interrupted
wait
