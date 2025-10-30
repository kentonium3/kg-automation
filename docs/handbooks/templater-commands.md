---
id: templater-commands
title: Templater Commands (Canon v2)
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: 2025-10-19
revision: v1.0
audience: agents_and_humans
tags: [obsidian, templater]
aliases: []
links: []
---
# Templater Commands

Use CMD-P → **Templater: Run user function**:

- **normalizeFm** — normalize `id`/owners and tidy FM
- **enforceEnums** — validate/repair `doc_type`, `level`, `status`, `audience`
- **revBump** — bump `revision` and update `last_updated`
- **setTitleFromH1** — copy first H1 into `title` if missing

## Base template (picker)
Use **Templater: Create new note from template → base** to choose doc_type, level, status, and audience at creation.
