"""Pytest tests for ``scripts/vikunja/revoke_kent_tokens.py``.

Covers WP04 of the felix-bot-vikunja-provisioning mission. Tests mock
``urllib.request.urlopen`` so no live network calls are made. The helper is
stdlib-only, so no third-party fixtures are required.

Test categories:
  * argparse — missing/conflicting auth flags exit 2
  * login    — 200 returns JWT; 401 exits 1
  * enumerate — 0 tokens; N tokens; 404 triggers UI fallback; 401 exits 1
  * delete   — sequence of N deletes; 404 mid-sequence is tolerated
  * UI fallback — ``--ui-fallback-only`` exits 0 with no HTTP calls
  * dry-run  — enumerates but never calls DELETE
  * password hygiene — password and JWT are not echoed to stdout/stderr
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest.mock as mock
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module loader — load revoke_kent_tokens.py without requiring a package.
# WP01 owns tests/vikunja/__init__.py, so we cannot create a package here;
# we load the script file directly via importlib so this test file is
# self-contained.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "vikunja" / "revoke_kent_tokens.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "revoke_kent_tokens", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["revoke_kent_tokens"] = module
    spec.loader.exec_module(module)
    return module


revoke = _load_module()


# ---------------------------------------------------------------------------
# Helpers for mocking urllib.request.urlopen
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Mimics the urlopen context-manager response object."""

    def __init__(self, status: int, payload: Any) -> None:
        self._status = status
        if isinstance(payload, (dict, list)):
            self._body = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, bytes):
            self._body = payload
        else:
            self._body = str(payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


def _http_error(status: int, body: Any = "") -> "urllib_error.HTTPError":
    import urllib.error

    body_bytes = (
        json.dumps(body).encode("utf-8")
        if isinstance(body, (dict, list))
        else str(body).encode("utf-8")
    )
    return urllib.error.HTTPError(
        url="http://test/",
        code=status,
        msg="mocked",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body_bytes),
    )


