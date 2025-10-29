---
id: process-handoff
title: /process-handoff
doc_type: handbook
level: reference
status: approved
owners: ["@kentonium3"]
last_validated: 2025-10-18
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
---

**Usage:** `/process-handoff <path>`

**Steps**
1) Read JSON; validate schema
2) Checkout/ensure target branch
3) Apply file edits / tasks
4) Run `python tooling/scripts/validate_docs.py`
5) Commit & push; write response JSON next to request
6) Comment summary (if applicable)

**Never** edit `.github/workflows/**`.
