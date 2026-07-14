# Contract: liveness probe classification (post-publish)

Supersedes the routine/unexpected split in
`kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md`
for the classification dimension. All other aspects of that contract (probe command,
timeout, alive→None, probe-error semantics) remain in force.

## Function

`probe_oauth_liveness(credential, *, now_utc=None) -> Optional[LivenessResult]`

Signature unchanged. Returns `None` when alive; a `LivenessResult` on failure/error.

## Classifications (closed set)

| Value | Meaning | recovery_command |
|-------|---------|------------------|
| `dead` | `gog` returned `invalid_grant` — the refresh token is no longer valid. Always actionable; re-auth required. | the credential's configured `recovery_command` |
| `probe-error` | The probe could not determine liveness (timeout, gog binary missing, or a non-`invalid_grant` non-zero exit). Not a credential-death signal. | `None` |

There is **no** `dead-routine-7day` or `dead-unexpected`. No 7-day cycle is
computed; `keyring_file` mtime is not consulted for classification.

## `dead` result requirements

- `classification == "dead"`.
- `reason` states the token failed the liveness probe (`invalid_grant`) and to run
  the recovery command. It MUST NOT reference a "7-day", "Testing-app", "cycle
  boundary", or baseline-source label.
- `recovery_command` equals the credential's configured `recovery_command`.
- `probed_at` is tz-aware UTC.

## Alert (orchestrator) requirements

- Exactly one issue per dead credential per dedup window.
- Title prefix: `credential-liveness-dead: <credential_name>`.
- Body includes the "investigate at https://myaccount.google.com/permissions"
  guidance unconditionally (every dead token is genuinely unexpected), plus the
  recovery command.
- Labels unchanged: `P1-bug`, `area/infrastructure`.

## Preserved (regression pins)

- rc=0 → `None` (alive), logged `credential_alive`.
- TimeoutExpired → `probe-error`, reason mentions the 15s timeout.
- gog binary missing → `probe-error`, reason "gog binary not found".
- non-`invalid_grant` non-zero exit → `probe-error`, reason includes the exit code.
- `enabled is False` → `ValueError`.
