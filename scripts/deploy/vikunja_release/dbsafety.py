"""Database-safety primitives for the Vikunja release route (#1087, WP02).

Design: ``kitty-specs/vikunja-image-deploy-01M65D3V/research.md`` R-6
(write-boundary snapshot), R-11 (rollback guard), R-15 (deadlines), R-16
(output allowlist) and R-21 INV-2; ``data-model.md`` (Snapshot);
``analysis-report.md`` U1 (``pre_version`` in ``snapshot.json``).

Callers:

* WP04 ACTIVATE: :func:`snapshot` after ``compose down``, the ``active``
  untag and the no-container check (INV-2). It passes ``pre_version`` (read
  from ``/api/v1/info`` before the stop) and ``running_image_id``.
* WP06 rollback helper: :func:`rollback_guard` after Kent's restore;
  :func:`read_snapshot` for ``pre_version`` and ``db_sha256``.

Nothing here prints. Every refusal is a :class:`~core.Fail` with a stable
code; raw SQLite or Docker text is carried only in ``detail_private``.

The live data folder is only ever read: files are opened ``O_RDONLY`` and
copied into a private folder first, and SQLite only ever opens those copies.

Private folders (R-16; review cycle 1). :func:`open_private_root` verifies a
root through a no-follow descriptor (a folder, owned by the effective uid,
mode 0700) and never repairs an existing one; the snapshot's ``<UTC>/``,
``raw/`` and ``work/`` folders and every file the snapshot writes are created
relative to verified descriptors (``dir_fd=``, ``O_EXCL|O_NOFOLLOW``).
Residual risk, accepted: SQLite takes pathnames, so the scratch copy, the
``VACUUM INTO`` target and the integrity check are reached by pathname inside
the verified 0700 root, as are the paths handed to callers afterwards.
Swapping a pathname there needs code running as the root's owner
(``claude``) on office2, which is inside the trust boundary (the same user
could already write anything the deploy writes).
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from scripts.deploy.lib.installed_report import record_installed
from scripts.deploy.vikunja_release import core
# Reused durable-write primitives of WP01's marker writer (same pattern:
# exclusive create, write every byte, fsync the file, fsync the parent).
from scripts.deploy.vikunja_release.core import _fsync_dir, _write_all

DB_NAME = "vikunja.db"
WAL_NAME = DB_NAME + "-wal"
SHM_NAME = DB_NAME + "-shm"
#: Source file name -> key in ``snapshot.json`` ``raw``.
SOURCE_KEYS = {DB_NAME: "db", WAL_NAME: "wal", SHM_NAME: "shm"}
SNAPSHOT_JSON = "snapshot.json"
SNAPSHOT_SCHEMA_VERSION = 1

#: R-15: the overall SQLite budget, and the busy timeout (capped by what is
#: left of the budget) for every connection.
SQLITE_BUDGET_S = 120.0
BUSY_TIMEOUT_S = 5.0
#: SQLite VM instructions between deadline checks (progress handler).
_PROGRESS_STEPS = 1000

#: Migration signals (pkg/migration/20261022220000.go in the Vikunja fork).
LEGACY_BACKUP_TABLE = "task_repeat_legacy_backup"
REPEATS_COLUMN = "repeats"

DOCKER_TIMEOUT = core.DOCKER_TIMEOUT
DEFAULT_CONTAINER = "vikunja"
DEFAULT_ACTIVE_TAG = "office2.local/vikunja:active"

_CHUNK = 1024 * 1024
_MAX_SNAPSHOT_JSON = 64 * 1024
_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,47}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_CONTAINER_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
#: Literal values allowed in ``snapshot.json`` beyond :func:`core.allowed_value`.
_LITERALS = {"integrity_check": frozenset({"ok"})}


# ---------------------------------------------------------------------------
# Private file copy with hashing
# ---------------------------------------------------------------------------


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
#: The umask held around every create (folders 0700, files 0600), whatever
#: the caller's umask: a restrictive one (0400, 0277) would otherwise leave a
#: folder this process cannot open, or a file it cannot write.
PRIVATE_UMASK = 0o077


@contextlib.contextmanager
def _private_umask():
    """Hold :data:`PRIVATE_UMASK` for the block, then restore the caller's.
    The umask is process-wide; the release entrypoints are single-threaded."""
    previous = os.umask(PRIVATE_UMASK)
    try:
        yield
    finally:
        os.umask(previous)


def _open_source(path: os.PathLike | str, dir_fd: int | None = None) -> int:
    """Open *path* read-only (no symlink, no FIFO hang); regular files only.
    With *dir_fd*, *path* is a name relative to that folder descriptor."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise core.Fail("SNAPSHOT_SOURCE_INVALID")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _check_deadline(deadline: core.Deadline | None) -> None:
    if deadline is not None and deadline.remaining() <= 0:
        raise core.Fail("SNAPSHOT_DEADLINE")


