#!/usr/bin/env python3
"""Atomic Vikunja secrets cutover with auto-rollback.

This is the moment-of-truth helper of ADR-0002 Phase 1 (issue #304). It
rotates `/data/services/openclaw/secrets/vikunja-api` atomically from
kent's token to felix-bot's token, restarts `openclaw-gateway.service`,
verifies post-swap attribution, and auto-rolls back from the `.bak` file
on any verification failure.

Atomic semantics (FR-005..FR-008, NFR-002..NFR-004):
    1. Verify pre-conditions (paths, mode, no stale `.bak`).
    2. Backup current secrets to `.kent-pre-felix-bot.bak`
       (write-temp-then-rename, mode 600, readback-verified).
    3. Rotate secrets — write felix-bot's token via
       write-temp-then-rename, chmod 600 BEFORE rename so the target
       path never appears with the wrong permission bits.
    4. `systemctl --user restart openclaw-gateway` + poll `is-active`
       up to `--gateway-health-timeout` seconds.
    5. Post-swap attribution probe (FR-008 / C-11) — issue a NEW write
       with the rotated token (POST a probe comment to a low-impact
       task), read it back, assert the new comment's
       `created_by.username == 'felix-bot'`, then best-effort DELETE
       the probe comment. Reading an existing task's `created_by` is
       insufficient because that field reflects who originally created
       the task, not who is currently writing.
    6. On any step 3-5 failure, auto-rollback: restore `.bak`, restart
       gateway, verify kent attribution is restored. Exit 1.

A standalone `--rollback-from-bak` mode triggers the same rollback path
for operator-driven recovery during the 7-day soak (R-006, R-009).

Invocation:

    python3 scripts/vikunja/swap_vikunja_secrets.py \\
        --new-token-file <path-to-felix-bot-token> \\
        [--secrets-path /data/services/openclaw/secrets/vikunja-api] \\
        [--bak-suffix .kent-pre-felix-bot.bak] \\
        [--gateway-unit openclaw-gateway.service] \\
        [--gateway-health-timeout 30] \\
        [--vikunja-base-url https://office2.tail0f5f56.ts.net/api/v1] \\
        [--verify-task-id 1] \\
        [--dry-run]

Manual rollback (operator-driven, during soak):

    python3 scripts/vikunja/swap_vikunja_secrets.py \\
        --rollback-from-bak \\
        [--secrets-path ...] [--bak-suffix ...] [--gateway-unit ...]

Exit codes:
    0 — cutover (or rollback) succeeded and attribution verified
    1 — operational failure; helper auto-rolled back where possible
    2 — usage error (malformed args, missing files, conflicting flags)

Output:
    SUMMARY: phase=<name> result=<ok|fail> ... — one line per phase
    JSON summary on stdout at completion (success or rollback).
"""
from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_SECRETS_PATH = "/data/services/openclaw/secrets/vikunja-api"
DEFAULT_BAK_SUFFIX = ".kent-pre-felix-bot.bak"
DEFAULT_GATEWAY_UNIT = "openclaw-gateway.service"
DEFAULT_GATEWAY_HEALTH_TIMEOUT = 30
DEFAULT_VIKUNJA_BASE_URL = "https://office2.tail0f5f56.ts.net/api/v1"
DEFAULT_VERIFY_TASK_ID = 1

EXPECTED_FELIX_USER = "felix-bot"
EXPECTED_KENT_USER = "kent"
DEFAULT_OWNER = "claude"
DEFAULT_GROUP = "claude"


class VerificationFailed(Exception):
    """Raised when post-swap (or post-rollback) attribution verification fails."""


class GatewayRestartFailed(Exception):
    """Raised when systemctl restart or is-active poll fails."""


def _summary(**fields) -> None:
    """Emit a parseable SUMMARY line to stdout."""
    pairs = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"SUMMARY: {pairs}")


