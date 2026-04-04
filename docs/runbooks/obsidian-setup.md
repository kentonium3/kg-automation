---
id: obsidian-setup
title: Obsidian Setup Guide
doc_type: handbook
level: howto
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-11-01'
last_validated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---

# Obsidian Setup Guide

This handbook documents the standard Obsidian configuration for this repository's vault.

## Vault Root

The vault root for this repository is: `docs/`

## Templater Configuration

Templater plugin settings should be configured as follows:

- **Template folder**: `_templates`
- **Script folder**: `_templater-scripts`

These settings are tracked in the repository at:
`docs/.obsidian/plugins/templater-obsidian/data.json`

## Runner Templates

The following runner templates are available in `docs/_templates/`:

- `_run-revBump.md` - Execute revision bump script
- `_run-normalizeFm.md` - Execute frontmatter normalization script
- `_run-enforceEnums.md` - Execute enum enforcement script
- `_run-setTitleFromH1.md` - Execute title-from-H1 script
- `_diag-user-fns.md` - List available user functions (diagnostic)

## Standard Hotkeys (Shared)

### Reference File

The shared hotkey reference is maintained at:
`docs/.obsidian-shared/hotkeys.example.json`

This file defines the standard hotkey bindings for Templater operations across all machines.

### Manual Application Steps

To apply the standard hotkeys on your machine:

1. Open Obsidian
2. Navigate to **Settings → Hotkeys**
3. Configure the following bindings:
   - **Templater: Insert template** → `_run-revBump.md` → `Ctrl+Alt+B`
   - **Templater: Insert template** → `_run-normalizeFm.md` → `Ctrl+Alt+N`
   - **Templater: Insert template** → `_run-enforceEnums.md` → `Ctrl+Alt+E`
   - **Templater: Insert template** → `_run-setTitleFromH1.md` → `Ctrl+Alt+T`
   - **Templater: Replace templates in the active file** → `Ctrl+Alt+R`

### Optional: Copy Example as Baseline

If you want to start with the example as a baseline:

1. Manually copy `docs/.obsidian-shared/hotkeys.example.json` to `docs/.obsidian/hotkeys.json`
2. Refine the hotkeys in Obsidian's Settings → Hotkeys UI

**Important**: The file `.obsidian/hotkeys.json` is not tracked in git (it remains local to your machine). Only the example file is tracked for reference.

### Power User Helper (Optional)

A PowerShell helper script is available at:
`docs/.obsidian-shared/apply-hotkeys-example.ps1`

This script (not tracked in git) can copy the example to your local `.obsidian/hotkeys.json`:

```powershell
cd docs/.obsidian-shared
.\apply-hotkeys-example.ps1
```

After running, review the hotkeys in Obsidian → Settings → Hotkeys.

## Verification

To verify that user scripts are properly loaded:

1. Insert the `_diag-user-fns.md` template in any note
2. It should list: `revBump, normalizeFm, enforceEnums, setTitleFromH1`

If scripts are missing, check the Templater script folder setting.
