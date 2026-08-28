#!/usr/bin/env python3
"""Capture the ``claude`` user's crontab into backed-up storage.

The problem this solves (kentonium3/kg-automation#895): on 2026-08-27 the
``claude`` crontab was destroyed along with ``/home/claude``, and the only
surviving copy was ``/data/services/security-monitor/baselines/crontabs.txt`` —
a file written for *drift detection*, not as a backup, and one the documented
rebaseline procedure deletes. ``/var/spool/cron`` is not in the Restic source
set, so the crontab was not recoverable from a snapshot.

This helper writes the crontab under ``/data/services/``, which *is* already a
Restic source path. That is deliberate: ``restic forget`` in
``scripts/office2/restic-backup.sh`` runs without ``--group-by`` and therefore
defaults to ``host,paths``, so adding a fifth source path would split the
snapshot path-group and permanently strand the existing snapshots from pruning.
Writing into an existing source path avoids that entirely.

Scope: the ``claude`` crontab only. ``crontab -u kgale -l`` and
``crontab -u root -l`` both return permission denied to an unprivileged reader,
so covering them would need sudo (Tier 0). Nothing here claims otherwise.

The refusal rules below are the point of this helper, not garnish. It runs on a
timer, which means it can fire *during* the incident it protects against — if
the crontab is being destroyed at 13:21 and this runs at 13:22, a naive
implementation would overwrite the good artifact with an empty one and the next
backup would faithfully preserve the emptiness.

Usage:
    python3 scripts/office2/crontab_capture.py
    python3 scripts/office2/crontab_capture.py --dry-run
    python3 scripts/office2/crontab_capture.py --force   # bypass shrink guard only

Exit codes:
    0  success (captured, or unchanged)
    1  operational error, including a refused capture
    2  usage error
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ARTIFACT_PATH = Path("/data/services/host-state/crontabs/claude.crontab")
DEFAULT_STATE_PATH = Path("/data/services/host-state/last-tick.json")

#: A successful read whose body is smaller than this fraction of the stored body
#: is treated as suspicious truncation and refused. ``crontab -l`` reads a local
#: spool file and is unlikely to return a partial success — but "unlikely" is not
#: an invariant, and the cost of the guard is one comparison against a failure
#: that silently destroys the artifact this helper exists to create.
SHRINK_REFUSE_RATIO = 0.5

HEADER_PREFIX = "# "
#: First and last lines of the provenance header. The header is delimited by an
#: explicit sentinel rather than matched heuristically, so a user's own leading
#: ``#`` comments in the crontab are never mistaken for ours and stripped.
HEADER_FIRST_LINE = "# captured-by: crontab_capture.py"
HEADER_SENTINEL = "# --- end crontab_capture header ---"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_crontab() -> tuple[int, bytes]:
    """Return ``(returncode, stdout_bytes)`` from ``crontab -l``.

    Deliberately **not** ``text=True``. Text mode applies universal-newline
    translation (CRLF -> LF) and locale decoding, either of which would silently
    break the promise that the stored body is byte-identical to ``crontab -l``
    output — and a crontab containing non-UTF-8 bytes would raise outright.
    Byte identity is FR-003, so the whole capture path stays bytes-native and
    only the JSON pointer is text.

    Injected by tests so the suite never touches a real crontab.
    """
    proc = subprocess.run(["crontab", "-l"], capture_output=True)
    return proc.returncode, proc.stdout


def build_header(*, user: str, host: str, now: str) -> bytes:
    """Provenance header, so a file found in a months-old snapshot explains itself."""
    return (
        f"{HEADER_FIRST_LINE}\n"
        f"{HEADER_PREFIX}captured-at-utc: {now}\n"
        f"{HEADER_PREFIX}source-user: {user}\n"
        f"{HEADER_PREFIX}source-host: {host}\n"
        f"{HEADER_PREFIX}NOTE: reinstall with `crontab <file>` — cron ignores leading\n"
        f"{HEADER_PREFIX}comments, so this file is directly reinstallable as-is.\n"
        f"{HEADER_SENTINEL}\n"
    ).encode("utf-8")


def strip_header(data: bytes) -> bytes:
    """Return the crontab body, dropping only our own provenance header.

    Bytes in, bytes out — the body must survive untouched, including CRLF, a
    missing trailing newline, and non-UTF-8 content. The header is recognised by
    its exact first line and terminated by an explicit sentinel, so a user's own
    leading comments are never mistaken for ours.
    """
    if not data.startswith(HEADER_FIRST_LINE.encode("utf-8")):
        return data
    lines = data.splitlines(keepends=True)
    sentinel = HEADER_SENTINEL.encode("utf-8")
    for i, line in enumerate(lines):
        if line.rstrip(b"\r\n") == sentinel:
            return b"".join(lines[i + 1:])
    # First line matched but no sentinel: refuse to guess, treat it all as body.
    return data


def write_atomic(path: Path, value: bytes) -> None:
    """Write ``value`` to ``path`` atomically (tempfile + os.replace)."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(value)
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except FileNotFoundError:
            mode = 0o644
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_state(state_path: Path, payload: dict) -> None:
    """Write the freshness pointer. Never fatal.

    Losing the freshness signal is strictly preferable to failing the capture,
    matching the convention in scripts/openclaw/deploy/deploy_agent_prompts.py.
    """
    try:
        write_atomic(state_path, (json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    except OSError:
        pass


def _state(
    *,
    status: str,
    exit_code: int,
    artifact_path: Path,
    artifact_bytes: int,
    artifact_changed: bool,
    user: str,
) -> dict:
    return {
        "status": status,
        "exit_code": exit_code,
        "completed_at_utc": _utc_now_iso(),
        "artifact_path": str(artifact_path),
        "artifact_bytes": artifact_bytes,
        "artifact_changed": artifact_changed,
        "source_user": user,
    }


def capture(
    *,
    artifact_path: Path,
    state_path: Path,
    force: bool = False,
    dry_run: bool = False,
    read_crontab=_read_crontab,
    user: str | None = None,
    host: str | None = None,
) -> int:
    """Capture the crontab. Returns the process exit code."""
    user = user or os.environ.get("USER") or "claude"
    host = host or socket.gethostname()

    existing_body = b""
    if artifact_path.exists():
        try:
            existing_body = strip_header(artifact_path.read_bytes())
        except OSError as exc:
            # Read as bytes so a non-UTF-8 artifact cannot raise UnicodeDecodeError
            # here — that would escape this handler and abort before the freshness
            # pointer is written, hiding the failure from the canary entirely.
            print(f"ERROR: cannot read existing artifact {artifact_path}: {exc}", file=sys.stderr)

    def refuse(reason: str) -> int:
        # Preserving the old artifact is the right *data* outcome, but it is not
        # a healthy run and must not be recorded as one — a refusal that reports
        # success is the #891 defect class (a check that cannot fail).
        print(f"WARN: refusing to overwrite artifact — {reason}")
        print(f"ERROR: capture refused — {reason}", file=sys.stderr)
        write_state(
            state_path,
            _state(
                status="error",
                exit_code=1,
                artifact_path=artifact_path,
                artifact_bytes=len(existing_body),
                artifact_changed=False,
                user=user,
            ),
        )
        print(
            f"SUMMARY: captured=false changed=false bytes={len(existing_body)} "
            f"refused=true reason={reason.split(' ')[0]}"
        )
        return 1

    rc, stdout = read_crontab()

    if rc != 0:
        return refuse(f"crontab-read-failed (exit {rc})")
    if not stdout.strip():
        return refuse("empty-crontab-read")

    new_body = stdout
    # First run (no prior artifact) is never a shrink.
    if existing_body and not force:
        old_len, new_len = len(existing_body), len(new_body)
        if old_len and new_len < old_len * SHRINK_REFUSE_RATIO:
            return refuse(f"suspicious-truncation ({new_len} vs stored {old_len} bytes)")
    elif existing_body and force:
        print("WARN: --force given; shrink guard bypassed")

    changed = new_body != existing_body
    artifact_bytes = len(new_body)

    if dry_run:
        print(f"INFO: dry-run — would {'rewrite' if changed else 'leave unchanged'} {artifact_path}")
        print(f"SUMMARY: captured=false changed={str(changed).lower()} bytes={artifact_bytes} refused=false")
        return 0

    if changed:
        content = build_header(user=user, host=host, now=_utc_now_iso()) + new_body
        try:
            write_atomic(artifact_path, content)
        except OSError as exc:
            print(f"ERROR: cannot write artifact {artifact_path}: {exc}", file=sys.stderr)
            write_state(
                state_path,
                _state(
                    status="error", exit_code=1, artifact_path=artifact_path,
                    artifact_bytes=len(existing_body), artifact_changed=False, user=user,
                ),
            )
            print("SUMMARY: captured=false changed=false bytes=0 refused=false")
            return 1
        print(f"INFO: artifact updated ({artifact_bytes} bytes)")
    else:
        # Idempotent: unchanged content leaves the artifact's mtime alone so the
        # backup sees no churn. The pointer still advances, so freshness is real.
        print("INFO: crontab unchanged; artifact left untouched")

    write_state(
        state_path,
        _state(
            status="success", exit_code=0, artifact_path=artifact_path,
            artifact_bytes=artifact_bytes, artifact_changed=changed, user=user,
        ),
    )
    print(
        f"SUMMARY: captured=true changed={str(changed).lower()} "
        f"bytes={artifact_bytes} refused=false"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crontab_capture.py",
        description="Capture the claude crontab into Restic-backed-up storage (#895).",
    )
    p.add_argument("--artifact-path", type=Path, default=DEFAULT_ARTIFACT_PATH,
                   help="Where the captured crontab is written.")
    p.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH,
                   help="Where the freshness pointer is written.")
    p.add_argument("--force", action="store_true",
                   help="Bypass the shrink guard only. Never bypasses the empty/failed guard.")
    p.add_argument("--dry-run", action="store_true", help="Report intent; write nothing.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return capture(
            artifact_path=args.artifact_path,
            state_path=args.state_path,
            force=args.force,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        # Any escape here still owes the canary a signal and the caller a SUMMARY.
        # Silence would read as "never ran" only after max_age elapses; an explicit
        # error pointer is visible immediately.
        print(f"ERROR: unexpected failure: {exc}", file=sys.stderr)
        write_state(
            args.state_path,
            _state(
                status="error",
                exit_code=1,
                artifact_path=args.artifact_path,
                artifact_bytes=0,
                artifact_changed=False,
                user=os.environ.get("USER") or "claude",
            ),
        )
        print("SUMMARY: captured=false changed=false bytes=0 refused=false error=unexpected")
        return 1


if __name__ == "__main__":
    sys.exit(main())
