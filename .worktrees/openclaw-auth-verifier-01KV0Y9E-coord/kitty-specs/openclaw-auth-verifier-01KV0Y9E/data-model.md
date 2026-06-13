# Phase 1 Data Model: OpenClaw Auth Verifier

**Mission**: `openclaw-auth-verifier-01KV0Y9E`
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

This phase documents the structured shapes the verifier produces internally and the on-disk substrates it reads. Implementation surface is Python dataclasses + JSON literals; no database schema is created (only existing OpenClaw SQLite is read).

---

## Entity: `Finding`

Structured verdict produced by `--check` for each detected condition. Single source of truth for both human-readable formatting and exit-code mapping.

```python
@dataclass(frozen=True)
class Finding:
    type: Literal[
        "shadow",                # Sub-agent has per-agent auth row(s) — overrides inheritance
        "drift",                 # Plaintext sha != main SQLite sha
        "anthropic_rejected",    # HTTP 401/403 from Anthropic ping
        "network",               # HTTP timeout, DNS, TLS failure
        "main_empty",            # main has no auth_profile_store row (rotation invariant broken)
        "plaintext_missing",     # /data/services/openclaw/secrets/anthropic absent
    ]
    target: str                  # Sub-agent ID for shadow; path for drift/plaintext_missing; "main" for main_empty; "anthropic" for *_rejected/network
    evidence: dict[str, str | int]   # Type-specific deterministic fields; NEVER contains key values
    suggested_action: str        # Single-line operator hint, copy-pasteable when possible
```

### Evidence shapes by type

| Finding type | Evidence keys | Notes |
|---|---|---|
| `shadow` | `agent`, `store_rows`, `state_rows`, `last_update_ms`, `sqlite_path` | `last_update_ms` is the max of the two tables' `updated_at` columns |
| `drift` | `plaintext_sha8`, `sqlite_sha8`, `plaintext_path`, `sqlite_path` | Both shas are sha256[:8] — eight hex chars; NEVER the full value |
| `anthropic_rejected` | `http_status`, `response_summary` | `response_summary` is the response's first 80 chars, scrubbed of any key-shape `sk-ant-` patterns |
| `network` | `error_class`, `error_message` | `error_message` is the exception's repr, scrubbed of any key-shape patterns |
| `main_empty` | `agent`, `sqlite_path` | Always `agent: "main"` |
| `plaintext_missing` | `plaintext_path` | Always `/data/services/openclaw/secrets/anthropic` |

### Invariants

- `evidence` MUST NOT contain any string of length ≥ 90 starting with `sk-ant-` (the Anthropic key prefix). Enforced by a `__post_init__` sanitization check.
- `suggested_action` MUST NOT contain any string matching the same pattern.
- `target` is always non-empty; `type` is always non-empty.

## Entity: `AgentAuthState`

Discovered for each `~/.openclaw/agents/<id>/agent/openclaw-agent.sqlite` glob match.

```python
@dataclass(frozen=True)
class AgentAuthState:
    agent_id: str                # e.g., "felix-admin-capture", "main"
    sqlite_path: pathlib.Path    # absolute
    store_rows: int              # COUNT(*) FROM auth_profile_store
    state_rows: int              # COUNT(*) FROM auth_profile_state
    last_update_ms: int          # MAX(updated_at) across both tables; 0 if both empty
    canonical_key_sha8: Optional[str]  # sha256[:8] of profiles.anthropic:default.key; None if agent has zero rows OR is not main
```

### Health verdicts (computed, not stored)

- `agent_id == "main"`: healthy iff `store_rows == 1 AND state_rows == 1`. Anything else triggers `main_empty` finding.
- `agent_id != "main"`: healthy iff `store_rows == 0 AND state_rows == 0`. Anything else triggers `shadow` finding.

## Entity: `PlaintextFileState`

Discovered from a single read of `/data/services/openclaw/secrets/anthropic`.

