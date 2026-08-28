#!/usr/bin/env python3
"""Compare the repo's backup script against the copy deployed on office2 (#903).

``scripts/office2/restic-backup.sh`` is the repo source of truth for the live
``/data/services/backup/scripts/backup.sh``, but nothing has ever compared them.
#889 changed the repo copy with no manifest and the live file was installed by
hand; they currently match, which is luck rather than enforcement — on the one
script the Tier-2 change-control guarantee depends on.

WHY THIS ONLY OBSERVES. ``/data/services/backup/scripts/`` is ``root:root``
deliberately: it holds the ``NOPASSWD`` sudo target ``backup.sh``, and a
claude-writable directory on that path makes the grant equivalent to
``NOPASSWD: ALL``. That was #899, a real privilege escalation fixed on
2026-08-27. So this component never writes there and never remediates. The
operator installs; this reports.

FAIL CLOSED. An unreadable deployed copy is ``inconclusive``, never ``match``.
A comparator that reports agreement when it cannot see one side converts an
unknown into a false assurance, which is the failure mode it exists to prevent.

Usage:
    python3 scripts/office2/backup_script_drift.py
    python3 scripts/office2/backup_script_drift.py --dry-run

Exit codes:
    0  match
    1  drift
    2  inconclusive, or usage error
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REPO_PATH = Path("/home/claude/kg-automation/scripts/office2/restic-backup.sh")
DEFAULT_DEPLOYED_PATH = Path("/data/services/backup/scripts/backup.sh")
#: NOT under /data/services/backup/state/ -- that directory is root:root and this
#: component runs as claude, so writes there fail. The parent
#: /data/services/backup/ IS claude-owned, so a sibling directory works and stays
#: inside the Restic source set. Learned the hard way: the first deploy failed
#: post-verification because the pointer could not be created at all.
DEFAULT_STATE_PATH = Path("/data/services/backup/drift/script-drift-last-tick.json")

MATCH = "match"
DRIFT = "drift"
INCONCLUSIVE = "inconclusive"

#: verdict -> (status, exit_code). ``verdict`` is diagnostic; health rides on
#: ``status``/``exit_code``, which are the keys the canary's explicit-error scan
#: actually reads. ``verdict`` is named to avoid colliding with that scan's keys
#: (error/errors/exit_status/cycle_error).
_HEALTH = {MATCH: ("success", 0), DRIFT: ("error", 1), INCONCLUSIVE: ("error", 2)}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(path: Path) -> tuple[str | None, str | None]:
    """Return ``(md5, reason_unreadable)`` for *path*, refusing to follow symlinks.

    ``O_NOFOLLOW`` and the ``S_ISREG`` check are the security-relevant part, not
    the hash. ``Path.read_bytes()`` follows symlinks, so a deployed ``backup.sh``
    that was a symlink into ``/home/claude/kg-automation/`` would hash the repo
    file and report ``match`` — reporting clean in exactly the situation that
    matters most, because the deployed sudo target would then be effectively
    claude-controlled. That is #899 wearing a disguise, and a comparator that
    blesses it is worse than none.

    Anything that is not a plain regular file we can open without traversing a
    link is ``inconclusive``.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        if getattr(exc, "errno", None) in (errno.ELOOP, errno.EMLINK):
            return None, f"{path} is a symlink; refusing to follow"
        return None, f"{path} unreadable: {exc.strerror or exc}"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, f"{path} is not a regular file"
        h = hashlib.md5()
        with os.fdopen(fd, "rb", closefd=True) as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest(), None
    except OSError as exc:
        try:
            os.close(fd)
        except OSError:
            pass
        return None, f"{path} unreadable: {exc.strerror or exc}"


