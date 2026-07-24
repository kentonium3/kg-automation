"""Vikunja config helpers: canonical lookups for the Vikunja API base URL
(mission #520) **and** the Vikunja API token path
(mission vikunja-token-seam-kent-cutover-01KY8XQ0, phase 2 of #860).

This module is the sole source of truth for *how the Felix runtime reaches
Vikunja*: which URL it talks to (:func:`get_vikunja_base_url`) and which
credential it authenticates as (:func:`get_vikunja_token_path`). All
runtime-path scripts must call these helpers rather than hardcoding a URL
string or a token-file path. See FR-006/FR-007/FR-008 (#520) and FR-001/NFR-002
of the token-seam mission.

Base-URL resolution order
-------------------------
1. ``VIKUNJA_BASE_URL`` environment variable, if set and non-empty
2. Contents of ``/data/services/openclaw/config/vikunja-base-url.txt``, whitespace-stripped

If neither is available, :exc:`VikunjaConfigError` is raised with a message naming
both expected sources.

Token-path resolution order
---------------------------
1. ``VIKUNJA_TOKEN_PATH`` environment variable, if set and non-empty
2. The module default ``/data/services/openclaw/secrets/vikunja-api-kent``
   (the kent-owned runtime credential — the mission end-state)

This is the **single token-resolution point** (FR-001): ``VikunjaClient``'s
default-token loading resolves through it, and every runtime consumer routes
through it (directly or via the client), so the runtime Vikunja identity can
be changed at exactly one point with no per-consumer edit. A missing/unreadable
token file raises exactly one :exc:`VikunjaConfigError` (NFR-002), never N
divergent per-script messages.

Public surface
--------------
Constants: _CANONICAL_FILE_PATH, _DEFAULT_TOKEN_PATH (module-private, exposed
    for monkeypatching in tests)
Exceptions: VikunjaConfigError
Functions: get_vikunja_base_url, get_vikunja_token_path
"""
from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = [
    "VikunjaConfigError",
    "get_vikunja_base_url",
    "get_vikunja_token_path",
]

_CANONICAL_FILE_PATH = Path("/data/services/openclaw/config/vikunja-base-url.txt")
_URL_REGEX = re.compile(r"^https?://[^/]+/api/v1/?$")

#: Environment override for the token path (highest-precedence resolution source).
_TOKEN_PATH_ENV_VAR = "VIKUNJA_TOKEN_PATH"

#: The single canonical default Vikunja token path. This is the **kent-owned**
#: runtime credential — the token-seam mission's end-state (FR-003). The
#: felix-bot ``vikunja-api`` literal deliberately lives nowhere in the runtime
#: surface anymore (SC-001); it survives only as a dormant credential file on
#: office2. Exposed (underscore-prefixed) so tests may monkeypatch it.
_DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api-kent")


class VikunjaConfigError(RuntimeError):
    """Raised when URL config cannot be resolved.

    Possible causes:
    - Neither ``VIKUNJA_BASE_URL`` env var nor the canonical config file is present
    - The resolved value is empty
    - The resolved value does not match the expected URL pattern
    """


def get_vikunja_base_url() -> str:
    """Return the canonical Vikunja API base URL.

    Resolution order:
      1. VIKUNJA_BASE_URL environment variable, if set and non-empty
      2. Contents of ``/data/services/openclaw/config/vikunja-base-url.txt``,
         stripped of whitespace

    Returns:
        URL with trailing slash, e.g., ``"https://office2.tail0f5f56.ts.net/api/v1/"``

    Raises:
        VikunjaConfigError: if neither source is available, if the resolved value
            is empty, or if the value does not match a valid Vikunja API base URL
            pattern (``^https?://[^/]+/api/v1/?$``).
    """
    value = os.environ.get("VIKUNJA_BASE_URL", "").strip()

    if not value:
        # Env var is absent or empty — try the canonical file
        if not _CANONICAL_FILE_PATH.exists():
            raise VikunjaConfigError(
                f"Vikunja base URL not available. Set VIKUNJA_BASE_URL env var, "
                f"or create {_CANONICAL_FILE_PATH} with a single line containing the URL."
            )
        try:
            value = _CANONICAL_FILE_PATH.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise VikunjaConfigError(
                f"Vikunja base URL file at {_CANONICAL_FILE_PATH} could not be read: {exc}"
            ) from exc

    if not value:
        raise VikunjaConfigError(
            f"Vikunja base URL is empty "
            f"(env var VIKUNJA_BASE_URL and {_CANONICAL_FILE_PATH} both empty)."
        )

    if not _URL_REGEX.match(value):
        raise VikunjaConfigError(
            f"Vikunja base URL value {value!r} does not match expected pattern "
            f"(https?://<host>/api/v1[/])."
        )

    # Normalize: always return with trailing slash
    if not value.endswith("/"):
        value = value + "/"

    return value


def get_vikunja_token_path() -> Path:
    """Return the canonical filesystem path to the Vikunja API token file.

    This is the sole source of truth for *which* Vikunja credential the Felix
    runtime authenticates as (FR-001). Every runtime consumer resolves its token
    path here — directly, or via :class:`~scripts.common.vikunja_client.VikunjaClient`
    — so the runtime identity is a one-line change at exactly one point (the
    module default :data:`_DEFAULT_TOKEN_PATH`, or the ``VIKUNJA_TOKEN_PATH``
    override) with no per-consumer edit.

    Resolution order:
      1. ``VIKUNJA_TOKEN_PATH`` environment variable, if set and non-empty
      2. The module default ``/data/services/openclaw/secrets/vikunja-api-kent``
         (the kent-owned runtime credential).

    Returns:
        The resolved token-file path — guaranteed (at call time) to exist and be
        readable.

    Raises:
        VikunjaConfigError: if the resolved path does not exist or is not
            readable. This is the single fail-loud error (NFR-002); its message
            names both the ``VIKUNJA_TOKEN_PATH`` env var and the resolved path,
            so there are never N divergent per-script errors.
    """
    override = os.environ.get(_TOKEN_PATH_ENV_VAR, "").strip()
    if override:
        resolved = Path(override)
        source = f"the {_TOKEN_PATH_ENV_VAR} env var ({override!r})"
    else:
        resolved = _DEFAULT_TOKEN_PATH
        source = f"the module default ({_TOKEN_PATH_ENV_VAR} unset or empty)"

    if not resolved.is_file() or not os.access(resolved, os.R_OK):
        raise VikunjaConfigError(
            f"Vikunja token file not available at {resolved} (resolved from "
            f"{source}). Set {_TOKEN_PATH_ENV_VAR} to a readable token file, "
            f"or create {_DEFAULT_TOKEN_PATH}."
        )

    return resolved
