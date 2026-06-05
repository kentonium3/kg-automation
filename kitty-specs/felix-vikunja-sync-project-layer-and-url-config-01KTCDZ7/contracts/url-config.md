# Contract: URL Config (`scripts/common/vikunja_config.py`)

**Spec FRs**: FR-006, FR-007, FR-008, FR-010
**NFRs**: NFR-005, NFR-006
**New module**: `scripts/common/vikunja_config.py`

## Public API

```python
def get_vikunja_base_url() -> str:
    """Return the canonical Vikunja API base URL.

    Resolution order:
      1. VIKUNJA_BASE_URL environment variable, if set and non-empty
      2. Contents of /data/services/openclaw/config/vikunja-base-url.txt,
         stripped of whitespace

    Returns:
        URL with trailing slash, e.g., "https://office2.tail0f5f56.ts.net/api/v1/"

    Raises:
        VikunjaConfigError: if neither source is available. Error message
            names both expected locations.
    """
```

```python
class VikunjaConfigError(RuntimeError):
    """Raised when URL config cannot be resolved."""
```

## Configuration file format

**Path**: `/data/services/openclaw/config/vikunja-base-url.txt`
**Permissions**: `0644` (world-readable; not a secret)
**Owner**: `claude:claude`
**Directory**: `/data/services/openclaw/config/` (mode `0755`, owner `claude:claude`, created by deploy script)
**Format**: single line of UTF-8 text containing the base URL
**Validation**: must match `^https?://[^/]+/api/v1/?$` after whitespace strip. Trailing slash optional in the file; `get_vikunja_base_url()` returns the URL with a guaranteed trailing slash.

**Initial value**: `https://office2.tail0f5f56.ts.net/api/v1/` (per spec Assumptions — Tailscale HTTPS is canonical).

## Environment variable format

**Name**: `VIKUNJA_BASE_URL`
**Format**: same as file format (URL string)
**Exports**:
- `~/.bashrc` for the `claude` user on office2:
  ```bash
  export VIKUNJA_BASE_URL="$(cat /data/services/openclaw/config/vikunja-base-url.txt 2>/dev/null)"
  ```
- `/data/services/openclaw/secrets/openclaw-gateway.env` (systemd EnvironmentFile for `openclaw-gateway.service`):
  ```
  VIKUNJA_BASE_URL=https://office2.tail0f5f56.ts.net/api/v1/
  ```

Both exports derive from the file; the file is the single source of truth. A future operator change to the file requires re-sourcing `~/.bashrc` for interactive sessions and regenerating the env file + restarting `openclaw-gateway.service` (same pattern as `gog-keyring-password` rotation; see `docs/runbooks/credential-rotation-ops.md`).

## Helper semantics

- **Cache scope**: the function reads the env var / file on every call. Touchpoints call it once at module init; this scope is sufficient and avoids stale-cache concerns.
- **Trailing slash**: `get_vikunja_base_url()` ensures a trailing slash, so consumers can concatenate paths as `f"{base_url}tasks/all"` without conditional logic.
- **No retries on file read**: a transient filesystem error is a structured failure; consumer scripts exit non-zero per the no-silent-fallback contract.
- **Path traversal**: not applicable — the helper does not accept any input.

## Consumer migration pattern

Each runtime-path script (per FR-008) replaces its existing URL constant or argument with a call to `get_vikunja_base_url()` at module init. Example:

**Before**:
```python
VIKUNJA_BASE = "https://office2.tail0f5f56.ts.net/api/v1/"
```

**After**:
```python
from scripts.common.vikunja_config import get_vikunja_base_url
VIKUNJA_BASE = get_vikunja_base_url()
```

For scripts that take the URL as a CLI argument (e.g., `query_active_habits_v2.py --vikunja-base-url`), the CLI default value becomes `get_vikunja_base_url()` instead of a hardcoded constant. Explicit `--vikunja-base-url=<url>` arguments override the config (useful for testing).

## Test contract

Unit tests in `tests/test_vikunja_config.py` must verify:

1. Env var precedence: when `VIKUNJA_BASE_URL` is set, the file is not consulted.
2. File fallback: when the env var is unset, the file is read and returned.
3. Trailing-slash normalization: the function returns a URL with trailing slash regardless of whether the file/env has one.
4. Whitespace stripping: leading/trailing whitespace in the file is stripped.
5. Empty values: empty env var falls through to the file; empty file raises.
6. Both missing: raises `VikunjaConfigError` with a message naming both expected locations.
7. URL validation: a string that doesn't match the URL regex raises `VikunjaConfigError`.

Fixtures use `tmp_path` and `monkeypatch` (env var and the canonical file path via dependency injection or `monkeypatch.setattr`). No live HTTP; no live filesystem outside `tmp_path`.

## NFR-006 verification

Per spec NFR-006, after the FR-008 migration:

```bash
grep -rn "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/
```

returns only:
1. The path/value in `scripts/common/vikunja_config.py` (the config file path constant)
2. The 6 explicit FR-010 exclusions
3. Test fixtures in `tests/`

Any other hit is a regression.

## Out-of-scope scripts (FR-010 — deferred to follow-up)

The following scripts continue to use their existing URL handling and are NOT migrated in this mission:

- `scripts/vikunja/provision_felix_bot.py`
- `scripts/vikunja/validate_felix_bot.py`
- `scripts/vikunja/swap_vikunja_secrets.py`
- `scripts/vikunja/revoke_kent_tokens.py`
- `scripts/vikunja/setup_goals.py`
- `scripts/habits/migrate_schedule.py`
- `scripts/habits/query_active_habits.py` (v1, legacy)
- `scripts/security/credential_health_check/vikunja_writer.py`

A follow-up issue is filed from this mission to track their migration.
