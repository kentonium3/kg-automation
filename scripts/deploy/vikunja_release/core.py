"""Core primitives for the Vikunja image-archive release route (#1087).

Design: ``kitty-specs/vikunja-image-deploy-01M65D3V/research.md`` (R-9 to R-24
take precedence over R-1 to R-8), ``data-model.md`` and
``contracts/entrypoints.md``. This module holds only pure or injectable
primitives; it contains no entrypoint logic.

Callers (work packages of mission ``vikunja-image-deploy-01M65D3V``):

* WP02 ``dbsafety.py`` / ``readiness.py``: :class:`Fail`, :func:`run`,
  :class:`Deadline`, :func:`write_private_log`.
* WP03 ``deploy-vikunja-release-stage.py``: :func:`load_release`,
  :func:`run_cli`, :func:`emit`, :func:`docker_store_ok`, :func:`image_id`,
  :func:`image_facts`, :func:`verify_archive`, :func:`marker_read`.
* WP04 ``deploy-vikunja-release-activate.py``: everything above plus
  :func:`container_image`, :func:`marker_create`, :func:`marker_update`,
  :meth:`Deadline.check` / :meth:`Deadline.cap`.
* WP06 rollback helper: :func:`load_release`, :func:`run`,
  :func:`container_image`, :func:`image_id`, :func:`marker_read`,
  :func:`marker_update` (outcome ``rolled_back``), :func:`emit`.
* WP07 ingress helper: :func:`load_release`, :func:`run`, :func:`emit`,
  :func:`run_cli`; :func:`verify_size_and_sha` and :func:`sha256_file` for
  the office4 source archives (both are hashed, never parsed).
* Every entrypoint and helper: :func:`register_summaries` (its fixed summary
  identifiers, at import).

Output rule (R-16, FR-019): nothing here prints raw command output. Raw
text goes only to :func:`write_private_log` (a 0700 folder, 0600 files);
:func:`emit` passes only allowlisted value kinds and redacts the rest.

Deadline rule (R-15, FR-018): every subprocess call goes through :func:`run`,
which always passes ``timeout=`` and never uses a shell.

Archive trust model (R-13): ``services/vikunja/release.json`` is the reviewed
trust root. :func:`verify_archive` checks the archive's size, then its
streamed sha256, against the pinned values BEFORE the file is opened with
:mod:`tarfile`, so the tar parser only ever sees the exact pinned bytes. Any
archive that is not the pinned one is refused with ``ARCHIVE_SIZE_MISMATCH``
or ``ARCHIVE_SHA_MISMATCH`` and is never parsed. Callers must not parse an
archive any other way.

The file is opened once: the size comes from ``fstat`` on that descriptor,
the hash is streamed from that handle, and tarfile parses the same handle
after a rewind. The path is never reopened, so replacing the path after the
hash cannot change what is parsed. Trust boundary: in-place concurrent writes
to the archive file itself are out of scope, because the ingress folder is
claude-owned, 0700 and create-only, so only the applier can write it; and
WP03's post-load check that the loaded image ID (content-addressed: the
config digest) equals the pinned ``image.config_digest`` is the binding
guarantee for what docker loads.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping, TextIO

# ---------------------------------------------------------------------------
# Errors and exit codes (T002)
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]{1,95}")


class Fail(Exception):
    """A refusal or failure with a stable, public error code.

    ``code`` is safe to print. ``detail_private`` may hold raw text (Docker
    stderr, logs); it is never printed, only written to a private log.
    """

    def __init__(self, code: str, detail_private: str | None = None) -> None:
        if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
            raise ValueError(f"invalid error code: {code!r}")
        super().__init__(code)
        self.code = code
        self.detail_private = detail_private


class ReleaseError(Fail):
    """``release.json`` is unreadable or invalid. ``key`` is the dotted schema
    path of the offending field (schema names only, never a value)."""

    def __init__(self, code: str, key: str | None = None) -> None:
        super().__init__(code)
        self.key = key


# ---------------------------------------------------------------------------
# Output allowlist (T002, R-16)
# ---------------------------------------------------------------------------

REDACTED = "REDACTED"

PHASES = frozenset({"started", "stopped", "snapshotted", "retagged", "started_new", "verified"})
OUTCOMES = frozenset({"success", "failed", "rolled_back"})

_HEX_ID_RE = re.compile(r"(sha256:)?[0-9a-f]{12,64}")
_PATH_RE = re.compile(r"/[A-Za-z0-9._/@+-]*")
_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)|\d{8}T\d{6}Z"
)
_VERSION_RE = re.compile(r"v?\d+\.\d+\.\d+(-[0-9]+-[0-9a-f]{7,40})?")
_FIELD_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,47}")
_SUMMARY_ID_RE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")

#: Registered summary identifiers. A summary is never free text: it is one of
#: these fixed identifiers, printed verbatim. Entrypoints register their own
#: identifiers once, at import, with :func:`register_summaries`.
_SUMMARIES: set[str] = {"FAILED"}


def register_summaries(*ids: str) -> None:
    """Register fixed summary identifiers (``STAGE_VERIFIED`` and so on).

    Call at module import with literals only. Each identifier must be an
    uppercase stable identifier; anything else raises ``ValueError``.
    """
    for sid in ids:
        if not isinstance(sid, str) or not _SUMMARY_ID_RE.fullmatch(sid):
            raise ValueError(f"invalid summary identifier: {sid!r}")
    _SUMMARIES.update(ids)


def registered_summaries() -> frozenset[str]:
    return frozenset(_SUMMARIES)


def _safe_path_str(value: str) -> bool:
    return bool(_PATH_RE.fullmatch(value)) and ".." not in value.split("/")


#: Field keys under which a stable error code may appear. A code-shaped
#: value (``HUNTER2_TOKEN``) under any other key is redacted.
CODE_KEYS = frozenset({"code", "error"})


def _is_code_key(key: str | None) -> bool:
    return key is not None and (key in CODE_KEYS or key.endswith("_code"))


def allowed_value(value: Any, key: str | None = None) -> bool:
    """True when *value* is an allowlisted public value kind (R-16).

    Kinds: an int count (not bool); a hex ID or digest; an absolute path; a
    UTC timestamp; a release version; a marker phase or outcome name; and,
    only under a code key (:data:`CODE_KEYS` or ``*_code``), a stable code.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, Path):
        return value.is_absolute() and _safe_path_str(str(value))
    if not isinstance(value, str):
        return False
    return bool(
        (_is_code_key(key) and _CODE_RE.fullmatch(value))
        or _HEX_ID_RE.fullmatch(value)
        or _TIMESTAMP_RE.fullmatch(value)
        or _VERSION_RE.fullmatch(value)
        or value in PHASES
        or value in OUTCOMES
        or (value.startswith("/") and _safe_path_str(value))
    )


