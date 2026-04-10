---
work_package_id: WP01
title: Registry Foundation
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-024-vault-path-registry-mvp
base_commit: 47a0f13a2386115fd0dc1e35e8ba22d057bd3e29
created_at: '2026-04-10T15:34:56.162918+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
shell_pid: "14356"
agent: "claude"
history:
- date: '2026-04-10T13:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/vault/
execution_mode: code_change
owned_files:
- scripts/vault/paths.json
- scripts/vault/resolver.py
- scripts/vault/paths.sh
- scripts/vault/README.md
tags: []
---

# WP01: Registry Foundation

## Objective

Build the foundation of the vault path registry: the JSON data file, Python resolver, shell resolver, and documentation. After this WP, both Python and shell consumers can look up the inbox path by logical name. No templates or deploy script yet — that comes in WP02.

## Context

- New directory: `scripts/vault/` — following the repo's `scripts/<concern>/` pattern
- Python 3.13 standard library only — no new dependencies
- `jq` is available on both Mac and office2 (verified)
- The MVP registry has exactly ONE entry: `inbox` → current inbox path
- This is deterministic code: JSON file + Python script + shell script — no LLM involvement at runtime

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP01 --agent claude`
- Execution: single lane worktree

---

## Subtask T001: Create scripts/vault/paths.json

**Purpose**: Create the JSON registry file — the single source of truth for vault paths.

**Steps**:
1. Create directory `scripts/vault/` in the repo (the worktree)
2. Create `scripts/vault/paths.json` with this content:

```json
{
  "version": 1,
  "updated": "2026-04-10",
  "paths": {
    "inbox": "/home/kgale/second-brain/notes/00-Inbox"
  }
}
```

**Schema notes**:
- `version` is an integer for future schema evolution
- `updated` is a YYYY-MM-DD string (informational)
- `paths` is a map of logical name → absolute physical path
- Logical names are lowercase, underscore-separated
- Paths are absolute and do not have trailing slashes

**Validation**:
- [ ] File exists at `scripts/vault/paths.json`
- [ ] JSON is valid: `python3 -m json.tool scripts/vault/paths.json` parses without error
- [ ] Contains exactly one entry in `paths` (the inbox)
- [ ] Path has no trailing slash

---

## Subtask T002: Create Python Resolver (resolver.py)

**Purpose**: Provide a Python function that reads the registry and returns resolved paths by logical name.

**Steps**:
1. Create `scripts/vault/resolver.py`
2. Implement a module with these characteristics:

```python
"""Vault path registry resolver.

Read scripts/vault/paths.json and return absolute paths by logical name.

Usage:
    from scripts.vault.resolver import get_vault_path
    inbox = get_vault_path("inbox")
"""
import json
from pathlib import Path

_REGISTRY_PATH = Path(__file__).parent / "paths.json"


class VaultPathError(Exception):
    """Base exception for vault path errors."""


class RegistryNotFoundError(VaultPathError):
    """Registry file is missing or unreadable."""


class UnknownPathError(VaultPathError):
    """Requested logical name is not in the registry."""


def _load_registry():
    """Load and parse the registry file. Raise RegistryNotFoundError on failure."""
    try:
        with open(_REGISTRY_PATH) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise RegistryNotFoundError(
            f"Vault path registry not found at {_REGISTRY_PATH}"
        ) from e
    except json.JSONDecodeError as e:
        raise RegistryNotFoundError(
            f"Vault path registry is not valid JSON: {e}"
        ) from e


def get_vault_path(name: str) -> str:
    """Return the absolute path for a logical vault name.

    Args:
        name: Logical name (e.g., "inbox")

    Returns:
        Absolute path as a string.

    Raises:
        RegistryNotFoundError: Registry file missing or malformed.
        UnknownPathError: Logical name not in registry.
    """
    registry = _load_registry()
    paths = registry.get("paths", {})
    if name not in paths:
        available = ", ".join(sorted(paths.keys())) or "(none)"
        raise UnknownPathError(
            f"Unknown vault path '{name}'. Available: {available}"
        )
    return paths[name]


