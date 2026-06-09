# Data Model — Credential Liveness Probe

**Mission**: `credential-liveness-probe-01KTP9M8`
**Phase**: 1 — Design

## New Entities

### `LivenessResult` (Python dataclass)

Returned by `probe_oauth_liveness()`. `None` is returned when the credential is alive; a populated `LivenessResult` is returned otherwise.

**Module**: `scripts/security/credential_health_check/liveness.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

LivenessClassification = Literal[
    "dead-routine-7day",
    "dead-unexpected",
    "probe-error",
]


@dataclass(frozen=True)
class LivenessResult:
    """Per-credential probe outcome. Returned only on failure or error.

    Alive credentials return None from probe_oauth_liveness(); this dataclass
    is never instantiated for healthy probes.
    """
    credential_name: str
    classification: LivenessClassification
    reason: str
    recovery_command: Optional[str]
    probed_at: datetime  # UTC; ISO 8601 when serialized
```

**Invariants**:
- `frozen=True` → immutable after construction; the orchestrator can pass it around without defensive copies.
- `reason` is human-readable and goes into the GitHub issue body verbatim.
- `recovery_command` is `None` only for `classification == "probe-error"` (since recovery is not "re-auth" when the probe itself failed). Always set for `dead-*` classifications, pulled from the manifest's `liveness_probe.recovery_command` field.
- `probed_at` is always UTC; serialized as ISO 8601 with `Z` suffix when written to logs or issue bodies.

**State transitions**: none — this is a value object. The same credential can produce a new `LivenessResult` on each probe; no continuity across instances.

---

## Modified Entities

### `Credential` (existing dataclass)

**Module**: `scripts/security/credential_health_check/manifest.py`

Add an optional attribute:

```python
@dataclass
class Credential:
    # ... existing fields unchanged ...
    liveness_probe: Optional[LivenessProbeConfig] = None
```

### `LivenessProbeConfig` (new nested dataclass)

```python
@dataclass(frozen=True)
class LivenessProbeConfig:
    enabled: bool
    gog_account: Optional[str]      # "kentgale@gmail.com" for the gog default
    keyring_file: Optional[str]     # absolute path; used for mtime → cycle classification
    recovery_command: str           # exact CLI command embedded in issue body
```

**Invariants**:
- When `enabled is True`, all of `gog_account`, `keyring_file`, `recovery_command` MUST be non-empty.
- When `enabled is False`, the other fields MAY be omitted (the credential is configured but liveness is paused).
- Schema is parsed strictly: unknown fields inside the `liveness_probe` block raise `ManifestQualityError` (per the existing manifest-quality pattern).

---

## Manifest schema extension

### Existing `credential-manifest.json` shape (excerpt)

```json
{
  "credentials": [
    {
      "name": "gog-credentials-keyring",
      "type": "managed-credential-store",
      "scope": "...",
      "storage": "/home/claude/.config/gogcli/credentials.json",
      ...
    }
  ]
}
```

### Extended shape (this mission)

```json
{
  "credentials": [
    {
      "name": "gog-credentials-keyring",
      "type": "managed-credential-store",
      "scope": "...",
      "storage": "/home/claude/.config/gogcli/credentials.json",
      "liveness_probe": {
        "enabled": true,
        "gog_account": "kentgale@gmail.com",
        "keyring_file": "/home/claude/.config/gogcli/keyring/_gogcli_key_v1_dG9rZW46ZGVmYXVsdDprZW50Z2FsZUBnbWFpbC5jb20",
        "recovery_command": "ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh"
      },
      ...
    }
  ]
}
```

**Backward compatibility**:
- Existing readers (cadence.py, listing.py, github_writer.py, vikunja_writer.py) iterate `credentials` and access named fields. They ignore the new block.
- Credentials WITHOUT a `liveness_probe` block parse cleanly into `Credential.liveness_probe = None` — the orchestrator's `_process_liveness_alert` then skips them.

---

## Filesystem dependencies

### Gog keyring file

Path: `/home/claude/.config/gogcli/keyring/_gogcli_key_v1_<base64>`

**Read access**: `stat().st_mtime` only. We never read content.

