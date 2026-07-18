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

> The `.tmpl` render mechanism (`deploy.py` + `targets.json` + `{{VAULT_*}}`
> markers) was **retired in #752**. Agent prompts and instruction files are now
> hand-authored directly (the committed `.md` is the sole source) and deployed
> by the agent-prompt-sync timer, which copies them verbatim. The registry below
> (`paths.json` / `resolver.py` / `paths.sh`) is unchanged and still consumed by
> live code (inbox/journal routing).

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

## Adding a new logical path

1. Edit `paths.json` to add the new entry (logical name → absolute path).
2. Consume it from code via `resolver.get_vault_path("<name>")` (Python) or
   `$VAULT_<NAME>` after sourcing `paths.sh` (shell).

## Design principles

- **One registry for live code.** `paths.json` is consulted by `resolver.py` /
  `paths.sh` at the point of use (inbox/journal routing), and by humans editing
  paths. When a folder moves, update `paths.json` — no hunting through consumers.
- **Deterministic code for deterministic work.** No LLM involvement in path
  lookup. Reserve AI tokens for tasks that actually need reasoning.
- **Prompts are hand-authored (#752).** Agent standing orders are no longer
  generated from `.tmpl` templates; their paths are written literally in the
  committed `.md`. The `04-Growth` privacy-pointer is guarded against silent
  drift by a CI check (`tests/openclaw/test_privacy_pointer.py`) rather than the
  retired `{{VAULT_GROWTH_NAME}}` render-time indirection.

## Privacy boundary

The `_private/` path is intentionally NOT in the registry. Autonomous agents
discover paths only through the registry, so keeping `_private` out means they
cannot reference it even accidentally. The policy boundary in standing orders
remains hardcoded for defense in depth.
