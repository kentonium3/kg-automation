#!/usr/bin/env bash
# vault-snapshot.sh — Daily git snapshot of Obsidian vault
# Outbound-only: add, commit, push. NEVER pulls or resets.
# Obsidian Sync is authoritative for live state.
set -euo pipefail

VAULT_REPO="/home/kgale/second-brain"
cd "$VAULT_REPO"

# Check for changes
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "No changes to snapshot."
    exit 0
fi

# Stage all changes (respects .gitignore)
git add -A

# Commit with date-stamped message
git commit -m "vault snapshot $(date +%Y-%m-%d-%H%M)"

# Push to origin
git push origin main

echo "Snapshot complete: $(git log --oneline -1)"