def list_vault_paths() -> dict:
    """Return a copy of all logical name → path mappings."""
    registry = _load_registry()
    return dict(registry.get("paths", {}))


if __name__ == "__main__":
    # Simple CLI for manual verification
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 resolver.py <logical-name>")
        sys.exit(1)
    try:
        print(get_vault_path(sys.argv[1]))
    except VaultPathError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

**Important design notes**:
- Standard library only (`json`, `pathlib`, `sys`)
- Custom exceptions let callers distinguish between "registry broken" and "name not found"
- Module-level `_REGISTRY_PATH` uses `Path(__file__).parent` so it works regardless of cwd
- CLI entry point is a bonus for manual verification

**Validation**:
- [ ] File exists at `scripts/vault/resolver.py`
- [ ] Python syntax is valid: `python3 -c "import ast; ast.parse(open('scripts/vault/resolver.py').read())"`

---

## Subtask T003: Create Shell Resolver (paths.sh)

**Purpose**: Provide a sourceable shell script that reads the registry and exports `VAULT_*` environment variables.

**Steps**:
1. Create `scripts/vault/paths.sh`
2. Implement with this content:

```bash
#!/usr/bin/env bash
# Vault path registry — shell resolver.
#
# Usage:
#   source scripts/vault/paths.sh
#   echo "$VAULT_INBOX"
#
# After sourcing, each logical name from paths.json is exported as
# VAULT_<UPPERCASE_NAME>. Example: "inbox" -> $VAULT_INBOX

# Determine this script's directory even when sourced
__vault_resolver_dir="$( cd "$( dirname "${BASH_SOURCE[0]:-$0}" )" && pwd )"
__vault_registry="${__vault_resolver_dir}/paths.json"

if [ ! -f "$__vault_registry" ]; then
    echo "vault resolver: registry not found at $__vault_registry" >&2
    unset __vault_resolver_dir __vault_registry
    return 1 2>/dev/null || exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "vault resolver: jq is required but not installed" >&2
    unset __vault_resolver_dir __vault_registry
    return 1 2>/dev/null || exit 1
fi

# Export each path with VAULT_<UPPERCASE> prefix
while IFS=$'\t' read -r __vault_name __vault_path; do
    __vault_var="VAULT_$(echo "$__vault_name" | tr '[:lower:]' '[:upper:]')"
    export "$__vault_var=$__vault_path"
done < <(jq -r '.paths | to_entries[] | "\(.key)\t\(.value)"' "$__vault_registry")

unset __vault_resolver_dir __vault_registry __vault_name __vault_path __vault_var
```

**Important design notes**:
- Uses `BASH_SOURCE` fallback to `$0` so both bash and zsh work
- Silent on success (no stdout output when everything works)
- Errors to stderr with clear prefix
- Returns from function if sourced, exits if executed directly
- Uses `jq -r` with tab-separated output for safe parsing
- Unsets internal variables to avoid polluting the shell

**Validation**:
- [ ] File exists at `scripts/vault/paths.sh`
- [ ] Bash syntax is valid: `bash -n scripts/vault/paths.sh`

---

## Subtask T004: Create README.md

**Purpose**: Document the registry schema, resolver APIs, and usage patterns.

**Steps**:
1. Create `scripts/vault/README.md` with this content:

```markdown
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
| `deploy.py` | Build-time: replaces `{{VAULT_*}}` markers in `.tmpl` files (WP02) |
| `targets.json` | List of `.tmpl` → resolved file mappings (WP02) |

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

## Design principles

- **Build-time resolution, not runtime.** Agents and scripts get resolved paths
  baked in. The registry is only consulted by humans editing paths and by the
  deploy script.
- **Single source of truth.** When a folder moves, update `paths.json` and
  redeploy — no hunting through agent standing orders.
- **Deterministic code for deterministic work.** No LLM involvement in path
  lookup. Reserve AI tokens for tasks that actually need reasoning.

## Adding a new path

1. Edit `paths.json` to add the new logical name → physical path entry
2. Update any template files (`*.tmpl`) that need the new path, using
   `{{VAULT_<NAME>}}` as the marker
3. Run `python3 scripts/vault/deploy.py` (dry-run) to see what would change
4. Run with `--apply` to write the resolved files

## Privacy boundary

The `_private/` path is intentionally NOT in the registry. Autonomous agents
discover paths only through the registry, so keeping `_private` out means they
cannot reference it even accidentally. The policy boundary in standing orders
remains hardcoded for defense in depth.
```

