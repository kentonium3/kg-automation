# Contract: Vault Path Registry Schema

**File:** `scripts/vault/paths.json`
**Inherited from:** Mission 024 (MVP)
**Modified by:** Mission 026 (extension to all paths)

## Schema

```json
{
  "version": 1,
  "updated": "YYYY-MM-DD",
  "paths": {
    "<logical_name>": "/absolute/physical/path"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | integer | yes | Schema version. Currently 1. Bumping requires a schema-migration mission. |
| `updated` | string (ISO date) | yes | Last-modified date. Informational only; not consumed by the resolver. |
| `paths` | object | yes | Map of logical name → absolute physical path. |
| `paths.<key>` | string | yes | Absolute path to the folder. No trailing slash. |

## Rules

1. **Logical names are lowercase, underscore-separated.** Examples: `inbox`, `inbox_processed`, `constitution`.
2. **Physical paths are absolute.** No `~`, no `$HOME`, no relative paths.
3. **Physical paths have no trailing slash.** `/home/kgale/second-brain/notes/01-Inbox`, not `/home/kgale/second-brain/notes/01-Inbox/`.
4. **`_private` is NEVER a key.** The privacy boundary path is deliberately excluded so that the resolver cannot return it under any circumstances.
5. **Adding a new logical name is a data change.** No code changes required — the resolver handles any key present in `paths`.

## Mission 026 required keys after WP01

```
system, inbox, inbox_processed, constitution, growth, health,
business, finance, journal, resources
```

Ten logical names total. Adding an eleventh (or removing one) is a subsequent-mission concern.

## Resolver contract

`scripts/vault/resolver.py` provides:

```python
def get_vault_path(name: str) -> str:
    """Return the absolute path for the given logical name.

    Raises UnknownPathError if name is not in the registry.
    Raises RegistryNotFoundError if the registry file is missing or malformed.
    """
```

`scripts/vault/paths.sh` provides shell exports:

```bash
source scripts/vault/paths.sh
# Exports $VAULT_INBOX, $VAULT_INBOX_PROCESSED, etc.
# Variable name = VAULT_<uppercase(logical_name)>
```

## Invariants

- `resolver.py` and `paths.sh` must agree on path values — they read the same registry file.
- `resolver.py` must raise `UnknownPathError` for any name not in `paths`.
- `paths.sh` must not export a variable for any name that is not in `paths` (no default fallbacks).
- The registry file must parse as valid JSON. Malformed JSON is a hard failure.

## Test-first acceptance checks (WP01 exit criteria)

- [ ] `python3 scripts/vault/resolver.py inbox` prints the current inbox path without error
- [ ] `python3 scripts/vault/resolver.py inbox_processed` prints the inbox-processed target path without error
- [ ] `python3 scripts/vault/resolver.py system` prints the system path without error
- [ ] `python3 scripts/vault/resolver.py _private` raises UnknownPathError (or equivalent non-zero exit)
- [ ] `python3 scripts/vault/resolver.py bogus_name` raises UnknownPathError
- [ ] `source scripts/vault/paths.sh && test -n "$VAULT_INBOX_PROCESSED"` passes
- [ ] All 10 required logical names are present in `paths.json`
- [ ] `paths.json` parses as valid JSON
