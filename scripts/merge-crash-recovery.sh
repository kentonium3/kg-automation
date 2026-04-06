#!/usr/bin/env bash
# merge-crash-recovery.sh — Complete post-crash cleanup after a VS Code crash
# during spec-kitty merge.
#
# The crash consistently leaves this state:
#   - Git merge commits: completed
#   - Status files (JSONL, snapshot, frontmatter): written but uncommitted
#   - Worktree removal: usually completed
#   - Branch deletion: sometimes incomplete
#   - Push to origin: not performed
#
# Usage: ./scripts/merge-crash-recovery.sh <feature-slug>
# Example: ./scripts/merge-crash-recovery.sh 009-daily-habit-checkin
#
# CAPTURING THE CRASH (for diagnosing which command triggers it):
#
# Before running the merge, wrap the Claude Code session in `script -F` to
# stream all terminal output to a file in real-time. The -F flag flushes on
# every write, so when VS Code crashes (SIGTERM, exit code 15) the log is
# already on disk up to the last line printed.
#
#   mkdir -p ~/merge-captures
#   script -F ~/merge-captures/f0XX-merge-$(date +%Y%m%d).log
#   claude                    # start Claude Code inside the script session
#   # ... proceed with merge ...
#   # If VS Code crashes, the log survives at ~/merge-captures/
#   # After recovery, if the script session survived, type 'exit' to close it
#
# Place the log file outside the repo to avoid adding FSEvents load to the
# already-saturated event queue during worktree removal.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <feature-slug>"
    echo "Example: $0 009-daily-habit-checkin"
    exit 1
fi

FEATURE="$1"
SPEC_DIR="kitty-specs/${FEATURE}"

# Verify we're in the repo root
if [[ ! -d ".git" ]]; then
    echo "Error: Run this from the repository root."
    exit 1
fi

# Verify the feature spec directory exists
if [[ ! -d "${SPEC_DIR}" ]]; then
    echo "Error: Feature directory '${SPEC_DIR}' not found."
    exit 1
fi

echo "=== Merge Crash Recovery for ${FEATURE} ==="
echo ""

# Step 1: Check for stale worktrees
echo "--- Step 1: Checking worktrees ---"
STALE_WORKTREES=$(git worktree list | grep "${FEATURE}" || true)
if [[ -n "${STALE_WORKTREES}" ]]; then
    echo "Found stale worktrees:"
    echo "${STALE_WORKTREES}"
    echo ""
    while IFS= read -r line; do
        WT_PATH=$(echo "$line" | awk '{print $1}')
        echo "Removing: ${WT_PATH}"
        git worktree remove "${WT_PATH}" --force
    done <<< "${STALE_WORKTREES}"
    echo "Worktrees removed."
else
    echo "No stale worktrees found."
fi
echo ""

# Step 2: Check for stale branches
echo "--- Step 2: Checking branches ---"
STALE_BRANCHES=$(git branch | grep "${FEATURE}-WP" || true)
if [[ -n "${STALE_BRANCHES}" ]]; then
    echo "Found stale branches:"
    echo "${STALE_BRANCHES}"
    echo ""
    while IFS= read -r branch; do
        branch=$(echo "$branch" | xargs)  # trim whitespace
        echo "Deleting: ${branch}"
        git branch -d "${branch}" 2>/dev/null || git branch -D "${branch}"
    done <<< "${STALE_BRANCHES}"
    echo "Branches deleted."
else
    echo "No stale branches found."
fi
echo ""

# Step 3: Commit uncommitted status files
echo "--- Step 3: Checking for uncommitted status files ---"
STATUS_FILES=$(git status --porcelain -- "${SPEC_DIR}/" || true)
if [[ -n "${STATUS_FILES}" ]]; then
    echo "Found uncommitted changes:"
    echo "${STATUS_FILES}"
    echo ""
    git add "${SPEC_DIR}/"
    git commit -m "chore: commit ${FEATURE} post-merge status updates after VS Code crash"
    echo "Status files committed."
else
    echo "No uncommitted status files."
fi
echo ""

# Step 4: Push to origin
echo "--- Step 4: Pushing to origin ---"
UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null || true)
if [[ -n "${UNPUSHED}" ]]; then
    echo "Unpushed commits:"
    echo "${UNPUSHED}"
    echo ""
    git push
    echo "Pushed."
else
    echo "Already up to date with origin."
fi
echo ""

echo "=== Recovery complete ==="
