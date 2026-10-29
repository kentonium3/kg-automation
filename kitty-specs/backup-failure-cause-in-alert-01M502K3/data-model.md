# Data Model: Backup alerts name why the run failed

## Backup state pointer — new key

| Key | Type | Values | Written when |
|---|---|---|---|
| `failure_reason` | string or null | `"backup_mount_missing"`, `"repo_inaccessible"`, `"backup_failed"`, `"unclassified"`, or `null` | every run, by the EXIT trap |

**Invariants**
- `null` if and only if the script exited 0 (the run completed).
- A non-null value only from the fixed literal set above. The value is never derived from command output.
- Computing the value can't change the script's exit status, and can't stop the pointer from being written.
- `schema_version` stays `2`, because the key is additive and diagnostic-only.

## Key ledger — new optional member `cause`

```json
"cause": {
  "key": "failure_reason",
  "codes": {
    "backup_mount_missing": "backup drive /mnt/backups is not mounted",
    "repo_inaccessible": "restic repository could not be opened",
    "backup_failed": "restic backup command failed",
    "unclassified": "backup script exited early for an unclassified reason"
  }
}
```

**Rule 9 (validator)**
1. `cause` is an object with exactly the members `key` and `codes`.
2. `key` is a non-empty string that **is declared in `diagnostic_only`**. It is never adjudicated, because a cause must not decide health.
3. `codes` is a non-empty object. Each name matches `^[a-z][a-z0-9_]{0,63}$`. Each text is a non-empty string of at most 120 characters with no control characters.

## Evidence enrichment (runtime)

| Verdict from the ledger probe | Pointer `cause.key` value | Evidence |
|---|---|---|
| ok | anything | unchanged |
| unknown (not evaluable) | anything | unchanged |
| non-ok (unhealthy, stale, or explicit error) | absent, `null`, or not a string | unchanged |
| non-ok | string in `codes` | `<evidence>; cause: <declared text>` |
| non-ok | other string | `<evidence>; cause: unrecognised failure code` (a fixed marker; the raw value is never included) |
| any | ledger `cause` member malformed at runtime | unchanged (ignored; the evaluator does not raise) |

`ok`, `stale`, `evaluable` and `signal` on the `ProbeResult` are never altered.
