"""HTTP wrapper for the Felix-Vikunja reconciliation driver.

Single typed entry point for every Vikunja HTTP call this mission makes.
Mirrors ``scripts/habits/record_completion.py:_http_request`` — same shape,
same error semantics, same docstring conventions.

This module is pure HTTP. No business logic. No state writes. No subprocess.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


HTTP_TIMEOUT_SECONDS = 10


def _http_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> tuple[int, Any]:
    """Issue an authenticated HTTP request via ``urllib``.

    Args:
        method: ``GET``, ``POST``, ``PUT``, ``DELETE``.
        url: Fully qualified URL.
        token: Vikunja bearer token.
        body: Optional dict — serialized to JSON if present.
        timeout: Per-call timeout in seconds (default ``HTTP_TIMEOUT_SECONDS``).

    Returns:
        Tuple ``(status_code, parsed_json_or_none)``. ``parsed_json_or_none``
        is ``None`` when the response body is empty or non-JSON.

    Raises:
        OSError: On network error, non-2xx HTTP status, or HTTPError. The
            message includes the method + URL + (when available) the server's
            error body so the operator can triage quickly.
    """
    data: bytes | None = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover -- purely defensive
            err_body = ""
        raise OSError(
            f"{method} {url} failed with HTTP {e.code}: {err_body!r}"
        ) from e
    except urllib.error.URLError as e:
        raise OSError(f"{method} {url} network failure: {e}") from e

    if status < 200 or status >= 300:
        raise OSError(f"{method} {url} returned HTTP {status}: {raw!r}")

    parsed: Any = None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Vikunja sometimes returns non-JSON body on success (rare).
            parsed = None
    return status, parsed


def get_json(url: str, token: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> Any:
    """GET ``url`` and return the parsed JSON body. Raises OSError on failure.

    Convenience wrapper around ``_http_request`` for read-only Vikunja calls.
    """
    _, parsed = _http_request("GET", url, token, timeout=timeout)
    return parsed


def post_json(
    url: str,
    token: str,
    body: dict,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> Any:
    """POST ``body`` to ``url`` and return the parsed JSON body.

    Convenience wrapper around ``_http_request``. The driver itself is
    read-only against Vikunja, but this helper is exported for cross-WP
    consistency in case a future capability adds write paths.
    """
    _, parsed = _http_request("POST", url, token, body=body, timeout=timeout)
    return parsed
