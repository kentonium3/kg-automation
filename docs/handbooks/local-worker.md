---
id: local-worker
title: Local Worker — Contract & Usage
doc_type: handbook
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-15
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
---

# Local Worker — Contract & Usage

**Purpose:** perform tasks that require local machine access (Dropbox paths, local apps, LAN, sandboxed deployments), while GitHub remains the system of record.

## When to use
- Inventories: apps, versions present locally.
- Dropbox/Filesystem checks: resolve platform-specific paths.
- Local test/stage: run a tool or spin a tiny local service for validation.

## Handoff (request)
```json
{
  "type": "handoff.request",
  "handoff_id": "L-0001",
  "from_agent": "chatgpt",
  "to_agent": "local-worker",
  "created_at": "2025-10-15T00:00:00Z",
  "purpose": "Local inventory & Dropbox path sanity",
  "requires_local": true,
  "inputs": {"tasks": [{"action": "inventory_apps"},{"action": "check_dropbox_paths","paths":["Automation","kg-automation"]}]},
  "next_actions": ["Commit response to branch","Open issues if mismatches found"]
}
```

## Handoff (response)
```json
{
  "type": "handoff.response",
  "handoff_id": "L-0001",
  "from_agent": "local-worker",
  "to_agent": "chatgpt",
  "status": "completed",
  "outputs": {"apps":["Dropbox 201.4","Git 2.46","Python 3.11.9"],"dropbox":{"root":"C:\\Users\\Kent\\Dropbox","exists":true,"kg-automation":"C:\\Users\\Kent\\Dropbox\\Automation\\kg-automation"}},
  "notes": "All paths good on Office3."
}
```

## Guardrails
- Execute only allowlisted tasks.
- Write results back as `*-local-worker-response.json` on the same branch.
- Never mutate local secrets; surface prompts/instructions instead.
