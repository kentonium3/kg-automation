---
title: Vault Path Registry
doc_type: reference
status: approved
---

# Vault Path Registry

Single source of truth for vault folder paths. Eliminates hardcoded paths across
agent standing orders, scripts, and documentation by centralizing them in
`paths.json` and providing resolvers for Python and shell consumers.

## Files

| File | Purpose |
|---|---|
| `paths.json` | The registry data — logical name → physical path map |
| `resolver.py` | Python API: `from scripts.vault.resolver import get_vault_path` |
| `paths.sh` | Shell API: `source paths.sh` → `$VAULT_<NAME>` env vars |
| `deploy.py` | Build-time: replaces `{{VAULT_*}}` markers in `.tmpl` files |
| `targets.json` | List of `.tmpl` → resolved file mappings for deploy.py |

## Schema: paths.json

```json
{
  "version": 1,
  "updated": "YYYY-MM-DD",
  "paths": {
    "logical_name": "/absolute/physical/path"
  }
}
```

- `version` is an integer for future schema changes
- `updated` is informational
- Logical names: lowercase, underscore-separated (e.g., `inbox`, `inbox_processed`)
- Paths: absolute, no trailing slash

## Python usage

```python
from scripts.vault.resolver import get_vault_path

inbox_path = get_vault_path("inbox")
# → "/home/kgale/second-brain/notes/00-Inbox"
```

Raises `UnknownPathError` if the logical name is not registered.
Raises `RegistryNotFoundError` if the registry file is missing or malformed.

CLI usage: `python3 scripts/vault/resolver.py inbox`

## Shell usage

```bash
source scripts/vault/paths.sh
echo "$VAULT_INBOX"
# → /home/kgale/second-brain/notes/00-Inbox
```

Each logical name is exported as `VAULT_<UPPERCASE_NAME>`.

## Deploy workflow

The deploy script processes template files and writes resolved output:

```bash
# Dry-run (default) — show what would change
python3 scripts/vault/deploy.py

# Apply — write resolved files and SCP to office2 if configured
python3 scripts/vault/deploy.py --apply

# Apply but skip office2 sync
python3 scripts/vault/deploy.py --apply --no-office2
```

### Adding a new migration

1. Create a `.tmpl` version of your target file with `{{VAULT_<NAME>}}` markers
2. Add an entry to `targets.json` pointing to the template and output
3. Run `python3 scripts/vault/deploy.py` (dry-run) to preview
4. Run with `--apply` to write the resolved file

### Adding a new logical path

1. Edit `paths.json` to add the new entry
2. Update any templates that need the new path
3. Run `deploy.py --apply` to refresh resolved files

## Design principles

- **Build-time resolution, not runtime.** Agents and scripts get resolved paths
  baked in. The registry is only consulted by humans editing paths and by the
  deploy script. This keeps runtime behavior unchanged and avoids adding tool-
  call complexity to agents.
- **Single source of truth.** When a folder moves, update `paths.json` and
  redeploy — no hunting through agent standing orders.
- **Deterministic code for deterministic work.** No LLM involvement in path
  lookup. Reserve AI tokens for tasks that actually need reasoning.

## Privacy boundary

The `_private/` path is intentionally NOT in the registry. Autonomous agents
discover paths only through the registry, so keeping `_private` out means they
cannot reference it even accidentally. The policy boundary in standing orders
remains hardcoded for defense in depth.
