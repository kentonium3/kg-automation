#!/usr/bin/env bash
# Vault path registry — shell resolver.
#
# Usage:
#   source scripts/vault/paths.sh
#   echo "$VAULT_INBOX"       # absolute path: /home/kgale/.../01-Inbox
#   echo "$VAULT_INBOX_NAME"  # folder name only: 01-Inbox
#
# After sourcing, each logical name from paths.json is exported in two forms:
#   VAULT_<UPPERCASE_NAME>       -> absolute path (e.g., $VAULT_INBOX)
#   VAULT_<UPPERCASE_NAME>_NAME  -> folder basename (e.g., $VAULT_INBOX_NAME)
#
# Use the _NAME form when you need the shape of a relative reference or a
# bare folder name (routing tables, JSON examples, natural-language prose)
# while still flowing the identifier through the registry so renames propagate.

# Determine this script's directory even when sourced (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
    __vault_resolver_src="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    __vault_resolver_src="${(%):-%x}"
else
    __vault_resolver_src="$0"
fi
__vault_resolver_dir="$( cd "$( dirname "$__vault_resolver_src" )" && pwd )"
__vault_registry="${__vault_resolver_dir}/paths.json"

if [ ! -f "$__vault_registry" ]; then
    echo "vault resolver: registry not found at $__vault_registry" >&2
    unset __vault_resolver_src __vault_resolver_dir __vault_registry
    return 1 2>/dev/null || exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "vault resolver: jq is required but not installed" >&2
    unset __vault_resolver_src __vault_resolver_dir __vault_registry
    return 1 2>/dev/null || exit 1
fi

# Export each path in two forms:
#   VAULT_<UPPERCASE>       -> absolute path
#   VAULT_<UPPERCASE>_NAME  -> basename (folder name only)
while IFS=$'\t' read -r __vault_name __vault_path; do
    __vault_upper="$(echo "$__vault_name" | tr '[:lower:]' '[:upper:]')"
    __vault_var="VAULT_${__vault_upper}"
    __vault_var_name="VAULT_${__vault_upper}_NAME"
    __vault_basename="$(basename "$__vault_path")"
    export "$__vault_var=$__vault_path"
    export "$__vault_var_name=$__vault_basename"
done < <(jq -r '.paths | to_entries[] | "\(.key)\t\(.value)"' "$__vault_registry")

unset __vault_resolver_src __vault_resolver_dir __vault_registry \
      __vault_name __vault_path __vault_upper __vault_var __vault_var_name \
      __vault_basename
