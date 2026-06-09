# Contract: `probe_oauth_liveness()`

**Module**: `scripts/security/credential_health_check/liveness.py`

```python
def probe_oauth_liveness(
    credential: Credential,
    *,
    now_utc: Optional[datetime] = None,
) -> Optional[LivenessResult]: ...
```

## Inputs

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `credential` | `Credential` | yes | MUST have `credential.liveness_probe is not None` AND `credential.liveness_probe.enabled is True`. Caller (the orchestrator) is responsible for the filter; callee asserts and raises `ValueError` if violated. |
| `now_utc` | `Optional[datetime]` | no | Override for testing. Default: `datetime.now(timezone.utc)`. MUST be timezone-aware UTC if supplied. |

## Outputs

| Return | Meaning |
|---|---|
| `None` | Credential is alive — probe exited 0 with no `invalid_grant` in stderr. |
| `LivenessResult(classification="dead-routine-7day", ...)` | Probe failed with `invalid_grant` AND keyring mtime + 7d is within ±24h of now. Recovery command populated. |
| `LivenessResult(classification="dead-unexpected", ...)` | Probe failed with `invalid_grant` AND keyring mtime + 7d is NOT within ±24h of now. Recovery command populated. Unexpected-context note in `reason`. |
| `LivenessResult(classification="probe-error", ...)` | Probe could not complete (timeout, gog binary missing, env var missing, network down). Recovery command is `None`. |

## Side effects

NONE except:
- One subprocess call to `gog` (bounded by 15s timeout).
- One `Path.stat()` call against the keyring file (read-only).
- One structured log line at INFO (the probe writes `credential_alive` / `credential_dead` / `credential_probe_error` via `logging`).

NO file writes. NO network calls except the gog subprocess. NO GitHub API calls (orchestrator's job). NO Vikunja API calls. NO modifications to the credential or its config.

## Behavior

```
gog_account = credential.liveness_probe.gog_account
keyring_file = Path(credential.liveness_probe.keyring_file)
recovery_command = credential.liveness_probe.recovery_command

t0 = monotonic()
try:
    result = subprocess.run(
        [
            "/home/linuxbrew/.linuxbrew/bin/gog",
            "--account", gog_account,
            "calendar", "list",
            "-j",
            "--max-results", "1",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        env={"GOG_KEYRING_BACKEND": "file", "GOG_KEYRING_PASSWORD": ...},
    )
except subprocess.TimeoutExpired:
    return LivenessResult(
        credential_name=credential.name,
        classification="probe-error",
        reason="liveness probe exceeded 15s timeout",
        recovery_command=None,
        probed_at=now_utc or datetime.now(timezone.utc),
    )
except FileNotFoundError:
    return LivenessResult(... classification="probe-error", reason="gog binary not found at /home/linuxbrew/.linuxbrew/bin/gog", recovery_command=None, ...)

duration_ms = (monotonic() - t0) * 1000

if result.returncode == 0:
    log INFO credential_alive
    return None

if "invalid_grant" in result.stderr:
    mtime = datetime.fromtimestamp(keyring_file.stat().st_mtime, tz=timezone.utc)
    expected_expiration = mtime + timedelta(days=7)
    delta = abs((now_utc or datetime.now(timezone.utc)) - expected_expiration)
    if delta <= timedelta(hours=24):
        classification = "dead-routine-7day"
    else:
        classification = "dead-unexpected"
    return LivenessResult(...classification=classification, reason=..., recovery_command=recovery_command, ...)

# non-zero exit but NOT invalid_grant
return LivenessResult(... classification="probe-error", reason=f"gog exited {result.returncode}: {result.stderr.strip()[:200]}", recovery_command=None, ...)
```

## Tests (mandatory; covered by NFR-004 + NFR-005)

| Test | Setup | Expected |
|---|---|---|
| `test_alive_returns_none` | `subprocess.run` returns rc=0, empty stderr | `None` |
| `test_dead_routine_7day` | `subprocess.run` returns rc=1, stderr contains `invalid_grant`; mocked keyring mtime = now - 6.9 days | `classification == "dead-routine-7day"` |
| `test_dead_unexpected_too_early` | `subprocess.run` returns rc=1, stderr contains `invalid_grant`; mocked keyring mtime = now - 3 days | `classification == "dead-unexpected"` |
| `test_dead_unexpected_too_late` | `subprocess.run` returns rc=1, stderr contains `invalid_grant`; mocked keyring mtime = now - 9 days | `classification == "dead-unexpected"` |
| `test_routine_boundary_just_inside` | mocked keyring mtime = now - 7.0 days - 23h | `classification == "dead-routine-7day"` (within ±24h) |
| `test_routine_boundary_just_outside` | mocked keyring mtime = now - 7.0 days - 25h | `classification == "dead-unexpected"` |
| `test_probe_timeout` | `subprocess.run` raises `TimeoutExpired` | `classification == "probe-error"`, reason mentions "15s" |
| `test_probe_missing_binary` | `subprocess.run` raises `FileNotFoundError` | `classification == "probe-error"`, reason mentions "gog binary not found" |
| `test_probe_other_failure` | `subprocess.run` returns rc=2, stderr does NOT contain `invalid_grant` | `classification == "probe-error"`, reason mentions exit code 2 |
| `test_recovery_command_in_dead_result` | `dead-routine-7day` case | `result.recovery_command == credential.liveness_probe.recovery_command` |
| `test_recovery_command_none_in_probe_error` | `probe-error` case | `result.recovery_command is None` |
| `test_raises_if_liveness_probe_disabled` | `credential.liveness_probe.enabled is False` | Raises `ValueError` (caller filtered incorrectly) |
| `test_probed_at_is_utc` | any case | `result.probed_at.tzinfo == timezone.utc` |

Coverage gate: `pytest --cov=scripts.security.credential_health_check.liveness --cov-branch --cov-fail-under=90`.
