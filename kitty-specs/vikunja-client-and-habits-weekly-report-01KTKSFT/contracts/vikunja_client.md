# Contract: `scripts/common/vikunja_client.py` — shared Vikunja HTTP client

**Mission**: `vikunja-client-and-habits-weekly-report-01KTKSFT` | **Spec FR**: FR-001/002 | **Data model**: [VikunjaClient](../data-model.md#entity-vikunjaclient-new-persistent-within-a-single-process)

## Purpose

Centralized Vikunja HTTP wrapper. First consumer: the new weekly helper. Future consumers: `scripts/sync/fetch.py`, `scripts/vikunja/*` (deliberate follow-up issues).

## Module structure

```python
# scripts/common/vikunja_client.py

class VikunjaError(Exception):
    """Base exception for all Vikunja-client failures."""
    path: str
    status: int | None

class VikunjaHttpError(VikunjaError): ...
class VikunjaAuthError(VikunjaHttpError): ...
class VikunjaNotFoundError(VikunjaHttpError): ...
class VikunjaBadRequestError(VikunjaHttpError): ...
class VikunjaServerError(VikunjaHttpError): ...
class VikunjaTimeoutError(VikunjaError): ...

class VikunjaClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None: ...

    def get(self, path: str, *, params: dict[str, str] | None = None,
            timeout: float | None = None) -> Any: ...
    def post(self, path: str, *, json: dict | None = None,
             params: dict[str, str] | None = None,
             timeout: float | None = None) -> Any: ...
    def put(self, path: str, *, json: dict | None = None,
            params: dict[str, str] | None = None,
            timeout: float | None = None) -> Any: ...
    def delete(self, path: str, *, params: dict[str, str] | None = None,
               timeout: float | None = None) -> Any: ...
```

## Behavior

### Construction

- `base_url=None`: read via `scripts.common.vikunja_config.get_vikunja_base_url()`. Strip trailing slash.
- `token=None`: read from `/data/services/openclaw/secrets/vikunja-api`. Strip surrounding whitespace.
- `timeout`: 30.0 by default; positive float.
- Constructor validates: base_url matches URL regex, token non-empty, timeout positive. Raises `ValueError` on validation failure.

### Request execution

- Compose URL: `f"{self.base_url}{path}"` (caller passes path beginning with `/`).
- If `params` is provided, urlencode + append as query string.
- Set headers: `Authorization: Bearer <token>`, `Content-Type: application/json` (for POST/PUT).
- For POST/PUT with `json` argument: serialize via `json.dumps(json).encode("utf-8")`; pass to `urllib.request.Request(..., data=body)`.
- Apply timeout to `urllib.request.urlopen(..., timeout=effective_timeout)`.
- On success: parse response body as JSON; return parsed object.

### Error mapping

| HTTP status / network condition | Exception class |
|---|---|
| 401 | `VikunjaAuthError(path=path, status=401)` |
| 404 | `VikunjaNotFoundError(path=path, status=404)` |
| 400 | `VikunjaBadRequestError(path=path, status=400)` |
| 5xx | `VikunjaServerError(path=path, status=<5xx>)` |
| Other non-2xx | `VikunjaHttpError(path=path, status=<code>)` |
| `socket.timeout` / `urllib.error.URLError` timeout | `VikunjaTimeoutError(path=path, status=None)` |
| `json.JSONDecodeError` on response body | `VikunjaServerError(path=path, status=<actual>)` (server returned non-JSON) |

### Redaction policy

- Default `__str__(exc)` returns `f"{type(exc).__name__}: {exc.path}"`. NO request body. NO response body.
- Exception instance carries `exc.verbose_message()` method that returns a more detailed string including response status text + truncated body (first 200 chars) — intended for ad-hoc operator debugging, never logged by default.

## Test fixtures (FR-011, FR-012)

The test suite uses `urlopen` mocked via the global guard in `tests/conftest.py`. Per-test fixtures provide canned responses:

| Fixture name | Scenario |
|---|---|
| `mock_response_200_json` | Happy-path GET; returns a sample tasks list. |
| `mock_response_401` | Token invalid. |
| `mock_response_404` | Project not found. |
| `mock_response_400` | Bad filter syntax. |
| `mock_response_500` | Vikunja down. |
| `mock_response_timeout` | Request times out. |
| `mock_response_non_json` | Server returned HTML or empty. |

## Usage example (from the new weekly helper)

```python
from scripts.common.vikunja_client import VikunjaClient, VikunjaError

client = VikunjaClient(timeout=10.0)
try:
    tasks = client.get(
        "/projects/13/tasks",
        params={"filter": "done=true", "per_page": "200"},
    )
except VikunjaError as exc:
    # Log redaction-safe message; let caller decide whether to retry / surface
    raise
```

## Out of scope for the client

- Retry policy (no built-in retries; caller retries if desired).
- Caching (clients are short-lived; the sync cache is a separate concern in mission #518 / #520).
- Pagination iteration helpers (caller handles `per_page` + `page` if needed).
- Async / await variants.
