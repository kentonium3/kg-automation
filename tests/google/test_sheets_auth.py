"""Unit tests for ``scripts.google.sheets_auth`` (mission WP01).

CI-safe by construction: the real ``google-*`` packages are NOT installed here
or in CI (they live only in the office2 venv). These tests inject fakes into
``sys.modules`` for ``google``, ``google.oauth2.credentials``, and
``google.auth.transport.requests`` **before** importing the module under test,
so nothing requires the real libraries and no test touches the network. The
module's google imports are lazy (inside ``load_sheets_credentials``), so the
fakes are resolved at call time.

Canonical invocation (repo threshold 90):

    pytest tests/google/test_sheets_auth.py \
        --cov=scripts.google.sheets_auth --cov-branch --cov-fail-under=90

Covers:
- valid token → returned unchanged;
- expired-but-refreshable → ``refresh`` called + persisted;
- refresh failure → ``SheetsAuthError`` (no interactive flow attempted);
- missing token → ``SheetsAuthError`` with re-mint message;
- malformed/unreadable token → ``SheetsAuthError``;
- account path resolution honors ``FELIX_GOOGLE_DIR``; bad account → ``ValueError``;
- persisted token file perms are ``0600`` (and dir ``0700``);
- load never forces a scope onto ``from_authorized_user_file``.
"""
from __future__ import annotations

import importlib
import stat
import sys
import types
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# Fake google libraries — injected into sys.modules before importing the SUT.
# --------------------------------------------------------------------------- #


class _RefreshError(Exception):
    """Stand-in for ``google.auth.exceptions.RefreshError`` (e.g. invalid_grant)."""


class _FakeRequest:
    """Stand-in for ``google.auth.transport.requests.Request`` (transport)."""


class _FakeCredentials:
    """Minimal ``Credentials`` double.

    Records whether ``refresh`` was called and exposes the ``valid`` /
    ``expired`` / ``refresh_token`` surface that ``load_sheets_credentials``
    inspects. ``from_authorized_user_file`` is monkeypatched per-test to return
    a configured instance (or raise), so the file's actual contents are
    irrelevant.
    """

    def __init__(
        self,
        *,
        valid: bool = True,
        expired: bool = False,
        refresh_token: str | None = "rt-xyz",
        refresh_exc: Exception | None = None,
    ) -> None:
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self._refresh_exc = refresh_exc
        self.refresh_called = False

    def refresh(self, request: object) -> None:
        self.refresh_called = True
        assert isinstance(request, _FakeRequest)
        if self._refresh_exc is not None:
            raise self._refresh_exc
        # A successful refresh flips the credentials to valid.
        self.valid = True
        self.expired = False

    def to_json(self) -> str:
        return '{"token": "REDACTED-should-never-be-printed"}'

    @classmethod
    def from_authorized_user_file(cls, *args, **kwargs):  # pragma: no cover
        # Default loader; each test monkeypatches this to return a configured
        # instance (or raise). Defined so ``monkeypatch.setattr`` has an existing
        # attribute to override and restore.
        raise AssertionError("from_authorized_user_file should be patched per-test")


