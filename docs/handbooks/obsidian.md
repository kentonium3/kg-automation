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
- **Community plugin configuration files (data.json) are shared by default.** If a plugin stores per-user secrets or volatile caches, add those paths to `.gitignore`.
- **Ignored:** `workspace*.json`, `graph.json`, plugin caches.

## Location
Vault root: `kg-automation/docs`
Config: `docs/.obsidian/`

## Templater
The Templater plugin automates front-matter updates and template workflows.

### Configuration
- **Templates folder:** `_templates`
- **Scripts folder:** `_templater-scripts` (set this in Obsidian UI under Templater settings; then commit updated config)

### Command: Bump Revision
Bind a hotkey to template `_templates/_commands/bump-revision.md` to:
- Increment `revision` (vMAJOR.MINOR → vMAJOR.(MINOR+1))
- Update `last_validated` to today's date (YYYY-MM-DD)
- Add missing keys with sensible defaults

This ensures docs stay up-to-date with minimal manual overhead.

## Working Notes
- If a plugin stores noisy per-user data, add it to `.gitignore` under `docs/.obsidian/plugins/<name>/**` as needed.
- Keep Docs CI green: Obsidian files are JSON; they are not scanned as docs.
