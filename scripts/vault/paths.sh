#!/usr/bin/env bash
# Vault path registry — shell resolver.
#
# Usage:
#   source scripts/vault/paths.sh
#   echo "$VAULT_INBOX"
#
# After sourcing, each logical name from paths.json is exported as
# VAULT_<UPPERCASE_NAME>. Example: "inbox" -> $VAULT_INBOX

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

# Export each path with VAULT_<UPPERCASE> prefix
while IFS=$'\t' read -r __vault_name __vault_path; do
    __vault_var="VAULT_$(echo "$__vault_name" | tr '[:lower:]' '[:upper:]')"
    export "$__vault_var=$__vault_path"
done < <(jq -r '.paths | to_entries[] | "\(.key)\t\(.value)"' "$__vault_registry")

unset __vault_resolver_src __vault_resolver_dir __vault_registry __vault_name __vault_path __vault_var