def emit(summary: str, _stream: TextIO | None = None, **fields: Any) -> str:
    """Write one public line: ``summary key=value ...`` and return it.

    The summary must be a registered identifier (:func:`register_summaries`);
    it is never free text. Each field value must pass :func:`allowed_value`.
    Anything else is replaced by ``REDACTED``; this never raises, so it is
    safe on failure paths. ``None`` field values are written as ``-``.
    """
    head = summary if isinstance(summary, str) and summary in _SUMMARIES else REDACTED
    parts = [head]
    for key, value in fields.items():
        if not _FIELD_KEY_RE.fullmatch(key):
            continue
        if value is None:
            shown = "-"
        elif allowed_value(value, key):
            shown = str(value)
        else:
            shown = REDACTED
        parts.append(f"{key}={shown}")
    line = " ".join(parts)
    stream = _stream if _stream is not None else sys.stdout
    stream.write(line + "\n")
    stream.flush()
    return line


def _utc_stamp(now: datetime | None = None) -> str:
    moment = now if now is not None else datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _ensure_private_dir(root: Path) -> None:
    os.makedirs(root, mode=0o700, exist_ok=True)
    st = os.lstat(root)
    if not stat.S_ISDIR(st.st_mode):
        raise OSError("private root is not a directory")
    if stat.S_IMODE(st.st_mode) != 0o700:
        os.chmod(root, 0o700)


_LOG_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")


