# Model Assignment Baseline

**Date**: 2026-04-09T17:25Z
**Source**: `/home/claude/.openclaw/openclaw.json` on office2
**Backup**: `/home/claude/.openclaw/openclaw.json.backup.2026-04-09`
**Restic backup**: Confirmed 2026-04-09 04:00 UTC (completed successfully)

## Global Default

```json
"agents": {
  "defaults": {
    "model": {
      "primary": "anthropic/claude-sonnet-4-6"
    },
    "models": {
      "anthropic/claude-sonnet-4-6": {}
    }
  }
}
```

## Per-Agent Model Assignments

| Agent ID | Explicit Model | Effective Model | Notes |
|---|---|---|---|
| `main` | *(none — inherits default)* | `anthropic/claude-sonnet-4-6` | Orchestrator. No `model` field in config — relies on global default. |
| `felix-admin-capture` | `anthropic/claude-sonnet-4-6` | `anthropic/claude-sonnet-4-6` | Inbox classification. 8 runs/day. |
| `felix-admin-habits` | `anthropic/claude-sonnet-4-6` | `anthropic/claude-sonnet-4-6` | Daily check-in + weekly review. |
| `felix-admin-escalation` | `anthropic/claude-sonnet-4-6` | `anthropic/claude-sonnet-4-6` | Overdue task detection. |
| `felix-admin-tasker` | `anthropic/claude-sonnet-4-6` | `anthropic/claude-sonnet-4-6` | Task enrichment. |

## Key Observations

- All 5 agents use the same model (Sonnet 4-6)
- `main` has no explicit `model` field — it inherits from `agents.defaults.model.primary`
- When the global default is changed to Haiku (WP04), `main` will need an explicit `model` field added to stay on Sonnet
- The `agents.defaults.models` map only lists Sonnet — Haiku will need to be added

## Cost Baseline

- ~$4/day, ~$115/month projected (all Sonnet)
- ~2.5M tokens/day across all agents
- Spend limit: $100 (raised from $35 on 2026-04-09)