def _install_fake_google(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register fake google.* modules in ``sys.modules``."""
    google_mod = types.ModuleType("google")

    oauth2_mod = types.ModuleType("google.oauth2")
    creds_mod = types.ModuleType("google.oauth2.credentials")
    creds_mod.Credentials = _FakeCredentials  # type: ignore[attr-defined]

    auth_mod = types.ModuleType("google.auth")
    transport_mod = types.ModuleType("google.auth.transport")
    requests_mod = types.ModuleType("google.auth.transport.requests")
    requests_mod.Request = _FakeRequest  # type: ignore[attr-defined]
    exceptions_mod = types.ModuleType("google.auth.exceptions")
    exceptions_mod.RefreshError = _RefreshError  # type: ignore[attr-defined]

    for name, mod in {
        "google": google_mod,
        "google.oauth2": oauth2_mod,
        "google.oauth2.credentials": creds_mod,
        "google.auth": auth_mod,
        "google.auth.transport": transport_mod,
        "google.auth.transport.requests": requests_mod,
        "google.auth.exceptions": exceptions_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)


@pytest.fixture()
def sheets_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Import ``scripts.google.sheets_auth`` with fake google libs installed.

    ``FELIX_GOOGLE_DIR`` points at an isolated tmp dir so no real credential
    home is touched. The module is (re)loaded fresh so import happens under the
    fakes.
    """
    _install_fake_google(monkeypatch)
    monkeypatch.setenv("FELIX_GOOGLE_DIR", str(tmp_path))
    module = importlib.import_module("scripts.google.sheets_auth")
    module = importlib.reload(module)
    return module


def _seed_token(module, account: str = "personal") -> Path:
    """Create a placeholder token.json (contents irrelevant — file is faked)."""
    tok = module.token_path(account)
    tok.parent.mkdir(parents=True, exist_ok=True)
    tok.write_text("{}")
    return tok


# --------------------------------------------------------------------------- #
# Path resolution + guards (T001)
# --------------------------------------------------------------------------- #


def test_scopes_default_is_spreadsheets(sheets_auth):
    assert sheets_auth.SCOPES_DEFAULT == [
        "https://www.googleapis.com/auth/spreadsheets"
    ]


def test_credential_dir_honors_felix_google_dir(sheets_auth, tmp_path):
    assert sheets_auth.credential_dir("personal") == tmp_path / "personal"
    assert sheets_auth.credential_dir() == tmp_path / "personal"  # default account


def test_credential_dir_custom_account(sheets_auth, tmp_path):
    assert sheets_auth.credential_dir("intentional") == tmp_path / "intentional"


def test_client_secret_and_token_paths(sheets_auth, tmp_path):
    assert sheets_auth.client_secret_path("personal") == (
        tmp_path / "personal" / "client_secret.json"
    )
    assert sheets_auth.token_path("personal") == tmp_path / "personal" / "token.json"


@pytest.mark.parametrize(
    "bad",
    [
        "../evil",
        "/abs/path",
        "-leading-dash",
        "_leading-underscore",
        "Upper",
        "has space",
        "dot.name",
        "",
        "a/b",
    ],
)
def test_bad_account_name_raises_value_error(sheets_auth, bad):
    with pytest.raises(ValueError):
        sheets_auth.credential_dir(bad)


@pytest.mark.parametrize("good", ["personal", "intentional", "a", "a1_b-2", "0start"])
def test_good_account_names_accepted(sheets_auth, tmp_path, good):
    assert sheets_auth.credential_dir(good) == tmp_path / good


def test_load_credentials_rejects_bad_account(sheets_auth):
    with pytest.raises(ValueError):
        sheets_auth.load_sheets_credentials("../evil")


# --------------------------------------------------------------------------- #
# Load / refresh / persist + fail-safe (T002)
# --------------------------------------------------------------------------- #


def test_valid_token_returned_unchanged(sheets_auth, monkeypatch):
    creds = _FakeCredentials(valid=True, expired=False)
    _seed_token(sheets_auth)
    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *a, **k: creds),
    )

    result = sheets_auth.load_sheets_credentials("personal")

    assert result is creds
    assert result.refresh_called is False


def test_load_uses_token_own_scopes_not_forced(sheets_auth, monkeypatch):
    """Regression (deploy gotcha #3): load_sheets_credentials must NOT force a
    scope onto ``from_authorized_user_file``. A token minted with a combined
    ``calendar + spreadsheets`` scope otherwise fails refresh with
    ``invalid_scope`` if the helper forces ``spreadsheets`` only. The loader
    gets only the token path; the token's own granted scopes drive the
    refresh."""
    captured: dict = {}
    creds = _FakeCredentials(valid=True, expired=False)

    def fake_from_file(*a, **k):
        captured["args"] = a
        captured["kwargs"] = k
        return creds

    _seed_token(sheets_auth)
    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(fake_from_file),
    )

    sheets_auth.load_sheets_credentials(
        "personal", scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )

    # Only the token path is passed — no scopes list forced onto the loader.
    assert len(captured["args"]) == 1
    assert "scopes" not in captured["kwargs"]
    assert not any(isinstance(x, list) for x in captured["args"])


def test_expired_refreshable_token_is_refreshed_and_persisted(sheets_auth, monkeypatch):
    creds = _FakeCredentials(valid=False, expired=True, refresh_token="rt-xyz")
    _seed_token(sheets_auth)
    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *a, **k: creds),
    )

    result = sheets_auth.load_sheets_credentials("personal")

    assert result is creds
    assert result.refresh_called is True
    # Refreshed token was persisted to the per-account path.
    assert sheets_auth.token_path("personal").exists()


