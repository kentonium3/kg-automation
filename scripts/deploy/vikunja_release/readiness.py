"""Readiness and private log-capture primitives (#1087, WP02).

Design: ``kitty-specs/vikunja-image-deploy-01M65D3V/research.md`` R-8
(post-start verification), R-14 (evidence before teardown), R-15 (deadlines)
and R-16 (output allowlist).

Callers:

* WP04 ACTIVATE: :func:`wait_ready` for the release version inside the 300 s
  outage deadline; :func:`capture_logs` before any teardown;
  :func:`migration_ok` on the captured log.
* WP06 rollback helper: :func:`capture_logs` for the failed container;
  :func:`wait_ready` for the pre-cutover version (``snapshot.json``
  ``pre_version``).

Nothing here prints. Response bodies and container logs are never returned
or echoed: :func:`wait_ready` returns only the matched version string,
:func:`capture_logs` only a private file path, and :func:`migration_ok` only
a bool and digit-only counts.
"""

from __future__ import annotations

import json
import os
import re
import select
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.deploy.vikunja_release import core
from scripts.deploy.vikunja_release.core import _write_all
from scripts.deploy.vikunja_release.dbsafety import open_private_root

#: R-8 / R-15: poll interval and per-request timeout.
POLL_INTERVAL_S = 5.0
REQUEST_TIMEOUT_S = 5.0
#: Largest ``/api/v1/info`` body read (the real one is well under 1 KiB).
_MAX_BODY = 64 * 1024

#: core.run's kill margin over curl's own --max-time, and the least time
#: worth starting a probe in.
_PROBE_GRACE_S = 2
_MIN_PROBE_S = 1.0

#: R-14: ``docker logs`` bounds: time, bytes read, and lines asked for.
LOGS_TIMEOUT_S = 30
LOGS_MAX_BYTES = 10 * 1024 * 1024
LOGS_TAIL_LINES = 20000
_READ_CHUNK = 64 * 1024
_REAP_TIMEOUT_S = 5.0

_URL_RE = re.compile(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._-]+)*/?")
_CONTAINER_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")

#: pkg/migration/migration.go: ``log.Info("Ran all migrations successfully.")``.
MIGRATIONS_OK_TEXT = "Ran all migrations successfully."
#: pkg/migration/20261022220000.go: the RRULE migration's summary line.
_RRULE_SUMMARY_RE = re.compile(
    r"RRULE migration: (\d+) legacy-repeat task\(s\) processed\W+(\d+) converted, "
    r"(\d+) already had an RRULE, (\d+) unconvertible \([^)]*\); (\d+) row\(s\) used the server zone"
)
RRULE_COUNT_KEYS = ("processed", "converted", "already_rrule", "unconvertible", "server_zone")

#: ``docker logs --timestamps`` prefix: an RFC 3339 (nano) timestamp and a space.
_DOCKER_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}) ")
#: One logfmt pair: ``key=value`` with a Go-quoted (escapes allowed) or bare value.
_LOGFMT_PAIR_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_.-]*)=("(?:[^"\\]|\\.)*"|[^\s"=]*)')

# ---------------------------------------------------------------------------
# T010: readiness (R-8, R-15)
# ---------------------------------------------------------------------------


def _curl_argv(url: str, max_time: int) -> list[str]:
    """The probe: one GET, a hard ``--max-time``, a body cap, and the HTTP
    status appended on its own last line. No shell; the URL is validated."""
    return ["curl", "-sS", "--max-time", str(max_time), "--max-filesize", str(_MAX_BODY),
            "-o", "-", "-w", "\n%{http_code}", url]


def _probe(url: str, max_time: int, runner: core.Runner) -> tuple[str, str | None]:
    """One killable probe. Returns ``(kind, version)``, where kind is
    ``"ok"`` (HTTP 200 with a parseable JSON ``version``) or ``"retry"``
    (curl timeout 28, connection refused 7, any other curl error, a non-200
    status such as 503, an oversize or unparseable body). The subprocess is
    killed by :func:`core.run` at ``max_time + 2`` seconds whatever the
    server does. Raises ``READY_PROBE_UNAVAILABLE`` when curl cannot run.
    The body is parsed for ``version`` only and dropped."""
    try:
        rc, out, _err = core.run(_curl_argv(url, max_time), max_time + _PROBE_GRACE_S,
                                 step="READY_PROBE", runner=runner)
    except core.Fail as exc:
        if exc.code == "TIMEOUT_READY_PROBE":
            return "retry", None
        raise core.Fail("READY_PROBE_UNAVAILABLE", detail_private=exc.code) from exc
    if rc != 0:
        return "retry", None
    body, sep, status = out.rpartition("\n")
    if not sep or status.strip() != "200":
        return "retry", None
    if len(body.encode("utf-8", errors="replace")) > _MAX_BODY:
        return "retry", None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, RecursionError):
        return "retry", None
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str):
        return "retry", None
    return "ok", version


