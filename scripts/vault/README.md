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
from scripts.vault.resolver import get_vault_path, get_vault_folder_name

inbox_path = get_vault_path("inbox")
# → "/home/kgale/second-brain/notes/01-Inbox"

inbox_name = get_vault_folder_name("inbox")
# → "01-Inbox"
```

Raises `UnknownPathError` if the logical name is not registered.
Raises `RegistryNotFoundError` if the registry file is missing or malformed.

CLI usage:

```bash
python3 scripts/vault/resolver.py inbox         # prints absolute path
python3 scripts/vault/resolver.py inbox --name  # prints folder name only
```

## Shell usage

```bash
source scripts/vault/paths.sh
echo "$VAULT_INBOX"       # → /home/kgale/second-brain/notes/01-Inbox
echo "$VAULT_INBOX_NAME"  # → 01-Inbox
```

Each logical name is exported in two forms:
- `VAULT_<UPPERCASE_NAME>` — absolute path
- `VAULT_<UPPERCASE_NAME>_NAME` — folder basename only

Use the `_NAME` form when you need the shape of a relative-path reference or
a bare folder name (routing tables, JSON examples, natural-language prose)
while still flowing the identifier through the registry so renames propagate.

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

### Marker forms in `.tmpl` files

Two marker forms are supported:

| Marker | Resolves to | Use when |
|---|---|---|
| `{{VAULT_INBOX}}` | `/home/kgale/second-brain/notes/01-Inbox` (absolute path) | You need the full, unambiguous path — e.g., in an absolute-path reference inside an agent standing order |
| `{{VAULT_INBOX_NAME}}` | `01-Inbox` (folder name only) | You need the shape of a relative reference, a bare folder name in a routing table, or a natural-language mention — while still flowing the identifier through the registry |

Example mixing both forms in a single `.tmpl`:

```markdown
<!-- absolute-path reference (agent reads the file directly) -->
Read the inbox at `{{VAULT_INBOX}}/*.md`

<!-- relative-path fragment in a routing table -->
| Topic | Route to |
|---|---|
| goals | `{{VAULT_CONSTITUTION_NAME}}/Goals-MOC.md` |

<!-- natural-language prose -->
Items older than 7 days are moved to the `{{VAULT_INBOX_PROCESSED_NAME}}` folder.
```

### Adding a new migration

1. Create a `.tmpl` version of your target file with `{{VAULT_<NAME>}}` or `{{VAULT_<NAME>_NAME}}` markers
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
