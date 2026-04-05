---
title: Observation Intelligence Layer — Operations Runbook
doc_type: runbook
audience: both
status: approved
feature: F014
---

# Observation Intelligence Layer — Operations Runbook

This runbook covers the Felix Core Digest system: agent activity logging
via `log_action.py` and digest generation via `summarize.py`.

## Reading Digests in Obsidian

Digests appear in the vault under `Agent-Logs/`:

```
Agent-Logs/
├── overview.md                     ← consolidated daily summary
├── felix-admin-capture/
│   └── YYYY-MM-DD-log.md          ← per-agent daily detail
├── felix-admin-habits/
│   └── YYYY-MM-DD-log.md
└── felix-admin-tasker/
    └── YYYY-MM-DD-log.md
```

- **overview.md** regenerates on each summarize.py run for the current day
- Per-agent files show run-by-run detail with routine counts and elevated items
- Digests refresh within 15 minutes of agent activity (via Obsidian Sync)
- Retention: last 5 days visible; older files automatically deleted

## Accessing Raw JSONL on office2

Raw logs are at `~/second-brain/agents/logs/{agent-name}/YYYY-MM-DD.jsonl`:

```bash
# View today's logs for capture agent
ssh office2-claude 'cat ~/second-brain/agents/logs/felix-admin-capture/$(date +%Y-%m-%d).jsonl'

# Pretty-print with jq
ssh office2-claude 'jq . ~/second-brain/agents/logs/felix-admin-capture/$(date +%Y-%m-%d).jsonl'

# Filter by category
ssh office2-claude 'jq "select(.category == \"error\")" ~/second-brain/agents/logs/*/$(date +%Y-%m-%d).jsonl'
```

Each line is a single JSON object — one agent action. Fields: `ts`, `run_id`,
`agent`, `autonomy_level`, `category`, `action`, `target`, `outcome`, and
optionally `context` and `trace`.

## Changing Verbosity

Edit `docs/constitution/agent-registry.json` and set `log_verbosity`:

| Level | What's Written |
|---|---|
| `brief` | Required fields only (ts, run_id, agent, category, action, target, outcome) |
| `standard` | Required + context block (default for all agents) |
| `verbose` | Required + context + trace (debugging data) |

After editing:

```bash
scp docs/constitution/agent-registry.json office2-claude:~/repos/kg-automation/docs/constitution/
```

Use `verbose` only during active debugging. Return to `standard` when done.

## Verifying the Timer

```bash
# List all active timers
ssh office2-claude 'systemctl --user list-timers'

# Check felix-core-digest specifically
ssh office2-claude 'systemctl --user status felix-core-digest.timer'

# View recent execution logs
ssh office2-claude 'journalctl --user -u felix-core-digest.service --since today'
```

## Running Manually

```bash
# Dry run (shows what would be written, no file changes)
ssh office2-claude 'python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py --dry-run'

# Live run for today
ssh office2-claude 'python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py'

# Run for a specific date
ssh office2-claude 'python3 ~/repos/kg-automation/scripts/openclaw/observation/summarize.py --date 2026-04-03'
```

## Troubleshooting

### No digests appearing

1. Check timer is running: `systemctl --user status felix-core-digest.timer`
2. Check JSONL files exist: `ls ~/second-brain/agents/logs/*/$(date +%Y-%m-%d).jsonl`
3. Run summarize.py manually with `--dry-run` to see output
4. Check Obsidian Sync: `systemctl --user status obsidian-sync.service` (kgale user)

### Parse errors in journal

Malformed JSONL line in a log file. Check the raw log:

```bash
ssh office2-claude 'python3 -m json.tool ~/second-brain/agents/logs/{agent}/$(date +%Y-%m-%d).jsonl'
```

Fix the agent instruction if it's producing malformed output.

### Stale output (digest not updating)

The idempotency check compares JSONL file mtime vs. digest file mtime.
If the JSONL file hasn't been modified since the last digest was written,
summarize.py skips that agent. Force regeneration by touching the JSONL file:

```bash
ssh office2-claude 'touch ~/second-brain/agents/logs/{agent}/$(date +%Y-%m-%d).jsonl'
```

### Missing agent in digest

Verify the agent is in `agent-registry.json` and has `log_verbosity` set.
Unregistered agents are logged to stderr and skipped.

## Architecture Note

- `log_action.py` is a utility script, not a deployed service — no monitoring needed
- Agents call it via OpenClaw exec tool during their runs
- If an agent fails to call `log_action.py`, the action is simply not logged
  (no cascading failure — summarize.py processes whatever JSONL exists)
- `summarize.py` runs as `felix-core-digest.service` via systemd timer
- Registered in `service-inventory.json` as a scheduled service (not in AGENT-REGISTRY.md)
