---
id: templater-commands
title: Templater Commands (Canon v2)
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: "2025-10-30"
revision: v1.0
audience: agents_and_humans
tags: [obsidian, templater]
aliases: []
links: []
---
# Templater Commands

Use CMD-P → **Templater: Run user function**:

- **normalizeFm** — normalize `id` to filename stem, ensure owners array, tidy FM spacing.
- **enforceEnums** — validate/repair `doc_type`, `level`, `status`, `audience` against `docs/standards/allowed-values.json`.
- **revBump** — bump `revision` (vX.Y → vX.Y+1) and set `last_updated` to today.
- **setTitleFromH1** — if `title` missing, copy from first `# H1`.

## Base template (picker)
Use **Templater: Create new note from template → base** to choose `doc_type`, `level`, `status`, and `audience` at creation. Then run **normalizeFm** and **enforceEnums** before committing.