def write_private_log(root: os.PathLike | str, name: str, text: str,
                      now: datetime | None = None) -> Path:
    """Write raw *text* to a new 0600 file in the 0700 folder *root*.

    Returns only the file path; the text is never printed. Raises
    ``Fail("PRIVATE_LOG_WRITE_FAILED")`` on any filesystem error.
    """
    if not _LOG_NAME_RE.fullmatch(name):
        raise Fail("PRIVATE_LOG_NAME_INVALID")
    base = Path(root)
    try:
        _ensure_private_dir(base)
        stamp = _utc_stamp(now)
        for attempt in range(100):
            suffix = "" if attempt == 0 else f"-{attempt}"
            target = base / f"{stamp}-{name}{suffix}.log"
            try:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                continue
            try:
                os.fchmod(fd, 0o600)
                os.write(fd, text.encode("utf-8", errors="replace"))
                os.fsync(fd)
            finally:
                os.close(fd)
            return target
    except OSError as exc:
        raise Fail("PRIVATE_LOG_WRITE_FAILED") from exc
    raise Fail("PRIVATE_LOG_WRITE_FAILED")


# ---------------------------------------------------------------------------
# CLI exit helper (T002)
# ---------------------------------------------------------------------------

MODES = ("--dry-run", "--apply")


