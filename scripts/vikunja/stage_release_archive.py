#!/usr/bin/env python3
"""Ingress helper: copy the Vikunja release archives to office2 (#1087, WP07).

Operator helper. It runs on **office4** and copies both archives named in
``services/vikunja/release.json`` from the PM's office4 custody paths
(``roots.office4_sources``) into a create-only, ``claude``-owned 0700 folder
on office2, through ``ssh office2-claude`` only (research R-4, FR-006, C-002).

Usage: ``stage_release_archive.py --dry-run | --apply`` (anything else exits 2).

``--dry-run`` makes no remote change. It refuses forbidden paths, hashes both
office4 sources against the record, and over SSH checks whether the artifacts
parent exists (``parent_code=EXISTS|CREATE``; an existing parent must be a
real folder, not a symlink, owned by ``claude``, mode 700, else
``INGRESS_DEST_PARENT_UNSAFE``), that the destination does not exist
(``test ! -e``), and that ``/data`` has at least twice the total archive size
free.

``--apply`` repeats every dry-run check, then:

1. Creates the artifacts parent when absent (``umask 077 && mkdir``, no
   ``-p``) and verifies it in one remote command as above.
2. ``umask 077 && mkdir <dest>``: create-only; an existing folder is
   ``INGRESS_DEST_EXISTS``.
3. For each archive, a ``test ! -e <final>`` pre-check (fast path; an
   existing final is ``INGRESS_DEST_FILE_EXISTS``), then
   ``set -o noclobber; cat > <dest>/.<name>.<nonce>.part`` with the local
   file on the ssh stdin and a timeout scaled to its size. The nonce is
   128-bit (``secrets.token_hex(16)``), so only this run can have created
   that path.
4. Remote ``sha256sum`` of the part must equal the record
   (``INGRESS_SHA_MISMATCH`` otherwise). Then ``ln -T -- <part> <final>``,
   which refuses anything at final (a folder or a symlink to one included) (``INGRESS_DEST_FILE_EXISTS``: both files are
   kept and the part path is reported on stderr), then ``rm -f -- <part>``.
   Cleanup on any other failure removes only this run's part, never a final.
5. Prints both remote shas.

Refusals (no ssh call is made): a source under ``/home/codex`` (the PM's
custody evidence, never read), or a destination outside
``/data/services/vikunja/release-artifacts/``.

Output (R-16): stdout carries a summary line first, then detail lines, with
only allowlisted values (paths, hashes, counts, codes). Raw ssh stderr goes
only to a private 0700 folder on office4. Every subprocess call is
time-bounded (R-15). It never overwrites, never escalates privilege, never uses another account.
"""

from __future__ import annotations

import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.vikunja_release import core  # noqa: E402

PROG = "stage_release_archive.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE = REPO_ROOT / "services" / "vikunja" / "release.json"
DEFAULT_PRIVATE_ROOT = Path.home() / ".local" / "state" / "vikunja-release-ingress" / "failures"

#: Every remote argv starts with exactly this prefix (C-002).
SSH_PREFIX: tuple[str, ...] = ("ssh", "-o", "BatchMode=yes", "office2-claude")
DEST_PARENT = "/data/services/vikunja/release-artifacts"
#: The artifacts parent must be a real folder owned by this user, mode 700.
REMOTE_USER = "claude"
PARENT_MODE = "700"
FORBIDDEN_SOURCE_ROOT = "/home/codex"
SPACE_PATH = "/data"
SPACE_FACTOR = 2

CHECK_TIMEOUT = 30
#: Transfer and hash timeouts: a base plus the size at a conservative rate.
TRANSFER_BASE = 60
TRANSFER_RATE = 1024 * 1024  # bytes per second (1 MiB/s floor)
HASH_BASE = 60
HASH_RATE = 20 * 1024 * 1024

_COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")

