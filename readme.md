---
id: readme
title: kg-automation Repository
doc_type: readme
level: reference
status: approved
owners:
  - '@kentonium3'
last_validated: '2025-10-21'
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
---

# Option B: Cross-Platform Doc ⇄ JSON Sync

This folder contains a cross-platform synchronizer to keep a Markdown charter
and its machine-readable JSON manifest in sync.

## Files
- `scripts/kg_sync_docs.py` — Markdown → JSON converter (Python 3.9+)
- `docs/strategy/strategic_acceleration_charter.md` — example source Markdown
- `docs/strategy/strategic_acceleration_charter.json` — generated manifest (output)
- `.github/workflows/charter-sync.yml` — CI check to ensure JSON matches Markdown

## Usage
```bash
# one-shot write/update locally
python scripts/kg_sync_docs.py docs/strategy/strategic_acceleration_charter.md --write

# CI-style check (non-zero exit if out-of-sync)
python scripts/kg_sync_docs.py docs/strategy/strategic_acceleration_charter.md --check
```


## Watch mode (recommended)
Install deps once:
```bash
pip install -r requirements.txt
```

Start the watcher (recursively sync any Markdown with `machine_manifest` front-matter):
```bash
python scripts/kg_sync_watch.py docs
```

### VS Code
- Open the repo in VS Code
- Run task: **Watch: Doc→JSON sync** (Terminal → Run Task)
- The task runs in the background and updates JSON on every save.
- CI still enforces consistency if edits happen outside VS Code.

### One-shot full sync
```bash
python scripts/kg_sync_watch.py docs --once
```

## Document ⇄ JSON Sync (KG Sync)
- Install: `pip install -r requirements.txt`
- Watcher: `python tooling/scripts/kg_sync_watch.py docs`
- VS Code: Run Task → **Watch: Doc→JSON sync (kg-sync)**
- Optional pre-commit hook: `git config core.hooksPath tooling/hooks`
