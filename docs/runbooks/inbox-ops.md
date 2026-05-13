---
title: Inbox Processing Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# Inbox processing operations

## Overview

The felix-admin-capture agent processes Kent's Obsidian inbox autonomously.
It runs on office2 via OpenClaw, 3 times daily on a cron schedule. It reads
unprocessed notes from `01-Inbox/`, classifies content, routes it to the
correct vault locations, creates Vikunja tasks for action items, and writes
a processing log.

## Agent management

- **Agent name**: `felix-admin-capture`
- **Workspace on office2**: `/data/services/openclaw/inbox-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-capture/`
- **Model**: `anthropic/claude-sonnet-4-6`

### Workspace files

| File | Purpose |
|------|---------|
| SOUL.md | Kent-voice authoring identity |
| USER.md | Kent's context |
| IDENTITY.md | Agent identity metadata |
| TOOLS.md | Vault paths, Vikunja API reference |
| AGENTS.md | Standing orders: full processing workflow |

### Update workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/inbox-agent/$f" \
    < scripts/openclaw/agents/felix-admin-capture/$f
done
```

### Verify agent

```bash
ssh office2-claude "openclaw agents list"
```

Expected: `felix-admin-capture` with workspace `/data/services/openclaw/inbox-agent`.

## Schedule

Three cron jobs run the agent in isolated sessions:

| Job | Schedule (UTC) | Local time (EDT) |
|-----|---------------|-----------------|
| inbox-morning | `0 11 * * *` | 7:00 AM ET |
| inbox-midday | `0 16 * * *` | 12:00 PM ET |
| inbox-evening | `0 22 * * *` | 6:00 PM ET |

All jobs have a 5-minute (300s) timeout and use `--no-deliver` (no WhatsApp
notification on completion).

### View jobs

```bash
ssh office2-claude "openclaw cron list"
```

### Manual trigger

```bash
ssh office2-claude "openclaw cron run <job-uuid>"
```

Get the UUID from `openclaw cron list`. Cron run by name is not currently
supported.

### Direct agent invocation

```bash
ssh office2-claude "openclaw agent --agent felix-admin-capture \
  --message 'Process the inbox now.' --json --timeout 300"
