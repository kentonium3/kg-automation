---
id: obsidian-linter-alignment
title: Obsidian Linter Alignment
doc_type: reference
level: overview
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
tags: [obsidian, linter, ci]
aliases: []
links: []
---
# Obsidian Linter Alignment

This vault uses Obsidian Linter for convenience only. **Docs CI** enforces semantic rules; cosmetics are advisory.
This config disables cosmetic rules that previously caused authoring thrash.

**Disabled (cosmetic)**
- Heading blank lines (MD022/MD032 analog)
- Consecutive blank lines (MD012 analog)
- Single H1 (MD025 analog)
- Line length (MD013 analog)
- Bare URLs (MD034 analog)
- YAML key sort/order, title case & heading style enforcement, space after list markers

**Enabled (safe)**
- Trim trailing whitespace
- Ensure final newline

**Excluded from lint-on-save**
- `docs/_templates/**`, `docs/.obsidian/**`

Docs CI remains the source of truth for blocking rules.
