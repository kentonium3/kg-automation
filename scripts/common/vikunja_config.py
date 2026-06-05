"""Vikunja URL config helper: canonical lookup for the Vikunja API base URL (mission #520).

This is the sole source of truth for the Vikunja API base URL across the codebase.
All runtime-path scripts must call ``get_vikunja_base_url()`` rather than hardcoding
a URL string.  See FR-006, FR-007, FR-008 in the mission spec and the contract at
``kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/contracts/url-config.md``.

Resolution order
----------------
1. ``VIKUNJA_BASE_URL`` environment variable, if set and non-empty
2. Contents of ``/data/services/openclaw/config/vikunja-base-url.txt``, whitespace-stripped

If neither is available, :exc:`VikunjaConfigError` is raised with a message naming
both expected sources.

Public surface
--------------
Constants: _CANONICAL_FILE_PATH (module-private, exposed for monkeypatching in tests)
Exceptions: VikunjaConfigError
Functions: get_vikunja_base_url
"""
from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = [
    "VikunjaConfigError",
    "get_vikunja_base_url",
]

_CANONICAL_FILE_PATH = Path("/data/services/openclaw/config/vikunja-base-url.txt")
_URL_REGEX = re.compile(r"^https?://[^/]+/api/v1/?$")


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
