# KG Sync: Doc ⇄ JSON Watcher

- Run once: `pip install -r requirements.txt`
- Start watcher: `python tooling/scripts/kg_sync_watch.py docs`
- VS Code task: **Watch: Doc→JSON sync (kg-sync)**
- CI: `.github/workflows/charter-sync.yml` fails PRs if JSON is out of sync.
- Any markdown with this front matter will be synced:

```yaml
---
machine_manifest: path/to/paired.json
---
```
