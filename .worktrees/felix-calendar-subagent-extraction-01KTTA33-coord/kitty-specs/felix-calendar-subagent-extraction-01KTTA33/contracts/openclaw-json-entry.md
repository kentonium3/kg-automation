# Contract: openclaw.json entry for felix-admin-calendar

**Owner**: deploy script `scripts/deploy/deploy-felix-admin-calendar.sh`
**Mutation surface**: `/home/claude/.openclaw/openclaw.json` on office2 (in-place via SSH+jq)

## Exact entry to insert

```json
{
  "id": "felix-admin-calendar",
  "name": "felix-admin-calendar",
  "workspace": "/data/services/openclaw/calendar-agent",
  "agentDir": "/home/claude/.openclaw/agents/felix-admin-calendar/agent",
  "model": "anthropic/claude-haiku-4-5"
}
```

## Insertion procedure

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
ssh office2-claude "
  set -euo pipefail
  cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-${TS}
  jq '.agents.list += [{
        \"id\": \"felix-admin-calendar\",
        \"name\": \"felix-admin-calendar\",
        \"workspace\": \"/data/services/openclaw/calendar-agent\",
        \"agentDir\": \"/home/claude/.openclaw/agents/felix-admin-calendar/agent\",
        \"model\": \"anthropic/claude-haiku-4-5\"
      }]' ~/.openclaw/openclaw.json.bak-${TS} > ~/.openclaw/openclaw.json.new
  jq . ~/.openclaw/openclaw.json.new > /dev/null  # parse validation
  mv ~/.openclaw/openclaw.json.new ~/.openclaw/openclaw.json
  jq '.agents.list[] | select(.id == \"felix-admin-calendar\")' ~/.openclaw/openclaw.json
"
```

## Post-edit validation (deploy script + pytest)

The deploy script's pytest invocation runs `scripts/openclaw/agents/tests/test_openclaw_config_schema.py` against a fresh SSH copy of `~/.openclaw/openclaw.json`. Tests:

- `test_openclaw_json_parses()` — `jq .` exits 0
- `test_felix_admin_calendar_entry_present()` — `select(.id == "felix-admin-calendar")` returns 1 entry
- `test_felix_admin_calendar_entry_complete()` — entry has all 5 required keys
- `test_workspace_path_pattern()` — workspace matches `^/data/services/openclaw/[a-z-]+-agent$`
- `test_agentdir_path_pattern()` — agentDir matches `^/home/claude/\.openclaw/agents/[a-z-]+/agent$`
- `test_model_known()` — model present in `agents.defaults.models` keys

## Idempotency

If the deploy script is re-run after a partial failure:

- The pre-existing `~/.openclaw/openclaw.json.bak-<old-ts>` files are left in place (operator cleans up after success)
- The jq step uses `+=` which would duplicate the entry. Therefore:
  - Pre-flight check: `jq '.agents.list[] | select(.id == "felix-admin-calendar")' ~/.openclaw/openclaw.json` → if entry already present, SKIP this step entirely (mark as already-deployed) and continue to verify+restart

## Rollback

```bash
ssh office2-claude "cp ~/.openclaw/openclaw.json.bak-${TS} ~/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway.service"
```
