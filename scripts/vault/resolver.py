"""Vault path registry resolver.

Read scripts/vault/paths.json and return absolute paths by logical name.

Usage:
    from scripts.vault.resolver import get_vault_path, get_vault_folder_name
    inbox = get_vault_path("inbox")                  # "/home/kgale/.../01-Inbox"
    inbox_name = get_vault_folder_name("inbox")      # "01-Inbox"

CLI:
    python3 scripts/vault/resolver.py inbox          # prints absolute path
    python3 scripts/vault/resolver.py inbox --name   # prints folder name only
"""
import json
import sys
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


def get_vault_folder_name(name: str) -> str:
    """Return the basename (folder name only) for a logical vault name.

    This is a sibling to get_vault_path() that returns just the final path
    component. Useful for references that need to preserve relative-path
    shape or appear in natural-language prose — e.g., rendering
    "01-Inbox/Values.md" in a routing table or "the 01-Inbox folder" in
    docs, while still flowing the underlying identifier through the
    registry so renames propagate automatically.

    Args:
        name: Logical name (e.g., "inbox")

    Returns:
        Folder basename as a string (e.g., "01-Inbox").

    Raises:
        RegistryNotFoundError: Registry file missing or malformed.
        UnknownPathError: Logical name not in registry.
    """
    absolute = get_vault_path(name)
    return Path(absolute).name


def list_vault_paths() -> dict:
    """Return a copy of all logical name to path mappings."""
    registry = _load_registry()
    return dict(registry.get("paths", {}))


if __name__ == "__main__":
    # Usage:
    #   python3 resolver.py <logical-name>          -> absolute path
    #   python3 resolver.py <logical-name> --name   -> folder name only
    if len(sys.argv) < 2:
        print(
            "Usage: python3 resolver.py <logical-name> [--name]",
            file=sys.stderr,
        )
        sys.exit(1)
    name_only = "--name" in sys.argv[2:]
    try:
        if name_only:
            print(get_vault_folder_name(sys.argv[1]))
        else:
            print(get_vault_path(sys.argv[1]))
    except VaultPathError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
