#!/bin/bash
# Bidirectional git sync for second-brain non-vault content
# Runs every 15 minutes via systemd timer as kgale user
# Vault (notes/) is gitignored — only syncs agent configs, logs, assets

set -euo pipefail

REPO_DIR="/home/kgale/second-brain"
LOG_TAG="second-brain-sync"

log() { logger -t "$LOG_TAG" "$1"; }

cd "$REPO_DIR" || { log "ERROR: Cannot cd to $REPO_DIR"; exit 0; }

# Pull from origin (ff-only to avoid merge commits)
if ! git pull --ff-only origin main 2>&1; then
    log "WARNING: pull --ff-only failed (diverged history?), skipping sync cycle"
    exit 0
fi

# Stage any local changes (respects .gitignore — notes/ excluded)
git add -A

# Commit if there are staged changes
if ! git diff --cached --quiet; then
    git commit -m "chore: auto-sync second-brain from office2"
    if ! git push origin main 2>&1; then
        log "WARNING: push failed, will retry next cycle"
        exit 0
    fi
    log "Synced: committed and pushed local changes"
else
    log "No local changes to sync"
fi