def atomic_write_file(
    path: Path,
    content_bytes: bytes,
    mode: int = 0o600,
    owner: str = DEFAULT_OWNER,
    group: str = DEFAULT_GROUP,
) -> None:
    """Atomically write `content_bytes` to `path` via write-temp-then-rename.

    Steps:
        1. Open `<path>.tmp` with O_WRONLY|O_CREAT|O_TRUNC|O_EXCL so any
           leftover tmp file aborts the operation cleanly.
        2. Write all bytes, fsync, close.
        3. `os.chmod` the tmp file to the target mode — BEFORE rename, so
           the target path is never visible with the default umask perms.
        4. `os.chown` the tmp file to (owner, group) — BEFORE rename, so
           the target path is never visible with the wrong ownership.
           Required by C-002 / data-model E-4: secrets must be owned by
           the claude service account, not root. When run as root the
           chown is meaningful; when run as a non-root user that lacks
           CAP_CHOWN, chown to self is a no-op (PermissionError on a
           cross-user chown is silently ignored — the file simply stays
           owned by the invoker, which preserves the invariant in dev/
           test environments where the helper is run as the developer).
        5. `os.rename(tmp, path)` — atomic on the same filesystem.

    On any error, the tmp file is best-effort removed and the exception
    propagates.

    Args:
        path: Final destination path.
        content_bytes: Raw bytes to write (caller controls encoding).
        mode: POSIX mode for the final file (default 0o600).
        owner: POSIX username to chown to (default 'claude').
        group: POSIX group name to chown to (default 'claude').

    Raises:
        OSError: On any filesystem error (caller decides handling).
        KeyError: When `owner` or `group` do not resolve via pwd/grp
            (e.g., running as root on a host where 'claude' is missing).
    """
    # Resolve uid/gid BEFORE opening the file so a bad owner/group name
    # fails fast without leaving an orphan tmp behind.
    #
    # When running as root we MUST be able to resolve `owner`/`group` —
    # otherwise the chown would silently leave the file root-owned and
    # violate the E-4 invariant. When running as non-root, missing
    # owner/group is non-fatal: the chown would have been a no-op anyway
    # (we can't chown across users without CAP_CHOWN). Skip the chown in
    # that case rather than failing the whole write.
    running_as_root = os.geteuid() == 0
    uid: int | None
    gid: int | None
    try:
        uid = pwd.getpwnam(owner).pw_uid
    except KeyError as exc:
        if running_as_root:
            raise KeyError(
                f"atomic_write_file: owner user {owner!r} does not exist on "
                f"this host (running as root — refusing to leave file root-owned)."
            ) from exc
        uid = None
    try:
        gid = grp.getgrnam(group).gr_gid
    except KeyError as exc:
        if running_as_root:
            raise KeyError(
                f"atomic_write_file: owner group {group!r} does not exist on "
                f"this host (running as root — refusing to leave file root-owned)."
            ) from exc
        gid = None

    # Use a stable .tmp sibling in the same directory so rename is atomic.
    # We always APPEND `.tmp` (rather than replace the suffix) so the tmp
    # file is unambiguously the in-flight artifact for `path`.
    tmp_path = Path(str(path) + ".tmp")

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_EXCL
    fd = None
    try:
        try:
            fd = os.open(str(tmp_path), flags, mode)
        except FileExistsError as exc:
            raise OSError(
                f"Refusing to write {path}: stale tmp file {tmp_path} "
                f"already exists. Investigate and remove before retrying."
            ) from exc
        os.write(fd, content_bytes)
        os.fsync(fd)
        os.close(fd)
        fd = None
        # chmod the tmp BEFORE rename so the target path is never visible
        # with looser permissions.
        os.chmod(str(tmp_path), mode)
        # chown the tmp BEFORE rename so the target path is never visible
        # with the wrong ownership. A non-root invoker may not have
        # permission to chown across users; that's expected in dev and
        # is a no-op when chown'ing to self. We only swallow
        # PermissionError — anything else (e.g., the tmp vanishing)
        # propagates. If `uid`/`gid` could not be resolved (non-root,
        # missing user on host) we skip the chown entirely.
        if uid is not None and gid is not None:
            try:
                os.chown(str(tmp_path), uid, gid)
            except PermissionError:
                # Non-root invoker chowning to a different owner is allowed
                # to be a no-op. The file stays owned by the caller, which
                # still satisfies E-4 in dev/test environments where the
                # invoker IS the claude account.
                pass
        os.rename(str(tmp_path), str(path))
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        # Best-effort cleanup of the tmp file.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def _read_bytes(path: Path) -> bytes:
    with open(str(path), "rb") as fh:
        return fh.read()


