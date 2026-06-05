"""Tests for `scripts/vikunja/provision_felix_bot.py`.

Tests invoke the helper via subprocess and monkey-patch
`urllib.request.urlopen` in-process for the unit-tests that exercise the
HTTP code paths. Subprocess pattern mirrors
`tests/openclaw/agents/main/test_felix_file_issue.py`. Where the
subprocess path can't easily mock urlopen (because the helper runs in a
fresh Python interpreter), we use `--dry-run` and stdin injection to
keep the test hermetic without live network calls.

WP01 of mission `felix-bot-vikunja-provisioning-01KRT3N4`.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / "scripts" / "vikunja" / "provision_felix_bot.py"


# ---------------------------------------------------------------------------
# Subprocess env helper
# ---------------------------------------------------------------------------


def _subprocess_env(**extra) -> dict:
    """Build a subprocess env with PYTHONPATH=REPO_ROOT and a dummy VIKUNJA_BASE_URL."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.setdefault("VIKUNJA_BASE_URL", "https://vikunja.test/api/v1/")
    env.update(extra)
    return env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_kent_token(tmp_path: Path, content: str = "kent-token-abc123") -> Path:
    """Write a kent token file with mode 600 + non-empty content."""
    p = tmp_path / "kent-vikunja-api"
    p.write_text(content)
    os.chmod(str(p), 0o600)
    return p


def _load_helper_module():
    """Import provision_felix_bot.py as a module for in-process tests."""
    spec = importlib.util.spec_from_file_location(
        "provision_felix_bot_under_test", str(HELPER_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeHTTPResponse:
    """Minimal stand-in for urllib.request.urlopen()'s context-manager response."""

    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def _ok_json_response(payload, status: int = 200) -> FakeHTTPResponse:
    return FakeHTTPResponse(status, json.dumps(payload).encode("utf-8"))


def _http_error(status: int, body: bytes = b""):
    """Build a urllib HTTPError of the requested status with a body that can be
    re-read by the helper."""
    import urllib.error

    err = urllib.error.HTTPError(
        url="http://test/", code=status, msg="", hdrs=None, fp=io.BytesIO(body)
    )
    return err


# ---------------------------------------------------------------------------
# 1. Argparse / CLI surface
# ---------------------------------------------------------------------------


def test_help_succeeds():
    """`--help` exits 0 and prints the argparse description."""
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--help"],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 0
    assert "--kent-token-file" in result.stdout
    assert "--token-output-file" in result.stdout
    assert "--password-from-stdin" in result.stdout
    assert "--dry-run" in result.stdout


def test_missing_required_args_exits_2(tmp_path):
    """argparse rejects missing --kent-token-file / --token-output-file."""
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--dry-run"],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert (
        "required" in result.stderr.lower()
        or "the following arguments" in result.stderr.lower()
    )


# ---------------------------------------------------------------------------
# 2. Identity gate
# ---------------------------------------------------------------------------


def test_identity_gate_missing_kent_token_file_exits_2(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--kent-token-file",
            str(tmp_path / "does-not-exist"),
            "--token-output-file",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "kent token file not readable" in result.stderr


def test_identity_gate_wrong_mode_exits_2(tmp_path):
    """Token file at mode 644 must be rejected by the identity gate."""
    p = tmp_path / "kent-token"
    p.write_text("kent-token-content-1234567890")
    os.chmod(str(p), 0o644)
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--kent-token-file",
            str(p),
            "--token-output-file",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "unsafe mode" in result.stderr


def test_identity_gate_empty_token_file_exits_2(tmp_path):
    """Empty (but mode-600) token file must still be rejected."""
    p = tmp_path / "kent-token"
    p.write_text("")
    os.chmod(str(p), 0o600)
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--kent-token-file",
            str(p),
            "--token-output-file",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "empty" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 3. Dry-run end-to-end (no network)
# ---------------------------------------------------------------------------


def test_dry_run_full_path_succeeds_and_writes_summary(tmp_path):
    """Dry-run produces a SUMMARY line and never makes a network call."""
    kent = _write_kent_token(tmp_path)
    token_out = tmp_path / "felix-bot-token"
    valid_token = "felix-bot-token-1234567890ABCDEF"
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--kent-token-file",
            str(kent),
            "--token-output-file",
            str(token_out),
            "--dry-run",
        ],
        input=valid_token + "\n",
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # Stdout: JSON line + final SUMMARY line
    assert "SUMMARY: felix-bot registered" in result.stdout
    assert "12 projects shared" in result.stdout
    assert "token captured to" in result.stdout
    # In dry-run, the token output file is NOT created.
    assert not token_out.exists(), (
        "Dry-run must not touch --token-output-file."
    )


def test_dry_run_empty_token_exits_2(tmp_path):
    """Empty stdin on token line → exit 2 (usage error)."""
    kent = _write_kent_token(tmp_path)
    token_out = tmp_path / "felix-bot-token"
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--kent-token-file",
            str(kent),
            "--token-output-file",
            str(token_out),
            "--dry-run",
        ],
        input="\n",
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "empty stdin" in result.stderr.lower()


