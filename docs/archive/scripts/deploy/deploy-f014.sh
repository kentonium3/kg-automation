#!/usr/bin/env bash
set -euo pipefail

# F014: Deploy Felix Core Digest to office2
#
# Prerequisites:
#   - WP01-WP05 merged to main
#   - SSH access to office2-claude configured
#   - Python 3 installed on office2
#
# Usage: ./scripts/deploy/deploy-f014.sh

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "=== F014: Felix Core Digest Deployment ==="

echo ""
echo "--- Stage 1: Deploy observation module ---"
for f in log_action.py summarize.py config.py __init__.py; do
  scp "$REPO_ROOT/scripts/openclaw/observation/$f" \
    "office2-claude:~/repos/kg-automation/scripts/openclaw/observation/$f"
done
echo "  Observation module deployed"

echo ""
echo "--- Stage 2: Deploy agent-registry.json ---"
scp "$REPO_ROOT/docs/constitution/agent-registry.json" \
  office2-claude:~/repos/kg-automation/docs/constitution/agent-registry.json
echo "  Registry deployed"

echo ""
echo "--- Stage 3: Deploy AGENTS.md files ---"
# Workspace names don't follow a uniform pattern — use explicit mapping
declare -A WORKSPACES=(
  [felix-admin-capture]="inbox-agent"
  [felix-admin-habits]="habits-agent"
  [felix-admin-tasker]="tasker-agent"
)
for agent in "${!WORKSPACES[@]}"; do
  ws="${WORKSPACES[$agent]}"
  ssh office2-claude "mkdir -p /data/services/openclaw/$ws"
  scp "$REPO_ROOT/scripts/openclaw/agents/$agent/AGENTS.md" \
    "office2-claude:/data/services/openclaw/$ws/AGENTS.md"
done
echo "  Agent workspaces updated"

echo ""
echo "--- Stage 4: Deploy systemd timer/service ---"
ssh office2-claude "mkdir -p ~/.config/systemd/user"
scp "$REPO_ROOT/scripts/office2/felix-core-digest.timer" \
  office2-claude:~/.config/systemd/user/felix-core-digest.timer
scp "$REPO_ROOT/scripts/office2/felix-core-digest.service" \
  office2-claude:~/.config/systemd/user/felix-core-digest.service
echo "  Systemd units deployed"

echo ""
echo "--- Stage 5: Enable and start timer ---"
ssh office2-claude "systemctl --user daemon-reload && \
  systemctl --user enable felix-core-digest.timer && \
  systemctl --user start felix-core-digest.timer"
echo "  Timer enabled and started"

echo ""
echo "--- Stage 6: Update second-brain .gitignore ---"
ssh office2-claude 'grep -q "^agents/logs/" ~/second-brain/.gitignore 2>/dev/null || \
  echo "agents/logs/" >> ~/second-brain/.gitignore'
echo "  Gitignore updated (idempotent)"

echo ""
echo "--- Stage 7: Create log directories ---"
ssh office2-claude "mkdir -p ~/second-brain/agents/logs/{felix-admin-capture,felix-admin-habits,felix-admin-tasker}"
echo "  Log directories created"

echo ""
echo "--- Stage 8: Validation ---"
echo "  Checking timer status..."
ssh office2-claude "systemctl --user status felix-core-digest.timer --no-pager" || true
echo ""
echo "  Running summarize.py --dry-run..."
ssh office2-claude "python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py --dry-run" || true

echo ""
echo "=== F014: Deployment complete ==="
echo ""
echo "Manual verification checklist:"
echo "  [ ] Timer active: ssh office2-claude 'systemctl --user list-timers'"
echo "  [ ] Dry run clean: ssh office2-claude 'python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py --dry-run'"
echo "  [ ] Test log write:"
echo "      ssh office2-claude 'python3 ~/repos/kg-automation/scripts/openclaw/observation/log_action.py \\"
echo "        --agent felix-admin-capture --category routine --action test_entry --target test --outcome completed'"
echo "  [ ] Verify JSONL: ssh office2-claude 'cat ~/second-brain/agents/logs/felix-admin-capture/$(date +%Y-%m-%d).jsonl'"
echo "  [ ] Wait 15 min, check digest: ssh office2-claude 'ls ~/second-brain/notes/Agent-Logs/'"
echo "  [ ] Verify in Obsidian on Mac"
echo "  [ ] Gitignore: ssh office2-claude 'grep agents/logs ~/second-brain/.gitignore'"
echo ""
echo "  [ ] Linger enabled (required for user timers when not logged in):"
echo "      ssh office2-kgale 'sudo loginctl enable-linger claude'"
