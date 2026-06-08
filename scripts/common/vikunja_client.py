"""Shared Vikunja HTTP client (mission vikunja-client-and-habits-weekly-report-01KTKSFT).

Stateless, stdlib-only wrapper around Vikunja's REST API. Encapsulates base
URL composition, token loading, request execution, timeout policy, and
typed error semantics. First consumer is the new weekly habit-report
helper (WP02); future migrations of ``scripts/sync/fetch.py`` and
``scripts/vikunja/*`` are deliberate follow-up issues.

Per Felix Constitution Directive 6 this is the deterministic
infrastructure layer: no LLM, no global state, no caching. Each method is
a pure function of inputs to parsed JSON OR typed exception.

Authoritative contract:
``kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/vikunja_client.md``.

Public surface
--------------
Constants: ``DEFAULT_TOKEN_PATH``, ``DEFAULT_TIMEOUT``
Exceptions: ``VikunjaError``, ``VikunjaHttpError``, ``VikunjaAuthError``,
    ``VikunjaNotFoundError``, ``VikunjaBadRequestError``,
    ``VikunjaServerError``, ``VikunjaTimeoutError``
Class: ``VikunjaClient``

Redaction policy (FR-011, FR-012)
---------------------------------
Default ``str(exc)`` returns ``"<ExceptionClass>: <path>"`` only — never
response body content. ``exc.verbose_message()`` returns the longer
representation including the status code; intended for ad-hoc debugging,
never logged by default.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_TOKEN_PATH",
    "DEFAULT_TIMEOUT",
    "VikunjaError",
    "VikunjaHttpError",
    "VikunjaAuthError",
    "VikunjaNotFoundError",
    "VikunjaBadRequestError",
    "VikunjaServerError",
    "VikunjaTimeoutError",
    "VikunjaClient",
]

DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
DEFAULT_TIMEOUT = 30.0

_BASE_URL_PATTERN = re.compile(r"^https?://[^/]+/api/v1$")


# ---------------------------------------------------------------------------
# Exception hierarchy (per data-model.md + contracts/vikunja_client.md)
# ---------------------------------------------------------------------------


class VikunjaError(Exception):
    """Base exception for all Vikunja-client failures.

    Carries ``path`` (the request path that triggered the error) and
    ``status`` (HTTP status code, or None for network-layer failures like
    timeouts).

    Default ``str(exc)`` redacts response body content per FR-012 — only
    the class name and the request path appear. Use
    :meth:`verbose_message` for ad-hoc debugging.
    """

    def __init__(self, path: str, status: int | None = None) -> None:
        self.path = path
        self.status = status
        super().__init__(f"{type(self).__name__}: {path}")

    def verbose_message(self) -> str:
        """Detailed representation for ad-hoc operator debugging.

        Includes status code; never logged by default.
        """
        return f"{type(self).__name__}(path={self.path!r}, status={self.status!r})"


class VikunjaHttpError(VikunjaError):
    """Base for HTTP-status-derived failures (non-2xx that don't match a specific subclass)."""


class VikunjaAuthError(VikunjaHttpError):
    """HTTP 401 — token expired or invalid."""


class VikunjaNotFoundError(VikunjaHttpError):
    """HTTP 404 — resource not found."""


class VikunjaBadRequestError(VikunjaHttpError):
    """HTTP 400 — malformed request (e.g. invalid filter syntax)."""


class VikunjaServerError(VikunjaHttpError):
    """HTTP 5xx, network-layer URL errors that are not timeouts, and non-JSON response bodies."""


class VikunjaTimeoutError(VikunjaError):
    """Request exceeded the timeout budget (socket.timeout or URLError(timeout))."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class VikunjaClient:
    """Stdlib-only HTTP wrapper around Vikunja's REST API.

    Stateless per-instance: each instantiation captures ``base_url``,
    ``token``, ``timeout`` at construct time. No retries, no caching, no
    pagination iteration helpers — callers handle those concerns.

    Parameters are keyword-only to keep the contract self-documenting.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if base_url is None:
            from scripts.common.vikunja_config import get_vikunja_base_url

            base_url = get_vikunja_base_url()
        normalized_base_url = base_url.rstrip("/")
        if not _BASE_URL_PATTERN.match(normalized_base_url):
            raise ValueError(
                f"Invalid Vikunja base_url {base_url!r}: expected "
                f"https?://<host>/api/v1[/]"
            )

        if token is None:
            token = self._load_default_token()
        token = token.strip()
        if not token:
            raise ValueError("Vikunja token must be a non-empty string")

        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError(f"Vikunja timeout must be positive, got {timeout!r}")

        self.base_url = normalized_base_url
        self.token = token
        self.timeout = float(timeout)

    @staticmethod
    def _load_default_token() -> str:
        try:
            return DEFAULT_TOKEN_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(
                f"Vikunja token file {DEFAULT_TOKEN_PATH} could not be read: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public HTTP surface
    # ------------------------------------------------------------------

    def get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("GET", path, params=params, json_body=None, timeout=timeout)

    def post(
        self,
        path: str,
        *,
        json: dict | None = None,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("POST", path, params=params, json_body=json, timeout=timeout)

    def put(
        self,
        path: str,
        *,
        json: dict | None = None,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("PUT", path, params=params, json_body=json, timeout=timeout)

    def delete(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("DELETE", path, params=params, json_body=None, timeout=timeout)

    # ------------------------------------------------------------------
    # Private request execution + error mapping
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None,
        json_body: dict | None,
        timeout: float | None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        headers = {"Authorization": f"Bearer {self.token}"}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        effective_timeout = timeout if timeout is not None else self.timeout
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as response:
                body = response.read()
        except socket.timeout:
            raise VikunjaTimeoutError(path=path, status=None) from None
        except urllib.error.HTTPError as exc:
            raise self._map_http_error(path, exc.code) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise VikunjaTimeoutError(path=path, status=None) from None
            raise VikunjaServerError(path=path, status=None) from None

        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise VikunjaServerError(path=path, status=200) from None

    @staticmethod
    def _map_http_error(path: str, status: int) -> VikunjaHttpError:
        if status == 401:
            return VikunjaAuthError(path=path, status=status)
        if status == 404:
            return VikunjaNotFoundError(path=path, status=status)
        if status == 400:
            return VikunjaBadRequestError(path=path, status=status)
        if 500 <= status < 600:
            return VikunjaServerError(path=path, status=status)
        return VikunjaHttpError(path=path, status=status)