def test_dry_run_short_token_exits_2(tmp_path):
    """Implausibly short token → exit 2."""
    kent = _write_kent_token(tmp_path)
    token_out = tmp_path / "felix-bot-token"
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--kent-token-file",
            str(kent),
            "--token-output-file",
            str(token_out),
            "--dry-run",
        ],
        input="short\n",
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "plausible" in result.stderr.lower()


def test_password_required_outside_dry_run(tmp_path):
    """If --dry-run is omitted but --password-from-stdin is also omitted, the
    helper refuses to proceed (would otherwise need a password)."""
    kent = _write_kent_token(tmp_path)
    token_out = tmp_path / "felix-bot-token"
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--kent-token-file",
            str(kent),
            "--token-output-file",
            str(token_out),
        ],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "--password-from-stdin" in result.stderr


# ---------------------------------------------------------------------------
# 4. In-process HTTP path tests (urlopen mocked)
# ---------------------------------------------------------------------------


def test_register_felix_bot_happy_path(tmp_path):
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.return_value = _ok_json_response(
            {"id": 4242, "username": "felix-bot"}, status=200
        )
        result = module.register_felix_bot(
            username="felix-bot",
            email="kentgale+felix-bot@gmail.com",
            password="hunter2",
            base_url="https://example/api/v1/",
            dry_run=False,
        )
    assert result["user_id"] == 4242
    assert result["username"] == "felix-bot"


def test_register_felix_bot_409_conflict_exits_1():
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.side_effect = _http_error(409, b'{"message":"already exists"}')
        with pytest.raises(SystemExit) as ei:
            module.register_felix_bot(
                username="felix-bot",
                email="kentgale+felix-bot@gmail.com",
                password="hunter2",
                base_url="https://example/api/v1/",
                dry_run=False,
            )
    assert ei.value.code == 1


def test_register_felix_bot_400_exits_1():
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.side_effect = _http_error(400, b'{"message":"missing field"}')
        with pytest.raises(SystemExit) as ei:
            module.register_felix_bot(
                username="felix-bot",
                email="bad",
                password="hunter2",
                base_url="https://example/api/v1/",
                dry_run=False,
            )
    assert ei.value.code == 1


def test_register_felix_bot_5xx_exits_1():
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.side_effect = _http_error(503, b"")
        with pytest.raises(SystemExit) as ei:
            module.register_felix_bot(
                username="felix-bot",
                email="kentgale+felix-bot@gmail.com",
                password="hunter2",
                base_url="https://example/api/v1/",
                dry_run=False,
            )
    assert ei.value.code == 1