core.register_summaries("INGRESS_DRY_RUN_OK", "INGRESS_APPLIED", "INGRESS_SOURCE_VERIFIED",
                        "INGRESS_REMOTE_SHA", "INGRESS_PLAN", "INGRESS_PART_KEPT")


# ---------------------------------------------------------------------------
# Plan and path refusals
# ---------------------------------------------------------------------------

def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _items(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    sources = record["roots"]["office4_sources"]
    return [
        {"source": sources["archive"], **record["archive"]},
        {"source": sources["rollback_archive"], **record["rollback"]["archive"]},
    ]


def plan(record: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(dest, items)``; each item has ``source``, ``remote``,
    ``sha256`` and ``size``. Refuses before any read or remote call:

    * ``INGRESS_SOURCE_FORBIDDEN``: a source (literal or resolved) under
      ``/home/codex``.
    * ``INGRESS_DEST_FORBIDDEN``: a destination that is not exactly one plain
      folder directly under ``/data/services/vikunja/release-artifacts/``,
      archives in different folders, or an unsafe or duplicate file name.
    """
    items = _items(record)
    for item in items:
        src = item["source"]
        if _under(src, FORBIDDEN_SOURCE_ROOT) or _under(os.path.realpath(src), FORBIDDEN_SOURCE_ROOT):
            raise core.Fail("INGRESS_SOURCE_FORBIDDEN")
    dests = {os.path.dirname(item["path"]) for item in items}
    if len(dests) != 1:
        raise core.Fail("INGRESS_DEST_FORBIDDEN")
    dest = dests.pop()
    parent, leaf = os.path.split(dest)
    if parent != DEST_PARENT or not _COMPONENT_RE.fullmatch(leaf) or leaf in (".", ".."):
        raise core.Fail("INGRESS_DEST_FORBIDDEN")
    names = [os.path.basename(item["path"]) for item in items]
    if len(set(names)) != len(names) or not all(_COMPONENT_RE.fullmatch(n) for n in names):
        raise core.Fail("INGRESS_DEST_FORBIDDEN")
    out = [{"source": item["source"], "remote": f"{dest}/{name}", "sha256": item["sha256"],
            "size": item["size"]} for item, name in zip(items, names)]
    return dest, out


# ---------------------------------------------------------------------------
# Remote calls (all through ``ssh office2-claude``)
# ---------------------------------------------------------------------------

def remote_argv(command: str) -> list[str]:
    """The full argv for one remote shell command."""
    return [*SSH_PREFIX, command]


def _ssh(command: str, timeout: float, step: str, runner: core.Runner) -> tuple[int, str, str]:
    return core.run(remote_argv(command), timeout, step=step, runner=runner)


def _ssh_failed(rc: int, err: str, code: str) -> core.Fail:
    """255 is ssh's own failure (connection, auth); anything else is *code*."""
    return core.Fail("INGRESS_SSH_FAILED" if rc == 255 else code, detail_private=err)


def scaled_timeout(size: int, base: int, rate: int) -> int:
    return base + -(-size // rate)


def check_parent(runner: core.Runner) -> bool:
    """True when the artifacts parent exists (as anything, a symlink included);
    False when it is absent. Read-only."""
    p = shlex.quote(DEST_PARENT)
    rc, _, err = _ssh(f"test -e {p} || test -L {p}", CHECK_TIMEOUT, "INGRESS_PARENT_CHECK", runner)
    if rc == 0:
        return True
    if rc == 1:
        return False
    raise _ssh_failed(rc, err, "INGRESS_REMOTE_CHECK_FAILED")


def parent_safety_command() -> str:
    p = shlex.quote(DEST_PARENT)
    return (f"test -d {p} && test ! -L {p} && test \"$(stat -c %U {p})\" = {REMOTE_USER} "
            f"&& test \"$(stat -c %a {p})\" = {PARENT_MODE}")


def verify_parent(runner: core.Runner) -> None:
    """One remote command: a real folder (not a symlink), owned by
    ``claude``, mode 700. Anything else is ``INGRESS_DEST_PARENT_UNSAFE``."""
    rc, _, err = _ssh(parent_safety_command(), CHECK_TIMEOUT, "INGRESS_PARENT_VERIFY", runner)
    if rc == 255:
        raise core.Fail("INGRESS_SSH_FAILED", detail_private=err)
    if rc != 0:
        raise core.Fail("INGRESS_DEST_PARENT_UNSAFE", detail_private=err)


def ensure_parent(runner: core.Runner) -> None:
    """Create the artifacts parent when absent (``umask 077 && mkdir``, no
    ``-p``), then verify it. An existing parent is only verified."""
    if not check_parent(runner):
        rc, _, err = _ssh(f"umask 077 && mkdir {shlex.quote(DEST_PARENT)}", CHECK_TIMEOUT,
                          "INGRESS_PARENT_MKDIR", runner)
        if rc == 255:
            raise core.Fail("INGRESS_SSH_FAILED", detail_private=err)
        if rc != 0 and not check_parent(runner):
            raise core.Fail("INGRESS_DEST_PARENT_CREATE_FAILED", detail_private=err)
    verify_parent(runner)


def check_remote(dest: str, total: int, runner: core.Runner) -> tuple[int, bool]:
    """Read-only remote checks. Returns ``(free bytes on /data, parent
    exists)``. An existing parent must pass :func:`verify_parent`."""
    parent_exists = check_parent(runner)
    if parent_exists:
        verify_parent(runner)
    rc, _, err = _ssh(f"test ! -e {shlex.quote(dest)}", CHECK_TIMEOUT, "INGRESS_DEST_CHECK", runner)
    if rc == 1:
        raise core.Fail("INGRESS_DEST_EXISTS")
    if rc != 0:
        raise _ssh_failed(rc, err, "INGRESS_REMOTE_CHECK_FAILED")
    rc, out, err = _ssh(f"df --output=avail -B1 {shlex.quote(SPACE_PATH)}", CHECK_TIMEOUT,
                        "INGRESS_SPACE_CHECK", runner)
    if rc != 0:
        raise _ssh_failed(rc, err, "INGRESS_REMOTE_CHECK_FAILED")
    lines = [line.strip() for line in out.strip().splitlines()]
    if len(lines) != 2 or not lines[1].isdigit():
        raise core.Fail("INGRESS_SPACE_UNPARSEABLE", detail_private=out)
    avail = int(lines[1])
    if avail < SPACE_FACTOR * total:
        raise core.Fail("INGRESS_SPACE_INSUFFICIENT")
    return avail, parent_exists


def _remove(remote: str, runner: core.Runner) -> None:
    """Best effort ``rm -f`` of this run's own ``.part`` path; never raises.
    Only ever called with a path from :func:`part_path`."""
    try:
        _ssh(f"rm -f -- {shlex.quote(remote)}", CHECK_TIMEOUT, "INGRESS_REMOVE", runner)
    except core.Fail:
        pass


_NONCE_RE = re.compile(r"[0-9a-f]{32}")


def new_nonce() -> str:
    """A 128-bit nonce for one ``.part`` name."""
    return secrets.token_hex(16)


def part_path(final: str, nonce: str) -> str:
    """``<dest>/.<name>.<nonce>.part``: a name only this run can have chosen,
    so a file at this path was created by this run's noclobber stream."""
    if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
        raise ValueError("nonce must be 32 lowercase hex characters")
    folder, name = os.path.split(final)
    return f"{folder}/.{name}.{nonce}.part"


def _stream(item: Mapping[str, Any], part: str, runner: core.Runner) -> None:
    """Stream one local file into this run's new ``.part`` path (noclobber).
    On any failure only *part* is removed."""
    argv = remote_argv(f"set -o noclobber; cat > {shlex.quote(part)}")
    timeout = scaled_timeout(item["size"], TRANSFER_BASE, TRANSFER_RATE)
    try:
        fd = os.open(item["source"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise core.Fail("INGRESS_SOURCE_UNREADABLE") from exc
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            raise core.Fail("INGRESS_SOURCE_UNREADABLE")
        try:
            proc = runner(argv, stdin=fh, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            _remove(part, runner)
            raise core.Fail("INGRESS_TRANSFER_TIMEOUT", detail_private=_text(exc.stderr)) from exc
        except OSError as exc:
            _remove(part, runner)
            raise core.Fail("INGRESS_EXEC_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
    if proc.returncode != 0:
        _remove(part, runner)
        raise _ssh_failed(proc.returncode, _text(proc.stderr) or "", "INGRESS_TRANSFER_FAILED")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _remote_sha(item: Mapping[str, Any], part: str, runner: core.Runner) -> str:
    """Remote sha256 of this run's ``.part``; removes only the part on any
    failure or mismatch."""
    timeout = scaled_timeout(item["size"], HASH_BASE, HASH_RATE)
    try:
        rc, out, err = _ssh(f"sha256sum -- {shlex.quote(part)}", timeout, "INGRESS_REMOTE_HASH", runner)
    except core.Fail:
        _remove(part, runner)
        raise
    if rc != 0:
        _remove(part, runner)
        raise _ssh_failed(rc, err, "INGRESS_REMOTE_HASH_FAILED")
    fields = out.split()
    actual = fields[0] if fields else ""
    if not _HEX64_RE.fullmatch(actual) or actual != item["sha256"]:
        _remove(part, runner)
        raise core.Fail("INGRESS_SHA_MISMATCH")
    return actual


def _final_present(final: str, runner: core.Runner) -> bool | None:
    """True when anything (a symlink included) is at *final*, False when
    nothing is, None when the probe is inconclusive (ssh failure, timeout,
    exec failure)."""
    q = shlex.quote(final)
    try:
        rc, _, _ = _ssh(f"test -e {q} || test -L {q}", CHECK_TIMEOUT, "INGRESS_FILE_CHECK", runner)
    except core.Fail:
        return None
    return {0: True, 1: False}.get(rc)


def _publish(item: Mapping[str, Any], part: str, runner: core.Runner, err_out: TextIO) -> None:
    """``ln -T -- <part> <final>``, then remove the part.

    ``-T`` makes ``ln`` treat *final* as the link name even when it is a
    folder or a symlink to one, so anything at *final* is a refusal:
    ``INGRESS_DEST_FILE_EXISTS``, both kept, the part path reported on
    stderr. If the follow-up probe of *final* is inconclusive, the part is
    kept and reported too (``INGRESS_PUBLISH_FAILED``). Only a probe that
    shows *final* absent lets the part be removed. A failed part removal is
    ``INGRESS_PART_REMOVE_FAILED`` with the final left published.
    """
    final = item["remote"]
    try:
        rc, _, err = _ssh(f"ln -T -- {shlex.quote(part)} {shlex.quote(final)}", CHECK_TIMEOUT,
                          "INGRESS_PUBLISH", runner)
    except core.Fail:
        # ln may or may not have run; the part is ours either way, and a
        # published final is a separate link that survives its removal
        _remove(part, runner)
        raise
    if rc != 0:
        present = _final_present(final, runner)
        if present is False:
            _remove(part, runner)
            raise _ssh_failed(rc, err, "INGRESS_PUBLISH_FAILED")
        core.emit("INGRESS_PART_KEPT", err_out, part=part)
        raise core.Fail("INGRESS_DEST_FILE_EXISTS" if present else "INGRESS_PUBLISH_FAILED",
                        detail_private=err)
    try:
        rc, _, err = _ssh(f"rm -f -- {shlex.quote(part)}", CHECK_TIMEOUT, "INGRESS_REMOVE", runner)
    except core.Fail as exc:
        rc, err = -1, exc.detail_private or exc.code
    if rc != 0:
        core.emit("INGRESS_PART_KEPT", err_out, part=part)
        raise core.Fail("INGRESS_PART_REMOVE_FAILED", detail_private=err)


def _transfer(item: Mapping[str, Any], nonce: str, runner: core.Runner, err_out: TextIO) -> str:
    """Pre-check, stream to the part, verify, publish. Returns the sha."""
    final = item["remote"]
    rc, _, err = _ssh(f"test ! -e {shlex.quote(final)}", CHECK_TIMEOUT, "INGRESS_FILE_CHECK", runner)
    if rc == 1:
        raise core.Fail("INGRESS_DEST_FILE_EXISTS")
    if rc != 0:
        raise _ssh_failed(rc, err, "INGRESS_REMOTE_CHECK_FAILED")
    part = part_path(final, nonce)
    _stream(item, part, runner)
    sha = _remote_sha(item, part, runner)
    _publish(item, part, runner, err_out)
    return sha



# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def preflight(record: Mapping[str, Any], runner: core.Runner
              ) -> tuple[str, list[dict[str, Any]], int, bool]:
    """Path refusals, local source hashes, then the read-only remote checks."""
    dest, items = plan(record)
    for item in items:
        core.verify_size_and_sha(item["source"], item["size"], item["sha256"])
    total = sum(item["size"] for item in items)
    avail, parent_exists = check_remote(dest, total, runner)
    return dest, items, avail, parent_exists


def execute(mode: str, release_path: os.PathLike | str, runner: core.Runner,
            out: TextIO, err_out: TextIO | None = None,
            nonce: Callable[[], str] = new_nonce) -> None:
    err_out = err_out if err_out is not None else sys.stderr
    record = core.load_release(release_path)
    dest, items, avail, parent_exists = preflight(record, runner)
    total = sum(item["size"] for item in items)
    if mode == "dry-run":
        core.emit("INGRESS_DRY_RUN_OK", out, dest=dest, files=len(items), total_bytes=total,
                  avail_bytes=avail, parent_code="EXISTS" if parent_exists else "CREATE")
        for item in items:
            core.emit("INGRESS_SOURCE_VERIFIED", out, source=item["source"], sha256=item["sha256"],
                      size=item["size"])
        for item in items:
            core.emit("INGRESS_PLAN", out, remote=item["remote"])
        return

    ensure_parent(runner)
    rc, _, err = _ssh(f"umask 077 && mkdir {shlex.quote(dest)}", CHECK_TIMEOUT, "INGRESS_MKDIR", runner)
    if rc != 0:
        if rc == 255:
            raise core.Fail("INGRESS_SSH_FAILED", detail_private=err)
        probe, _, _ = _ssh(f"test -e {shlex.quote(dest)}", CHECK_TIMEOUT, "INGRESS_DEST_CHECK", runner)
        raise core.Fail("INGRESS_DEST_EXISTS" if probe == 0 else "INGRESS_MKDIR_FAILED",
                        detail_private=err)
    shas = [_transfer(item, nonce(), runner, err_out) for item in items]
    core.emit("INGRESS_APPLIED", out, dest=dest, files=len(items), total_bytes=total)
    for item, sha in zip(items, shas):
        core.emit("INGRESS_REMOTE_SHA", out, remote=item["remote"], sha256=sha)


def main(argv: list[str] | None = None, *, release_path: os.PathLike | str = DEFAULT_RELEASE,
         runner: core.Runner = subprocess.run,
         private_root: os.PathLike | str | None = DEFAULT_PRIVATE_ROOT,
         stdout: TextIO | None = None, stderr: TextIO | None = None,
         nonce: Callable[[], str] = new_nonce) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    return core.run_cli(args, PROG, lambda mode: execute(mode, release_path, runner, out, err, nonce),
                        private_root=private_root, stdout=out, stderr=stderr)


if __name__ == "__main__":
    sys.exit(main())
