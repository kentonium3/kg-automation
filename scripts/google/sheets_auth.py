"""Per-account OAuth credential loading for the Felix Sheets helper.

This module is the Sheets-scoped sibling of ``scripts/google/calendar_auth.py``
(mission felix-calendar-helper, #699). It reuses the same per-account OAuth
substrate to resolve **per-account** credentials under
``~/.config/felix/google/<account>/`` and return valid Google ``Credentials``,
**failing safe** on any auth problem.

Design constraints (mission felix-time-logging, contract C3, deploy gotcha #3):

- **No interactive consent here.** office2 is headless; the interactive mint
  (loopback consent flow) stays a Mac-side operator step. This module only
  *loads* an existing token and *refreshes* it in place. Any failure raises a
  typed :class:`SheetsAuthError` carrying an actionable "re-mint on the Mac"
  message — it never opens a browser or local server.
- **CI-safe imports.** ``google-api-python-client`` / ``google-auth`` /
  ``google-auth-oauthlib`` are NOT in ``requirements.txt`` (they live only in a
  dedicated office2 venv). So the google imports are done **lazily inside
  functions**; importing this module never requires the google packages.
- **Least privilege.** The default scope is ``spreadsheets`` — sufficient for
  the time-logging append/read workflow.
- **Load WITHOUT forcing scopes (deploy gotcha #3).** The token is loaded via
  ``Credentials.from_authorized_user_file(str(tok))`` using whatever scopes the
  token was actually minted with — ``scopes=`` is never passed into the loader
  or the refresh call. Forcing a scope that differs from what the token was
  minted with makes the refresh fail ``invalid_scope``. The ``personal`` token
  is re-minted once (out of band, at deploy) with the combined
  ``calendar + spreadsheets`` scopes; because this loader (and the calendar
  loader) are scope-agnostic at runtime, the combined token loads cleanly for
  both. ``SCOPES_DEFAULT`` is advisory only — used in the re-mint hint message,
  never forced at load/refresh.
- **Secrets never printed.** Token contents are never logged or returned as
  strings; writes are atomic (temp + ``os.replace``) with ``0600`` perms.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from google.oauth2.credentials import Credentials

__all__ = [
    "SheetsAuthError",
    "SCOPES_DEFAULT",
    "DEFAULT_ACCOUNT",
    "credential_dir",
    "client_secret_path",
    "token_path",
    "load_sheets_credentials",
]

# Least-privilege scope for the time-logging Sheets append/read workflow.
SCOPES_DEFAULT: list[str] = ["https://www.googleapis.com/auth/spreadsheets"]

# Default credential home (override via FELIX_GOOGLE_DIR for test isolation and
# for staging alternate roots). Per-account subdirectories live beneath it.
DEFAULT_GOOGLE_DIR = Path.home() / ".config" / "felix" / "google"

# The account RFC #681 proved and Kent chose to develop against first.
DEFAULT_ACCOUNT = "personal"

# Account selector charset. Anchored, no path separators, no leading dot —
# blocks `../`, absolute paths, and other traversal attempts.
_ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SheetsAuthError(Exception):
    """Raised when per-account Sheets credentials cannot be loaded or refreshed.

    Carries an actionable, operator-facing message telling Kent to re-mint the
    token on the Mac (never interactive on headless office2). The consuming
    helper maps this to exit code 3 (auth failure), distinct from usage (2) and
    operational/API errors (1).
    """


def _google_dir() -> Path:
    """Resolve the credential home, honoring ``FELIX_GOOGLE_DIR``.

    Read at call time (not import time) so tests can point it at a tmp dir via
    ``monkeypatch.setenv`` before invoking these helpers.
    """
    override = os.environ.get("FELIX_GOOGLE_DIR")
    return Path(override) if override else DEFAULT_GOOGLE_DIR


def _validate_account(account: str) -> str:
    """Return ``account`` if it satisfies the charset rule, else raise.

    :raises ValueError: on any name that could enable path traversal (the helper
        maps this to exit 2 / usage error).
    """
    if not _ACCOUNT_RE.match(account):
        raise ValueError(
            f"invalid account name {account!r}: must match "
            f"{_ACCOUNT_RE.pattern} (lowercase alphanumeric, '_' and '-'; "
            "no path separators or leading dot)"
        )
    return account


def credential_dir(account: str = DEFAULT_ACCOUNT) -> Path:
    """Return the per-account credential directory.

    ``FELIX_GOOGLE_DIR`` (default ``~/.config/felix/google``) ``/ <account>``.

    :raises ValueError: if ``account`` fails the charset rule.
    """
    return _google_dir() / _validate_account(account)


def client_secret_path(account: str = DEFAULT_ACCOUNT) -> Path:
    """Return the per-account ``client_secret.json`` path (operator-staged)."""
    return credential_dir(account) / "client_secret.json"


def token_path(account: str = DEFAULT_ACCOUNT) -> Path:
    """Return the per-account ``token.json`` path (authorized-user token)."""
    return credential_dir(account) / "token.json"


def _write_token(creds: "Credentials", account: str) -> None:
    """Persist ``creds`` atomically to the per-account token path.

    Directory is created ``0700``, the token file is written via a temp file in
    the same directory then ``os.replace``d into place and ``chmod``ed ``0600``.
    Token contents are never printed.
    """
    cred_dir = credential_dir(account)
    cred_dir.mkdir(parents=True, exist_ok=True)
    cred_dir.chmod(0o700)

    dest = token_path(account)
    tmp = dest.with_name(dest.name + ".tmp")
    # Write, restrict, then atomically swap so a reader never sees a partial
    # file and the token never transiently exists world-readable.
    tmp.write_text(creds.to_json())
    tmp.chmod(0o600)
    os.replace(tmp, dest)
    dest.chmod(0o600)


def load_sheets_credentials(
    account: str = DEFAULT_ACCOUNT,
    scopes: list[str] | None = None,
) -> "Credentials":
    """Load and (if needed) refresh per-account Google ``Credentials``.

    Behavior (fail-safe):

    - Load ``token.json`` if present; if the resulting credentials are already
      valid, return them unchanged.
    - If expired **and** a ``refresh_token`` is present, refresh in place,
      persist the refreshed token (atomic, ``0600``), and return.
    - On **any** failure — missing token, unreadable/invalid token, no
      ``refresh_token``, or a refresh error (``invalid_grant`` /
      ``RefreshError``) — raise :class:`SheetsAuthError` with an actionable
      re-mint message. **Never** runs an interactive consent flow (office2 is
      headless).

    :param account: credential-set selector (default ``personal``).
    :param scopes: recommended *mint-time* scopes (advisory; defaults to
        :data:`SCOPES_DEFAULT`). Used only in the re-mint hint — the token's own
        granted scopes are used for load/refresh at runtime.
    :raises ValueError: if ``account`` fails the charset rule (usage error).
    :raises SheetsAuthError: on any auth failure (auth error, exit 3).
    """
    scopes = list(scopes) if scopes is not None else list(SCOPES_DEFAULT)
    # Validate the account name first (raises ValueError → exit 2) before any
    # filesystem or google-library work.
    account = _validate_account(account)

    # Lazy imports: keep module import CI-safe when the google packages (which
    # live only in the office2 venv) are absent. Tests inject fakes via
    # sys.modules before importing this module.
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # pragma: no cover - env-specific import guard
        raise SheetsAuthError(
            "google auth libraries are not installed in this interpreter; "
            "run the Sheets helper under its dedicated venv "
            "(/data/services/openclaw/felix-calendar/venv on office2)"
        ) from exc

    scope_str = " ".join(scopes)
    tok = token_path(account)
    remint_hint = (
        f"re-mint token on the Mac for account {account!r} with scope "
        f"{scope_str} (interactive consent is never run on headless office2)"
    )

    if not tok.exists():
        raise SheetsAuthError(f"no token.json for account {account!r}: {remint_hint}")

    try:
        # Load with the token's OWN granted scopes — do NOT force ``scopes``.
        # Forcing a scope that differs from what the token was minted with makes
        # the refresh fail ``invalid_scope`` (deploy gotcha #3). Least-privilege
        # is a mint-time choice (``SCOPES_DEFAULT`` is the recommended mint scope in
        # the re-mint hint); at runtime the helper uses whatever was granted and
        # fails safe (exit 3 / API 403) if a needed operation isn't permitted.
        creds: Any = Credentials.from_authorized_user_file(str(tok))
    except (OSError, ValueError) as exc:
        raise SheetsAuthError(
            f"could not read credentials for account {account!r} "
            f"({exc}): {remint_hint}"
        ) from exc

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001 - any refresh failure is fatal here
            # google.auth.exceptions.RefreshError (e.g. invalid_grant) is the
            # common case, but treat *any* refresh failure as an auth failure so
            # no bad-credentials path ever reaches a Sheets mutation.
            raise SheetsAuthError(
                f"token refresh failed for account {account!r} "
                f"({type(exc).__name__}: {exc}): {remint_hint}"
            ) from exc
        _write_token(creds, account)
        return creds

    # Token exists but is neither valid nor refreshable (missing refresh_token,
    # revoked, or otherwise unusable) — fail safe.
    raise SheetsAuthError(
        f"credentials for account {account!r} are invalid and not refreshable: "
        f"{remint_hint}"
    )
