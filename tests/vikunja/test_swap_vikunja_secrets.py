"""Tests for `scripts/vikunja/swap_vikunja_secrets.py` (WP03).

Coverage targets:
    - argparse + path validation
    - atomic_write_file utility (mode-before-rename, chown-before-rename,
      atomicity)
    - backup_secrets (happy, stale-.bak refusal, readback fail)
    - rotate_secrets (happy, readback fail)
    - restart_gateway (subprocess mock — happy, restart fail, timeout)
    - verify_attribution (write+readback happy, POST 401 reject,
      wrong-user on readback, cleanup-delete best-effort)
    - auto-rollback orchestration (write+readback probe fires after
      secrets swap)
    - --rollback-from-bak manual mode
    - deeply-degraded state (rollback restored but verify still fails)
    - --dry-run mode (no writes, no subprocess, no HTTP)

All filesystem mutations use the pytest `tmp_path` fixture; no real
`/data/services/openclaw` access. `subprocess.run` and
`urllib.request.urlopen` are mocked.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / "scripts" / "vikunja" / "swap_vikunja_secrets.py"


def _load_module():
    """Load the helper module directly via importlib (its filename contains
    underscores, so it's importable as `swap_vikunja_secrets`)."""
    spec = importlib.util.spec_from_file_location(
        "swap_vikunja_secrets", str(HELPER_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


@pytest.fixture
def secrets_fixture(tmp_path, mod):
    """Set up a fake secrets file with mode 600 and a writable new-token file."""
    secrets = tmp_path / "vikunja-api"
    secrets.write_bytes(b"kent-token-original\n")
    os.chmod(secrets, 0o600)

    new_token = tmp_path / "new_token.txt"
    new_token.write_bytes(b"felix-bot-shiny-new-token\n")
    os.chmod(new_token, 0o600)

    return {
        "secrets": secrets,
        "new_token": new_token,
        "bak": Path(str(secrets) + ".kent-pre-felix-bot.bak"),
        "tmp_path": tmp_path,
    }


# ---------------------- atomic_write_file ----------------------


def test_atomic_write_creates_file_with_mode_600(tmp_path, mod):
    target = tmp_path / "out.txt"
    mod.atomic_write_file(target, b"hello", mode=0o600)
    assert target.read_bytes() == b"hello"
    actual_mode = stat.S_IMODE(target.stat().st_mode)
    assert actual_mode == 0o600


def test_atomic_write_chmods_before_rename(tmp_path, mod):
    """The mode MUST be set on the tmp file BEFORE the rename, so the target
    path is never visible with the default umask permissions.

    We patch os.chmod and os.rename and assert the call order.
    """
    target = tmp_path / "out.txt"
    call_order: list[str] = []

    real_chmod = os.chmod
    real_rename = os.rename

    def tracked_chmod(p, m):
        # Record the chmod target (we expect it to be the .tmp).
        call_order.append(f"chmod:{Path(p).name}")
        return real_chmod(p, m)

    def tracked_rename(src, dst):
        call_order.append(f"rename:{Path(src).name}->{Path(dst).name}")
        return real_rename(src, dst)

    with patch.object(mod.os, "chmod", side_effect=tracked_chmod), \
         patch.object(mod.os, "rename", side_effect=tracked_rename):
        mod.atomic_write_file(target, b"x", mode=0o600)

    assert call_order == [
        "chmod:out.txt.tmp",
        "rename:out.txt.tmp->out.txt",
    ], f"Expected chmod-before-rename order; got {call_order}"


def test_atomic_write_refuses_existing_tmp(tmp_path, mod):
    """If a stale .tmp file exists, atomic_write_file must refuse (O_EXCL)."""
    target = tmp_path / "out.txt"
    stale_tmp = tmp_path / "out.txt.tmp"
    stale_tmp.write_bytes(b"stale leftover")
    with pytest.raises(OSError, match="stale tmp file"):
        mod.atomic_write_file(target, b"new", mode=0o600)


def test_atomic_write_chowns_before_rename(tmp_path, mod):
    """`os.chown` MUST be called on the tmp file BEFORE `os.rename`, so the
    target path is never visible owned by the invoker (e.g., root) when
    the spec requires claude:claude.

    The test patches pwd/grp resolution so the (uid, gid) is deterministic
    regardless of what users exist on the developer's host, then patches
    os.chown and os.rename and asserts the call order.
    """
    target = tmp_path / "out.txt"
    call_order: list[str] = []

    real_rename = os.rename

    fake_pwd = MagicMock()
    fake_pwd.getpwnam.return_value = MagicMock(pw_uid=4242)
    fake_grp = MagicMock()
    fake_grp.getgrnam.return_value = MagicMock(gr_gid=4242)

    def tracked_chown(p, uid, gid):
        call_order.append(f"chown:{Path(p).name}:{uid}:{gid}")
        # Don't actually attempt the cross-user chown (would require root).
        return None

    def tracked_rename(src, dst):
        call_order.append(f"rename:{Path(src).name}->{Path(dst).name}")
        return real_rename(src, dst)

    with patch.object(mod, "pwd", fake_pwd), \
         patch.object(mod, "grp", fake_grp), \
         patch.object(mod.os, "chown", side_effect=tracked_chown), \
         patch.object(mod.os, "rename", side_effect=tracked_rename):
        mod.atomic_write_file(target, b"x", mode=0o600, owner="claude", group="claude")

    # chown must come before rename, and the chown target must be the
    # tmp file (not the final path).
    assert call_order == [
        "chown:out.txt.tmp:4242:4242",
        "rename:out.txt.tmp->out.txt",
    ], f"Expected chown-before-rename order with tmp as chown target; got {call_order}"


def test_atomic_write_unknown_owner_raises_keyerror_when_root(tmp_path, mod):
    """If `owner` doesn't resolve via pwd.getpwnam AND we're running as
    root, raise KeyError before any filesystem mutation — leaving the
    file root-owned would violate the E-4 ownership invariant."""
    target = tmp_path / "out.txt"
    fake_pwd = MagicMock()
    fake_pwd.getpwnam.side_effect = KeyError("no such user")

    with patch.object(mod, "pwd", fake_pwd), \
         patch.object(mod.os, "geteuid", return_value=0):
        with pytest.raises(KeyError, match="does not exist"):
            mod.atomic_write_file(
                target, b"x", mode=0o600, owner="ghost-user", group="claude"
            )
    # No tmp file should be left behind — the resolve failure is pre-IO.
    assert not (tmp_path / "out.txt.tmp").exists()
    assert not target.exists()


def test_atomic_write_unknown_owner_non_root_is_tolerant(tmp_path, mod):
    """A non-root invoker on a host that lacks the 'claude' user should
    still succeed — the chown would have been a no-op anyway. We must
    not block the developer's local test runs."""
    target = tmp_path / "out.txt"
    fake_pwd = MagicMock()
    fake_pwd.getpwnam.side_effect = KeyError("no such user")
    fake_grp = MagicMock()
    fake_grp.getgrnam.side_effect = KeyError("no such group")

    with patch.object(mod, "pwd", fake_pwd), \
         patch.object(mod, "grp", fake_grp), \
         patch.object(mod.os, "geteuid", return_value=12345):
        mod.atomic_write_file(target, b"x", mode=0o600)
    assert target.read_bytes() == b"x"


def test_atomic_write_chown_permission_error_is_swallowed(tmp_path, mod):
    """A non-root invoker chowning to a different user gets PermissionError.
    The helper must swallow it (no-op for dev/test) and still complete
    the rename so the file exists at the target."""
    target = tmp_path / "out.txt"

    fake_pwd = MagicMock()
    fake_pwd.getpwnam.return_value = MagicMock(pw_uid=0)
    fake_grp = MagicMock()
    fake_grp.getgrnam.return_value = MagicMock(gr_gid=0)

    def boom(*args, **kwargs):
        raise PermissionError("operation not permitted")

    with patch.object(mod, "pwd", fake_pwd), \
         patch.object(mod, "grp", fake_grp), \
         patch.object(mod.os, "chown", side_effect=boom):
        mod.atomic_write_file(target, b"x", mode=0o600)
    assert target.read_bytes() == b"x"


def test_atomic_write_no_partial_target_on_error(tmp_path, mod):
    """If chmod fails, the rename must not have happened — target should not exist."""
    target = tmp_path / "never_appears.txt"

    def boom(*args, **kwargs):
        raise PermissionError("simulated chmod failure")

    with patch.object(mod.os, "chmod", side_effect=boom):
        with pytest.raises(PermissionError):
            mod.atomic_write_file(target, b"x", mode=0o600)

    assert not target.exists(), "Target must not exist if chmod failed before rename."


# ---------------------- backup_secrets ----------------------


def test_backup_happy(tmp_path, mod, secrets_fixture):
    info = mod.backup_secrets(secrets_fixture["secrets"], secrets_fixture["bak"])
    assert secrets_fixture["bak"].exists()
    assert secrets_fixture["bak"].read_bytes() == b"kent-token-original\n"
    assert stat.S_IMODE(secrets_fixture["bak"].stat().st_mode) == 0o600
    assert info["bak_size_bytes"] == len(b"kent-token-original\n")


def test_backup_refuses_existing_bak(tmp_path, mod, secrets_fixture):
    secrets_fixture["bak"].write_bytes(b"old bak from a prior failed rotation")
    with pytest.raises(FileExistsError, match="Stale backup"):
        mod.backup_secrets(secrets_fixture["secrets"], secrets_fixture["bak"])


def test_backup_readback_mismatch_raises(tmp_path, mod, secrets_fixture):
    """If the readback bytes differ from what was written, raise OSError."""
    original_read = mod._read_bytes
    call_count = {"n": 0}

    def tampered_read(p):
        # First call: source read (return real bytes). Second call: bak
        # readback — return tampered bytes to simulate corruption.
        call_count["n"] += 1
        if call_count["n"] == 1:
            return original_read(p)
        return b"CORRUPTED"

    with patch.object(mod, "_read_bytes", side_effect=tampered_read):
        with pytest.raises(OSError, match="readback mismatch"):
            mod.backup_secrets(secrets_fixture["secrets"], secrets_fixture["bak"])


# ---------------------- rotate_secrets ----------------------


def test_rotate_happy(tmp_path, mod, secrets_fixture):
    new_bytes = b"felix-bot-token\n"
    info = mod.rotate_secrets(new_bytes, secrets_fixture["secrets"])
    assert secrets_fixture["secrets"].read_bytes() == new_bytes
    assert stat.S_IMODE(secrets_fixture["secrets"].stat().st_mode) == 0o600
    assert info["new_size_bytes"] == len(new_bytes)


def test_rotate_rejects_empty_token(tmp_path, mod, secrets_fixture):
    with pytest.raises(ValueError, match="empty"):
        mod.rotate_secrets(b"   \n", secrets_fixture["secrets"])


# ---------------------- restart_gateway ----------------------


def _mk_completed(returncode=0, stdout="", stderr=""):
    cp = subprocess.CompletedProcess(args=[], returncode=returncode)
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def test_restart_gateway_happy(mod):
    call_log = []

    def fake_run(cmd, **kwargs):
        call_log.append(tuple(cmd))
        if cmd[:3] == ["systemctl", "--user", "restart"]:
            return _mk_completed(0, "", "")
        if cmd[:3] == ["systemctl", "--user", "is-active"]:
            return _mk_completed(0, "active\n", "")
        raise AssertionError(f"unexpected cmd {cmd}")

    with patch.object(mod.subprocess, "run", side_effect=fake_run):
        info = mod.restart_gateway("test.service", health_timeout=5)
    assert info["is_active"] is True
    assert info["unit"] == "test.service"
    assert ("systemctl", "--user", "restart", "test.service") in call_log
    assert ("systemctl", "--user", "is-active", "test.service") in call_log


def test_restart_gateway_restart_fails(mod):
    def fake_run(cmd, **kwargs):
        return _mk_completed(1, "", "Job failed")

    with patch.object(mod.subprocess, "run", side_effect=fake_run):
        with pytest.raises(mod.GatewayRestartFailed, match="failed"):
            mod.restart_gateway("test.service", health_timeout=2)


def test_restart_gateway_is_active_timeout(mod):
    """is-active never returns 'active' — helper raises on timeout."""
    def fake_run(cmd, **kwargs):
        if cmd[2] == "restart":
            return _mk_completed(0, "", "")
        return _mk_completed(3, "inactive\n", "")

    # Patch time.monotonic to advance quickly past the deadline.
    monotonic_seq = iter([0.0, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0])

    def fake_monotonic():
        try:
            return next(monotonic_seq)
        except StopIteration:
            return 100.0

    with patch.object(mod.subprocess, "run", side_effect=fake_run), \
         patch.object(mod.time, "monotonic", side_effect=fake_monotonic), \
         patch.object(mod.time, "sleep", return_value=None):
        with pytest.raises(mod.GatewayRestartFailed, match="did not reach"):
            mod.restart_gateway("test.service", health_timeout=2)


# ---------------------- verify_attribution ----------------------


def _mk_urlopen_response(status: int, body: dict | None):
    """Build a context-manager mock that mimics urllib.request.urlopen."""
    resp = MagicMock()
    resp.getcode.return_value = status
    resp.read.return_value = json.dumps(body).encode("utf-8") if body is not None else b""
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


def _capture_request_calls(responses):
    """Return a side_effect callable for urlopen that also captures each
    Request object so the test can assert on method/url/body.

    Pass an iterable of context-manager mocks (or exceptions) in the order
    you expect them to be consumed. Returns (side_effect, calls_list).
    """
    iterator = iter(responses)
    calls: list[dict] = []

    def side_effect(req, *args, **kwargs):
        # `req` is the urllib.request.Request instance.
        data = req.data
        if isinstance(data, (bytes, bytearray)):
            try:
                parsed = json.loads(data.decode("utf-8"))
            except Exception:
                parsed = data
        else:
            parsed = None
        calls.append({
            "method": req.get_method(),
            "url": req.full_url,
            "body": parsed,
        })
        nxt = next(iterator)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt

    return side_effect, calls


def test_verify_attribution_write_readback_happy(mod):
    """Happy path performs POST (write) -> GET (readback) -> DELETE (cleanup)
    and asserts the readback's created_by.username == expected_user."""
    post_body = {"id": 999, "comment": "probe", "author": {"username": "felix-bot"}}
    get_body = {"id": 999, "comment": "probe", "author": {"username": "felix-bot"}}
    delete_body: dict | None = {"message": "deleted"}

    responses = [
        _mk_urlopen_response(201, post_body),    # POST comment
        _mk_urlopen_response(200, get_body),     # GET comment readback
        _mk_urlopen_response(200, delete_body),  # DELETE cleanup
    ]
    side_effect, calls = _capture_request_calls(responses)

    with patch.object(mod.urllib.request, "urlopen", side_effect=side_effect):
        info = mod.verify_attribution(
            base_url="https://example.invalid/api/v1",
            token="t",
            task_id=1,
            expected_user="felix-bot",
        )

    assert info["verified"] is True
    assert info["created_by"] == "felix-bot"
    assert info["comment_id"] == 999
    assert info["cleanup_ok"] is True

    # Assert a NEW write was issued (not just a read of an existing task).
    assert len(calls) == 3, f"Expected POST+GET+DELETE; got {len(calls)} calls"
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/tasks/1/comments")
    assert isinstance(calls[0]["body"], dict)
    assert "comment" in calls[0]["body"]
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"].endswith("/tasks/1/comments/999")
    assert calls[2]["method"] == "DELETE"
    assert calls[2]["url"].endswith("/tasks/1/comments/999")


def test_verify_attribution_post_401_raises(mod):
    """If the POST itself returns 401, the token is rejected — raise."""
    err = urllib.error.HTTPError(
        url="x", code=401, msg="Unauthorized", hdrs=None,
        fp=io.BytesIO(b'{"message":"invalid token"}'),
    )
    with patch.object(mod.urllib.request, "urlopen", side_effect=err):
        with pytest.raises(mod.VerificationFailed, match="HTTP 401"):
            mod.verify_attribution(
                base_url="https://x/api/v1",
                token="t",
                task_id=1,
                expected_user="felix-bot",
            )


def test_verify_attribution_readback_wrong_user_raises(mod):
    """The POST succeeds (HTTP 201) but the readback shows the new comment
    is attributed to the WRONG user — raise VerificationFailed so the
    auto-rollback handler fires. This is the very thing Codex flagged
    that a plain GET on an existing task could NOT catch."""
    post_body = {"id": 999, "comment": "probe", "author": {"username": "kent"}}
    get_body = {"id": 999, "comment": "probe", "author": {"username": "kent"}}
    # We still issue DELETE for cleanup even on failure (finally clause).
    delete_body: dict | None = {"message": "deleted"}

    responses = [
        _mk_urlopen_response(201, post_body),
        _mk_urlopen_response(200, get_body),
        _mk_urlopen_response(200, delete_body),
    ]
    side_effect, calls = _capture_request_calls(responses)

    with patch.object(mod.urllib.request, "urlopen", side_effect=side_effect):
        with pytest.raises(mod.VerificationFailed, match="NEW comment"):
            mod.verify_attribution(
                base_url="https://x/api/v1",
                token="t",
                task_id=1,
                expected_user="felix-bot",
            )

    # The write+readback was issued — proving the probe wasn't read-only.
    assert calls[0]["method"] == "POST"
    assert calls[1]["method"] == "GET"
    # Cleanup DELETE was attempted even though verification failed.
    assert any(c["method"] == "DELETE" for c in calls)


def test_verify_attribution_cleanup_failure_does_not_fail_verification(mod):
    """DELETE cleanup is best-effort. A URLError on DELETE must NOT raise."""
    post_body = {"id": 999, "comment": "probe", "author": {"username": "felix-bot"}}
    get_body = {"id": 999, "comment": "probe", "author": {"username": "felix-bot"}}
    delete_err = urllib.error.URLError("network down at cleanup time")

    responses = [
        _mk_urlopen_response(201, post_body),
        _mk_urlopen_response(200, get_body),
        delete_err,
    ]
    side_effect, _calls = _capture_request_calls(responses)

    with patch.object(mod.urllib.request, "urlopen", side_effect=side_effect):
        info = mod.verify_attribution(
            base_url="https://x/api/v1",
            token="t",
            task_id=1,
            expected_user="felix-bot",
        )

    assert info["verified"] is True
    assert info["cleanup_ok"] is False


# ---------------------- argparse + main entry ----------------------


def _run_helper(args, env=None):
    """Invoke the helper as a subprocess; return CompletedProcess."""
    cmd = [sys.executable, str(HELPER_PATH), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_help_works():
    result = _run_helper(["--help"])
    assert result.returncode == 0
    assert "Atomic Vikunja secrets cutover" in result.stdout


def test_skip_post_verify_in_swap_mode_rejected(tmp_path):
    """--skip-post-verify without --rollback or --dry-run is a usage error."""
    nt = tmp_path / "nt"
    nt.write_bytes(b"x")
    os.chmod(nt, 0o600)
    secrets = tmp_path / "secrets"
    secrets.write_bytes(b"y")
    os.chmod(secrets, 0o600)
    result = _run_helper([
        "--new-token-file", str(nt),
        "--secrets-path", str(secrets),
        "--skip-post-verify",
    ])
    assert result.returncode == 2
    assert "skip-post-verify" in result.stderr


def test_conflicting_rollback_and_new_token_rejected(tmp_path):
    nt = tmp_path / "nt"
    nt.write_bytes(b"x")
    result = _run_helper([
        "--rollback-from-bak",
        "--new-token-file", str(nt),
    ])
    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr


def test_missing_new_token_file_rejected():
    result = _run_helper([
        "--new-token-file", "/nonexistent/path/does/not/exist",
    ])
    assert result.returncode == 2
    assert "not found" in result.stderr


# ---------------------- dry-run mode ----------------------


def test_dry_run_no_writes_no_subprocess_no_http(tmp_path, mod, secrets_fixture):
    """--dry-run must touch nothing — no fs writes, no subprocess, no HTTP."""
    args_ns = mod.build_parser().parse_args([
        "--new-token-file", str(secrets_fixture["new_token"]),
        "--secrets-path", str(secrets_fixture["secrets"]),
        "--bak-suffix", ".kent-pre-felix-bot.bak",
        "--dry-run",
    ])

    original_secrets_bytes = secrets_fixture["secrets"].read_bytes()

    with patch.object(mod.subprocess, "run", side_effect=AssertionError("no subprocess in dry-run")), \
         patch.object(mod.urllib.request, "urlopen", side_effect=AssertionError("no HTTP in dry-run")):
        rc = mod.perform_swap(args_ns)
    assert rc == 0
    # Secrets file untouched, bak not created.
    assert secrets_fixture["secrets"].read_bytes() == original_secrets_bytes
    assert not secrets_fixture["bak"].exists()


# ---------------------- end-to-end orchestration (mocked) ----------------------


def _make_swap_args(mod, secrets_fixture, **overrides):
    raw_args = [
        "--new-token-file", str(secrets_fixture["new_token"]),
        "--secrets-path", str(secrets_fixture["secrets"]),
        "--bak-suffix", ".kent-pre-felix-bot.bak",
        "--gateway-unit", "test-gateway.service",
        "--gateway-health-timeout", "2",
        "--vikunja-base-url", "https://example.invalid/api/v1",
        "--verify-task-id", "42",
    ]
    if overrides.get("rollback"):
        raw_args.append("--rollback-from-bak")
    return mod.build_parser().parse_args(raw_args)


def _systemctl_happy_run():
    """Return a fake subprocess.run that always reports healthy gateway."""
    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["systemctl", "--user", "restart"]:
            return _mk_completed(0, "", "")
        if cmd[:3] == ["systemctl", "--user", "is-active"]:
            return _mk_completed(0, "active\n", "")
        raise AssertionError(f"unexpected cmd {cmd}")
    return fake_run


def _verify_responses(username: str):
    """Build the 3-call response sequence verify_attribution issues per
    invocation: POST comment -> GET comment -> DELETE comment, all
    attributed to `username`."""
    body = {"id": 999, "comment": "probe", "author": {"username": username}}
    return [
        _mk_urlopen_response(201, body),                  # POST
        _mk_urlopen_response(200, body),                  # GET (readback)
        _mk_urlopen_response(200, {"message": "ok"}),     # DELETE (cleanup)
    ]


def test_full_happy_path_swap_exits_0(mod, secrets_fixture):
    args = _make_swap_args(mod, secrets_fixture)

    # Post-swap verify: write+readback both attributed to felix-bot.
    responses = _verify_responses("felix-bot")

    with patch.object(mod.subprocess, "run", side_effect=_systemctl_happy_run()), \
         patch.object(mod.urllib.request, "urlopen", side_effect=responses):
        rc = mod.perform_swap(args)

    assert rc == 0
    assert secrets_fixture["bak"].exists()
    assert secrets_fixture["bak"].read_bytes() == b"kent-token-original\n"
    assert secrets_fixture["secrets"].read_bytes() == b"felix-bot-shiny-new-token\n"


def test_auto_rollback_on_verify_failure(mod, secrets_fixture):
    """Post-swap write+readback shows the NEW comment was attributed to
    kent (not felix-bot) — verify raises, helper restores .bak, post-
    rollback write+readback shows kent, exit 1."""
    args = _make_swap_args(mod, secrets_fixture)

    # Post-swap: probe comment attributes to kent => VerificationFailed.
    # Post-rollback: probe comment attributes to kent => rollback OK.
    responses = (
        _verify_responses("kent")  # post-swap probe: WRONG user
        + _verify_responses("kent")  # post-rollback probe: kent restored
    )

    with patch.object(mod.subprocess, "run", side_effect=_systemctl_happy_run()), \
         patch.object(mod.urllib.request, "urlopen", side_effect=responses):
        rc = mod.perform_swap(args)

    assert rc == 1
    # After rollback the secrets file should hold kent's original bytes.
    assert secrets_fixture["secrets"].read_bytes() == b"kent-token-original\n"
    # The .bak should still exist (we restored from it; we don't unlink).
    assert secrets_fixture["bak"].exists()


def test_auto_rollback_then_deeply_degraded(mod, secrets_fixture):
    """Verify fails, rollback restores .bak, but post-rollback verify still fails."""
    args = _make_swap_args(mod, secrets_fixture)

    responses = (
        _verify_responses("kent")            # post-swap: wrong user -> rollback
        + _verify_responses("someone-else")  # post-rollback: still wrong -> degraded
    )

    with patch.object(mod.subprocess, "run", side_effect=_systemctl_happy_run()), \
         patch.object(mod.urllib.request, "urlopen", side_effect=responses):
        rc = mod.perform_swap(args)

    assert rc == 1


def test_manual_rollback_happy(mod, secrets_fixture):
    """--rollback-from-bak with a valid .bak restores kent and exits 0."""
    # Set up: create a .bak by hand (simulating a prior swap completed), and
    # imagine the live secrets contains felix-bot's token (post-swap state).
    secrets_fixture["bak"].write_bytes(b"kent-token-original\n")
    os.chmod(secrets_fixture["bak"], 0o600)
    secrets_fixture["secrets"].write_bytes(b"felix-bot-currently-active\n")
    os.chmod(secrets_fixture["secrets"], 0o600)

    args = _make_swap_args(mod, secrets_fixture, rollback=True)

    with patch.object(mod.subprocess, "run", side_effect=_systemctl_happy_run()), \
         patch.object(mod.urllib.request, "urlopen", side_effect=_verify_responses("kent")):
        rc = mod.perform_manual_rollback(args)

    assert rc == 0
    assert secrets_fixture["secrets"].read_bytes() == b"kent-token-original\n"


def test_manual_rollback_missing_bak_exits_2(mod, secrets_fixture):
    """Without a .bak, the manual rollback exits 2 at arg-validation."""
    args = _make_swap_args(mod, secrets_fixture, rollback=True)
    # bak intentionally not created
    with pytest.raises(SystemExit) as exc_info:
        mod.perform_manual_rollback(args)
    assert exc_info.value.code == 2


def test_gateway_restart_failure_triggers_rollback(mod, secrets_fixture):
    """If systemctl restart fails AFTER rotate, helper auto-rolls back.
    Forward verify is skipped (restart failed first), so only the
    post-rollback write+readback probe is consumed."""
    args = _make_swap_args(mod, secrets_fixture)

    call_phase = {"n": 0}

    def fake_run(cmd, **kwargs):
        # First restart (forward): fail.
        # Second restart (rollback): succeed.
        if cmd[:3] == ["systemctl", "--user", "restart"]:
            call_phase["n"] += 1
            if call_phase["n"] == 1:
                return _mk_completed(1, "", "service didn't start")
            return _mk_completed(0, "", "")
        if cmd[:3] == ["systemctl", "--user", "is-active"]:
            return _mk_completed(0, "active\n", "")
        raise AssertionError(f"unexpected cmd {cmd}")

    with patch.object(mod.subprocess, "run", side_effect=fake_run), \
         patch.object(mod.urllib.request, "urlopen", side_effect=_verify_responses("kent")):
        rc = mod.perform_swap(args)

    assert rc == 1
    # After rollback, secrets should contain kent's original bytes.
    assert secrets_fixture["secrets"].read_bytes() == b"kent-token-original\n"
