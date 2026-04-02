#!/usr/bin/env bash
set -euo pipefail

# F013: Deploy felix-admin-tasker (task intelligence agent) to office2
#
# Prerequisites:
#   - WP01-WP06 merged to main
#   - SSH access to office2-claude configured
#   - OpenClaw installed on office2
#
# Usage: ./scripts/deploy/deploy-f013.sh
#
# Deployment order (per plan.md):
#   1. Task-intelligence skill
#   2. Agent workspace (tasker)
#   3. Capture agent update (delegation)
#   4. Cron job

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "=== F013: Deploying task-intelligence skill ==="
ssh office2-claude "mkdir -p ~/.openclaw/skills/task-intelligence"
scp "$REPO_ROOT/scripts/openclaw/skills/task-intelligence/SKILL.md" \
  office2-claude:~/.openclaw/skills/task-intelligence/SKILL.md
echo "  Skill deployed"

echo ""
echo "=== F013: Deploying agent workspace ==="
ssh office2-claude "mkdir -p /data/services/openclaw/tasker-agent"
for f in AGENTS.md SOUL.md USER.md IDENTITY.md TOOLS.md; do
  scp "$REPO_ROOT/scripts/openclaw/agents/felix-admin-tasker/$f" \
    "office2-claude:/data/services/openclaw/tasker-agent/$f"
done
echo "  Agent workspace deployed"

echo ""
echo "=== F013: Updating felix-admin-capture ==="
scp "$REPO_ROOT/scripts/openclaw/agents/felix-admin-capture/AGENTS.md" \
  office2-claude:/data/services/openclaw/inbox-agent/AGENTS.md
echo "  Capture agent updated"

echo ""
echo "=== F013: Setting up cron ==="
ssh office2-claude 'openclaw cron add \
  --name "task-detection" \
  --cron "0 */4 * * *" \
  --agent felix-admin-tasker \
  --session isolated \
  --message '"'"'{"action": "detect_incomplete"}'"'"' \
  --no-deliver'
echo "  Cron job configured"

echo ""
echo "=== F013: Verifying cron ==="
ssh office2-claude "openclaw cron list"

echo ""
echo "=== F013: Running validation ==="
echo "Step 1: Test direct enrichment..."
ssh office2-claude 'openclaw agent --agent felix-admin-tasker \
  --message '"'"'{"action": "enrich_task", "raw_text": "F013 validation test task -- delete after testing", "source_reference": "test/f013-validation", "inferred_identity": "personal"}'"'"' \
  --json --timeout 120'

echo ""
echo "=== F013: Deployment complete ==="
echo ""
echo "Manual validation steps:"
echo "  1. Check WhatsApp for proposal message from Felix"
echo "  2. Reply 'yes' to confirm the test task"
echo "  3. Verify task appears in Vikunja Inbox with attributes"
echo "  4. Check action log:"
echo "     ssh office2-claude \"cat ~/second-brain/agents/logs/task-intelligence-$(date +%Y-%m-%d).md\""
echo "  5. Delete the test task from Vikunja"

# === End-to-End Verification Checklist ===
#
# [ ] Direct enrichment: Agent proposes and creates task (validation above)
# [ ] Detection polling: Run detect_incomplete, verify it finds flat Inbox tasks
#     ssh office2-claude 'openclaw agent --agent felix-admin-tasker \
#       --message '"'"'{"action": "detect_incomplete"}'"'"' --json --timeout 300'
# [ ] Retroactive enrichment: Run batch of 3
#     ssh office2-claude 'openclaw agent --agent felix-admin-tasker \
#       --message '"'"'{"action": "retroactive_enrichment", "batch_size": 3}'"'"' --json --timeout 300'
# [ ] Capture delegation: Wait for next inbox processing run, verify delegation
#     (check capture agent logs for delegation attempt)
# [ ] Fallback: Temporarily stop tasker agent, verify capture creates flat task
# [ ] Action logging: Verify all actions appear in log file
# [ ] Cron execution: Wait for next 4-hour cycle, verify detection runs
#
# NOTE: Some checks require waiting for scheduled events. Mark as verified
# over the first 24 hours of operation.