```python
@dataclass(frozen=True)
class PlaintextFileState:
    path: pathlib.Path
    exists: bool
    size_bytes: int              # 0 if not exists
    sha8: Optional[str]          # sha256[:8] of file contents (stripped); None if not exists
    mode: int                    # 0o600 expected; reported for diagnostic
    uid: int                     # claude expected; reported for diagnostic
    gid: int                     # claude expected; reported for diagnostic
```

### Health verdicts (computed, not stored)

- `not exists`: triggers `plaintext_missing` finding.
- `exists AND sha8 != main's canonical_key_sha8`: triggers `drift` finding.
- `exists AND sha8 == main's canonical_key_sha8`: clean.

## Entity: `AnthropicPingResult`

Single API call result.

```python
@dataclass(frozen=True)
class AnthropicPingResult:
    status: Literal["ok", "rejected", "network_error"]
    http_status: Optional[int]   # None for network errors
    model_echoed: Optional[str]  # The "model" field from response body when status="ok"
    error_summary: Optional[str] # Scrubbed first-80-chars when status != "ok"
```

### Source

POST to `https://api.anthropic.com/v1/messages` with body:
```json
{
    "model": "claude-haiku-4-5",
    "max_tokens": 8,
    "messages": [{"role": "user", "content": "ping"}]
}
```
Headers: `x-api-key: <plaintext file value>`, `anthropic-version: 2023-06-01`, `content-type: application/json`. Timeout: 5s connect + 15s total.

## Entity: `RotationManifest`

Written by `anthropic-rotate.sh` at rotation start; read by `anthropic-rotate.sh --rollback <ts>`.

```jsonc
// ~/.cache/anthropic-rotate/manifest.<unix-ts>.json
{
    "rotation_ts": 1734106823,
    "started_at_iso": "2026-06-13T17:00:23Z",
    "backups": {
        "plaintext_file": "/data/services/openclaw/secrets/anthropic.pre-rotate.1734106823.bak",
        "openclaw_json": "/home/claude/.openclaw/openclaw.json.bak",
        "sqlite_import_bak": "/home/claude/.openclaw/agents/main/agent/auth-profiles.json.sqlite-import.1734106823.bak"
    },
    "rotation_completed_at_iso": null,         // Filled at end-of-rotation
    "verify_outcome": null                     // "passed" | "failed:<finding-type>" | null if rolled back
}
```

### Lifecycle

- Created at the start of `anthropic-rotate.sh` (immediately after argument parsing).
- Updated at end-of-rotation with `verify_outcome` (or left null on rollback).
- Old manifests (> 30 days) are pruned by a future cleanup step (out of scope for this mission; deferred).

## Constants / Configuration

| Constant | Value | Where defined |
|---|---|---|
| `OPENCLAW_AGENTS_DIR` | `~/.openclaw/agents` | `scripts/security/anthropic_verify/core.py` |
| `PLAINTEXT_FILE` | `/data/services/openclaw/secrets/anthropic` | `scripts/security/anthropic_verify/core.py` |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | `scripts/security/anthropic_verify/core.py` |
| `ANTHROPIC_PING_MODEL` | `claude-haiku-4-5` | `scripts/security/anthropic_verify/core.py` |
| `ANTHROPIC_PING_MAX_TOKENS` | `8` | `scripts/security/anthropic_verify/core.py` |
| `URLLIB_CONNECT_TIMEOUT_SEC` | `5` | `scripts/security/anthropic_verify/core.py` |
| `URLLIB_TOTAL_TIMEOUT_SEC` | `15` | `scripts/security/anthropic_verify/core.py` |
| `SHA_FINGERPRINT_LEN` | `8` (hex chars) | `scripts/security/anthropic_verify/core.py` |
| `MANIFEST_DIR` | `~/.cache/anthropic-rotate` | `scripts/security/anthropic-rotate.sh` |

All constants are module-level; no runtime configuration is read from environment variables (per spec C-005's "no key in env" rule and to keep the verifier deterministic across invocations).