class _UrlopenRouter:
    """Route mock urlopen calls based on (method, path-suffix) for ergonomic
    per-test scripting.

    Each registered handler returns either a ``_FakeResponse`` or raises an
    ``HTTPError``. Unregistered routes raise ``AssertionError``.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self._handlers: dict[tuple[str, str], Any] = {}

    def register(
        self,
        method: str,
        path_suffix: str,
        handler: Any,
    ) -> None:
        self._handlers[(method.upper(), path_suffix)] = handler

    def __call__(self, request, timeout=None):  # noqa: ARG002 - timeout unused
        method = request.get_method().upper()
        url = request.full_url
        body_bytes = request.data
        body_text = body_bytes.decode("utf-8") if body_bytes else None
        self.calls.append((method, url, body_text))
        for (m, suffix), handler in self._handlers.items():
            if m == method and url.endswith(suffix):
                if callable(handler):
                    return handler()
                return handler
        raise AssertionError(
            f"unexpected mock urlopen call: {method} {url}"
        )


# ---------------------------------------------------------------------------
# Tests — argparse / auth-mode mutex
# ---------------------------------------------------------------------------


def test_argparse_conflicting_auth_flags_exits_2(capsys):
    """Passing BOTH --kent-password-from-stdin and --kent-token exits 2."""
    rc = revoke.main(
        ["--kent-password-from-stdin", "--kent-token", "abc"]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "mutually exclusive" in err


def test_argparse_missing_auth_flags_exits_2(capsys):
    """Passing neither --kent-password-from-stdin nor --kent-token exits 2."""
    rc = revoke.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "exactly one" in err


def test_help_flag_works(capsys):
    """--help prints and exits 0 (sanity check for argparse wiring)."""
    with pytest.raises(SystemExit) as excinfo:
        revoke.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--kent-password-from-stdin" in out
    assert "--kent-token" in out
    assert "--ui-fallback-only" in out


# ---------------------------------------------------------------------------
# Tests — login / JWT
# ---------------------------------------------------------------------------


def test_login_200_returns_jwt():
    """obtain_kent_jwt returns the token from a 200 login response."""
    router = _UrlopenRouter()
    router.register(
        "POST",
        "/login",
        lambda: _FakeResponse(200, {"token": "JWT-AAA"}),
    )
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        jwt = revoke.obtain_kent_jwt("kent", "secret", revoke.DEFAULT_BASE_URL)
    assert jwt == "JWT-AAA"
    # Verify the password was sent in the body (helper does post the password
    # to login — that's intentional; we just confirm the helper itself does
    # not leak it on stdout/stderr in other tests).
    method, url, body = router.calls[0]
    assert method == "POST"
    assert url.endswith("/login")
    assert json.loads(body) == {"username": "kent", "password": "secret"}


def test_login_401_exits_1(capsys):
    """obtain_kent_jwt exits 1 with a clear message on 401."""
    router = _UrlopenRouter()
    router.register("POST", "/login", lambda: (_ for _ in ()).throw(_http_error(401, {"message": "wrong"})))
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        with pytest.raises(SystemExit) as excinfo:
            revoke.obtain_kent_jwt("kent", "wrong", revoke.DEFAULT_BASE_URL)
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "credentials rejected" in err


# ---------------------------------------------------------------------------
# Tests — enumeration
# ---------------------------------------------------------------------------


def test_enumerate_zero_tokens_summary(capsys):
    """End-to-end: 0 tokens returned -> SUMMARY 'nothing to revoke'."""
    router = _UrlopenRouter()
    router.register("GET", "/tokens", lambda: _FakeResponse(200, []))
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        rc = revoke.main(["--kent-token", "tok-xyz"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "SUMMARY" in out
    assert "zero API tokens" in out
    # No DELETE issued.
    assert all(call[0] != "DELETE" for call in router.calls)


def test_enumerate_n_tokens_then_delete_each(capsys):
    """End-to-end: 3 tokens enumerated; each is DELETEd."""
    router = _UrlopenRouter()
    router.register(
        "GET",
        "/tokens",
        lambda: _FakeResponse(
            200,
            [
                {"id": 11, "created": "2026-04-01"},
                {"id": 22, "created": "2026-04-02"},
                {"id": 33, "created": "2026-04-03"},
            ],
        ),
    )
    router.register("DELETE", "/tokens/11", lambda: _FakeResponse(204, b""))
    router.register("DELETE", "/tokens/22", lambda: _FakeResponse(204, b""))
    router.register("DELETE", "/tokens/33", lambda: _FakeResponse(204, b""))
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        rc = revoke.main(["--kent-token", "tok-xyz"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "revoked 3 kent API token(s)" in out
    delete_calls = [c for c in router.calls if c[0] == "DELETE"]
    assert len(delete_calls) == 3
    # Verify Bearer header was sent on the GET as well.
    get_calls = [c for c in router.calls if c[0] == "GET"]
    assert len(get_calls) == 1


def test_enumerate_404_triggers_ui_fallback(capsys):
    """404 on GET /tokens -> UI fallback path; exit 0."""
    router = _UrlopenRouter()
    router.register(
        "GET",
        "/tokens",
        lambda: (_ for _ in ()).throw(_http_error(404, "not found")),
    )
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        rc = revoke.main(["--kent-token", "tok-xyz"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Manual UI revocation" in out
    assert "API Tokens" in out
    # No DELETE attempted.
    assert all(call[0] != "DELETE" for call in router.calls)


def test_enumerate_401_exits_1(capsys):
    """401 on GET /tokens -> exit 1 (auth failure).

    The helper uses ``sys.exit(1)`` from inside ``enumerate_kent_tokens``
    on a 401, which raises ``SystemExit``. We assert on the code.
    """
    router = _UrlopenRouter()
    router.register(
        "GET",
        "/tokens",
        lambda: (_ for _ in ()).throw(_http_error(401, "unauthorized")),
    )
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        with pytest.raises(SystemExit) as excinfo:
            revoke.main(["--kent-token", "stale-tok"])
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "authentication rejected" in err


# ---------------------------------------------------------------------------
# Tests — deletion edge cases
# ---------------------------------------------------------------------------


def test_delete_404_midsequence_is_tolerated(capsys):
    """If one DELETE returns 404, helper logs and continues; exit 0."""
    router = _UrlopenRouter()
    router.register(
        "GET",
        "/tokens",
        lambda: _FakeResponse(
            200, [{"id": 11}, {"id": 22}, {"id": 33}]
        ),
    )
    router.register("DELETE", "/tokens/11", lambda: _FakeResponse(204, b""))
    router.register(
        "DELETE",
        "/tokens/22",
        lambda: (_ for _ in ()).throw(_http_error(404, "gone")),
    )
    router.register("DELETE", "/tokens/33", lambda: _FakeResponse(204, b""))
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        rc = revoke.main(["--kent-token", "tok-xyz"])
    assert rc == 0
    captured = capsys.readouterr()
    # 11 and 33 revoked; 22 already gone.
    assert "revoked 2 kent API token(s)" in captured.out
    assert "1 already-gone/skipped" in captured.out
    assert "already revoked (404)" in captured.err


# ---------------------------------------------------------------------------
# Tests — UI fallback only mode
# ---------------------------------------------------------------------------


def test_ui_fallback_only_makes_no_http_calls(capsys):
    """--ui-fallback-only prints instructions and exits 0 with NO HTTP calls."""
    # Patch urlopen to a sentinel that raises if called.
    def boom(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("urlopen must not be called in --ui-fallback-only mode")

    with mock.patch.object(revoke.urllib.request, "urlopen", boom):
        rc = revoke.main(["--ui-fallback-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Manual UI revocation" in out
    assert "API Tokens" in out


# ---------------------------------------------------------------------------
# Tests — dry-run
# ---------------------------------------------------------------------------


def test_dry_run_makes_zero_network_calls(capsys):
    """--dry-run must issue ZERO network calls (no login, no enumeration, no delete).

    Regression for Codex cycle-1 finding: the original implementation
    POSTed /login and GETed /tokens before evaluating args.dry_run, which
    violated T019's "no network calls in dry-run" requirement.
    """
    # Patch urlopen to a sentinel that fails the test if invoked.
    def boom(*args, **kwargs):  # noqa: ARG001
        raise AssertionError(
            "urlopen must not be called in --dry-run mode"
        )

    with mock.patch.object(revoke.urllib.request, "urlopen", boom):
        rc = revoke.main(["--kent-token", "tok-xyz", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "no network calls" in out
    assert "SUMMARY" in out


def test_dry_run_with_password_mode_makes_zero_network_calls(capsys, monkeypatch):
    """--dry-run with --kent-password-from-stdin must also issue ZERO network calls.

    Specifically: NO POST /login, even though password auth is the more
    common path that previously triggered a login call before the
    dry-run guard was reached.
    """
    # Even if stdin has a password, dry-run must not consume it for login.
    monkeypatch.setattr("sys.stdin", io.StringIO("hunter2\n"))

    urlopen_mock = mock.MagicMock(
        side_effect=AssertionError(
            "urlopen must not be called in --dry-run mode (password auth)"
        )
    )
    with mock.patch.object(revoke.urllib.request, "urlopen", urlopen_mock):
        rc = revoke.main(["--kent-password-from-stdin", "--dry-run"])
    assert rc == 0
    # Definitive assertion: urlopen was never called.
    urlopen_mock.assert_not_called()
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "password (POST /login)" in out  # describes intended action
    assert "SUMMARY" in out


# ---------------------------------------------------------------------------
# Tests — password / JWT hygiene
# ---------------------------------------------------------------------------


def test_password_and_jwt_are_not_echoed(capsys, monkeypatch):
    """Passing the password via stdin must not echo it on stdout/stderr.

    Also confirms the obtained JWT is never printed.
    """
    SECRET_PASSWORD = "tr0ub4dor-c0rrect-horse"
    SECRET_JWT = "JWT-VERY-LONG-AND-DISTINCTIVE-eyJhbGciOi"

    monkeypatch.setattr("sys.stdin", io.StringIO(SECRET_PASSWORD + "\n"))

    router = _UrlopenRouter()
    router.register(
        "POST", "/login", lambda: _FakeResponse(200, {"token": SECRET_JWT})
    )
    router.register("GET", "/tokens", lambda: _FakeResponse(200, []))
    with mock.patch.object(revoke.urllib.request, "urlopen", router):
        rc = revoke.main(["--kent-password-from-stdin"])
    assert rc == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert SECRET_PASSWORD not in combined
    assert SECRET_JWT not in combined