def _check_path_mode(path: Path, expected_mode: int = 0o600) -> tuple[bool, int]:
    """Return (ok, actual_mode_bits) for `path`."""
    stat = path.stat()
    actual = stat.st_mode & 0o777
    return actual == expected_mode, actual


def backup_secrets(secrets_path: Path, bak_path: Path) -> dict:
    """Backup `secrets_path` to `bak_path` atomically.

    Behavior:
        - If `bak_path` already exists, raise — a stale .bak indicates a
          prior incomplete rotation. The operator must resolve before
          continuing.
        - Read source bytes; write `.bak` via `atomic_write_file`.
        - Readback verify (size + content equality).

    Returns:
        Summary dict with `bak_path`, `bak_size_bytes`.

    Raises:
        FileExistsError: When `.bak` already exists.
        OSError: On readback mismatch or any filesystem error.
    """
    if bak_path.exists():
        raise FileExistsError(
            f"Stale backup at {bak_path} — refusing to overwrite. A previous "
            f"rotation may be incomplete. Investigate before retrying."
        )

    content = _read_bytes(secrets_path)
    if not content:
        raise OSError(f"Source secrets file {secrets_path} is empty — refusing to back up.")

    atomic_write_file(bak_path, content, mode=0o600)

    readback = _read_bytes(bak_path)
    if readback != content:
        raise OSError(
            f"Backup readback mismatch: wrote {len(content)} bytes, "
            f"readback returned {len(readback)} bytes."
        )

    return {"bak_path": str(bak_path), "bak_size_bytes": len(content)}


def rotate_secrets(new_token_bytes: bytes, secrets_path: Path) -> dict:
    """Atomically replace `secrets_path` contents with `new_token_bytes`.

    Returns:
        Summary dict with `secrets_path`, `new_size_bytes`.

    Raises:
        OSError: On readback mismatch or any filesystem error.
        ValueError: When the new token is empty.
    """
    if not new_token_bytes or not new_token_bytes.strip():
        raise ValueError("New token is empty — refusing to rotate.")

    atomic_write_file(secrets_path, new_token_bytes, mode=0o600)

    readback = _read_bytes(secrets_path)
    if readback != new_token_bytes:
        raise OSError(
            f"Rotate readback mismatch: wrote {len(new_token_bytes)} bytes, "
            f"readback returned {len(readback)} bytes."
        )

    return {"secrets_path": str(secrets_path), "new_size_bytes": len(new_token_bytes)}