```

## Processing log

- **Location**: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- **Multiple runs per day**: Appended with time-stamped section headers

### Check recent logs

```bash
ssh office2-claude "ls -lt /home/kgale/second-brain/agents/logs/ | head"
```

### What to look for

- **Files processed**: Count and descriptions
- **Tasks created**: Vikunja tasks with project, label, and source
- **Goals routed**: Felix declarations added to Goals-MOC.md
- **Items flagged**: Errors, needs-review items, potential-goals

## WhatsApp trigger

Send "process my inbox" (or natural variations) via WhatsApp. The main agent
delegates to felix-admin-capture and responds with a processing summary.

**Known limitation**: The nested agent call requires sufficient timeout. If
the main agent times out before felix-admin-capture finishes, the processing
still completes but the summary is not relayed back.

## Cowork fallback

When the office2 agent is down or misconfigured, processing can be done
manually using the original Cowork skills on Mac.

### Fallback procedure

1. Open a Claude session on Mac
2. Invoke the inbox-processor skill manually:
   ```
   Use the inbox-processor skill to process my inbox
   ```
3. The skill reads from `~/second-brain/notes/01-Inbox/`
4. Results are written directly to the vault (syncs to office2 via Obsidian Sync)

### Skill locations (Mac)

- `~/second-brain/.claude/skills/inbox-processor/SKILL.md`
- `~/second-brain/.claude/skills/kent-voice/SKILL.md`
- `~/second-brain/.claude/skills/vault-writer/SKILL.md`

**Warning**: Do not run both the office2 agent and Cowork fallback
simultaneously on the same inbox files. This will cause duplicate processing.

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No processing logs | `ssh office2-claude "openclaw cron list"` | Verify cron jobs exist and are enabled |
| Vault not accessible | `ssh office2-claude "ls /home/kgale/second-brain/notes/01-Inbox/"` | Check Obsidian Sync: `ssh office2-kgale "systemctl status obsidian-sync"` |
| Vikunja tasks not created | Check processing log error section | Verify vikunja_api skill and API token |
| Agent not responding | `ssh office2-claude "openclaw agents list"` | Restart gateway: `ssh office2-claude "systemctl --user restart openclaw-gateway"` |
| Session lock error | Check for stale `.lock` files | `ssh office2-claude "rm -f ~/.openclaw/agents/felix-admin-capture/sessions/*.lock"` |
| Timeout on large inbox | Processing log shows partial results | Increase `--timeout-seconds` on cron jobs or process manually |
| Note mistakenly skipped (#185 dedup) | `ssh office2-claude "cat ~/second-brain/agents/state/inbox-routing.jsonl \| jq -c 'select(.filename==\"<filename>\")'"` | Edit the routing log to remove the offending entry (or move the note to a new filename). Next tick will re-route normally. |
| "Inbox quality" issue filed | See §"When you see an 'Inbox quality' issue" below | Fix frontmatter in each affected note per the issue body |

## When you see an "Inbox quality" issue (#185)

The `felix-admin-capture` agent files a batched GitHub issue with title
prefix `Inbox quality:` when one or more inbox notes have unparseable
frontmatter. The agent halts routing for those notes (rather than misfiling
them as generic content issues) and surfaces the problem through the
issue + an Obsidian callout marker on each affected note.

To resolve:

1. **Open the GitHub issue.** Each row in the body's table identifies an
   affected note by filename and the specific malformation reason.
2. **Open each affected note in Obsidian.** The agent has injected a
   `> [!error] felix-capture:` callout at the top of the note's body
   showing the same error and the issue number.
3. **Fix the malformation.** Common cases:
   - **Leading whitespace before `---`** — delete blank lines / spaces /
     BOM before the opening `---` fence.
   - **UTF-8 BOM** — re-save the file in UTF-8 without BOM. (Obsidian
     uses no-BOM UTF-8 by default; this usually comes from
     paste-from-Word or a misconfigured editor.)
   - **Missing closing `---`** — add the closing fence.
   - **Invalid YAML** — fix the syntax (mismatched quotes, unescaped
     colons in values, tab indentation).
4. **Save.** The next cron tick will:
   - Re-classify the note as well-formed
   - Auto-strip the callout marker as part of routing
   - Route the note normally and append to the routing log
5. **Close the GitHub issue manually** once all listed notes are fixed
   (or moved out of `01-Inbox/`).

   **Important — how dedup interacts with new failures**: while an
   "Inbox quality:" issue is OPEN, subsequent ticks that encounter new
   parse failures do NOT file a new issue and do NOT update the open
   issue's body. Newly-failing notes still get a callout marker
   injected pointing at the existing open issue, so they ARE
   discoverable by opening the inbox in Obsidian — but they will not
   appear in the issue's table.

   This means: keep the issue closed promptly. A new "Inbox quality:"
   issue is only filed by the next tick AFTER the previous one is
   closed. If you suspect new parse failures while an issue is open,
   check the inbox directly for notes with the felix-capture callout
   marker rather than relying on the issue body to enumerate them.

### Routing log

The agent uses an append-only JSONL file at
`~/second-brain/agents/state/inbox-routing.jsonl` (on office2, owned by
the `claude` user) as the load-bearing dedup substrate. Each line records
one successful route: `{filename, issue_number, vikunja_task_id, routed_at,
note_excerpt}`. The classifier reads this file on every cron tick and
filters already-routed filenames out of the agent's input.

If a note is mistakenly skipped, inspect this file:

```bash
ssh office2-claude "cat ~/second-brain/agents/state/inbox-routing.jsonl | jq -c"
```

To force re-routing of one filename, edit out the offending entry (or
just delete the whole file to reset state — the routing log is recreated
on the next route). The file is backed up by the nightly Restic job; it
is NOT git-tracked.

## Privacy boundary

**Absolute rule**: `04-Growth/_private/` is never read, processed, routed to,
referenced, or logged. This is enforced in SOUL.md, AGENTS.md, and TOOLS.md.
There are no exceptions.

> Path renumbered from `02-Growth/_private/` in mission 026 (#152). The
> constitutional boundary itself is unchanged — only the parent folder
> ordinal moved.

## Inbox-Processed destination

After mission 026 (#152), processed items are eligible to be moved into
`01-Inbox`'s sibling folder `02-Inbox-Processed/`. The actual move logic
ships in the inbox pre-scan helper (mission #149); this runbook is the
current consumer reference until that mission lands.