def run_cli(argv: list[str], prog: str, body: Callable[[str], None],
            private_root: os.PathLike | str | None = None,
            stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Run *body* for exactly ``--dry-run`` or ``--apply``; return 0, 1 or 2.

    * Any other argv: usage on stderr, exit 2.
    * *body* returns: exit 0.
    * *body* raises :class:`Fail`: one public line with the code (and, when
      *private_root* is set and the failure carries private detail, the
      private log path), exit 1.
    * Any other exception: ``INTERNAL_ERROR``, traceback written only to the
      private log, exit 1.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if len(argv) != 1 or argv[0] not in MODES:
        err.write(f"usage: {prog} --dry-run | --apply\n")
        err.flush()
        return EXIT_USAGE
    mode = argv[0][2:]
    try:
        body(mode)
    except Fail as exc:
        log = _private_detail(private_root, "fail", exc.detail_private)
        emit("FAILED", out, code=exc.code, private_log=log)
        return EXIT_FAIL
    except Exception:  # noqa: BLE001 - never echo an unexpected message
        log = _private_detail(private_root, "internal-error", traceback.format_exc())
        emit("FAILED", out, code="INTERNAL_ERROR", private_log=log)
        return EXIT_FAIL
    return EXIT_OK


def _private_detail(root: os.PathLike | str | None, name: str, text: str | None) -> Path | None:
    if root is None or not text:
        return None
    try:
        return write_private_log(root, name, text)
    except Fail:
        return None


# ---------------------------------------------------------------------------
# Bounded runner and deadline (T003, R-15)
# ---------------------------------------------------------------------------

Runner = Callable[..., Any]


def run(argv: list[str], timeout: float, *, step: str,
        runner: Runner = subprocess.run) -> tuple[int, str, str]:
    """Run *argv* (no shell) with a mandatory *timeout*; return
    ``(rc, stdout, stderr)``.

    ``TimeoutExpired`` becomes ``Fail("TIMEOUT_<step>")``; a failure to
    execute at all becomes ``Fail("EXEC_FAILED_<step>")``.
    """
    if not _CODE_RE.fullmatch(step):
        raise ValueError(f"invalid step: {step!r}")
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv must be a non-empty list of str")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number")
    try:
        proc = runner(list(argv), capture_output=True, text=True, errors="replace",
                      stdin=subprocess.DEVNULL, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise Fail(f"TIMEOUT_{step}", detail_private=_as_text(exc.stderr)) from exc
    except OSError as exc:
        raise Fail(f"EXEC_FAILED_{step}", detail_private=f"{type(exc).__name__}: {exc}") from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class Deadline:
    """A monotonic overall deadline (e.g. the 300 s outage window)."""

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        self._clock = clock
        self._seconds = float(seconds)
        self._start = clock()

    def remaining(self) -> float:
        return max(0.0, self._seconds - (self._clock() - self._start))

    def check(self, step: str) -> None:
        """Raise ``Fail("<step>_DEADLINE")`` once the deadline has passed."""
        if self.remaining() <= 0:
            raise Fail(f"{step}_DEADLINE")

    def cap(self, timeout: float, step: str) -> float:
        """The smaller of *timeout* and the time remaining; raises like
        :meth:`check` when none remains."""
        self.check(step)
        return min(float(timeout), self.remaining())


# ---------------------------------------------------------------------------
# Release record (T001)
# ---------------------------------------------------------------------------

_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_REVISION_RE = re.compile(r"[0-9a-f]{40}")
_PLATFORM_RE = re.compile(r"[a-z0-9]+/[a-z0-9]+")
_USER_RE = re.compile(r"[0-9]{1,10}")
_REF_RE = re.compile(r"[a-z0-9][a-z0-9.-]*(/[a-z0-9._-]+)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_URL_RE = re.compile(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._-]+)*/?")


def _abs_path(v: str) -> bool:
    return v.startswith("/") and _safe_path_str(v)


def _positive(v: int) -> bool:
    return v > 0


_ARCHIVE = {"path": (str, _abs_path), "sha256": (str, _HEX64_RE.fullmatch), "size": (int, _positive)}
_DIGEST = (str, _DIGEST_RE.fullmatch)
_REF = (str, _REF_RE.fullmatch)
_PATH = (str, _abs_path)

RELEASE_SCHEMA: Mapping[str, Any] = {
    "schema_version": (int, lambda v: v == 1),
    "release_version": (str, _VERSION_RE.fullmatch),
    "source_revision": (str, _REVISION_RE.fullmatch),
    "archive": _ARCHIVE,
    "image": {
        "config_digest": _DIGEST,
        "index_digest": _DIGEST,
        "platform": (str, _PLATFORM_RE.fullmatch),
        "user": (str, _USER_RE.fullmatch),
    },
    "tags": {"release": _REF, "active": _REF},
    "rollback": {"image_id": _DIGEST, "ref": _REF, "archive": _ARCHIVE},
    "service": {
        "compose_file": _PATH,
        "project": (str, _NAME_RE.fullmatch),
        "container": (str, _NAME_RE.fullmatch),
        "info_url": (str, _URL_RE.fullmatch),
        "data_dir": _PATH,
    },
    "roots": {
        "snapshots": _PATH,
        "activation": _PATH,
        "private_logs": _PATH,
        "office4_sources": {"archive": _PATH, "rollback_archive": _PATH},
    },
}


def _validate(data: Any, schema: Mapping[str, Any], prefix: str) -> None:
    if not isinstance(data, dict):
        raise ReleaseError("RELEASE_TYPE_INVALID", prefix.rstrip(".") or "<root>")
    for key in data:
        if key not in schema:
            raise ReleaseError("RELEASE_KEY_UNKNOWN", f"{prefix}{key}" if isinstance(key, str) else prefix)
    for key, rule in schema.items():
        dotted = f"{prefix}{key}"
        if key not in data:
            raise ReleaseError("RELEASE_KEY_MISSING", dotted)
        value = data[key]
        if isinstance(rule, Mapping):
            _validate(value, rule, dotted + ".")
            continue
        kind, check = rule
        if type(value) is not kind:  # exact: rejects bool for int
            raise ReleaseError("RELEASE_TYPE_INVALID", dotted)
        if not check(value):
            raise ReleaseError("RELEASE_VALUE_INVALID", dotted)


def load_release(path: os.PathLike | str) -> dict[str, Any]:
    """Load and validate ``services/vikunja/release.json``.

    Every key is required, unknown keys are refused, and every value is
    type- and format-checked. The release tag must name the release version.
    Raises :class:`ReleaseError` with a stable code.
    """
    try:
        with open(path, "rb") as fh:
            raw = fh.read(1024 * 1024 + 1)
    except OSError as exc:
        raise ReleaseError("RELEASE_UNREADABLE") from exc
    if len(raw) > 1024 * 1024:
        raise ReleaseError("RELEASE_UNREADABLE")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("RELEASE_UNREADABLE") from exc
    _validate(data, RELEASE_SCHEMA, "")
    if not data["tags"]["release"].endswith(":" + data["release_version"]):
        raise ReleaseError("RELEASE_VALUE_INVALID", "tags.release")
    return data


# ---------------------------------------------------------------------------
# Docker store preflight and identity (T004, R-13)
# ---------------------------------------------------------------------------

DOCKER_TIMEOUT = 30
_IMAGE_REF_RE = re.compile(rf"{_REF_RE.pattern}|{_DIGEST_RE.pattern}")
_ABSENT_MARKERS = ("no such image", "no such object", "no such container")


def _absent(stderr: str) -> bool:
    low = stderr.lower()
    return any(m in low for m in _ABSENT_MARKERS)


def _check_ref(ref: str) -> None:
    if not isinstance(ref, str) or not _IMAGE_REF_RE.fullmatch(ref):
        raise ValueError(f"invalid image reference: {ref!r}")


def docker_store_ok(runner: Runner = subprocess.run) -> bool:
    """Require the classic image store: ``Driver == overlay2`` and no
    containerd snapshotter in ``DriverStatus``.

    Raises ``DOCKER_UNREACHABLE`` when ``docker info`` fails, and
    ``DOCKER_STORE_UNSUPPORTED`` for anything else that is not the classic
    store (including output that cannot be parsed).
    """
    rc, out, err = run(["docker", "info", "--format", "{{json .}}"], DOCKER_TIMEOUT,
                       step="DOCKER_INFO", runner=runner)
    if rc != 0:
        raise Fail("DOCKER_UNREACHABLE", detail_private=err)
    try:
        info = json.loads(out)
    except json.JSONDecodeError as exc:
        raise Fail("DOCKER_STORE_UNSUPPORTED") from exc
    if not isinstance(info, dict) or info.get("Driver") != "overlay2":
        raise Fail("DOCKER_STORE_UNSUPPORTED")
    status = info.get("DriverStatus")
    if status is None:
        status = []
    if not isinstance(status, list):
        raise Fail("DOCKER_STORE_UNSUPPORTED")
    for entry in status:
        if not isinstance(entry, list):
            raise Fail("DOCKER_STORE_UNSUPPORTED")
        if any(isinstance(item, str) and "io.containerd.snapshotter" in item for item in entry):
            raise Fail("DOCKER_STORE_UNSUPPORTED")
    return True


def image_id(ref: str, runner: Runner = subprocess.run) -> str | None:
    """``docker image inspect --format {{.Id}}``; ``None`` when absent."""
    _check_ref(ref)
    rc, out, err = run(["docker", "image", "inspect", "--format", "{{.Id}}", ref], DOCKER_TIMEOUT,
                       step="DOCKER_INSPECT", runner=runner)
    if rc != 0:
        if _absent(err):
            return None
        raise Fail("DOCKER_INSPECT_FAILED", detail_private=err)
    value = out.strip()
    if not _DIGEST_RE.fullmatch(value):
        raise Fail("DOCKER_INSPECT_UNPARSEABLE")
    return value


REVISION_LABEL = "org.opencontainers.image.revision"


def image_facts(ref: str, runner: Runner = subprocess.run) -> dict[str, Any] | None:
    """Identity facts of a local image, or ``None`` when absent.

    Returns ``{"id", "architecture", "os", "user", "revision"}``; the
    revision is ``None`` when the image carries no revision label.
    """
    _check_ref(ref)
    rc, out, err = run(["docker", "image", "inspect", "--format", "{{json .}}", ref], DOCKER_TIMEOUT,
                       step="DOCKER_INSPECT", runner=runner)
    if rc != 0:
        if _absent(err):
            return None
        raise Fail("DOCKER_INSPECT_FAILED", detail_private=err)
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise Fail("DOCKER_INSPECT_UNPARSEABLE") from exc
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if not isinstance(data, dict):
        raise Fail("DOCKER_INSPECT_UNPARSEABLE")
    config = data.get("Config") or {}
    if not isinstance(config, dict):
        raise Fail("DOCKER_INSPECT_UNPARSEABLE")
    labels = config.get("Labels") or {}
    if not isinstance(labels, dict):
        raise Fail("DOCKER_INSPECT_UNPARSEABLE")
    facts = {
        "id": data.get("Id"),
        "architecture": data.get("Architecture"),
        "os": data.get("Os"),
        "user": config.get("User"),
        "revision": labels.get(REVISION_LABEL),
    }
    if not isinstance(facts["id"], str) or not _DIGEST_RE.fullmatch(facts["id"]):
        raise Fail("DOCKER_INSPECT_UNPARSEABLE")
    return facts


def container_image(name: str, runner: Runner = subprocess.run) -> tuple[str, str] | None:
    """``(.Image, .Config.Image)`` of container *name*, or ``None`` when absent.

    Uses a narrow format so no container environment is ever read.
    """
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid container name: {name!r}")
    rc, out, err = run(["docker", "container", "inspect", "--format", "{{.Image}} {{.Config.Image}}", name],
                       DOCKER_TIMEOUT, step="DOCKER_INSPECT", runner=runner)
    if rc != 0:
        if _absent(err):
            return None
        raise Fail("DOCKER_INSPECT_FAILED", detail_private=err)
    parts = out.split()
    if len(parts) != 2 or not _DIGEST_RE.fullmatch(parts[0]) or not _IMAGE_REF_RE.fullmatch(parts[1]):
        raise Fail("DOCKER_INSPECT_UNPARSEABLE")
    return parts[0], parts[1]


# ---------------------------------------------------------------------------
# Offline archive chain check (T005, R-13)
# ---------------------------------------------------------------------------

CHUNK = 1024 * 1024
_MAX_JSON_MEMBER = 1024 * 1024


def _sha256_handle(fh: BinaryIO) -> str:
    """Hex sha256 of an open binary handle from its current position,
    streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    for chunk in iter(lambda: fh.read(CHUNK), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: os.PathLike | str) -> str:
    """Hex sha256 of *path*, streamed in 1 MiB chunks (for reporting; WP07)."""
    with open(path, "rb") as fh:
        return _sha256_handle(fh)


def _open_regular(path: os.PathLike | str) -> BinaryIO:
    """Open *path* read-only and binary, refusing anything that is not a
    regular file. ``O_NONBLOCK`` keeps a planted FIFO from hanging the open.
    Raises ``ARCHIVE_MISSING`` or ``ARCHIVE_UNREADABLE``."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except FileNotFoundError as exc:
        raise Fail("ARCHIVE_MISSING") from exc
    except OSError as exc:
        raise Fail("ARCHIVE_UNREADABLE") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Fail("ARCHIVE_UNREADABLE")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _check_handle(fh: BinaryIO, size: int, sha256: str) -> None:
    """Size by ``fstat`` on the open descriptor, then the streamed sha256 of
    the same handle. Raises ``ARCHIVE_SIZE_MISMATCH``, ``ARCHIVE_SHA_MISMATCH``
    or ``ARCHIVE_UNREADABLE``."""
    try:
        if os.fstat(fh.fileno()).st_size != size:
            raise Fail("ARCHIVE_SIZE_MISMATCH")
        fh.seek(0)
        actual = _sha256_handle(fh)
    except OSError as exc:
        raise Fail("ARCHIVE_UNREADABLE") from exc
    if actual != sha256:
        raise Fail("ARCHIVE_SHA_MISMATCH")


def verify_size_and_sha(path: os.PathLike | str, size: int, sha256: str) -> None:
    """Size first (cheap), then sha256, on one open handle. Raises
    ``ARCHIVE_MISSING``, ``ARCHIVE_UNREADABLE``, ``ARCHIVE_SIZE_MISMATCH``
    or ``ARCHIVE_SHA_MISMATCH``. For an archive that is only hashed, never
    parsed (the rollback archive)."""
    with _open_regular(path) as fh:
        _check_handle(fh, size, sha256)


def _member_bytes(tar: tarfile.TarFile, members: dict[str, list[tarfile.TarInfo]], name: str) -> bytes:
    found = members.get(name, [])
    if not found:
        raise Fail("ARCHIVE_MEMBER_MISSING")
    if len(found) > 1:
        raise Fail("ARCHIVE_MEMBER_AMBIGUOUS")
    info = found[0]
    if not info.isreg() or info.size > _MAX_JSON_MEMBER:
        raise Fail("ARCHIVE_MEMBER_INVALID")
    fh = tar.extractfile(info)
    if fh is None:
        raise Fail("ARCHIVE_MEMBER_INVALID")
    return fh.read(_MAX_JSON_MEMBER + 1)


def _json(raw: bytes, code: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Fail(code) from exc


def _parse_pinned(fh: BinaryIO, config_name: str) -> tuple[Any, Any, bytes | None]:
    """Parse ``index.json``, ``manifest.json`` and the config blob from the
    already-verified handle *fh* (rewound to offset 0). Never takes a path.
    Every parser failure maps to ``ARCHIVE_UNREADABLE``."""
    try:
        fh.seek(0)
        with tarfile.open(fileobj=fh, mode="r:") as tar:
            members: dict[str, list[tarfile.TarInfo]] = {}
            for info in tar.getmembers():
                name = info.name[2:] if info.name.startswith("./") else info.name
                members.setdefault(name, []).append(info)
            index = _json(_member_bytes(tar, members, "index.json"), "ARCHIVE_INDEX_UNPARSEABLE")
            manifest = _json(_member_bytes(tar, members, "manifest.json"), "ARCHIVE_MANIFEST_UNPARSEABLE")
            config_raw = _member_bytes(tar, members, config_name) if config_name in members else None
    except (tarfile.TarError, OSError, ValueError, UnicodeError, RecursionError, MemoryError,
            OverflowError) as exc:
        raise Fail("ARCHIVE_UNREADABLE") from exc
    return index, manifest, config_raw


def verify_archive(path: os.PathLike | str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the release archive offline against *record* (R-13).

    1. Open the file once. Size (``fstat`` on that descriptor), then the
       sha256 streamed from the same handle (``record["archive"]``). Nothing
       is parsed until both equal the pinned values: the reviewed record is
       the trust root.
    2. Rewind the same handle and parse it with tarfile; the path is never
       reopened, so the parser sees exactly the bytes that were hashed.
       Without extracting to disk, and with every parser failure mapped to
       ``ARCHIVE_UNREADABLE``: ``index.json`` names exactly the index
       digest; ``manifest.json`` has one entry whose ``Config`` is
       ``blobs/sha256/<config hex>``; that blob's sha256 equals its name; and
       the config's architecture, os, ``config.User`` and revision label
       match the record.

    Returns the verified identities. Raises :class:`Fail` with a stable code.
    """
    archive = record["archive"]
    image = record["image"]
    config_hex = image["config_digest"].split(":", 1)[1]
    config_name = f"blobs/sha256/{config_hex}"
    os_want, arch_want = image["platform"].split("/", 1)
    with _open_regular(path) as fh:
        _check_handle(fh, archive["size"], archive["sha256"])
        index, manifest, config_raw = _parse_pinned(fh, config_name)

    entries = index.get("manifests") if isinstance(index, dict) else None
    if (not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict)
            or entries[0].get("digest") != image["index_digest"]):
        raise Fail("ARCHIVE_INDEX_MISMATCH")

    if (not isinstance(manifest, list) or len(manifest) != 1 or not isinstance(manifest[0], dict)
            or manifest[0].get("Config") != config_name):
        raise Fail("ARCHIVE_MANIFEST_MISMATCH")
    if config_raw is None:
        raise Fail("ARCHIVE_MEMBER_MISSING")
    if hashlib.sha256(config_raw).hexdigest() != config_hex:
        raise Fail("ARCHIVE_CONFIG_HASH_MISMATCH")

    config = _json(config_raw, "ARCHIVE_CONFIG_UNPARSEABLE")
    if not isinstance(config, dict):
        raise Fail("ARCHIVE_CONFIG_UNPARSEABLE")
    inner = config.get("config") or {}
    labels = inner.get("Labels") or {} if isinstance(inner, dict) else {}
    if config.get("architecture") != arch_want:
        raise Fail("ARCHIVE_ARCH_MISMATCH")
    if config.get("os") != os_want:
        raise Fail("ARCHIVE_OS_MISMATCH")
    if not isinstance(inner, dict) or inner.get("User") != image["user"]:
        raise Fail("ARCHIVE_USER_MISMATCH")
    if not isinstance(labels, dict) or labels.get(REVISION_LABEL) != record["source_revision"]:
        raise Fail("ARCHIVE_REVISION_MISMATCH")
    return {
        "sha256": archive["sha256"],
        "size": archive["size"],
        "index_digest": image["index_digest"],
        "config_digest": image["config_digest"],
    }


# ---------------------------------------------------------------------------
# Durable marker I/O (T006, R-12)
# ---------------------------------------------------------------------------

_MAX_MARKER = 64 * 1024


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _marker_valid(data: Any) -> bool:
    """A marker is a dict with a known ``phase``; ``outcome`` is absent,
    ``None`` or a known outcome; ``failed_phase`` (if set) is a known phase;
    every other value is ``None`` or an allowlisted public value (R-16).

    Types are checked before set membership, so a malformed value (a list
    or an object where a string belongs) is a refusal, never a TypeError.
    """
    if not isinstance(data, dict):
        return False
    phase = data.get("phase")
    if not isinstance(phase, str) or phase not in PHASES:
        return False
    outcome = data.get("outcome")
    if outcome is not None and (not isinstance(outcome, str) or outcome not in OUTCOMES):
        return False
    failed_phase = data.get("failed_phase")
    if failed_phase is not None and (not isinstance(failed_phase, str) or failed_phase not in PHASES):
        return False
    for key, value in data.items():
        if not isinstance(key, str) or not _FIELD_KEY_RE.fullmatch(key):
            return False
        if key in ("phase", "outcome", "failed_phase"):
            continue
        if value is not None and not allowed_value(value, key):
            return False
    return True


def _marker_bytes(data: Mapping[str, Any]) -> bytes:
    """Serialize a valid marker; refuses (before any filesystem mutation) a
    marker :func:`marker_read` could not read back: ``MARKER_INVALID`` for
    unsafe content, ``MARKER_TOO_LARGE`` above the reader's 64 KiB limit."""
    if not _marker_valid(dict(data)):
        raise Fail("MARKER_INVALID")
    payload = (json.dumps(dict(data), sort_keys=True, default=str) + "\n").encode("utf-8")
    if len(payload) > _MAX_MARKER:
        raise Fail("MARKER_TOO_LARGE")
    return payload


#: The write primitive, held as a module attribute so tests can inject a
#: short-writing fake without patching ``os`` process-wide.
_os_write = os.write


def _write_all(fd: int, payload: bytes) -> None:
    """Write every byte of *payload*, looping over short writes. A write
    that makes no progress raises ``OSError``."""
    view = memoryview(payload)
    while view:
        written = _os_write(fd, view)
        if not isinstance(written, int) or written <= 0:
            raise OSError("write made no progress")
        view = view[written:]


def marker_create(path: os.PathLike | str, data: Mapping[str, Any]) -> None:
    """Create the marker exclusively and durably.

    ``O_CREAT|O_EXCL|O_WRONLY`` with mode 0600, write, ``fsync``, then
    ``fsync`` the parent folder. A marker that already exists raises
    ``MARKER_EXISTS``; other filesystem errors raise ``MARKER_WRITE_FAILED``.
    A failed write leaves the (incomplete) marker in place: it is never
    deleted by code, and the reader refuses it as ``MARKER_UNREADABLE``,
    which fails closed before any Docker call.
    """
    target = Path(path)
    payload = _marker_bytes(data)
    try:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    except FileExistsError as exc:
        raise Fail("MARKER_EXISTS") from exc
    except OSError as exc:
        raise Fail("MARKER_WRITE_FAILED") from exc
    try:
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(target.parent)
    except OSError as exc:
        raise Fail("MARKER_WRITE_FAILED") from exc


def marker_update(path: os.PathLike | str, data: Mapping[str, Any]) -> None:
    """Replace an existing marker atomically and durably.

    Temp file in the same folder, ``fsync``, ``os.replace``, then ``fsync``
    the parent. A crash before the replace leaves the old marker intact.
    Refuses (``MARKER_MISSING``) when no marker exists, so an update can
    never stand in for the exclusive create.
    """
    target = Path(path)
    payload = _marker_bytes(data)
    if not target.is_file() or target.is_symlink():
        raise Fail("MARKER_MISSING")
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    except OSError as exc:
        raise Fail("MARKER_WRITE_FAILED") from exc
    try:
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_name, target)
        _fsync_dir(target.parent)
    except BaseException as exc:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise Fail("MARKER_WRITE_FAILED") from exc
        raise


def marker_read(path: os.PathLike | str) -> dict[str, Any] | None:
    """``None`` when absent, the dict when valid, else ``MARKER_UNREADABLE``
    (malformed JSON, JSON nested deeply enough to exhaust the decoder,
    unknown phase or outcome, unsafe field, symlink, non-regular file, or
    oversize)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise Fail("MARKER_UNREADABLE") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Fail("MARKER_UNREADABLE")
        raw = os.read(fd, _MAX_MARKER + 1)
    except OSError as exc:
        raise Fail("MARKER_UNREADABLE") from exc
    finally:
        os.close(fd)
    if len(raw) > _MAX_MARKER:
        raise Fail("MARKER_UNREADABLE")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, MemoryError) as exc:
        raise Fail("MARKER_UNREADABLE") from exc
    if not _marker_valid(data):
        raise Fail("MARKER_UNREADABLE")
    return data


__all__ = [
    "Deadline", "EXIT_FAIL", "EXIT_OK", "EXIT_USAGE", "Fail", "OUTCOMES", "PHASES",
    "RELEASE_SCHEMA", "ReleaseError", "allowed_value", "register_summaries", "registered_summaries", "container_image", "docker_store_ok",
    "emit", "image_facts", "image_id", "load_release", "marker_create", "marker_read",
    "marker_update", "run", "run_cli", "sha256_file", "verify_archive", "verify_size_and_sha",
    "write_private_log",
]
