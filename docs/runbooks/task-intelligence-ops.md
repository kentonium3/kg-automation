---
title: "Task Intelligence Operations"
doc_type: runbook
audience: agent-executable
status: approved
feature: F013
last_validated: 2026-04-02
---

# Task Intelligence Operations

This runbook covers operations for the felix-admin-tasker agent — the task
structuring and enrichment component of the Felix agent system running on
office2.

## Overview

felix-admin-tasker receives raw task descriptions (delegated from
felix-admin-capture or triggered manually), reasons through task attributes
(title, identity label, project, due date, priority), proposes a structured
task via WhatsApp, and — after Kent's confirmation — creates the task in
Vikunja with full metadata. It also performs retroactive enrichment of
existing flat tasks and detects incomplete directly-created tasks.

The agent operates at **Assisted (Level 1)** autonomy: every task creation
requires Kent's explicit confirmation before execution.

**Runs on**: office2 (Ubuntu 24.04 LTS), orchestrated by OpenClaw
**Agent name**: `felix-admin-tasker`
**Standing orders**: `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
**Skills used**: `task-intelligence`, `vikunja-api`

---

## Manual Invocation

All manual invocations require SSH to office2 as the claude user.

```bash
ssh office2-claude
```

### Enrich a specific task

Send a raw task description for structuring and confirmation:

```bash
ssh office2-claude "openclaw agent --agent felix-admin-tasker \
  --message '{\"action\": \"enrich_task\", \"raw_text\": \"Your task description here\", \"source_reference\": \"manual\", \"inferred_identity\": \"personal\"}' \
  --json --timeout 120"
```

Replace `"Your task description here"` with the actual task text. Set
`inferred_identity` to `personal`, `intentional`, or `metalcasework` as
appropriate.

### Run retroactive enrichment

Process a batch of flat/incomplete tasks from Inbox:

```bash
ssh office2-claude "openclaw agent --agent felix-admin-tasker \
  --message '{\"action\": \"retroactive_enrichment\", \"batch_size\": 3}' \
  --json --timeout 300"
```

The agent will propose up to `batch_size` tasks (max 5) via WhatsApp. Respond
per task to confirm, skip, or defer.

### Run incomplete task detection

Poll Inbox for directly-created tasks missing structure:

```bash
ssh office2-claude "openclaw agent --agent felix-admin-tasker \
  --message '{\"action\": \"detect_incomplete\"}' \
  --json --timeout 300"
```

The agent will offer enrichment for up to 3 tasks per run, one at a time via
WhatsApp.

---

## Scheduled Operations

Incomplete task detection runs on a cron schedule managed by OpenClaw.

| Action | Schedule | Description |
|---|---|---|
| detect_incomplete | `0 */4 * * *` | Every 4 hours |

### View cron schedule

```bash
ssh office2-claude "openclaw cron list"
```

### View agent logs

Logs are written daily to the second-brain agents directory:

```bash
ssh office2-claude "cat ~/second-brain/agents/logs/task-intelligence-\$(date +%Y-%m-%d).md"
```

To view logs from a specific date:

```bash
ssh office2-claude "cat ~/second-brain/agents/logs/task-intelligence-2026-04-02.md"
```

To search logs for errors:

```bash
ssh office2-claude "grep -i error ~/second-brain/agents/logs/task-intelligence-*.md"
```

### Check agent status

```bash
ssh office2-claude "openclaw agent list"
```

---

## Retroactive Enrichment

Retroactive enrichment processes existing flat tasks in the Inbox that lack
full structure (missing due date, identity label, or still parked in Inbox).

### Starting a batch

Invoke the retroactive enrichment action:

```bash
ssh office2-claude "openclaw agent --agent felix-admin-tasker \
  --message '{\"action\": \"retroactive_enrichment\", \"batch_size\": 5}' \
  --json --timeout 300"
```

The agent will:
1. Query Inbox for flat tasks (oldest first)
2. Exclude tasks with existing enrichment comments
3. Propose up to `batch_size` tasks in a single WhatsApp message

### Responding to a batch

Reply to the WhatsApp message using these patterns:

| Response | Effect |
|---|---|
| `all` or `yes` | Confirm all tasks in the batch |
| `1, 3` or `confirm 1 and 3` | Confirm specific tasks by number |
| `skip 2` | Mark task 2 as skipped (will not be proposed again) |
| `1 yes, 2 skip, 3 yes but high priority` | Per-task instructions |
| `later` or `defer` | Pause entire batch — no re-proposal until next manual trigger |

### Checking enrichment progress

Count remaining flat tasks in Inbox:

```bash
ssh office2-claude "curl -s -H \"Authorization: Bearer \$(cat /data/services/openclaw/secrets/vikunja-api)\" \
  \"https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%201&per_page=1\" \
  | python3 -c \"import sys,json; print(f'Flat tasks in Inbox: {len(json.load(sys.stdin))}')\""