**Write access**: NONE from this mission. Only `gog auth add` writes here (during `gog-reauth.sh`).

**Mtime semantics**: Updated to current wall-clock UTC when `gog auth add ... --step 2` writes the new refresh token. This is the proxy for "token mint time" used by the routine-vs-unexpected classifier.

---

## Logged events (structured INFO)

Every probe invocation emits one of these structured log lines (one per credential per cycle):

| Event name | Fields | When |
|---|---|---|
| `credential_alive` | `cycle_id`, `credential_name`, `probed_at`, `duration_ms` | Probe returned None (healthy) |
| `credential_dead` | `cycle_id`, `credential_name`, `classification`, `probed_at`, `duration_ms`, `reason`, `recovery_command`, `github_issue_filed` (bool), `github_issue_number` (if filed) | Probe returned `dead-routine-7day` or `dead-unexpected` |
| `credential_probe_error` | `cycle_id`, `credential_name`, `probed_at`, `duration_ms`, `error_detail` | Probe couldn't complete (timeout, gog missing, etc.) |
| `liveness_skipped` | `cycle_id`, `credential_name`, `reason` | Credential has no `liveness_probe` block OR `liveness_probe.enabled is False` |
| `alert_deduped` (existing event, reused) | `cycle_id`, `credential_name`, `variant=liveness`, `existing_issue` | Probe failed but existing open issue matches the title prefix |
| `alert_would_file` (existing event, reused) | `cycle_id`, `credential_name`, `variant=liveness`, `classification` | `--dry-run --liveness-only` and probe failed |

**Output channel**: stdout (existing `logging.basicConfig` with structured formatter; identical to existing signals).

---

## GitHub issue title format

| Classification | Title prefix |
|---|---|
| `dead-routine-7day` | `credential-liveness-routine-7day: <credential_name>` |
| `dead-unexpected` | `credential-liveness-unexpected: <credential_name>` |

**Dedup rule**: `github_writer.dedup_check(title_prefix)` returns the first matching open issue. The two prefixes are different strings, so a routine issue is never deduped against an unexpected issue (per FR-009).

**Body shape** (per Decision 9):

```
Credential `<credential_name>` failed liveness probe at <probed_at>.

Classification: <classification>
Reason: <reason>

Recovery command:
ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh

After re-auth, the next probe cycle will confirm liveness. Close this issue manually after recovery (auto-close is a future-work item, see kitty-specs/credential-liveness-probe-01KTP9M8/spec.md §Future Work).
```

For `dead-unexpected`, an additional line precedes the recovery command:

```
If you didn't recently change passwords or revoke access, investigate at https://myaccount.google.com/permissions before re-auth.
```

---

## Systemd units (configuration entities)

### `credential-liveness-probe.service`

```ini
[Unit]
Description=credential-liveness-probe — 6h OAuth liveness probe (kentonium3/kg-automation#572)
After=network-online.target openclaw-gateway.service
Wants=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=2min
ExecStart=/usr/bin/python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json --liveness-only
Environment=HOME=/home/claude
Environment=PYTHONPATH=/home/claude/kg-automation/scripts/security
Environment=GOG_KEYRING_BACKEND=file
EnvironmentFile=/data/services/openclaw/secrets/openclaw-gateway.env
WorkingDirectory=/home/claude
```

`EnvironmentFile` is the same file `openclaw-gateway` uses; we need `GOG_KEYRING_PASSWORD` to invoke `gog` from the probe path.

### `credential-liveness-probe.timer`

```ini
[Unit]
Description=Timer: credential-liveness-probe (every 6 hours)

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
Persistent=true
Unit=credential-liveness-probe.service

[Install]
WantedBy=timers.target
```

---

## Out of scope for this data model

- No new tables, no new databases, no new files in `~/second-brain/`. The data model is in-memory (dataclass) + file-mtime-read + JSON manifest extension + systemd unit text.
- No persistence between cycles beyond what the systemd journal captures. The probe is stateless across invocations.
- No new schemas in `docs/design/architecture/data/` beyond the additive `liveness_probe` block in the existing `credential-manifest.json`.
