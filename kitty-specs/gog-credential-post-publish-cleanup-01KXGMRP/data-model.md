# Data Model: gog credential post-publish cleanup

No persistent data schema changes. The "model" here is the in-memory config +
result dataclasses in the credential-liveness probe.

## LivenessProbeConfig (`manifest.py`)

Per-credential liveness probe config parsed from `credential-manifest.json`.

| Field | Before | After |
|-------|--------|-------|
| `enabled: bool` | required | unchanged |
| `gog_account: Optional[str]` | required when enabled | unchanged |
| `keyring_file: Optional[str]` | required when enabled | unchanged (kept; no longer read by the probe) |
| `recovery_command: Optional[str]` | required when enabled | unchanged |
| `reauth_marker_glob: Optional[str]` | optional | **removed** |

- `allowed_keys` (unknown-key guard) drops `reauth_marker_glob`.
- Validation invariant unchanged: `enabled` ⇒ `gog_account`, `keyring_file`,
  `recovery_command` all present (else `ManifestQualityError`).
- **Atomicity**: the JSON config in `credential-manifest.json` must drop the
  `reauth_marker_glob` key in the same change (unknown-key rejection).

## LivenessClassification (`liveness.py`)

```
Before: Literal["dead-routine-7day", "dead-unexpected", "probe-error"]
After:  Literal["dead", "probe-error"]
```

## LivenessResult (`liveness.py`)

Fields unchanged: `credential_name`, `classification`, `reason`,
`recovery_command`, `probed_at` (tz-aware UTC). Only the set of possible
`classification` values changes (above), and `reason` text for the dead path no
longer references a 7-day / Testing-app cycle or a baseline source label.

## Probe decision table (`probe_oauth_liveness`)

| gog result | Before | After |
|-----------|--------|-------|
| rc=0 | alive → `None` | unchanged |
| `invalid_grant` in stderr, baseline within ±24h of keyring/reauth+7d | `dead-routine-7day` | **`dead`** (no baseline computed) |
| `invalid_grant` in stderr, baseline outside window | `dead-unexpected` | **`dead`** |
| `invalid_grant` in stderr, keyring missing/unreadable | `probe-error` (baseline unavailable) | **`dead`** (keyring not consulted) |
| TimeoutExpired | `probe-error` | unchanged |
| FileNotFoundError (gog binary) | `probe-error` | unchanged |
| non-zero rc, not `invalid_grant` | `probe-error` | unchanged |
| `enabled` is False | raises `ValueError` | unchanged |

## Removed symbols (`liveness.py`)

- `_resolve_cycle_baseline(cfg)`
- `CYCLE_WINDOW_HOURS`, `EXPECTED_TTL_DAYS`
- all `reauth_marker_glob` references
- `glob` / `timedelta` / `Path` imports if they become unused after removal

## Alert construction (`orchestrator.py`)

- `_build_liveness_issue_body`: the "investigate at myaccount.google.com/permissions"
  block becomes unconditional (was gated on `dead-unexpected`).
- `_process_liveness_alert`: title prefix `credential-liveness-{classification.removeprefix('dead-')}`
  → `credential-liveness-dead: <name>`; comment referencing the two old classes updated.