def compare(repo_path, deployed_path) -> dict:
    """Compare two files. Pure: reads only, never writes, no side effects."""
    repo_path, deployed_path = Path(repo_path), Path(deployed_path)
    repo_md5, repo_why = _digest(repo_path)
    deployed_md5, deployed_why = _digest(deployed_path)

    if repo_md5 is None or deployed_md5 is None:
        why = [w for w in (repo_why, deployed_why) if w]
        return {
            "verdict": INCONCLUSIVE,
            "repo_md5": repo_md5,
            "deployed_md5": deployed_md5,
            "detail": "; ".join(why),
        }

    verdict = MATCH if repo_md5 == deployed_md5 else DRIFT
    return {
        "verdict": verdict,
        "repo_md5": repo_md5,
        "deployed_md5": deployed_md5,
        "detail": "identical" if verdict == MATCH else "contents differ",
    }


def write_atomic(path: Path, value: bytes) -> None:
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


_PROTECTED_PREFIX = Path("/data/services/backup/scripts")


def _reject_protected_state_path(state_path: Path) -> None:
    """Refuse to write anywhere under the root-owned scripts directory.

    The default state path is nowhere near it and neither the unit nor the deploy
    passes ``--state-path``. But this component owns a flag-controlled write
    primitive, and it exists specifically to guard a directory that must never
    become claude-writable. Closing the path here means a future permissions
    regression cannot be turned into a write by this tool.
    """
    try:
        resolved = state_path.resolve()
    except OSError:
        resolved = state_path
    if resolved == _PROTECTED_PREFIX or _PROTECTED_PREFIX in resolved.parents:
        raise ValueError(
            f"refusing to write state under {_PROTECTED_PREFIX} — this component "
            "observes that directory and must never write to it (#899)"
        )


def write_state(state_path: Path, result: dict) -> bool:
    """Record the run. Returns True on success.

    Failure is reported rather than swallowed. A silent failure here is not
    harmless: if a previous run wrote a fresh ``success`` pointer and this run
    detects drift but cannot update it, the canary keeps reading the stale clean
    result until it ages out — the component would be reporting healthy while
    knowing otherwise.
    """
    status, exit_code = _HEALTH[result["verdict"]]
    payload = {
        "status": status,
        "exit_code": exit_code,
        "completed_at_utc": _utc_now_iso(),
        "verdict": result["verdict"],
        "repo_md5": result["repo_md5"],
        "deployed_md5": result["deployed_md5"],
    }
    _reject_protected_state_path(state_path)
    try:
        write_atomic(state_path, (json.dumps(payload, indent=2) + "\n").encode("utf-8"))
        return True
    except OSError as exc:
        print(f"ERROR: could not write state pointer {state_path}: {exc}", file=sys.stderr)
        print("WARN: a stale healthy pointer may persist until it ages out", file=sys.stderr)
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backup_script_drift.py",
        description="Detect divergence between the repo and deployed backup script (#903).",
    )
    p.add_argument("--repo-path", type=Path, default=DEFAULT_REPO_PATH)
    p.add_argument("--deployed-path", type=Path, default=DEFAULT_DEPLOYED_PATH)
    p.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    p.add_argument("--dry-run", action="store_true", help="Compare and report; write no state.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = compare(args.repo_path, args.deployed_path)
    verdict = result["verdict"]
    _, exit_code = _HEALTH[verdict]

    if verdict == MATCH:
        print(f"INFO: repo and deployed backup script agree ({result['repo_md5']})")
    elif verdict == DRIFT:
        print(f"WARN: backup script DRIFT — repo {result['repo_md5']} "
              f"vs deployed {result['deployed_md5']}")
        print("WARN: the operator must reinstall; this component never writes "
              "to the deployed path (see #899)")
    else:
        print(f"WARN: comparison inconclusive — {result['detail']}")
        print(f"ERROR: cannot compare backup script — {result['detail']}", file=sys.stderr)

    if not args.dry_run:
        if not write_state(args.state_path, result) and exit_code == 0:
            # A clean comparison we could not record is not a clean run: the
            # previous pointer may still say success and would keep reading fresh.
            exit_code = 2

    print(f"SUMMARY: verdict={verdict} repo_md5={result['repo_md5']} "
          f"deployed_md5={result['deployed_md5']} exit_code={exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
