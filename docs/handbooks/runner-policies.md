---
id: HB-RUNNER-POLICIES
title: Handoff Runner Policies
doc_type: handbook
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-15
revision: 1.0
---

# Handoff Runner Policies

## Denylist (default)
The runner will **not** edit files under these prefixes unless explicitly permitted:

- `.github/workflows/`

**Why:** workflow files affect CI/CD execution. Changes must go through a human-reviewed PR.

## How to override (rare)
A request may opt in intentionally:

```json
{
  "inputs": {
    "allow_workflow_edit": true,
    "file_edits": [ ... ]
  }
}
