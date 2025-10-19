---
id: cmd-docs-self-heal
title: /docs-self-heal
doc_type: handbook
level: reference
status: approved
owners: ["@kentonium3"]
last_validated: 2025-10-18
revision: v1.0
---

**Purpose:** fix failing Docs CI for the current branch.

**Steps**
1) Parse last Docs CI log
2) For each failing file: add/normalize required front-matter keys; repair relative links
3) Re-run validator locally; repeat until green
4) Commit: `docs(ci): self-heal front-matter/links`

Respects `.claude/config.json`.
