"""Per-account OAuth credential loading for the Felix calendar helper.

This module generalizes the ``_load_or_mint`` / ``_write_token`` pattern proven
in ``scripts/google/workspace_auth_spike.py`` into a small, unit-testable auth
layer consumed by the calendar helper (WP02). It resolves **per-account**
credentials under ``~/.config/felix/google/<account>/`` and returns valid Google
``Credentials``, **failing safe** on any auth problem.

Design constraints (mission felix-calendar-helper, research D1/D5/D7):

- **No interactive consent here.** office2 is headless; the interactive mint
  (loopback consent flow) stays a Mac-side operator step. This module only
  *loads* an existing token and *refreshes* it in place. Any failure raises a
  typed :class:`CalendarAuthError` carrying an actionable "re-mint on the Mac"
  message — it never opens a browser or local server.
- **CI-safe imports.** ``google-api-python-client`` / ``google-auth`` /
  ``google-auth-oauthlib`` are NOT in ``requirements.txt`` (they live only in a
  dedicated office2 venv, research D3). So the google imports are done **lazily
  inside functions**; importing this module never requires the google packages.
- **Least privilege.** The default scope is ``calendar.events`` — sufficient for
  event CRUD and the bounded ``--self-check`` (research "Scope & auth-longevity").
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
    "CalendarAuthError",
    "SCOPES_DEFAULT",
    "DEFAULT_ACCOUNT",
    "credential_dir",
    "client_secret_path",
    "token_path",
    "load_credentials",
]

# Least-privilege scope for event CRUD + the bounded self-check
# (events().list(primary, maxResults=1)). Broader `calendar` scope is only
# needed for a calendars-list, which the helper deliberately avoids.
SCOPES_DEFAULT: list[str] = ["https://www.googleapis.com/auth/calendar.events"]

# Default credential home (override via FELIX_GOOGLE_DIR for test isolation and
# for staging alternate roots). Per-account subdirectories live beneath it.
DEFAULT_GOOGLE_DIR = Path.home() / ".config" / "felix" / "google"

# The account RFC #681 proved and Kent chose to develop against first.
DEFAULT_ACCOUNT = "personal"

# Account selector charset. Anchored, no path separators, no leading dot —
# blocks `../`, absolute paths, and other traversal attempts.
_ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class CalendarAuthError(Exception):
    """Raised when per-account credentials cannot be loaded or refreshed.

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


def load_credentials(
    account: str = DEFAULT_ACCOUNT,
    scopes: list[str] | None = None,
) -> "Credentials":
    """Load and (if needed) refresh per-account Google ``Credentials``.

    Behavior (research D7 fail-safe):

    - Load ``token.json`` if present; if the resulting credentials are already
      valid, return them unchanged.
    - If expired **and** a ``refresh_token`` is present, refresh in place,
      persist the refreshed token (atomic, ``0600``), and return.
    - On **any** failure — missing token, unreadable/invalid token, no
      ``refresh_token``, or a refresh error (``invalid_grant`` /
      ``RefreshError``) — raise :class:`CalendarAuthError` with an actionable
      re-mint message. **Never** runs an interactive consent flow (office2 is
      headless).

    :param account: credential-set selector (default ``personal``).
    :param scopes: OAuth scopes; defaults to :data:`SCOPES_DEFAULT`.
    :raises ValueError: if ``account`` fails the charset rule (usage error).
    :raises CalendarAuthError: on any auth failure (auth error, exit 3).
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
        raise CalendarAuthError(
            "google auth libraries are not installed in this interpreter; "
            "run the calendar helper under its dedicated venv "
            "(/data/services/openclaw/felix-calendar/venv on office2)"
        ) from exc

    scope_str = " ".join(scopes)
    tok = token_path(account)
    remint_hint = (
        f"re-mint token on the Mac for account {account!r} with scope "
        f"{scope_str} (interactive consent is never run on headless office2)"
    )

    if not tok.exists():
        raise CalendarAuthError(f"no token.json for account {account!r}: {remint_hint}")

    try:
        creds: Any = Credentials.from_authorized_user_file(str(tok), scopes)
    except (OSError, ValueError) as exc:
        raise CalendarAuthError(
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
            # no bad-credentials path ever reaches a calendar mutation.
            raise CalendarAuthError(
                f"token refresh failed for account {account!r} "
                f"({type(exc).__name__}: {exc}): {remint_hint}"
            ) from exc
        _write_token(creds, account)
        return creds

    # Token exists but is neither valid nor refreshable (missing refresh_token,
    # revoked, or otherwise unusable) — fail safe.
    raise CalendarAuthError(
        f"credentials for account {account!r} are invalid and not refreshable: "
        f"{remint_hint}"
    )