def test_enumerate_real_projects_filters_archived_and_pseudo():
    module = _load_helper_module()
    fake_projects = [
        {"id": 1, "title": "Inbox", "is_archived": False},
        {"id": 2, "title": "Everyday", "is_archived": False},
        {"id": 3, "title": "Archived Thing", "is_archived": True},
        {"id": -1, "title": "Pseudo Favorites", "is_archived": False},
        {"id": 4, "title": "Someday", "is_archived": False},
        {"id": 5, "title": "Personal Growth", "is_archived": False},
        {"id": 6, "title": "Business Acquisition", "is_archived": False},
        {"id": 7, "title": "CT-90day", "is_archived": False},
        {"id": 8, "title": "Health", "is_archived": False},
        {"id": 9, "title": "Intentional LLC", "is_archived": False},
        {"id": 10, "title": "Metal Casework", "is_archived": False},
        {"id": 11, "title": "Goals", "is_archived": False},
        {"id": 12, "title": "Research", "is_archived": False},
        {"id": 13, "title": "Habits", "is_archived": False},
    ]
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.return_value = _ok_json_response(fake_projects, status=200)
        real = module.enumerate_real_projects(
            base_url="https://example/api/v1/",
            kent_token="kent-token",
            dry_run=False,
        )
    ids = [p["id"] for p in real]
    assert ids == [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    assert 3 not in ids  # archived
    assert -1 not in ids  # pseudo


def test_enumerate_real_projects_too_few_exits_1():
    """Fewer than 12 real projects must halt the helper (FR-003 / NFR-005)."""
    module = _load_helper_module()
    skimpy = [
        {"id": i, "title": f"P{i}", "is_archived": False} for i in range(1, 6)
    ]
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.return_value = _ok_json_response(skimpy, status=200)
        with pytest.raises(SystemExit) as ei:
            module.enumerate_real_projects(
                base_url="https://example/api/v1/",
                kent_token="kent-token",
                dry_run=False,
            )
    assert ei.value.code == 1


def test_share_project_409_treated_as_success():
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.side_effect = _http_error(409, b'{"message":"already shared"}')
        ok = module.share_project_with_user(
            project_id=1,
            project_title="Inbox",
            username="felix-bot",
            base_url="https://example/api/v1/",
            kent_token="kent-token",
            dry_run=False,
        )
    assert ok is True


def test_share_project_403_exits_1():
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.side_effect = _http_error(403, b'{"message":"forbidden"}')
        with pytest.raises(SystemExit) as ei:
            module.share_project_with_user(
                project_id=7,
                project_title="CT-90day",
                username="felix-bot",
                base_url="https://example/api/v1/",
                kent_token="kent-token",
                dry_run=False,
            )
    assert ei.value.code == 1


def test_share_project_happy_path():
    module = _load_helper_module()
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.return_value = _ok_json_response(
            {"user_id": 42, "right": 1}, status=201
        )
        ok = module.share_project_with_user(
            project_id=1,
            project_title="Inbox",
            username="felix-bot",
            base_url="https://example/api/v1/",
            kent_token="kent-token",
            dry_run=False,
        )
    assert ok is True


def test_verify_shares_applied_all_present():
    module = _load_helper_module()
    projects = [{"id": pid, "title": f"P{pid}"} for pid in [1, 2, 4]]
    # Vikunja v0.24.6 GET /projects/{id}/users returns user objects with a
    # `username` field, not `user_id`. Verify matches on username.
    fake_shares = [{"id": 2, "username": "felix-bot", "right": 1, "created": "now"}]

    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.return_value = _ok_json_response(fake_shares, status=200)
        result = module.verify_shares_applied(
            projects=projects,
            felix_bot_username="felix-bot",
            base_url="https://example/api/v1/",
            kent_token="kent-token",
            dry_run=False,
        )
    assert result["verified"] == [1, 2, 4]
    assert result["missing"] == []


def test_verify_shares_applied_one_missing_exits_1():
    module = _load_helper_module()
    projects = [{"id": pid, "title": f"P{pid}"} for pid in [1, 2, 4]]

    # First two project share lists include felix-bot, third does not.
    # Vikunja v0.24.6 GET response uses `username` field, not `user_id`.
    responses = [
        _ok_json_response([{"id": 2, "username": "felix-bot", "right": 1}], status=200),
        _ok_json_response([{"id": 2, "username": "felix-bot", "right": 1}], status=200),
        _ok_json_response([{"id": 99, "username": "other-user", "right": 1}], status=200),
    ]
    with patch.object(module.urllib.request, "urlopen") as mock_urlopen:
        mock_urlopen.side_effect = responses
        with pytest.raises(SystemExit) as ei:
            module.verify_shares_applied(
                projects=projects,
                felix_bot_username="felix-bot",
                base_url="https://example/api/v1/",
                kent_token="kent-token",
                dry_run=False,
            )
    assert ei.value.code == 1


# ---------------------------------------------------------------------------
# 5. Token capture — file is mode 600
# ---------------------------------------------------------------------------


def test_capture_felix_bot_token_writes_mode_600(tmp_path):
    """Token output file is mode 600 immediately after the helper writes it."""
    module = _load_helper_module()
    out = tmp_path / "felix-bot-token"
    valid_token = "felix-bot-token-1234567890ABCDEF"
    stdin = io.StringIO(valid_token + "\n")

    # Set a permissive umask so we can prove the helper enforces mode
    # regardless of umask defaults.
    old_umask = os.umask(0o022)
    try:
        token = module.capture_felix_bot_token(
            token_output_file=out, stdin_source=stdin, dry_run=False
        )
    finally:
        os.umask(old_umask)

    assert token == valid_token
    assert out.exists()
    mode = stat.S_IMODE(out.stat().st_mode)
    assert mode == 0o600, f"expected 0o600 got {oct(mode)}"
    assert out.read_text().strip() == valid_token


def test_capture_felix_bot_token_empty_stdin_exits_2(tmp_path):
    module = _load_helper_module()
    out = tmp_path / "felix-bot-token"
    stdin = io.StringIO("\n")
    with pytest.raises(SystemExit) as ei:
        module.capture_felix_bot_token(
            token_output_file=out, stdin_source=stdin, dry_run=False
        )
    assert ei.value.code == 2
    assert not out.exists()


def test_capture_felix_bot_token_short_token_exits_2(tmp_path):
    module = _load_helper_module()
    out = tmp_path / "felix-bot-token"
    stdin = io.StringIO("short\n")
    with pytest.raises(SystemExit) as ei:
        module.capture_felix_bot_token(
            token_output_file=out, stdin_source=stdin, dry_run=False
        )
    assert ei.value.code == 2