```

### Pausing enrichment

Reply `later` to any batch proposal. The agent will stop sending batches until
manually triggered again. Tasks with a `proposed` comment are left in place and
will not be re-proposed as skipped or declined.

### Resuming enrichment

Invoke the retroactive enrichment action again. The agent picks up where it
left off, skipping tasks that already have enrichment comments.

---

## Skip, Defer, and Enrichment State

### Skipping a task during a batch

Reply `skip N` (where N is the task number) in the batch response. The agent
writes a `[Felix] enrichment | skipped` comment on the task. That task will
not be proposed again.

### Declining a detection offer

When the agent asks about an incomplete task via WhatsApp, reply `no`. The
agent writes a `[Felix] enrichment | declined` comment. That task will not be
proposed again (single-offer policy).

### Checking enrichment state for a specific task

Query the task's comments for enrichment state entries:

```bash
ssh office2-claude "curl -s -H \"Authorization: Bearer \$(cat /data/services/openclaw/secrets/vikunja-api)\" \
  \"https://office2.tail0f5f56.ts.net/api/v1/tasks/{TASK_ID}/comments\" \
  | python3 -c \"import sys,json; [print(c['comment']) for c in json.load(sys.stdin) if '[Felix] enrichment' in c['comment']]\""
```

Replace `{TASK_ID}` with the numeric Vikunja task ID.

### Enrichment comment format

All enrichment state is tracked via task comments with this format:

```
[Felix] enrichment | <status> | <ISO timestamp> | <optional notes>
```

| Status | Meaning |
|---|---|
| `proposed` | Enrichment offered, awaiting Kent's response |
| `confirmed` | Enrichment accepted, task updated |
| `skipped` | Kent explicitly skipped this task |
| `declined` | Kent declined enrichment for this task |

### Re-enabling a skipped or declined task

To allow the agent to propose enrichment again for a previously skipped or
declined task:

1. Open the task in the Vikunja web UI
2. Find and delete the `[Felix] enrichment | skipped` or `[Felix] enrichment | declined` comment
3. The next detection poll or retroactive enrichment run will find the task and offer enrichment again

This is the only way to override the single-offer policy.

---

## Troubleshooting

### Task not being enriched

| Check | How | Fix |
|---|---|---|
| Task has skip/decline comment | Query task comments (see above) | Delete the comment to re-enable |
| Task is not in Inbox | Check the task's project in Vikunja UI | Detection only checks Inbox — move it to Inbox if needed |
| Task is marked done | Check task status in Vikunja UI | Enrichment skips completed tasks — reopen if needed |
| Agent errors | `ssh office2-claude "grep -i error ~/second-brain/agents/logs/task-intelligence-*.md"` | Review error details and follow resolution steps |

### Duplicate enrichment proposals

The agent checks for existing enrichment comments before proposing. Duplicates
should not occur.

If you see duplicate proposals:
1. Check task comments for multiple `[Felix] enrichment |` entries
2. Verify the `GET /tasks/{id}/comments` endpoint is returning all comments
3. Check agent logs for any indication of comment-read failures

### WhatsApp conversation not arriving

1. Check WhatsApp channel status on your phone
2. Check agent logs for send failures:
   ```bash
   ssh office2-claude "grep -i 'whatsapp\|send\|channel' ~/second-brain/agents/logs/task-intelligence-\$(date +%Y-%m-%d).md"
   ```
3. Verify the agent is running:
   ```bash
   ssh office2-claude "openclaw agent list"
   ```

### Agent delegation failing (capture to tasker)

When felix-admin-capture cannot delegate to felix-admin-tasker:

1. Verify felix-admin-tasker is deployed:
   ```bash
   ssh office2-claude "openclaw agent list"
   ```
2. Check capture agent logs for timeout or delegation errors:
   ```bash
   ssh office2-claude "grep -i 'delegat\|timeout\|error' ~/second-brain/agents/logs/inbox-*.md"
   ```
3. Flat tasks should still appear in Inbox as a fallback — capture creates
   the task directly if delegation fails

### Vikunja API errors

1. Check Vikunja service health:
   ```bash
   ssh office2-claude "curl -s https://office2.tail0f5f56.ts.net/api/v1/info"
   ```
2. Check API token validity:
   ```bash
   ssh office2-claude "curl -s -H \"Authorization: Bearer \$(cat /data/services/openclaw/secrets/vikunja-api)\" \
     https://office2.tail0f5f56.ts.net/api/v1/user | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'Token valid — user: {d.get(\\\"username\\\", \\\"unknown\\\")}')\""
   ```
3. Review agent logs for specific error codes:
   ```bash
   ssh office2-claude "grep -i 'api\|401\|403\|404\|500' ~/second-brain/agents/logs/task-intelligence-\$(date +%Y-%m-%d).md"
   ```
4. If Vikunja is down, see `docs/runbooks/vikunja-ops.md` for service
   management procedures
