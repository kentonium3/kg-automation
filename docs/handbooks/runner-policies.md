---
id: runner-policies
title: Handoff Runner Policies
doc_type: handbook
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-15
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
---

# Handoff Runner Policies

## Denylist (default)
The runner will **not** edit files under these prefixes unless explicitly permitted:

- `.github/workflows/`

Rationale: workflow files affect CI/CD execution. Changes must go through a human-reviewed PR.

## Overriding (explicit, per-request)
To override (rare), set this flag in the handoff request:

```json
{
  "inputs": {
    "allow_workflow_edit": true,
    "file_edits": [ ... ]
  }
}
```

Use only for exceptional cases and prefer a normal PR edited by a human.

## Idempotent writes
The runner only writes a file when content actually changes.

## Responses
Each request produces a `*-github-runner-response.json` with:
- `status`: `planned` (no file_edits), `completed` (wrote files), or `noop` (no changes)
- `edited_files`, `skipped_files`, and `notes`