def wait_ready(url: str, expect_version: str, deadline: core.Deadline,
               runner: core.Runner = subprocess.run,
               sleep: Callable[[float], None] = time.sleep) -> str:
    """Poll *url* (``/api/v1/info``) until it answers HTTP 200 with JSON
    ``version == expect_version``; return that version.

    Each attempt is a ``curl`` subprocess with ``--max-time t``, where
    ``t = max(1, min(5, int(deadline.remaining())))``, killed by
    :func:`core.run` at ``t + 2`` s, so a trickling or hung server cannot
    hold a probe past that hard bound. Probing stops once less than 1 s
    remains. Attempts are 5 s apart. The deadline is checked again after
    every probe: an answer that completes after *deadline* is
    ``READY_TIMEOUT``, never success. Curl errors, timeouts, non-200
    statuses (503) and unparseable bodies are retried until the deadline,
    then ``READY_TIMEOUT``. A timely 200 whose ``version`` differs refuses at
    once with ``READY_WRONG_VERSION``. The body is never returned or echoed.
    """
    if not isinstance(url, str) or not _URL_RE.fullmatch(url):
        raise ValueError("invalid readiness URL")
    if not isinstance(expect_version, str) or not core.allowed_value(expect_version, "version"):
        raise ValueError("invalid expected version")
    while True:
        remaining = deadline.remaining()
        if remaining < _MIN_PROBE_S:
            raise core.Fail("READY_TIMEOUT")
        max_time = max(1, min(int(REQUEST_TIMEOUT_S), int(remaining)))
        kind, version = _probe(url, max_time, runner)
        if deadline.remaining() <= 0:
            raise core.Fail("READY_TIMEOUT")
        if kind == "ok":
            if version == expect_version:
                return version
            raise core.Fail("READY_WRONG_VERSION")
        sleep(min(POLL_INTERVAL_S, deadline.remaining()))


# ---------------------------------------------------------------------------
# T011: private log capture (R-14)
# ---------------------------------------------------------------------------


#: Read primitive for the log pipe, a module attribute so tests can count
#: the bytes actually read without patching ``os`` process-wide.
_os_read = os.read
#: Granularity of the wait for log output, so the deadline is re-checked
#: even while a silent child writes nothing.
_SELECT_SLICE_S = 0.25


