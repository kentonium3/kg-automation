# Quickstart — Verify Harden Inbox Capture

Deploy + verification steps (WP04). Commands for office2 use `ssh office2-claude`.
The `claude` user has no sudo; the openclaw.json edit + gateway restart + rebaseline
are `claude`-owned (no sudo) except where noted.

## Pre-merge (on the feature branch / in CI)

1. **Checker passes fleet-wide** (SC-001, SC-008):
   ```bash
   python3 -m scripts.openclaw.agents.env_assumptions
   # → "ok: no env-assumption findings"
   ```
2. **No stale form remains** in active prompts:
   ```bash
   grep -rn 'PYTHONPATH:?' scripts/openclaw/agents/*/AGENTS.md scripts/openclaw/agents/*/AGENTS.md.tmpl
   # → no matches (felix-doc-auditor excluded/suspended)
   ```
3. **Tests green**:
   ```bash
   pytest scripts/openclaw/agents/tests/ -q
   ```

## Deploy (after feat/harden-inbox-capture → main)

4. **Prompts auto-deploy** via the agent-prompt-sync timer (~5 min). Confirm **all six**
   active agents synced (Codex MED-6), not just capture:
   ```bash
   ssh office2-claude 'for pair in \
     "inbox-agent:felix-admin-capture" "escalation-agent:felix-admin-escalation" \
     "habits-agent:felix-admin-habits" "calendar-agent:felix-admin-calendar" \
     "tasker-agent:felix-admin-tasker" "main:main"; do \
       dd=${pair%%:*}; slug=${pair##*:}; \
       d=$(md5sum /data/services/openclaw/$dd/AGENTS.md 2>/dev/null | cut -d" " -f1); \
       r=$(md5sum /home/claude/kg-automation/scripts/openclaw/agents/$slug/AGENTS.md 2>/dev/null | cut -d" " -f1); \
       [ "$d" = "$r" ] && echo "OK $slug" || echo "DRIFT $slug ($dd)"; done'
   # deploy-dir names: verify each against service-inventory.json workspace field first
   ```
   Also check the prompt-sync log for copy actions/errors this cycle:
   ```bash
   ssh office2-claude 'tail -20 /data/services/openclaw/deploy/agent-prompt-sync.jsonl'
   ```
5. **Model flip** (manual, out-of-band): back up + edit `/home/claude/.openclaw/openclaw.json`,
   set the `felix-admin-capture` agent `model` to `anthropic/claude-sonnet-4-6`
   (read-modify-write; change only that one field), then validate JSON:
   ```bash
   ssh office2-claude 'cp /home/claude/.openclaw/openclaw.json /home/claude/.openclaw/openclaw.json.bak-$(date +%s) && jq -e ".agents.list[] | select(.id==\"felix-admin-capture\") | .model" /home/claude/.openclaw/openclaw.json'
   # → "anthropic/claude-sonnet-4-6"   (only after you make the edit)
   ```
6. **Restart the gateway** so it reloads config:
   ```bash
   ssh office2-claude 'systemctl --user restart openclaw-gateway.service && sleep 5 && systemctl --user is-active openclaw-gateway.service'
   ```
7. **Confirm the model is in effect BEFORE rebaselining** (Codex LOW-7 — don't bless a
   bad edit into the baseline) (SC-002):
   ```bash
   ssh office2-claude 'openclaw cron runs --id cc9977fa-e451-47e7-9a18-eb6d85775f26 --limit 1'
   # → "model":"claude-sonnet-4-6" on the newest capture run
   ```
8. **Manual rebaseline** (openclaw.json is a monitored audited surface), only after step 7:
   ```bash
   ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
   ```
   Record `Rebaseline: completed at <ts>` on the merge (SC-007).

## Behavioral verification
9. **Real-note routing, no hallucination** (SC-003): drop a test note in
   `01-Inbox`, trigger a capture run on-demand, confirm it routes correctly with no
   "not implemented/deployed" text and no exit-127/ModuleNotFoundError in the trajectory.
10. **Empty-inbox IDLE ×5** (SC-004, NFR-002): with an empty inbox, trigger 5 runs;
    each emits exactly `[felix-admin-capture]: IDLE`.
11. **Clean delivery ×5** (SC-005, NFR-003): 5 successful runs deliver their WhatsApp
    summary with no `🛠️ … failed` warning.
12. **Calendar clarification non-regression** (SC-006): a note implying a timed event
    with no time triggers the clarification question; Kent's reply routes it.
13. **Fleet non-regression**: confirm escalation-daily + habits-weekly next runs no
    longer surface the `🛠️ … failed` class.

## Rollback

- Prompts: revert the merge on main; prompt-sync restores prior AGENTS.md.
- Model: set the openclaw.json `model` back to `anthropic/claude-haiku-4-5`, restart
  gateway, rebaseline.
