# Contract: Manifest `liveness_probe` Block

**File**: `docs/design/architecture/data/credential-manifest.json`

This contract defines the optional per-credential `liveness_probe` block. The block is additive; credentials without it are skipped from liveness with an INFO log.

## JSON Schema

```json
{
  "liveness_probe": {
    "type": "object",
    "required": ["enabled"],
    "properties": {
      "enabled": {
        "type": "boolean",
        "description": "Master switch. When false, the credential is configured for liveness but probes are paused."
      },
      "gog_account": {
        "type": "string",
        "format": "email",
        "description": "Required when enabled is true. The Google account email that gog uses for this credential (e.g., kentgale@gmail.com)."
      },
      "keyring_file": {
        "type": "string",
        "format": "absolute-path",
        "description": "Required when enabled is true. Absolute path to the gog keyring file whose mtime represents the last token-mint time."
      },
      "recovery_command": {
        "type": "string",
        "description": "Required when enabled is true. The exact shell command embedded in the GitHub issue body when a probe fails. Must be operator-runnable as a one-liner."
      }
    },
    "additionalProperties": false
  }
}
```

## Validation rules

1. If `liveness_probe` is absent → credential is silently skipped from liveness (INFO log: `liveness_skipped` with `reason="no liveness_probe block"`).
2. If `liveness_probe.enabled is false` → credential is silently skipped (INFO log: `liveness_skipped` with `reason="liveness_probe disabled"`).
3. If `liveness_probe.enabled is true` AND any of `gog_account` / `keyring_file` / `recovery_command` is missing or empty → manifest-quality error at parse time (raises during `__main__.py` startup, NOT silently skipped at runtime).
4. `additionalProperties: false` → unknown keys inside the block raise manifest-quality error. Prevents typo'd config from being silently ignored.
5. `recovery_command` is NOT validated for executability at parse time — it's an operator-owned string. Validation is at deploy-script smoke-test time (the deploy script will attempt the path).

## Initial value (this mission)

Only one credential gets the block in this mission:

```json
{
  "name": "gog-credentials-keyring",
  "type": "managed-credential-store",
  ...
  "liveness_probe": {
    "enabled": true,
    "gog_account": "kentgale@gmail.com",
    "keyring_file": "/home/claude/.config/gogcli/keyring/_gogcli_key_v1_dG9rZW46ZGVmYXVsdDprZW50Z2FsZUBnbWFpbC5jb20",
    "recovery_command": "ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh"
  }
}
```

## Future-additions guidance

For a future Workspace-internal migration (Option A path), the second credential (e.g., `gog-credentials-keyring-workspace`) gets its own block:

```json
{
  "name": "gog-credentials-keyring-workspace",
  ...
  "liveness_probe": {
    "enabled": true,
    "gog_account": "kent@intentional.biz",
    "keyring_file": "/home/claude/.config/gogcli/keyring/_gogcli_key_v1_<workspace-base64>",
    "recovery_command": "ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh --account kent@intentional.biz"
  }
}
```

The probe iterates all credentials with `liveness_probe.enabled is true`; adding records is sufficient — no code change needed.

## Tests

| Test | Setup | Expected |
|---|---|---|
| `test_parse_with_full_block` | Manifest has gog credential with all 4 fields | `Credential.liveness_probe.enabled is True`, all fields populated |
| `test_parse_without_block` | Manifest credential has no `liveness_probe` key | `Credential.liveness_probe is None` |
| `test_parse_with_disabled_block` | `enabled: false`, no other fields | Parses cleanly, `enabled is False` |
| `test_parse_enabled_missing_gog_account` | `enabled: true` but no `gog_account` | Raises `ManifestQualityError` |
| `test_parse_enabled_missing_keyring_file` | `enabled: true` but no `keyring_file` | Raises `ManifestQualityError` |
| `test_parse_enabled_missing_recovery_command` | `enabled: true` but no `recovery_command` | Raises `ManifestQualityError` |
| `test_parse_unknown_subkey_raises` | `liveness_probe.foo: "bar"` | Raises `ManifestQualityError` (per `additionalProperties: false`) |

Existing manifest tests STAY passing.