def _copy_hashed(src: os.PathLike | str, dest_name: str, dest_dir_fd: int, dest_display: Path, *,
                 src_dir_fd: int | None = None, final_mode: int = 0o600,
                 deadline: core.Deadline | None = None) -> dict[str, Any]:
    """Copy *src* to a new file *dest_name* created (exclusively, no-follow)
    inside the folder descriptor *dest_dir_fd*, hashing the bytes as they are
    copied; ``fsync`` it and leave it at *final_mode*. The source is only read.

    Returns ``{"path", "sha256", "size"}``, where ``path`` is
    ``dest_display / dest_name``. Raises ``SNAPSHOT_SOURCE_CHANGED`` when the
    source's size or mtime moved while it was read (the caller must have
    stopped every writer first).

    With *deadline*, it is checked before each chunk and before the final
    ``fsync``; once it has passed, ``SNAPSHOT_DEADLINE`` (the partial copy
    stays in the private folder). Residual risk, accepted: a single
    ``read``, ``write`` or ``fsync`` that blocks in the kernel (a hung
    disk) cannot be interrupted in-process, so the overrun is bounded by
    one such call, not by the deadline. A worker process would be needed
    for a hard bound; the outage deadline's cleanup runs as soon as the
    call returns.
    """
    src_fd = _open_source(src, src_dir_fd)
    try:
        before = os.fstat(src_fd)
        with _private_umask():
            dest_fd = os.open(dest_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                              dir_fd=dest_dir_fd)
        digest = hashlib.sha256()
        size = 0
        try:
            os.fchmod(dest_fd, 0o600)
            while True:
                _check_deadline(deadline)
                chunk = os.read(src_fd, _CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                _write_all(dest_fd, chunk)
                size += len(chunk)
            _check_deadline(deadline)
            os.fsync(dest_fd)
            if final_mode != 0o600:
                os.fchmod(dest_fd, final_mode)
        finally:
            os.close(dest_fd)
        after = os.fstat(src_fd)
    finally:
        os.close(src_fd)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or size != after.st_size:
        raise core.Fail("SNAPSHOT_SOURCE_CHANGED")
    return {"path": str(dest_display / dest_name), "sha256": digest.hexdigest(), "size": size}


def _sha256_fd(fd: int, deadline: core.Deadline | None = None) -> str:
    """sha256 of *fd* from offset 0, checking *deadline* before each chunk
    (``SNAPSHOT_DEADLINE``; same residual risk as :func:`_copy_hashed`)."""
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        _check_deadline(deadline)
        chunk = os.read(fd, _CHUNK)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


_CODE_PREFIX_RE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")


def open_private_root(root: os.PathLike | str, *, code: str = "SNAPSHOT_ROOT") -> int:
    """Open *root* as a verified private folder and return its descriptor
    (the caller closes it). Create it first when absent.

    On office2 the snapshot, activation and failure roots do not exist until
    first use; their parent (``/data/services/vikunja``) must. So:

    * absent: ``mkdir`` exactly one level with mode 0700 (never ``parents``);
      a missing parent raises ``<code>_PARENT_MISSING``, any other creation
      error ``<code>_CREATE_FAILED``. Only a folder this call just created is
      ``fchmod``-ed to 0700 (umask-proof), through its descriptor;
    * then it is opened ``O_DIRECTORY|O_NOFOLLOW`` and checked by ``fstat``
      on that descriptor: a folder, owned by the effective uid, mode exactly
      0700. A symlink, a non-folder, a foreign owner or any other mode is
      ``<code>_UNSAFE``. An existing root is never ``chmod``-ed: it is
      refused, not repaired;
    * finally, on every open (created now or found existing), the parent
      folder is ``fsync``-ed so the root's own entry is durable before any
      descendant is relied on; a failure is ``<code>_PARENT_SYNC_FAILED``.

    Callers create everything inside the root relative to the descriptor
    (``dir_fd=``), so a root swapped after the check cannot redirect them.
    *code* is the stable-code prefix (``SNAPSHOT_ROOT``, ``ACTIVATION_ROOT``,
    ``FAILURES_ROOT``...).
    """
    if not isinstance(code, str) or not _CODE_PREFIX_RE.fullmatch(code):
        raise ValueError(f"invalid code prefix: {code!r}")
    created = False
    try:
        with _private_umask():
            os.mkdir(root, 0o700)
        created = True
    except FileExistsError:
        pass
    except FileNotFoundError as exc:
        raise core.Fail(f"{code}_PARENT_MISSING") from exc
    except OSError as exc:
        raise core.Fail(f"{code}_CREATE_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
    try:
        fd = os.open(root, _DIR_FLAGS)
    except OSError as exc:  # ELOOP (symlink), ENOTDIR (a file), EACCES ...
        raise core.Fail(f"{code}_UNSAFE", detail_private=f"{type(exc).__name__}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if created and stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid():
            os.fchmod(fd, 0o700)
            st = os.fstat(fd)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o700):
            raise core.Fail(f"{code}_UNSAFE")
    except OSError as exc:
        os.close(fd)
        raise core.Fail(f"{code}_UNSAFE", detail_private=f"{type(exc).__name__}: {exc}") from exc
    except BaseException:
        os.close(fd)
        raise
    # The root's own entry must be durable before anything inside it is
    # relied on (a snapshot, a marker). fsync the actual parent on EVERY
    # open, not only when this call created the root: an earlier creator
    # may have died (or failed) before its fsync, or lost a concurrent
    # mkdir race to us. Idempotent and cheap.
    try:
        _fsync_dir(Path(root).parent)
    except OSError as exc:
        os.close(fd)
        raise core.Fail(f"{code}_PARENT_SYNC_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
    return fd


def prepare_private_root(root: os.PathLike | str, *, code: str = "SNAPSHOT_ROOT") -> Path:
    """:func:`open_private_root`, then close the descriptor; returns the root
    as a :class:`Path`. For callers that hand the path on (e.g. to
    :func:`core.write_private_log`); prefer :func:`open_private_root` and
    ``dir_fd=`` creation where the caller writes itself."""
    os.close(open_private_root(root, code=code))
    return Path(root)


#: ACTIVATE's lifetime lock, inside the activation root. STAGE, ACTIVATE and
#: the rollback helper all take it through :func:`take_activation_lock`.
ACTIVATION_LOCK_NAME = "activation.lock"


def take_activation_lock(root_fd: int, *, busy_code: str, unsafe_code: str) -> int:
    """Take the exclusive, non-blocking ``flock`` on ``activation.lock`` in
    the verified activation-root descriptor *root_fd* and return the held
    descriptor; the lock lasts until the caller closes it (or the process
    dies, when the OS releases it).

    The file is opened relative to *root_fd* with
    ``O_CREAT|O_NOFOLLOW|O_RDWR`` and mode 0600 (private umask). A held
    lock raises ``Fail(busy_code)``; a symlink, a non-regular file or any
    other error raises ``Fail(unsafe_code)``. Nothing else is touched, so a
    caller can take it before any Docker call."""
    try:
        with _private_umask():
            fd = os.open(ACTIVATION_LOCK_NAME, os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR | os.O_CLOEXEC, 0o600,
                         dir_fd=root_fd)
    except OSError as exc:
        raise core.Fail(unsafe_code, detail_private=f"{type(exc).__name__}: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise core.Fail(unsafe_code)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise core.Fail(busy_code) from exc
    except core.Fail:
        os.close(fd)
        raise
    except OSError as exc:
        os.close(fd)
        raise core.Fail(unsafe_code, detail_private=f"{type(exc).__name__}: {exc}") from exc
    except BaseException:
        os.close(fd)
        raise
    return fd


def activation_lock_free(activation_root: os.PathLike | str) -> bool:
    """Dry-run probe: True when no process holds ``activation.lock``. Never
    creates the root or the file (an absent one is free). Other errors
    (``OSError``) propagate for the caller to map."""
    try:
        fd = os.open(Path(activation_root) / ACTIVATION_LOCK_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


#: ``docker image inspect`` format for :func:`untag_active`: the ID, then
#: every tag on the image, space-separated.
UNTAG_INSPECT_FORMAT = "{{.Id}}{{range .RepoTags}} {{.}}{{end}}"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def untag_active(runner: core.Runner, active_tag: str, keepers: list[tuple[str, str]], *,
                 unsafe_code: str, failed_code: str) -> str | None:
    """Remove the ``active`` TAG only, never an image (R-9, INV-1 lock).

    ``docker image rm <tag>`` deletes the image itself when that tag is its
    last name, so before it runs this proves the image ``active`` points at
    keeps another reference: one inspection of ``active`` returns its ID and
    every tag on it, and some ``(ref, expected_id)`` in *keepers* (the
    rollback ref and the release tag) must be among those tags with the ID
    equal to *expected_id*. Otherwise ``Fail(unsafe_code)`` with no
    ``image rm``. After the removal ``active`` must resolve to nothing
    (``Fail(failed_code)``). One combined inspection keeps the untag to
    three bounded calls, inside ACTIVATE's cleanup reserve.

    Returns the ID ``active`` pointed at, or ``None`` when it was already
    absent (nothing is run then). Shared by ACTIVATE (and its cleanup) and
    the rollback helper."""
    rc, out, err = core.run(["docker", "image", "inspect", "--format", UNTAG_INSPECT_FORMAT, active_tag],
                            DOCKER_TIMEOUT, step="DOCKER_INSPECT", runner=runner)
    if rc != 0:
        if "no such image" in err.lower() or "no such object" in err.lower():
            return None
        raise core.Fail(failed_code, detail_private=err or out)
    parts = out.split()
    if not parts or not _DIGEST_RE.fullmatch(parts[0]):
        raise core.Fail(failed_code, detail_private=out)
    current, names = parts[0], set(parts[1:])
    if not any(expected == current and ref != active_tag and ref in names for ref, expected in keepers):
        raise core.Fail(unsafe_code)
    rc, out, err = core.run(["docker", "image", "rm", active_tag], DOCKER_TIMEOUT, step="DOCKER_UNTAG",
                            runner=runner)
    if rc != 0 and "no such image" not in err.lower():
        raise core.Fail(failed_code, detail_private=err or out)
    if core.image_id(active_tag, runner=runner) is not None:
        raise core.Fail(failed_code)
    return current


def _make_subdir(name: str, parent_fd: int) -> int:
    """Create *name* (exclusive, 0700) inside *parent_fd*, ``fsync`` the
    parent so the new entry is durable before anything inside it is relied
    on, open it no-follow and return its descriptor. ``FileExistsError``
    and other ``OSError`` propagate."""
    with _private_umask():
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    os.fsync(parent_fd)
    fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    try:
        os.fchmod(fd, 0o700)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _remove_tree_fd(name: str, parent_fd: int) -> None:
    """Remove the flat folder *name* (files only) inside *parent_fd*. Best
    effort: the snapshot stays valid if the scratch folder survives."""
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError:
        return
    try:
        for entry in os.listdir(fd):
            try:
                os.unlink(entry, dir_fd=fd)
            except OSError:
                pass
    finally:
        os.close(fd)
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# SQLite under a deadline
# ---------------------------------------------------------------------------


def _connect(path: Path, deadline: core.Deadline, *, mode: str, immutable: bool = False) -> sqlite3.Connection:
    """Open *path* (a private copy) by URI with a busy timeout capped by the
    deadline and a progress handler that interrupts work once it passes."""
    remaining = deadline.remaining()
    if remaining <= 0:
        raise core.Fail("SNAPSHOT_DEADLINE")
    uri = f"{path.resolve().as_uri()}?mode={mode}" + ("&immutable=1" if immutable else "")
    conn = sqlite3.connect(uri, uri=True, timeout=min(BUSY_TIMEOUT_S, remaining), isolation_level=None)
    conn.set_progress_handler(lambda: 1 if deadline.remaining() <= 0 else 0, _PROGRESS_STEPS)
    return conn


def _sqlite_fail(exc: sqlite3.Error, deadline: core.Deadline) -> core.Fail:
    """Map a SQLite error to a stable code. Corruption is an integrity
    failure; an interrupt is the deadline; a lock is busy."""
    text = f"{type(exc).__name__}: {exc}"
    low = str(exc).lower()
    if "interrupt" in low or deadline.remaining() <= 0:
        return core.Fail("SNAPSHOT_DEADLINE", detail_private=text)
    if "locked" in low or "busy" in low:
        return core.Fail("SNAPSHOT_BUSY", detail_private=text)
    if isinstance(exc, sqlite3.OperationalError):
        return core.Fail("SNAPSHOT_SQLITE_FAILED", detail_private=text)
    # DatabaseError proper: "malformed", "file is not a database", ...
    return core.Fail("SNAPSHOT_INTEGRITY_FAILED", detail_private=text)


def _integrity_ok(conn: sqlite3.Connection) -> bool:
    return conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


# ---------------------------------------------------------------------------
# snapshot.json: validation and durable write
# ---------------------------------------------------------------------------


def _record_valid(data: Any) -> bool:
    """Every key is a lowercase field key and every leaf is ``None``, an
    allowlisted public value (R-16) or a fixed literal."""
    if not isinstance(data, dict):
        return False
    for key, value in data.items():
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            return False
        if value is None:
            continue
        if isinstance(value, dict):
            if not _record_valid(value):
                return False
            continue
        if isinstance(value, str) and value in _LITERALS.get(key, ()):
            continue
        if not core.allowed_value(value, key):
            return False
    return True


def _write_new_json(path: os.PathLike | str, data: Mapping[str, Any], *, dir_fd: int | None = None) -> None:
    """WP01's durable-create pattern: ``O_CREAT|O_EXCL|O_NOFOLLOW`` 0600,
    write every byte, ``fsync``, then ``fsync`` the parent folder. With
    *dir_fd*, *path* is a name inside that folder descriptor."""
    if not _record_valid(dict(data)):
        raise core.Fail("SNAPSHOT_RECORD_INVALID")
    payload = (json.dumps(dict(data), sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > _MAX_SNAPSHOT_JSON:
        raise core.Fail("SNAPSHOT_RECORD_INVALID")
    with _private_umask():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    if dir_fd is not None:
        os.fsync(dir_fd)
    else:
        _fsync_dir(Path(path).parent)


def read_snapshot(path: os.PathLike | str) -> dict[str, Any]:
    """Read and validate a ``snapshot.json``; ``SNAPSHOT_RECORD_UNREADABLE``
    when absent, oversize, malformed or carrying an unsafe value.

    The keys WP06 relies on: ``db_sha256``, ``db_path``, ``pre_version``
    (``None`` when ACTIVATE could not read it), ``running_image_id``,
    ``tasks_count``.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise core.Fail("SNAPSHOT_RECORD_UNREADABLE") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise core.Fail("SNAPSHOT_RECORD_UNREADABLE")
        raw = os.read(fd, _MAX_SNAPSHOT_JSON + 1)
    except OSError as exc:
        raise core.Fail("SNAPSHOT_RECORD_UNREADABLE") from exc
    finally:
        os.close(fd)
    if len(raw) > _MAX_SNAPSHOT_JSON:
        raise core.Fail("SNAPSHOT_RECORD_UNREADABLE")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise core.Fail("SNAPSHOT_RECORD_UNREADABLE") from exc
    if (not _record_valid(data) or data.get("schema_version") != SNAPSHOT_SCHEMA_VERSION
            or not isinstance(data.get("db_sha256"), str) or not _HEX64_RE.fullmatch(data["db_sha256"])):
        raise core.Fail("SNAPSHOT_RECORD_UNREADABLE")
    return data


# ---------------------------------------------------------------------------
# T007: write-boundary snapshot (R-6, R-21 INV-2)
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def snapshot(data_dir: os.PathLike | str, snap_root: os.PathLike | str,
             clock: Callable[[], datetime] = _utc_now, *,
             pre_version: str | None = None, running_image_id: str | None = None,
             deadline: core.Deadline | None = None) -> dict[str, Any]:
    """Take the write-boundary snapshot of ``<data_dir>/vikunja.db``.

    The caller guarantees INV-2 first (``compose down``, ``active`` untagged,
    no container). Then:

    1. open *snap_root* with :func:`open_private_root` (created when absent),
       and create ``<UTC>/`` and its ``raw/`` (0700) relative to it;
    2. copy ``vikunja.db`` plus any ``-wal``/``-shm`` into ``raw/``, hashing
       each (``SNAPSHOT_SOURCE_MISSING`` without the main file). ``raw/`` is
       evidence: its files are left read-only (0400) and never opened again;
    3. copy ``raw/`` into a scratch ``work/`` folder, open that copy
       read-write, ``PRAGMA wal_checkpoint(TRUNCATE)`` (so WAL-only committed
       rows are kept), ``integrity_check`` it, then ``VACUUM INTO
       <snap>/vikunja.db``; ``work/`` is removed afterwards;
    4. ``integrity_check`` the result, which must be ``ok``
       (``SNAPSHOT_INTEGRITY_FAILED`` otherwise, or for a corrupt source);
    5. record its sha256, ``count(*)`` of ``tasks`` and the raw hashes;
    6. write ``snapshot.json`` durably (exclusive create, fsync).

    *pre_version* is the version ``/api/v1/info`` reported before the stop
    (analysis U1); *running_image_id* is the image the DB was running under.
    Both must be allowlisted values (``SNAPSHOT_RECORD_INVALID``).

    All SQLite work runs under *deadline* (default: a fresh 120 s budget,
    R-15) with a busy timeout, and the raw and scratch copies and the final
    hash check it before every chunk (``SNAPSHOT_DEADLINE``). A single
    filesystem call that blocks in the kernel cannot be interrupted
    in-process; that overrun is the accepted residual risk (see
    :func:`_copy_hashed`). Every written file is reported through
    :func:`installed_report.record_installed`. Returns the recorded dict,
    plus ``snapshot_json`` (its path).
    """
    deadline = deadline if deadline is not None else core.Deadline(SQLITE_BUDGET_S)
    data = Path(data_dir)
    root = Path(snap_root)
    moment = clock().astimezone(timezone.utc)
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    for name, value in (("pre_version", pre_version), ("running_image_id", running_image_id)):
        if value is not None and not core.allowed_value(value, name):
            raise core.Fail("SNAPSHOT_RECORD_INVALID")

    if not os.path.lexists(data / DB_NAME):
        raise core.Fail("SNAPSHOT_SOURCE_MISSING")

    snap = root / stamp
    raw = snap / "raw"
    work = snap / "work"
    out = snap / DB_NAME
    fds: list[int] = []
    try:
        fds.append(open_private_root(root, code="SNAPSHOT_ROOT"))
        root_fd = fds[-1]
        try:
            fds.append(_make_subdir(stamp, root_fd))
            snap_fd = fds[-1]
            fds.append(_make_subdir("raw", snap_fd))
            raw_fd = fds[-1]
        except FileExistsError as exc:
            raise core.Fail("SNAPSHOT_DIR_EXISTS") from exc
        except OSError as exc:
            raise core.Fail("SNAPSHOT_WRITE_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc

        # 2. Verbatim evidence copies.
        sources: dict[str, Any] = {key: None for key in SOURCE_KEYS.values()}
        try:
            for name, key in SOURCE_KEYS.items():
                src = data / name
                if name != DB_NAME and not os.path.lexists(src):
                    continue
                sources[key] = _copy_hashed(src, name, raw_fd, raw, final_mode=0o400, deadline=deadline)
                record_installed(src, raw / name)
            os.fsync(raw_fd)
            os.fsync(snap_fd)
        except core.Fail:
            raise
        except OSError as exc:
            raise core.Fail("SNAPSHOT_COPY_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc

        # 3. Consolidate a scratch copy; raw/ is never opened by SQLite.
        try:
            work_fd = _make_subdir("work", snap_fd)
        except OSError as exc:
            raise core.Fail("SNAPSHOT_WRITE_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
        try:
            for name in SOURCE_KEYS:
                if os.path.lexists(raw / name):
                    _copy_hashed(name, name, work_fd, work, src_dir_fd=raw_fd, deadline=deadline)
            deadline.check("SNAPSHOT")
            # SQLite creates the scratch sidecars and the VACUUM target itself.
            with _private_umask():
                conn = _connect(work / DB_NAME, deadline, mode="rw")
                try:
                    busy, _log, _done = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if busy:
                        raise core.Fail("SNAPSHOT_BUSY")
                    if not _integrity_ok(conn):
                        raise core.Fail("SNAPSHOT_INTEGRITY_FAILED")
                    conn.execute("VACUUM INTO ?", (str(out),))
                finally:
                    conn.close()
        except sqlite3.Error as exc:
            raise _sqlite_fail(exc, deadline) from exc
        except OSError as exc:
            raise core.Fail("SNAPSHOT_WRITE_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
        finally:
            os.close(work_fd)
            _remove_tree_fd("work", snap_fd)

        # 4-5. Check and measure the result.
        try:
            out_fd = os.open(DB_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=snap_fd)
            fds.append(out_fd)
            if not stat.S_ISREG(os.fstat(out_fd).st_mode):
                raise core.Fail("SNAPSHOT_WRITE_FAILED")
            os.fchmod(out_fd, 0o600)
            os.fsync(out_fd)
            deadline.check("SNAPSHOT")
            conn = _connect(out, deadline, mode="ro", immutable=True)
            try:
                if not _integrity_ok(conn):
                    raise core.Fail("SNAPSHOT_INTEGRITY_FAILED")
                (tasks_count,) = conn.execute("SELECT count(*) FROM tasks").fetchone()
            finally:
                conn.close()
            db_sha = _sha256_fd(out_fd, deadline)
            db_size = os.fstat(out_fd).st_size
        except sqlite3.Error as exc:
            raise _sqlite_fail(exc, deadline) from exc
        except OSError as exc:
            raise core.Fail("SNAPSHOT_WRITE_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc

        # 6. The durable record.
        try:
            record_installed(raw / DB_NAME, out)
            record = {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "created_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data_dir": str(data.resolve()),
                "snapshot_dir": str(snap.resolve()),
                "db_path": str(out.resolve()),
                "db_sha256": db_sha,
                "db_size": db_size,
                "integrity_check": "ok",
                "tasks_count": int(tasks_count),
                "raw": sources,
                "pre_version": pre_version,
                "running_image_id": running_image_id,
            }
            _write_new_json(SNAPSHOT_JSON, record, dir_fd=snap_fd)
            target = snap / SNAPSHOT_JSON
            record_installed(target, target)
        except core.Fail:
            raise
        except OSError as exc:
            raise core.Fail("SNAPSHOT_WRITE_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
    finally:
        for fd in reversed(fds):
            os.close(fd)
    return {**record, "snapshot_json": str(target.resolve())}


# ---------------------------------------------------------------------------
# T008: migration detector
# ---------------------------------------------------------------------------


def is_migrated(db_path_copy: os.PathLike | str, deadline: core.Deadline | None = None) -> bool:
    """True when the DB at *db_path_copy* (a PRIVATE copy, never the live
    file) carries a migration signal: the ``task_repeat_legacy_backup``
    table exists, or ``tasks`` has a ``repeats`` column.

    Opens the copy with ``mode=ro``. Raises ``DB_TASKS_TABLE_MISSING`` when
    there is no ``tasks`` table (not a Vikunja DB: the answer is unknown) and
    ``DB_INSPECT_FAILED`` on any SQLite error.
    """
    deadline = deadline if deadline is not None else core.Deadline(SQLITE_BUDGET_S)
    try:
        # A WAL-mode copy makes SQLite create a -shm beside it, even read-only.
        with _private_umask():
            conn = _connect(Path(db_path_copy), deadline, mode="ro")
            try:
                backup = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (LEGACY_BACKUP_TABLE,)).fetchone()
                columns = [row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            finally:
                conn.close()
    except sqlite3.Error as exc:
        raise core.Fail("DB_INSPECT_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
    if not columns:
        raise core.Fail("DB_TASKS_TABLE_MISSING")
    return backup is not None or REPEATS_COLUMN in columns


# ---------------------------------------------------------------------------
# T009: rollback guard (R-11)
# ---------------------------------------------------------------------------


def _container_exists(runner: core.Runner, container: str) -> bool:
    rc, out, err = core.run(["docker", "ps", "-a", "--filter", f"name=^{container}$", "-q"],
                            DOCKER_TIMEOUT, step="DOCKER_PS", runner=runner)
    if rc != 0:
        raise core.Fail("DOCKER_PS_FAILED", detail_private=err)
    return bool(out.strip())


def rollback_guard(runner: core.Runner, data_dir: os.PathLike | str,
                   snapshot_json: os.PathLike | str, *,
                   container: str = DEFAULT_CONTAINER, active_tag: str = DEFAULT_ACTIVE_TAG,
                   work_dir: os.PathLike | str | None = None,
                   deadline: core.Deadline | None = None) -> dict[str, Any]:
    """Refuse to let the rollback image start unless the restored DB is the
    unmigrated snapshot (R-11, INV-1). Checks, in order, refusing at the
    first failure:

    1. no ``container`` exists (``GUARD_CONTAINER_PRESENT``);
    2. ``active_tag`` is untagged, i.e. the lock is held (``GUARD_LOCK_NOT_HELD``);
    3. ``vikunja.db-wal`` and ``vikunja.db-shm`` are both absent
       (``GUARD_SIDECAR_PRESENT``);
    4. the DB's sha256 equals ``snapshot.json`` ``db_sha256``
       (``GUARD_SHA_MISMATCH``); the DB is hashed while it is copied into a
       private folder, so the bytes checked next are the bytes hashed;
    5. ``is_migrated(copy)`` is False (``GUARD_DB_MIGRATED``).

    Any other exception refuses with ``GUARD_INSPECTION_ERROR`` (the inner
    code or error is kept in ``detail_private``). Nothing is written to
    *data_dir*: the private copy goes to a fresh 0700 folder under *work_dir*
    (default: the system temp folder), removed afterwards.

    Returns ``{"db_sha256": <hex>}`` when every check passes.
    """
    try:
        if not isinstance(container, str) or not _CONTAINER_RE.fullmatch(container):
            raise ValueError("invalid container name")
        if _container_exists(runner, container):
            raise core.Fail("GUARD_CONTAINER_PRESENT")
        if core.image_id(active_tag, runner=runner) is not None:
            raise core.Fail("GUARD_LOCK_NOT_HELD")
        data = Path(data_dir)
        if os.path.lexists(data / WAL_NAME) or os.path.lexists(data / SHM_NAME):
            raise core.Fail("GUARD_SIDECAR_PRESENT")
        expected = read_snapshot(snapshot_json)["db_sha256"]
        with _private_umask():
            scratch = tempfile.TemporaryDirectory(prefix="vikunja-guard-", dir=work_dir)
        with scratch as tmp:
            tmp_fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fchmod(tmp_fd, 0o700)
                copied = _copy_hashed(data / DB_NAME, DB_NAME, tmp_fd, Path(tmp), deadline=deadline)
            finally:
                os.close(tmp_fd)
            copy = Path(tmp) / DB_NAME
            if copied["sha256"] != expected:
                raise core.Fail("GUARD_SHA_MISMATCH")
            if is_migrated(copy, deadline):
                raise core.Fail("GUARD_DB_MIGRATED")
        return {"db_sha256": copied["sha256"]}
    except core.Fail as exc:
        if exc.code.startswith("GUARD_"):
            raise
        raise core.Fail("GUARD_INSPECTION_ERROR", detail_private=f"{exc.code}: {exc.detail_private or ''}") from exc
    except Exception as exc:  # noqa: BLE001 - any inspection error refuses
        raise core.Fail("GUARD_INSPECTION_ERROR", detail_private=f"{type(exc).__name__}: {exc}") from exc


__all__ = [
    "ACTIVATION_LOCK_NAME", "BUSY_TIMEOUT_S", "DB_NAME", "activation_lock_free", "take_activation_lock", "untag_active", "LEGACY_BACKUP_TABLE", "REPEATS_COLUMN", "SHM_NAME",
    "SNAPSHOT_JSON", "SQLITE_BUDGET_S", "WAL_NAME", "is_migrated", "open_private_root",
    "prepare_private_root", "read_snapshot",
    "rollback_guard", "snapshot",
]