def restart_gateway(unit: str, health_timeout: int) -> dict:
    """Restart `unit` via systemctl --user and poll is-active until healthy.

    Args:
        unit: systemd unit name (e.g., `openclaw-gateway.service`).
        health_timeout: max seconds to wait for `is-active` == `active`.

    Returns:
        Summary dict with `unit`, `restart_duration_s`, `is_active`.

    Raises:
        GatewayRestartFailed: On non-zero restart return code, restart
            subprocess error, or `is-active` timeout.
    """
    started = time.monotonic()
    try:
        result = subprocess.run(
            ["systemctl", "--user", "restart", unit],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise GatewayRestartFailed(
            f"systemctl --user restart {unit} timed out after 30s"
        ) from exc
    except FileNotFoundError as exc:
        raise GatewayRestartFailed("systemctl not found in PATH") from exc

    if result.returncode != 0:
        raise GatewayRestartFailed(
            f"systemctl --user restart {unit} failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    # Poll is-active until healthy or timeout.
    deadline = started + health_timeout
    last_state = "unknown"
    while time.monotonic() < deadline:
        try:
            probe = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            last_state = "probe-timeout"
        except FileNotFoundError as exc:
            raise GatewayRestartFailed("systemctl not found in PATH") from exc
        else:
            last_state = (probe.stdout or "").strip() or last_state
            if last_state == "active":
                duration = time.monotonic() - started
                return {
                    "unit": unit,
                    "restart_duration_s": round(duration, 3),
                    "is_active": True,
                }
        time.sleep(0.5)

    raise GatewayRestartFailed(
        f"Gateway {unit} did not reach is-active=active within "
        f"{health_timeout}s (last state: {last_state})"
    )


def _http_request_json(
    url: str,
    token: str,
    method: str = "GET",
    body: dict | None = None,
    timeout: int = 15,
) -> tuple[int, dict | list | None]:
    """Issue an HTTP request with bearer auth; return (status, parsed_json_or_None).

    Supports GET, POST, DELETE. POST/PUT requests serialize `body` as
    JSON and set Content-Type accordingly.
    """
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read()
        except Exception:
            raw = b""
    except urllib.error.URLError as exc:
        raise VerificationFailed(f"HTTP {method} to {url} failed: {exc}") from exc

    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, None


def _http_get_json(url: str, token: str, timeout: int = 15) -> tuple[int, dict | list | None]:
    """Backwards-compat thin wrapper around `_http_request_json` for GET."""
    return _http_request_json(url, token, method="GET", timeout=timeout)


def verify_attribution(
    base_url: str,
    token: str,
    task_id: int,
    expected_user: str,
) -> dict:
    """Prove `token` writes are attributed to `expected_user`.

    Per FR-008 and contract C-11, a read of a pre-existing task's
    `created_by` is NOT sufficient — it only reflects who originally
    created the task. To prove the *currently configured* token causes
    new Felix writes to attribute correctly, we issue a NEW write and
    read it back:

        1. POST a probe comment to `task_id` using `token`.
        2. GET the comment we just created.
        3. Assert the comment's `created_by.username == expected_user`.
        4. Best-effort DELETE the probe comment (cleanup; never fails
           the verification on cleanup error).

    Args:
        base_url: Vikunja API base URL (e.g., `https://.../api/v1`).
        token: Bearer token to use for the write+readback.
        task_id: ID of an existing task to attach the probe comment to.
        expected_user: Username expected at `created_by.username` on
            the newly created comment.

    Returns:
        Summary dict with `verified=True`, `task_id`, `comment_id`,
        `created_by`, `cleanup_ok`.

    Raises:
        VerificationFailed: On any non-2xx, missing attribution on the
            newly written comment, or mismatch with `expected_user`.
    """
    base = base_url.rstrip("/")
    post_url = f"{base}/tasks/{task_id}/comments"
    probe_text = (
        f"felix-bot-attribution-probe-{int(time.time() * 1000)}"
    )

    # Step 1: WRITE — POST a new comment with the live token.
    post_status, post_body = _http_request_json(
        post_url, token, method="POST", body={"comment": probe_text}
    )
    if post_status not in (200, 201):
        raise VerificationFailed(
            f"Probe comment POST to {post_url} returned HTTP {post_status} "
            f"(token rejected, task {task_id} missing, or API rejected the "
            f"write). Cannot confirm attribution."
        )
    if not isinstance(post_body, dict):
        raise VerificationFailed(
            f"Probe comment POST returned unexpected body type "
            f"{type(post_body).__name__}; cannot extract comment id."
        )

    comment_id = post_body.get("id")
    if not isinstance(comment_id, int):
        raise VerificationFailed(
            f"Probe comment POST response missing integer 'id': got {comment_id!r}."
        )

    # Step 2+3: READBACK — GET the comment we just created and check who
    # the server attributes it to. This is the load-bearing assertion.
    get_url = f"{base}/tasks/{task_id}/comments/{comment_id}"
    get_status, get_body = _http_request_json(get_url, token, method="GET")

    cleanup_ok = False
    actual_user: str | None = None
    try:
        if get_status != 200:
            raise VerificationFailed(
                f"Probe comment readback to {get_url} returned HTTP "
                f"{get_status}; cannot confirm attribution."
            )
        if not isinstance(get_body, dict):
            raise VerificationFailed(
                f"Probe comment readback returned unexpected body type "
                f"{type(get_body).__name__}; cannot read author."
            )

        # Vikunja v0.24.6 comment responses use `author` (not `created_by`)
        # to identify the writer — verified by live probe 2026-05-17. Earlier
        # versions of this code checked `created_by` and silently failed in
        # production. Tasks use `created_by`; comments use `author`.
        author = get_body.get("author") or {}
        actual_user = (
            author.get("username") if isinstance(author, dict) else None
        )
        if actual_user != expected_user:
            raise VerificationFailed(
                f"Attribution mismatch on NEW comment {comment_id} (task "
                f"{task_id}): expected author.username={expected_user!r}, "
                f"got {actual_user!r}. The rotated token does NOT cause new "
                f"writes to attribute to {expected_user!r}."
            )
    finally:
        # Step 4: CLEANUP — best-effort delete. Never raise from cleanup;
        # if delete fails, the operator will see the orphan probe comment
        # but the verification result still stands.
        try:
            _http_request_json(get_url, token, method="DELETE")
            cleanup_ok = True
        except VerificationFailed:
            # URLError during DELETE — leave the probe comment behind.
            cleanup_ok = False
        except Exception:
            cleanup_ok = False

    return {
        "verified": True,
        "task_id": task_id,
        "comment_id": comment_id,
        "created_by": actual_user,
        "cleanup_ok": cleanup_ok,
    }


def rollback(
    secrets_path: Path,
    bak_path: Path,
    gateway_unit: str,
    health_timeout: int,
    base_url: str,
    verify_task_id: int,
    skip_post_verify: bool = False,
) -> dict:
    """Restore secrets from `.bak`, restart gateway, verify kent attribution.

    Args:
        secrets_path: Live secrets path to restore.
        bak_path: `.bak` source.
        gateway_unit: systemd unit to restart.
        health_timeout: gateway health poll timeout in seconds.
        base_url: Vikunja API base URL for attribution probe.
        verify_task_id: Task to probe for kent attribution.
        skip_post_verify: If True, skip the post-rollback verify step.

    Returns:
        Summary dict with `rolled_back=True`, `attribution`, etc.

    Raises:
        FileNotFoundError: When `.bak` is missing.
        OSError: On filesystem errors.
        GatewayRestartFailed: On gateway restart failure.
        VerificationFailed: When post-rollback attribution is not kent.
    """
    if not bak_path.exists():
        raise FileNotFoundError(
            f"Cannot rollback: backup {bak_path} does not exist."
        )

    bak_content = _read_bytes(bak_path)
    if not bak_content:
        raise OSError(f"Backup {bak_path} is empty — refusing to restore.")

    _summary(phase="rollback_restore", result="start", bak=str(bak_path))
    atomic_write_file(secrets_path, bak_content, mode=0o600)

    readback = _read_bytes(secrets_path)
    if readback != bak_content:
        raise OSError(
            "Rollback readback mismatch — system is in an inconsistent "
            "state. Investigate manually."
        )
    _summary(phase="rollback_restore", result="ok", bytes=len(bak_content))

    _summary(phase="rollback_restart", result="start", unit=gateway_unit)
    restart_info = restart_gateway(gateway_unit, health_timeout)
    _summary(
        phase="rollback_restart",
        result="ok",
        duration_s=restart_info["restart_duration_s"],
    )

    if skip_post_verify:
        return {
            "rolled_back": True,
            "attribution": None,
            "skipped_verify": True,
            **restart_info,
        }

    # Post-rollback verification — kent should be the attribution now.
    _summary(phase="rollback_verify", result="start", expected=EXPECTED_KENT_USER)
    token = _read_bytes(secrets_path).decode("utf-8", errors="strict").strip()
    verify_info = verify_attribution(
        base_url=base_url,
        token=token,
        task_id=verify_task_id,
        expected_user=EXPECTED_KENT_USER,
    )
    _summary(phase="rollback_verify", result="ok", created_by=verify_info["created_by"])

    return {
        "rolled_back": True,
        "attribution": verify_info["created_by"],
        **restart_info,
    }


def _validate_pre_swap(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """Validate args for the swap-forward path. Returns (secrets, bak, new_token_file)."""
    secrets_path = Path(args.secrets_path)
    bak_path = Path(str(secrets_path) + args.bak_suffix)
    new_token_file = Path(args.new_token_file) if args.new_token_file else None

    if new_token_file is None:
        print("ERROR: --new-token-file is required for swap mode", file=sys.stderr)
        sys.exit(2)
    if not new_token_file.exists():
        print(f"ERROR: --new-token-file not found: {new_token_file}", file=sys.stderr)
        sys.exit(2)
    if not new_token_file.is_file():
        print(f"ERROR: --new-token-file is not a regular file: {new_token_file}", file=sys.stderr)
        sys.exit(2)

    ok, actual = _check_path_mode(new_token_file, 0o600)
    if not ok:
        print(
            f"ERROR: --new-token-file {new_token_file} mode is {oct(actual)}; "
            f"expected 0o600.",
            file=sys.stderr,
        )
        sys.exit(2)

    content = _read_bytes(new_token_file)
    if not content.strip():
        print(f"ERROR: --new-token-file {new_token_file} is empty", file=sys.stderr)
        sys.exit(2)

    if not secrets_path.exists():
        print(
            f"ERROR: --secrets-path {secrets_path} does not exist. "
            f"This helper rotates an existing secrets file; it does not create one.",
            file=sys.stderr,
        )
        sys.exit(2)

    return secrets_path, bak_path, new_token_file


def _validate_rollback(args: argparse.Namespace) -> tuple[Path, Path]:
    """Validate args for the --rollback-from-bak path. Returns (secrets, bak)."""
    secrets_path = Path(args.secrets_path)
    bak_path = Path(str(secrets_path) + args.bak_suffix)

    if not secrets_path.exists():
        print(
            f"ERROR: --secrets-path {secrets_path} does not exist — cannot "
            f"rollback an absent file.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not bak_path.exists():
        print(
            f"ERROR: backup file {bak_path} does not exist — nothing to roll back to.",
            file=sys.stderr,
        )
        sys.exit(2)

    return secrets_path, bak_path


def perform_swap(args: argparse.Namespace) -> int:
    """Drive the forward cutover with auto-rollback on verification failure."""
    secrets_path, bak_path, new_token_file = _validate_pre_swap(args)

    if args.dry_run:
        _summary(
            phase="dry_run",
            result="ok",
            secrets=str(secrets_path),
            bak=str(bak_path),
            new_token=str(new_token_file),
        )
        print(json.dumps({
            "dry_run": True,
            "would_backup": str(bak_path),
            "would_rotate": str(secrets_path),
            "would_restart": args.gateway_unit,
            "would_verify_user": EXPECTED_FELIX_USER,
        }))
        return 0

    new_token_bytes = _read_bytes(new_token_file)

    # --- Phase 1: Backup ---
    _summary(phase="backup", result="start", bak=str(bak_path))
    try:
        bak_info = backup_secrets(secrets_path, bak_path)
    except FileExistsError as exc:
        print(f"ERROR (backup): {exc}", file=sys.stderr)
        _summary(phase="backup", result="fail", reason="stale_bak")
        return 1
    except OSError as exc:
        print(f"ERROR (backup): {exc}", file=sys.stderr)
        _summary(phase="backup", result="fail", reason="io_error")
        return 1
    _summary(phase="backup", result="ok", bytes=bak_info["bak_size_bytes"])

    # --- Phases 2-4: Rotate + restart + verify (auto-rollback wrapped) ---
    try:
        _summary(phase="rotate", result="start", path=str(secrets_path))
        rotate_info = rotate_secrets(new_token_bytes, secrets_path)
        _summary(phase="rotate", result="ok", bytes=rotate_info["new_size_bytes"])

        _summary(phase="restart", result="start", unit=args.gateway_unit)
        restart_info = restart_gateway(args.gateway_unit, args.gateway_health_timeout)
        _summary(
            phase="restart",
            result="ok",
            duration_s=restart_info["restart_duration_s"],
        )

        if args.skip_post_verify:
            print(
                "WARN: --skip-post-verify set; not confirming attribution. "
                "This is for debugging only.",
                file=sys.stderr,
            )
            _summary(phase="verify", result="skipped")
            print(json.dumps({
                "swapped": True,
                "verified": False,
                "skipped_verify": True,
                **rotate_info,
                **restart_info,
            }))
            return 0

        _summary(phase="verify", result="start", expected=EXPECTED_FELIX_USER)
        verify_info = verify_attribution(
            base_url=args.vikunja_base_url,
            token=new_token_bytes.decode("utf-8", errors="strict").strip(),
            task_id=args.verify_task_id,
            expected_user=EXPECTED_FELIX_USER,
        )
        _summary(phase="verify", result="ok", created_by=verify_info["created_by"])

    except (VerificationFailed, GatewayRestartFailed, OSError, ValueError) as exc:
        print(f"ERROR (cutover): {type(exc).__name__}: {exc}", file=sys.stderr)
        print("AUTO-ROLLBACK INITIATED", file=sys.stderr)
        _summary(phase="auto_rollback", result="start", trigger=type(exc).__name__)
        try:
            rollback_info = rollback(
                secrets_path=secrets_path,
                bak_path=bak_path,
                gateway_unit=args.gateway_unit,
                health_timeout=args.gateway_health_timeout,
                base_url=args.vikunja_base_url,
                verify_task_id=args.verify_task_id,
                skip_post_verify=False,
            )
        except VerificationFailed as ve:
            print(
                f"CRITICAL: rollback completed file restore + restart but "
                f"post-rollback attribution verification still failed: {ve}\n"
                f"System is in a DEEPLY DEGRADED state. Investigate manually. "
                f"Secrets file may still contain the rejected token; "
                f"backup is at {bak_path}.",
                file=sys.stderr,
            )
            _summary(phase="auto_rollback", result="degraded", reason="verify_failed")
            return 1
        except (GatewayRestartFailed, OSError, FileNotFoundError) as rb_exc:
            print(
                f"CRITICAL: rollback itself failed: {type(rb_exc).__name__}: {rb_exc}\n"
                f"System may be in an INCONSISTENT state. Investigate immediately. "
                f"Backup is at {bak_path}.",
                file=sys.stderr,
            )
            _summary(phase="auto_rollback", result="fail", reason=type(rb_exc).__name__)
            return 1
        _summary(
            phase="auto_rollback",
            result="ok",
            attribution=rollback_info["attribution"],
        )
        return 1

    # --- Success ---
    print(json.dumps({
        "swapped": True,
        "verified": True,
        "secrets_path": str(secrets_path),
        "bak_path": str(bak_path),
        "created_by": verify_info["created_by"],
        "gateway_unit": args.gateway_unit,
        "restart_duration_s": restart_info["restart_duration_s"],
    }))
    return 0


def perform_manual_rollback(args: argparse.Namespace) -> int:
    """Drive operator-triggered rollback (--rollback-from-bak)."""
    secrets_path, bak_path = _validate_rollback(args)

    if args.dry_run:
        _summary(
            phase="dry_run_rollback",
            result="ok",
            secrets=str(secrets_path),
            bak=str(bak_path),
        )
        print(json.dumps({
            "dry_run": True,
            "would_restore_from": str(bak_path),
            "would_restart": args.gateway_unit,
            "would_verify_user": EXPECTED_KENT_USER,
        }))
        return 0

    _summary(phase="manual_rollback", result="start", bak=str(bak_path))
    try:
        info = rollback(
            secrets_path=secrets_path,
            bak_path=bak_path,
            gateway_unit=args.gateway_unit,
            health_timeout=args.gateway_health_timeout,
            base_url=args.vikunja_base_url,
            verify_task_id=args.verify_task_id,
            skip_post_verify=args.skip_post_verify,
        )
    except VerificationFailed as exc:
        print(
            f"CRITICAL: rollback restored .bak and restarted gateway but "
            f"post-rollback attribution verification failed: {exc}\n"
            f"System is in a DEEPLY DEGRADED state. Investigate manually.",
            file=sys.stderr,
        )
        _summary(phase="manual_rollback", result="degraded", reason="verify_failed")
        return 1
    except (GatewayRestartFailed, OSError, FileNotFoundError) as exc:
        print(
            f"ERROR (manual_rollback): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        _summary(phase="manual_rollback", result="fail", reason=type(exc).__name__)
        return 1

    _summary(
        phase="manual_rollback",
        result="ok",
        attribution=info.get("attribution"),
    )
    print(json.dumps({
        "rolled_back": True,
        **info,
    }))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--new-token-file",
        type=str,
        default=None,
        help="Path to file containing felix-bot's API token (output of WP01).",
    )
    parser.add_argument(
        "--secrets-path",
        type=str,
        default=DEFAULT_SECRETS_PATH,
        help=f"Live Vikunja secrets path (default {DEFAULT_SECRETS_PATH}).",
    )
    parser.add_argument(
        "--bak-suffix",
        type=str,
        default=DEFAULT_BAK_SUFFIX,
        help=f"Suffix appended to --secrets-path for the .bak (default {DEFAULT_BAK_SUFFIX}).",
    )
    parser.add_argument(
        "--gateway-unit",
        type=str,
        default=DEFAULT_GATEWAY_UNIT,
        help=f"systemd --user unit to restart (default {DEFAULT_GATEWAY_UNIT}).",
    )
    parser.add_argument(
        "--gateway-health-timeout",
        type=int,
        default=DEFAULT_GATEWAY_HEALTH_TIMEOUT,
        help=f"Seconds to wait for is-active=active (default {DEFAULT_GATEWAY_HEALTH_TIMEOUT}).",
    )
    parser.add_argument(
        "--vikunja-base-url",
        type=str,
        default=DEFAULT_VIKUNJA_BASE_URL,
        help=f"Vikunja API base URL (default {DEFAULT_VIKUNJA_BASE_URL}).",
    )
    parser.add_argument(
        "--verify-task-id",
        type=int,
        default=DEFAULT_VERIFY_TASK_ID,
        help=f"Task ID to probe for attribution (default {DEFAULT_VERIFY_TASK_ID}).",
    )
    parser.add_argument(
        "--rollback-from-bak",
        action="store_true",
        help="Operator-driven rollback mode: restore .bak, restart gateway, verify kent.",
    )
    parser.add_argument(
        "--skip-post-verify",
        action="store_true",
        help="Skip the post-swap attribution probe. For debugging only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without writing files, restarting, or probing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.rollback_from_bak and args.new_token_file:
        print(
            "ERROR: --rollback-from-bak and --new-token-file are mutually exclusive.",
            file=sys.stderr,
        )
        return 2

    if args.skip_post_verify and not (args.rollback_from_bak or args.dry_run):
        # In forward-swap mode without verification, the helper cannot
        # uphold its safety contract — exit per WP03 T011 guidance.
        print(
            "ERROR: --skip-post-verify is not permitted in forward-swap mode. "
            "Use it only with --rollback-from-bak or --dry-run for debugging.",
            file=sys.stderr,
        )
        return 2

    if args.rollback_from_bak:
        return perform_manual_rollback(args)

    return perform_swap(args)


if __name__ == "__main__":
    sys.exit(main())
