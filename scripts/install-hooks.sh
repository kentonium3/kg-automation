#!/usr/bin/env bash
# install-hooks.sh — install kg-automation's git hooks (idempotent).
#
# Currently installs:
#   - pre-commit: secret-scan staged content (see tooling/hooks/pre-commit
#     and #241).
#
# Usage: scripts/install-hooks.sh
#
# Idempotent: safe to re-run. Always overwrites the deployed hook with the
# in-repo source-of-truth.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC_DIR="$REPO_ROOT/tooling/hooks"
DST_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$SRC_DIR" ]; then
    echo "ERROR: hook source directory not found at $SRC_DIR" >&2
    exit 1
fi
if [ ! -d "$DST_DIR" ]; then
    echo "ERROR: .git/hooks not found at $DST_DIR — is this a git repo?" >&2
    exit 1
fi

installed=()
for src in "$SRC_DIR"/*; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    dst="$DST_DIR/$name"
    cp "$src" "$dst"
    chmod +x "$dst"
    installed+=("$name")
done

if [ ${#installed[@]} -eq 0 ]; then
    echo "No hooks to install (tooling/hooks/ is empty)."
    exit 0
fi

echo "Installed git hook(s) from tooling/hooks/ → .git/hooks/:"
for n in "${installed[@]}"; do
    echo "  - $n"
done
echo ""
echo "These hooks are local to this clone. Re-run this script after"
echo "cloning the repo on a new machine."