def _new_private_file(root_fd: int, name: str) -> tuple[int, str]:
    """Create ``<UTC>-<name>.log`` (0600, exclusive, no-follow) inside the
    verified folder descriptor *root_fd*; return ``(fd, file name)``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for attempt in range(100):
        fname = f"{stamp}-{name}{'' if attempt == 0 else f'-{attempt}'}.log"
        try:
            fd = os.open(fname, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root_fd)
        except FileExistsError:
            continue
        try:
            os.fchmod(fd, 0o600)
        except BaseException:
            os.close(fd)
            raise
        return fd, fname
    raise FileExistsError(name)


def _stop(proc: Any) -> None:
    """Kill the child if it still runs and reap it (bounded)."""
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=_REAP_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - best effort; never raise from cleanup
        pass
    try:
        if proc.stdout is not None:
            proc.stdout.close()
    except Exception:  # noqa: BLE001
        pass


def capture_logs(popen: Callable[..., Any], container: str, dest_dir: os.PathLike | str, *,
                 timeout: float = LOGS_TIMEOUT_S, max_bytes: int = LOGS_MAX_BYTES,
                 tail: int = LOGS_TAIL_LINES,
                 clock: Callable[[], float] = time.monotonic) -> Path | None:
    """Stream ``docker logs --timestamps --tail <tail> <container>`` (stderr
    merged into stdout, stdin ``/dev/null``) into a new 0600 file in the
    private folder *dest_dir*. *popen* is :class:`subprocess.Popen` in
    production (injected in tests).

    Bounds (R-14, R-15): at most *max_bytes* are ever read from the pipe;
    at the cap reading stops and the child is killed. The whole capture runs
    under a monotonic deadline of *timeout* seconds, with the pipe polled by
    ``select`` so a silent child cannot block past it. ``--tail`` is a
    second bound on what docker produces.

    *dest_dir* is opened with :func:`dbsafety.open_private_root` (created one
    level deep when absent; refused when it is a symlink, foreign-owned or
    not 0700), and the file is created relative to that descriptor.

    Returns the file path when the log was captured: in full (docker exited
    0) or truncated at the cap. Returns ``None`` on a timeout, a docker
    error or non-zero exit, or any filesystem error. It never raises: a
    failed capture must not block the teardown that follows.
    """
    try:
        if not isinstance(container, str) or not _CONTAINER_RE.fullmatch(container):
            return None
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            return None
        if isinstance(tail, bool) or not isinstance(tail, int) or tail <= 0:
            return None
        root_fd = open_private_root(dest_dir, code="LOGS_ROOT")
    except Exception:  # noqa: BLE001 - capture failure never propagates
        return None
    file_fd = None
    proc = None
    captured = False
    fname = ""
    try:
        end = clock() + float(timeout)
        file_fd, fname = _new_private_file(root_fd, f"docker-logs-{container}")
        proc = popen(["docker", "logs", "--timestamps", "--tail", str(tail), container],
                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        pipe = proc.stdout.fileno()
        written = 0
        outcome = "timeout"
        while True:
            remaining = end - clock()
            if remaining <= 0:
                break
            ready, _w, _x = select.select([pipe], [], [], min(remaining, _SELECT_SLICE_S))
            if not ready:
                continue
            chunk = _os_read(pipe, min(_READ_CHUNK, max_bytes - written))
            if not chunk:
                outcome = "eof"
                break
            _write_all(file_fd, chunk)
            written += len(chunk)
            if written >= max_bytes:
                outcome = "cap"
                break
        if outcome == "eof":
            try:
                rc = proc.wait(timeout=max(0.01, min(_REAP_TIMEOUT_S, end - clock())))
            except subprocess.TimeoutExpired:
                rc = None
            captured = rc == 0
        elif outcome == "cap":
            captured = True
        os.fsync(file_fd)
    except Exception:  # noqa: BLE001 - capture failure never propagates
        captured = False
    finally:
        if proc is not None:
            _stop(proc)
        if file_fd is not None:
            try:
                os.close(file_fd)
            except OSError:
                pass
        try:
            os.close(root_fd)
        except OSError:
            pass
    return Path(dest_dir) / fname if captured else None


def _unquote(raw: str) -> str | None:
    if not raw.startswith('"'):
        return raw
    try:
        value = json.loads(raw)  # Go's strconv.Quote output is JSON for printable text
    except (json.JSONDecodeError, RecursionError):
        return None  # an escape JSON lacks (\x..): the value is unknown
    return value if isinstance(value, str) else None


def log_record(line: str) -> tuple[str, str] | None:
    """``(level, msg)`` of one Vikunja log line, or ``None`` when the line
    is not a structured record.

    Accepted shapes, each with or without the ``docker logs --timestamps``
    prefix: logfmt (``time=... level=INFO msg="..."``, what this build
    emits) and slog JSON (``{"level":"INFO","msg":"..."}``). Logfmt is
    scanned pair by pair from the start, so text inside a quoted value
    (a task title, say) can never be read as another key; a line that is
    not wholly ``key=value`` pairs is not a record."""
    text = line.rstrip("\r\n")
    prefix = _DOCKER_TS_RE.match(text)
    if prefix:
        text = text[prefix.end():]
    text = text.strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, RecursionError):
            return None
        if isinstance(obj, dict) and isinstance(obj.get("msg"), str) and isinstance(obj.get("level"), str):
            return obj["level"], obj["msg"]
        return None
    fields: dict[str, str | None] = {}
    pos = 0
    while pos < len(text):
        match = _LOGFMT_PAIR_RE.match(text, pos)
        if not match:
            return None
        fields.setdefault(match.group(1), _unquote(match.group(2)))
        pos = match.end()
        if pos < len(text):
            if text[pos] != " ":
                return None
            while pos < len(text) and text[pos] == " ":
                pos += 1
    level, msg = fields.get("level"), fields.get("msg")
    if not isinstance(level, str) or not isinstance(msg, str):
        return None
    return level, msg


def migration_ok(log_path: os.PathLike | str | None) -> tuple[bool, dict[str, int] | None]:
    """Read a captured log privately. Returns ``(ok, counts)``:

    * ``ok`` is True when a record (:func:`log_record`) at level ``INFO``
      has a ``msg`` exactly equal to ``Ran all migrations successfully.``.
      A message that merely contains the phrase (a task title) does not
      count, and neither does unstructured text;
    * ``counts`` holds the last RRULE migration summary record's numbers
      (``processed``, ``converted``, ``already_rrule``, ``unconvertible``,
      ``server_zone``; ints only), matched against the whole ``msg``, or
      ``None`` when there is no summary record.

    An absent or unreadable log is ``(False, None)``. Nothing else from the
    log is returned.
    """
    if log_path is None:
        return False, None
    try:
        with open(log_path, "rb") as fh:
            raw = fh.read(LOGS_MAX_BYTES + 1)
    except OSError:
        return False, None
    ok = False
    counts: dict[str, int] | None = None
    for line in raw.decode("utf-8", errors="replace").splitlines():
        record = log_record(line)
        if record is None:
            continue
        level, msg = record
        if level.upper() == "INFO" and msg == MIGRATIONS_OK_TEXT:
            ok = True
        match = _RRULE_SUMMARY_RE.fullmatch(msg)
        if match:
            counts = {key: int(value) for key, value in zip(RRULE_COUNT_KEYS, match.groups())}
    return ok, counts


__all__ = [
    "LOGS_MAX_BYTES", "LOGS_TAIL_LINES", "LOGS_TIMEOUT_S", "MIGRATIONS_OK_TEXT", "POLL_INTERVAL_S",
    "REQUEST_TIMEOUT_S", "RRULE_COUNT_KEYS", "capture_logs", "log_record", "migration_ok", "wait_ready",
]