**Validation**:
- [ ] File exists at `scripts/vault/README.md`
- [ ] Content covers: schema, Python usage, shell usage, design principles, adding paths, privacy boundary

---

## Subtask T005: Verify Python Resolver

**Purpose**: Manually confirm the Python resolver works end-to-end.

**Steps**:
1. From the worktree root, run: `python3 scripts/vault/resolver.py inbox`
2. Verify output is: `/home/kgale/second-brain/notes/00-Inbox`
3. Run: `python3 scripts/vault/resolver.py nonexistent`
4. Verify error output mentions "Unknown vault path 'nonexistent'" and lists available names
5. Verify exit code is non-zero on error: `python3 scripts/vault/resolver.py nonexistent; echo $?`

**Validation**:
- [ ] `resolver.py inbox` prints the correct path
- [ ] `resolver.py nonexistent` prints a clear error to stderr
- [ ] Non-zero exit code on error

---

## Subtask T006: Verify Shell Resolver

**Purpose**: Manually confirm the shell resolver works in both bash and zsh.

**Steps**:
1. From the worktree root, run in bash:
   ```bash
   bash -c 'source scripts/vault/paths.sh && echo "$VAULT_INBOX"'
   ```
2. Verify output is: `/home/kgale/second-brain/notes/00-Inbox`
3. Run the same test in zsh:
   ```bash
   zsh -c 'source scripts/vault/paths.sh && echo "$VAULT_INBOX"'
   ```
4. Verify same output
5. Test missing registry error:
   ```bash
   bash -c 'mv scripts/vault/paths.json scripts/vault/paths.json.bak; source scripts/vault/paths.sh; mv scripts/vault/paths.json.bak scripts/vault/paths.json'
   ```
   Should print an error mentioning the registry path.

**Validation**:
- [ ] `$VAULT_INBOX` correctly set in bash
- [ ] `$VAULT_INBOX` correctly set in zsh
- [ ] Missing registry produces clear error

---

## Definition of Done

- [ ] `scripts/vault/` directory created with 4 files (paths.json, resolver.py, paths.sh, README.md)
- [ ] JSON is valid and contains the inbox entry
- [ ] Python resolver works for valid and invalid lookups
- [ ] Shell resolver works in bash and zsh
- [ ] README documents the schema, APIs, and usage
- [ ] All files committed to the worktree

## Risks

- **Module import path**: If someone tries `from scripts.vault.resolver import ...` but `scripts/` doesn't have `__init__.py`, Python may not find the module. For the MVP, direct script execution via `python3 scripts/vault/resolver.py` is the primary interface. If WP02's deploy script needs to import resolver.py, it will use the same directory pattern.
- **Shell compatibility**: The `BASH_SOURCE` fallback handles both bash and zsh, but the test should explicitly verify both.

## Reviewer Guidance

- JSON must be valid (parse test)
- Python syntax must be valid (AST parse test)
- Bash syntax must be valid (`bash -n`)
- Manual verification outputs match expected paths
- README is complete and clear

## Activity Log

- 2026-04-10T15:34:56Z – claude – shell_pid=14356 – Assigned agent via action command
- 2026-04-10T15:37:01Z – claude – shell_pid=14356 – Registry, resolvers, and README complete. Both resolvers verified.
- 2026-04-10T15:37:03Z – claude – shell_pid=14356 – Python and shell resolvers verified; README complete.