def test_refresh_error_raises_sheets_auth_error_no_interactive(sheets_auth, monkeypatch):
    refresh_err = _RefreshError("invalid_grant: Token has been expired or revoked.")
    creds = _FakeCredentials(
        valid=False, expired=True, refresh_token="rt-dead", refresh_exc=refresh_err
    )
    _seed_token(sheets_auth)
    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *a, **k: creds),
    )
    # Fail loudly if any interactive-flow entry point is ever reached.
    monkeypatch.setitem(
        sys.modules,
        "google_auth_oauthlib.flow",
        _no_interactive_module(),
    )

    with pytest.raises(sheets_auth.SheetsAuthError) as excinfo:
        sheets_auth.load_sheets_credentials("personal")

    assert creds.refresh_called is True  # refresh attempted, then failed
    assert "re-mint token on the Mac" in str(excinfo.value)


def test_missing_token_raises_sheets_auth_error_with_remint(sheets_auth):
    # No token seeded for this account.
    with pytest.raises(sheets_auth.SheetsAuthError) as excinfo:
        sheets_auth.load_sheets_credentials("personal")
    msg = str(excinfo.value)
    assert "no token.json" in msg
    assert "re-mint token on the Mac" in msg
    assert "spreadsheets" in msg


def test_expired_without_refresh_token_fails_safe(sheets_auth, monkeypatch):
    creds = _FakeCredentials(valid=False, expired=True, refresh_token=None)
    _seed_token(sheets_auth)
    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *a, **k: creds),
    )

    with pytest.raises(sheets_auth.SheetsAuthError) as excinfo:
        sheets_auth.load_sheets_credentials("personal")

    assert creds.refresh_called is False
    assert "not refreshable" in str(excinfo.value)


def test_unreadable_token_file_raises_sheets_auth_error(sheets_auth, monkeypatch):
    _seed_token(sheets_auth)

    def _boom(*a, **k):
        raise ValueError("malformed token file")

    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(_boom),
    )

    with pytest.raises(sheets_auth.SheetsAuthError) as excinfo:
        sheets_auth.load_sheets_credentials("personal")
    assert "could not read credentials" in str(excinfo.value)


def test_custom_scopes_appear_in_remint_message(sheets_auth):
    with pytest.raises(sheets_auth.SheetsAuthError) as excinfo:
        sheets_auth.load_sheets_credentials(
            "personal", scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
    assert "https://www.googleapis.com/auth/drive.readonly" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Persistence perms (T002)
# --------------------------------------------------------------------------- #


def test_persisted_token_perms_are_0600_and_dir_0700(sheets_auth, monkeypatch):
    creds = _FakeCredentials(valid=False, expired=True, refresh_token="rt-xyz")
    _seed_token(sheets_auth)
    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *a, **k: creds),
    )

    sheets_auth.load_sheets_credentials("personal")

    tok = sheets_auth.token_path("personal")
    cred_dir = sheets_auth.credential_dir("personal")
    assert stat.S_IMODE(tok.stat().st_mode) == 0o600
    assert stat.S_IMODE(cred_dir.stat().st_mode) == 0o700
    # The temp file used for the atomic swap must not linger.
    assert not tok.with_name(tok.name + ".tmp").exists()


def test_to_json_contents_never_returned_as_string(sheets_auth, monkeypatch):
    """The function returns a Credentials object, never the serialized token."""
    creds = _FakeCredentials(valid=True, expired=False)
    _seed_token(sheets_auth)
    monkeypatch.setattr(
        sys.modules["google.oauth2.credentials"].Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *a, **k: creds),
    )
    result = sheets_auth.load_sheets_credentials("personal")
    assert not isinstance(result, str)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _no_interactive_module() -> types.ModuleType:
    """A google_auth_oauthlib.flow whose entry points explode if ever touched."""
    mod = types.ModuleType("google_auth_oauthlib.flow")

    class _Explode:
        @staticmethod
        def from_client_secrets_file(*a, **k):  # pragma: no cover - must not run
            raise AssertionError("interactive consent flow must never be reached")

    mod.InstalledAppFlow = _Explode  # type: ignore[attr-defined]
    return mod
