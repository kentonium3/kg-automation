# Inbox processing delegation — main agent patch

Appended to the main agent's AGENTS.md on office2 at
`/data/services/openclaw/data/AGENTS.md`.

## Content added

```markdown
## Inbox processing delegation

When Kent asks to "process my inbox", "check my inbox", "run inbox
processing", or any natural variation of processing Obsidian inbox captures:

1. Trigger the inbox processing agent by running:
   ```bash
   openclaw agent --agent felix-admin-capture --message "Process the inbox now. Read all unprocessed files in 00-Inbox/, classify and route content per your standing orders, create Vikunja tasks for action items and research requests, route valid goal declarations, and write the processing log." --json --timeout 300
   ```
2. Wait for the result
3. Read the latest processing log:
   ```bash
   ls -t /home/kgale/second-brain/agents/logs/inbox-processing-*.md | head -1
   ```
   Then read that file to get the summary.
4. Summarize the results back to Kent: files processed, tasks created,
   items flagged for review

Do NOT process the inbox yourself. The felix-admin-capture agent handles
this with specific standing orders and kent-voice encoding.
```

## Deployment note

- `openclaw cron run <name>` does not work from within an agent turn (requires
  UUID, and cron jobs belong to the felix-admin-capture agent, not main)
- Using `openclaw agent --agent felix-admin-capture` as the delegation method
- Main agent needs sufficient timeout (>300s) to wait for felix-admin-capture
