# Agent Delegation Contract: felix-admin-capture → felix-admin-tasker

**Feature**: 013-vikunja-task-intelligence-agent
**Date**: 2026-04-02

## Delegation Command

felix-admin-capture invokes felix-admin-tasker via OpenClaw agent delegation:

```bash
openclaw agent --agent felix-admin-tasker \
  --message '<JSON payload>' \
  --json --timeout 120
```

## Message Payload

The message field contains a JSON object with the raw task input:

```json
{
  "action": "enrich_task",
  "raw_text": "Schedule car for oil change",
  "source_reference": "00-Inbox/2026-04-02-voice-note.md",
  "inferred_identity": "personal",
  "date_signals": ["next week"],
  "context_signals": ["car", "maintenance"]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| action | string | yes | Always `"enrich_task"` for new task handoff |
| raw_text | string | yes | Original task description |
| source_reference | string | yes | Path to originating inbox note |
| inferred_identity | string | no | Identity label if capture agent could infer it |
| date_signals | string[] | no | Date/time references found in text |
| context_signals | string[] | no | Keywords suggesting project, priority, or goal |

## Response

felix-admin-tasker returns JSON indicating handoff acceptance:

```json
{
  "status": "accepted",
  "task_text": "Schedule car for oil change",
  "next_step": "proposing_to_kent"
}
```

Or on error:

```json
{
  "status": "error",
  "error": "Vikunja API unavailable",
  "fallback_required": true
}
```

### Response Fields

| Field | Type | Description |
|---|---|---|
| status | string | `accepted` or `error` |
| task_text | string | Echo of received task text |
| next_step | string | What the tasker will do next |
| error | string | Error description (only on error) |
| fallback_required | boolean | If true, capture agent should create flat task |

## Fallback Behavior

If delegation fails (timeout, agent unavailable, error response with `fallback_required: true`):

1. felix-admin-capture creates a flat task in Vikunja Inbox (existing behavior)
2. felix-admin-capture logs the fallback event in its processing log
3. felix-admin-tasker's polling loop (FR-015) will detect the flat task and offer enrichment

## Timeout

- Delegation timeout: 120 seconds
- This covers only the handoff acceptance — not the full WhatsApp confirmation flow
- felix-admin-tasker acknowledges receipt quickly, then runs the confirmation flow asynchronously

## Retroactive Enrichment Trigger

For manual or scheduled retroactive enrichment, felix-admin-tasker is invoked directly:

```bash
openclaw agent --agent felix-admin-tasker \
  --message '{"action": "retroactive_enrichment", "batch_size": 5}' \
  --json --timeout 300
```

## Incomplete Task Detection (Polling)

For scheduled polling of incomplete tasks:

```bash
openclaw agent --agent felix-admin-tasker \
  --message '{"action": "detect_incomplete"}' \
  --json --timeout 300
```
