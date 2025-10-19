---
id: obsidian-handbook
title: Obsidian Vault (kg-automation/docs)
doc_type: handbook
level: reference
status: approved
owners: ["@kentonium3"]
last_validated: 2025-10-19
revision: v1.0
audience: agents_and_humans
---
## Purpose
Shared Obsidian configuration for the `docs` vault. We commit stable, cross-machine settings and ignore per-device UI state.

## Commit Policy
- **Committed:** app/appearance, core & community plugin lists, hotkeys, shared plugin settings, CSS snippets.
- **Ignored:** `workspace*.json`, `graph.json`, plugin caches.

## Location
Vault root: `kg-automation/docs`
Config: `docs/.obsidian/`

## Working Notes
- If a plugin stores noisy per-user data, add it to `.gitignore` under `docs/.obsidian/plugins/<name>/**` as needed.
- Keep Docs CI green: Obsidian files are JSON; they are not scanned as docs.
