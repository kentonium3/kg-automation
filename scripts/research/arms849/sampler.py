"""Memory measurement for the #849 run harness.

``GttSampler`` is the live per-attempt ceiling sampler. The graph store is
measured separately at run level: ``CgroupSeriesWriter`` records one exclusive
cgroup-v2 series per substrate generation and ``graph_store_report`` derives the
baseline, peak, and all-resident figures from those series plus ledger boundary
events. The run-level measurement is observational and never alters a cell.
"""

from __future__ import annotations

import errno
import itertools
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Self

__all__ = ["CGROUP_RECORD_FIELDS", "CGROUP_SERIES_FORMAT", "CgroupRecord", "CgroupSeriesHeader",
           "CgroupSeriesTrailer", "CgroupSeriesWriter", "GAP_INTERVALS", "GTT_CEILING_GIB",
           "SAMPLE_INTERVAL_S", "GttSampler", "Sample", "cgroup_memory_mib",
           "docker_container_id", "graph_store_report", "require_breached"]

GTT_CEILING_GIB = 57.5
DEFAULT_GTT_PATH = pathlib.Path("/sys/class/drm/card1/device/mem_info_gtt_used")
DEFAULT_CGROUP_ROOT = pathlib.Path("/sys/fs/cgroup")
GIB = 1024 ** 3
MIB = 1024 ** 2


@dataclass
class Sample:
    """What a sampler hands back: the peak, or None with the reason it could not measure.
    One failed reading INVALIDATES the window (peak None, reason kept) — a partial
    measurement must never look complete (Codex WP04 c1)."""
    peak: float | None
    reason: str | None = None
    readings: int = 0
    failures: int = 0
    missed_intervals: int = 0
    breached: bool = False
    samples: list[float] = field(default_factory=list)


class _Sampler:
    interval_s = 1.0

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.sample = Sample(peak=None, reason="not started")
        self._valid = True
        self._closed = False
        self._lock = threading.Lock()

    def read_once(self) -> float:  # pragma: no cover - overridden
        raise NotImplementedError

    def _take(self) -> None:
        # The reading itself runs unlocked (it may block); the closure check and every
        # mutation of the sample happen under ONE lock, so a window closed between the
        # check and the write can never be mutated (Codex WP04 c4).
        try:
            value = self.read_once()
        except Exception as exc:  # noqa: BLE001 — never into the arm; the window is invalid from here
            with self._lock:
                if self._closed:
                    return
                self.sample.failures += 1
                self._valid = False
                self.sample.reason = f"{type(exc).__name__}: {exc}"[:200]
                self.sample.peak = None
            return
        with self._lock:
            if self._closed:
                return
            self.sample.readings += 1
            self.sample.samples.append(value)
            if self._valid:
                if self.sample.peak is None or value > self.sample.peak:
                    self.sample.peak = value
                self.sample.reason = None
            self._check(value)

    def _loop(self) -> None:
        # Readings are scheduled against monotonic deadlines so the period is the interval,
        # not "read duration + interval"; a deadline that slips a whole period is counted.
        deadline = time.monotonic() + self.interval_s
        while not self._stop.wait(max(0.0, deadline - time.monotonic())):
            self._take()
            deadline += self.interval_s
            now = time.monotonic()
            if now > deadline:
                missed = int((now - deadline) // self.interval_s) + 1
                with self._lock:
                    if not self._closed:              # nothing in the sample moves after exit
                        self.sample.missed_intervals += missed
                deadline += missed * self.interval_s

    def _check(self, value: float) -> None:
        return None

    def __enter__(self):
        self.sample = Sample(peak=None, reason="no reading yet")
        self._valid = True
        self._closed = False
        self._stop.clear()
        self._take()                      # one synchronous reading first: a failing source is known immediately
        self._thread = threading.Thread(target=self._loop, name=type(self).__name__, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s * 3)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                # A read is still outstanding: the window cannot be called complete. Invalidate
                # it now; the late result is discarded (self._closed) when it arrives.
                self._valid = False
                self.sample.peak = None
                self.sample.reason = "a reading was still outstanding at exit; window incomplete"
            self._closed = True
            self.sample.samples = list(self.sample.samples)      # detach: the returned object is frozen from here


class GttSampler(_Sampler):
    """Peak GTT (GiB) over the window; ``breached`` once any reading exceeds the ceiling."""

    ceiling_gib = GTT_CEILING_GIB

    def __init__(self, path: pathlib.Path | str = DEFAULT_GTT_PATH, ceiling_gib: float = GTT_CEILING_GIB) -> None:
        super().__init__()
        self.path = pathlib.Path(path)
        self.ceiling_gib = float(ceiling_gib)
        self.breached = False

    def read_once(self) -> float:
        return int(self.path.read_text().strip()) / GIB

    def _check(self, value: float) -> None:
        if value > self.ceiling_gib:
            self.breached = True
            self.sample.breached = True

    @property
    def peak_gib(self) -> float | None:
        return self.sample.peak


def sample_once(sampler: _Sampler, hold_s: float = 0.0) -> Sample:
    """Enter one sampler window, optionally hold it open, and return its result."""
    with sampler:
        if hold_s:
            time.sleep(hold_s)
    return sampler.sample



# ---------------------------------------------------------------------------
# Run-level FalkorDB cgroup series: format, writer, report
# ---------------------------------------------------------------------------

#: The target series interval (seconds). The descriptor records the real value.
SAMPLE_INTERVAL_S = 1.0
#: Consecutive readings covering a generation may be at most this many intervals apart (inclusive).
GAP_INTERVALS = 5

CGROUP_SERIES_FORMAT = "arms849-falkordb-cgroup/1"
CGROUP_RECORD_FIELDS = ("ts", "cgroup_mib", "container_id")
_CGROUP_HEADER_FIELDS = ("series", "series_id", "started", "container", "container_id", "interval_s")
_CGROUP_TRAILER_FIELDS = ("closed", "readings", "failures")
_FULL_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_SERIES_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_number(value: Any) -> bool:
    """A real int or float — a bool is not a measurement."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_ts(value: Any) -> datetime:
    """A timestamp is accepted only in CANONICAL form: the string must be exactly what
    ``datetime.isoformat()`` produces for the parsed value (which is what the writer emits).
    ``fromisoformat`` also accepts other ISO forms — compact, week dates, 'Z', more than six
    fractional digits — and silently TRUNCATES precision it cannot hold, which moved a reading
    taken just after a window end into the window (Codex WP04 c18/c19). Requiring a round trip
    excludes every lossy or non-canonical form by construction rather than by listing them."""
    try:
        ts = datetime.fromisoformat(value)
    except TypeError:
        raise ValueError(f"timestamp must be an ISO-8601 string, got {value!r}") from None
    if ts.isoformat() != value:
        raise ValueError(f"timestamp {value!r} is not in canonical isoformat form "
                         f"(it would parse as {ts.isoformat()!r}); precision or form would be lost")
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"timestamp {value!r} is not timezone-aware")
    if ts.utcoffset() != timedelta(0):
        raise ValueError(f"timestamp {value!r} is not canonical UTC (+00:00)")
    try:
        return ts.astimezone(timezone.utc)
    except OverflowError:
        raise ValueError(f"timestamp {value!r} is out of range in UTC") from None


def _finite_float(value: Any, name: str) -> float:
    """A real int or float that is finite as a float; ValueError otherwise (never OverflowError)."""
    if not _is_number(value):
        raise ValueError(f"{name} must be a number, got {value!r}")
    try:
        out = float(value)
    except OverflowError:
        raise ValueError(f"{name} is out of float range") from None
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return out


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"clock returned a naive datetime {ts!r}; the series is UTC")
    return ts.astimezone(timezone.utc)


def _nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return value


def _full_container_id(value: Any) -> str:
    value = _nonempty_str(value, "container_id")
    if _FULL_CONTAINER_ID.fullmatch(value) is None:
        raise ValueError(f"container_id must be a full Docker container id (64 lowercase hex digits), got {value!r}")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    return value


def _safe_series_id(value: Any) -> str:
    value = _nonempty_str(value, "series_id")
    if _SAFE_SERIES_ID.fullmatch(value) is None:
        raise ValueError(f"series_id must be a safe filename token, got {value!r}")
    return value


def _valid_interval(value: Any) -> float:
    interval = _finite_float(value, "interval_s")
    if interval <= 0:
        raise ValueError(f"interval_s must be positive, got {interval!r}")
    try:
        delta = timedelta(seconds=interval)
        timedelta(seconds=GAP_INTERVALS * interval)
    except (OverflowError, OSError, ValueError):
        raise ValueError(
            f"interval_s and its {GAP_INTERVALS}-interval tolerance must be representable, got {interval!r}"
        ) from None
    if delta <= timedelta(0):
        raise ValueError(f"interval_s is below timedelta resolution, got {interval!r}")
    return interval


def _interval_delta(value: Any) -> timedelta:
    """A positive, finite and representable sampling interval."""
    return timedelta(seconds=_valid_interval(value))


@dataclass(frozen=True)
class CgroupRecord:
    """One direct cgroup-v2 memory charge reading, in MiB."""

    ts: datetime
    cgroup_mib: float
    container_id: str

    def to_line(self) -> str:
        value = _finite_float(self.cgroup_mib, "cgroup_mib")
        if value < 0:
            raise ValueError(f"cgroup_mib must be non-negative, got {value!r}")
        return json.dumps({"ts": _utc(self.ts).isoformat(), "cgroup_mib": value,
                           "container_id": _full_container_id(self.container_id)}) + "\n"

    @classmethod
    def from_obj(cls, obj: Any) -> CgroupRecord:
        if not isinstance(obj, dict) or set(obj) != set(CGROUP_RECORD_FIELDS):
            raise ValueError(f"record fields must be exactly {CGROUP_RECORD_FIELDS}, got {obj!r}")
        value = _finite_float(obj["cgroup_mib"], "cgroup_mib")
        if value < 0:
            raise ValueError(f"cgroup_mib must be non-negative, got {value!r}")
        return cls(_parse_ts(obj["ts"]), value, _full_container_id(obj["container_id"]))


@dataclass(frozen=True)
class CgroupSeriesHeader:
    """Identity and real interval of one substrate generation's cgroup series."""

    series_id: str
    started: datetime
    container: str
    container_id: str
    interval_s: float = SAMPLE_INTERVAL_S

    def to_line(self) -> str:
        interval = _valid_interval(self.interval_s)
        return json.dumps({"series": CGROUP_SERIES_FORMAT,
                           "series_id": _safe_series_id(self.series_id),
                           "started": _utc(self.started).isoformat(),
                           "container": _nonempty_str(self.container, "container"),
                           "container_id": _full_container_id(self.container_id),
                           "interval_s": interval}) + "\n"

    @classmethod
    def from_obj(cls, obj: Any) -> CgroupSeriesHeader:
        if not isinstance(obj, dict) or set(obj) != set(_CGROUP_HEADER_FIELDS):
            raise ValueError(f"header fields must be exactly {_CGROUP_HEADER_FIELDS}, got {obj!r}")
        if obj["series"] != CGROUP_SERIES_FORMAT:
            raise ValueError(f"series format {obj['series']!r} is not {CGROUP_SERIES_FORMAT!r}")
        interval = _valid_interval(obj["interval_s"])
        return cls(_safe_series_id(obj["series_id"]), _parse_ts(obj["started"]),
                   _nonempty_str(obj["container"], "container"), _full_container_id(obj["container_id"]),
                   interval)


@dataclass(frozen=True)
class CgroupSeriesTrailer:
    """Clean-close marker. Its absence means generation coverage is unknown."""

    closed: datetime
    readings: int
    failures: int

    def to_line(self) -> str:
        return json.dumps({"closed": _utc(self.closed).isoformat(),
                           "readings": _nonnegative_int(self.readings, "readings"),
                           "failures": _nonnegative_int(self.failures, "failures")}) + "\n"

    @classmethod
    def from_obj(cls, obj: Any) -> CgroupSeriesTrailer:
        if not isinstance(obj, dict) or set(obj) != set(_CGROUP_TRAILER_FIELDS):
            raise ValueError(f"trailer fields must be exactly {_CGROUP_TRAILER_FIELDS}, got {obj!r}")
        return cls(_parse_ts(obj["closed"]), _nonnegative_int(obj["readings"], "readings"),
                   _nonnegative_int(obj["failures"], "failures"))



def _docker_container_id(container: str) -> str:
    return subprocess.run(["docker", "inspect", "--format", "{{.Id}}", container],
                          capture_output=True, text=True, timeout=10, check=True).stdout.strip()


def docker_container_id(container: str) -> str:
    """Resolve ``container`` once and require Docker's full immutable id."""
    return _full_container_id(_docker_container_id(_nonempty_str(container, "container")))


def cgroup_memory_mib(container_id: str, *,
                      cgroup_root: pathlib.Path | str = DEFAULT_CGROUP_ROOT) -> float:
    """Read the container's cgroup-v2 memory charge directly, in MiB."""
    full_id = _full_container_id(container_id)
    path = pathlib.Path(cgroup_root) / "system.slice" / f"docker-{full_id}.scope" / "memory.current"
    raw = path.read_text(encoding="ascii").strip()
    try:
        used_bytes = int(raw)
    except ValueError:
        raise ValueError(f"cgroup memory.current must contain integer bytes, got {raw!r}") from None
    if used_bytes < 0:
        raise ValueError(f"cgroup memory.current must be non-negative, got {used_bytes}")
    return used_bytes / MIB


class CgroupSeriesWriter:
    """Host-side, exclusive writer for one substrate generation's cgroup series.

    The caller resolves the immutable container id once and passes it here. A failed
    reading writes no line, leaving an observable hole. ``close`` writes a trailer
    only for a cleanly quiesced writer; a pre-existing path is never reused.
    """

    def __init__(self, path: pathlib.Path | str, series_id: str, container: str, *,
                 container_id: str, started: datetime | None = None,
                 interval_s: float = SAMPLE_INTERVAL_S,
                 cgroup_root: pathlib.Path | str = DEFAULT_CGROUP_ROOT,
                 read: Callable[[str], float] | None = None,
                 clock: Callable[[], datetime] = _utc_now,
                 sleep: Callable[[float], Any] | None = None) -> None:
        self.path = pathlib.Path(path)
        self.series_id = _safe_series_id(series_id)
        self.container = _nonempty_str(container, "container")
        self.container_id = _full_container_id(container_id)
        self.interval_s = _valid_interval(interval_s)
        self._interval = _interval_delta(self.interval_s)
        self.started = _utc(started) if started is not None else None
        root = pathlib.Path(cgroup_root)
        self._read = read if read is not None else lambda cid: cgroup_memory_mib(cid, cgroup_root=root)
        self._clock = clock
        self._stop = threading.Event()
        self._sleep = sleep if sleep is not None else self._stop.wait
        self._fh: Any = None
        self._thread: threading.Thread | None = None
        self._k = 0
        self._trailer_written = False
        self._fatal = False
        self.readings = 0
        self.failures = 0
        self.last_error: str | None = None

    def open(self) -> None:
        if self._fh is not None:
            return
        if self._trailer_written:
            raise RuntimeError("a generation series writer cannot be reopened")
        if self.started is None:
            self.started = _utc(self._clock())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("x", encoding="utf-8")
        try:
            self._write(CgroupSeriesHeader(self.series_id, self.started, self.container,
                                           self.container_id, self.interval_s).to_line())
        except BaseException:
            self._fh.close()
            self._fh = None
            raise

    def _write(self, line: str) -> None:
        self._fh.write(line)
        self._fh.flush()

    def step(self) -> None:
        """Wait for the next target slot, then record one direct cgroup reading."""
        assert self.started is not None
        due = self.started + self._k * self._interval
        now = _utc(self._clock())
        if now > due + self._interval:
            self._k += int((now - due) / self._interval)
            due = self.started + self._k * self._interval
        wait = (due - now).total_seconds()
        if wait > 0:
            self._sleep(min(wait, self.interval_s))
        self._k += 1
        if self._stop.is_set():
            return
        try:
            value = _finite_float(self._read(self.container_id), "cgroup_mib")
            if value < 0:
                raise ValueError(f"cgroup_mib must be non-negative, got {value!r}")
        except Exception as exc:  # noqa: BLE001 — a failed reading is a hole, never a zero
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return
        self._write(CgroupRecord(_utc(self._clock()), value, self.container_id).to_line())
        self.readings += 1

    def run(self, max_readings: int | None = None) -> None:
        self.open()
        n = 0
        while not self._stop.is_set() and (max_readings is None or n < max_readings):
            self.step()
            n += 1

    def _run_background(self) -> None:
        try:
            self.run()
        except Exception as exc:  # noqa: BLE001 — retain an unclean series for report-time refusal
            self._fatal = True
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]

    def start(self) -> None:
        self.open()                         # header exists before the runner can start
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_background,
                                        name="CgroupSeriesWriter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s * 3 + 10)
            if self._thread.is_alive():
                self._fatal = True
                self.last_error = "writer thread did not stop cleanly"
                return                       # never make a still-running writer look complete
        self.close(clean=not self._fatal)

    def close(self, *, clean: bool = True) -> None:
        if self._fh is None:
            return
        try:
            if clean and not self._trailer_written:
                self._write(CgroupSeriesTrailer(_utc(self._clock()), self.readings,
                                                 self.failures).to_line())
                self._trailer_written = True
        finally:
            self._fh.close()
            self._fh = None


class _ReportUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _GenerationSeries:
    series_id: str
    interval_s: float | None
    started: datetime | None
    records: tuple[CgroupRecord, ...] = ()
    trailer: CgroupSeriesTrailer | None = None
    reason: str | None = None


def _could_not_check(reason: str) -> str:
    return f"could_not_check: {reason}"


def _load_generation(detail: Any, runs_dir: pathlib.Path) -> _GenerationSeries:
    """Load one descriptor-bound generation, reducing every file fault to a reason."""
    series_id = "unknown"
    interval: float | None = None
    started: datetime | None = None
    try:
        if not isinstance(detail, dict):
            raise _ReportUnavailable("descriptor_mismatch")
        try:
            series_id = _safe_series_id(detail.get("series_id"))
        except ValueError:
            raise _ReportUnavailable("unsafe_series_id") from None
        status = detail.get("writer_status")
        if status == "failed":
            return _GenerationSeries(series_id, None, None, reason="writer_failed")
        if status != "running":
            raise _ReportUnavailable("descriptor_mismatch")
        container_id = _full_container_id(detail.get("container_id"))
        try:
            interval = _valid_interval(detail.get("interval_s"))
        except ValueError:
            raise _ReportUnavailable("invalid_interval") from None
        started = _parse_ts(detail.get("started_ts"))
        expected_name = f"falkordb-cgroup-{series_id}.jsonl"
        described_path = detail.get("path")
        expected_runner_path = pathlib.PurePosixPath("/runs") / expected_name
        if not isinstance(described_path, str) or pathlib.PurePosixPath(described_path) != expected_runner_path:
            raise _ReportUnavailable("descriptor_mismatch")
        root = runs_dir.resolve()
        path = root / expected_name
        if path.parent != root or path.is_symlink():
            raise _ReportUnavailable("unsafe_path")
        fd: int | None = None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        except FileNotFoundError:
            raise _ReportUnavailable("absent") from None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise _ReportUnavailable("unsafe_path") from None
            raise _ReportUnavailable("unreadable") from None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise _ReportUnavailable("unsafe_path")
            with os.fdopen(fd, "rb") as fh:
                fd = None
                raw = fh.read()
        except OSError:
            raise _ReportUnavailable("unreadable") from None
        finally:
            if fd is not None:
                os.close(fd)
        if not raw.endswith(b"\n"):
            raise _ReportUnavailable("malformed")
        lines = raw.splitlines()
        if not lines:
            raise _ReportUnavailable("malformed")
        try:
            header = CgroupSeriesHeader.from_obj(json.loads(lines[0].decode("utf-8")))
        except Exception:
            raise _ReportUnavailable("malformed") from None
        trailer: CgroupSeriesTrailer | None = None
        record_lines = lines[1:]
        if record_lines:
            try:
                trailer = CgroupSeriesTrailer.from_obj(json.loads(record_lines[-1].decode("utf-8")))
            except Exception:
                pass
            else:
                record_lines = record_lines[:-1]
        records: list[CgroupRecord] = []
        for line in record_lines:
            try:
                record = CgroupRecord.from_obj(json.loads(line.decode("utf-8")))
            except Exception:
                raise _ReportUnavailable("malformed") from None
            if records and record.ts < records[-1].ts:
                raise _ReportUnavailable("coverage")
            records.append(record)
        if header.series_id != series_id or header.started != started or header.interval_s != interval:
            raise _ReportUnavailable("descriptor_mismatch")
        if header.container_id != container_id:
            raise _ReportUnavailable("wrong_container")
        if any(record.container_id != container_id for record in records):
            raise _ReportUnavailable("wrong_container")
        if any(record.ts < header.started for record in records):
            raise _ReportUnavailable("coverage")
        if trailer is not None and (trailer.closed < header.started
                                    or any(record.ts > trailer.closed for record in records)):
            raise _ReportUnavailable("coverage")
        if trailer is not None and trailer.readings != len(records):
            raise _ReportUnavailable("coverage")
        return _GenerationSeries(series_id, interval, started, tuple(records), trailer)
    except _ReportUnavailable as exc:
        return _GenerationSeries(series_id, interval, started, reason=exc.reason)
    except Exception:
        return _GenerationSeries(series_id, interval, started, reason="descriptor_mismatch")


def _generation_peak(generation: _GenerationSeries) -> float:
    if generation.reason is not None:
        raise _ReportUnavailable(generation.reason)
    assert generation.started is not None and generation.interval_s is not None
    if generation.trailer is None:
        raise _ReportUnavailable("coverage")
    records = generation.records
    if not records:
        raise _ReportUnavailable("coverage")
    try:
        interval = _interval_delta(generation.interval_s)
    except ValueError:
        raise _ReportUnavailable("invalid_interval") from None
    limit = GAP_INTERVALS * interval
    first_delta = records[0].ts - generation.started
    trailing_delta = generation.trailer.closed - records[-1].ts
    if (generation.trailer.closed < generation.started or first_delta < timedelta(0)
            or first_delta > limit or trailing_delta < timedelta(0) or trailing_delta > limit):
        raise _ReportUnavailable("coverage")
    if any(b.ts - a.ts > limit for a, b in itertools.pairwise(records)):
        raise _ReportUnavailable("coverage")
    return max(record.cgroup_mib for record in records)


def _by_series_id(generations: list[_GenerationSeries]) -> dict[str, _GenerationSeries]:
    return {generation.series_id: generation for generation in generations}


def _baseline_candidate(generations: list[_GenerationSeries], rows: list[Any]) -> tuple[float | str, str | None]:
    """The first generation's first-build boundary owns the run baseline."""
    generation = generations[0]
    source = generation.series_id
    if generation.reason == "writer_failed":
        return _could_not_check("writer_failed"), source
    event: dict[str, Any] | None = None
    for row in rows:
        if not (isinstance(row, dict) and row.get("record") == "event"
                and row.get("kind") == "graph_store_first_build"):
            continue
        detail = row.get("detail")
        if isinstance(detail, dict) and detail.get("series_id") == source:
            event = detail
            break
    if event is None:
        return _could_not_check("missing_first_build"), source
    if event.get("graphs_present") is True:
        return _could_not_check("graphs_present"), source
    if event.get("graphs_present") is not False:
        return _could_not_check("malformed_event"), source
    try:
        boundary = _parse_ts(event.get("ts"))
    except Exception:
        return _could_not_check("malformed_event"), source
    if generation.reason is not None:
        return _could_not_check(generation.reason), source
    eligible = [record for record in generation.records if record.ts <= boundary]
    if not eligible:
        return _could_not_check("absent"), source
    latest = eligible[-1]
    assert generation.interval_s is not None
    try:
        interval = _interval_delta(generation.interval_s)
    except ValueError:
        return _could_not_check("invalid_interval"), source
    if boundary - latest.ts > GAP_INTERVALS * interval:
        return _could_not_check("stale"), source
    return latest.cgroup_mib, source


def _all_resident_candidate(
        generations: list[_GenerationSeries], rows: list[Any]) -> tuple[float | str, str | None]:
    """The first schema-valid all-resident boundary owns the scalar, even when its series is unusable."""
    by_id = _by_series_id(generations)
    selected: tuple[dict[str, Any], _GenerationSeries, datetime] | None = None
    for row in rows:
        if not (isinstance(row, dict) and row.get("record") == "event"
                and row.get("kind") == "graph_store_all_resident"):
            continue
        event = row.get("detail")
        if not isinstance(event, dict) or type(event.get("n_graphs")) is not int or event["n_graphs"] != 8:
            continue
        generation = by_id.get(event.get("series_id"))
        if generation is None:
            continue
        try:
            boundary = _parse_ts(event.get("ts"))
        except Exception:
            continue
        selected = event, generation, boundary
        break
    if selected is None:
        failed = next((generation for generation in generations if generation.reason == "writer_failed"), None)
        if failed is not None:
            return _could_not_check("writer_failed"), failed.series_id
        return _could_not_check("not_all_resident_in_one_process"), None
    _event, generation, boundary = selected
    source = generation.series_id
    if generation.reason is not None:
        return _could_not_check(generation.reason), source
    following = next((record for record in generation.records if record.ts > boundary), None)
    if following is None:
        return _could_not_check("stale"), source
    assert generation.interval_s is not None
    try:
        interval = _interval_delta(generation.interval_s)
    except ValueError:
        return _could_not_check("invalid_interval"), source
    if following.ts - boundary > GAP_INTERVALS * interval:
        return _could_not_check("stale"), source
    return following.cgroup_mib, source


def _interval_consensus(details: list[Any]) -> tuple[float | str, list[str]]:
    candidates: list[tuple[str, float]] = []
    running_sources: list[str] = []
    failed_sources: list[str] = []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        status = detail.get("writer_status")
        if status not in {"running", "failed"}:
            continue
        try:
            series_id = _safe_series_id(detail.get("series_id"))
        except ValueError:
            return _could_not_check("unsafe_series_id"), running_sources
        if status == "failed":
            failed_sources.append(series_id)
            continue
        running_sources.append(series_id)
        try:
            interval = _valid_interval(detail.get("interval_s"))
        except ValueError:
            return _could_not_check("invalid_interval"), running_sources
        candidates.append((series_id, interval))
    if not candidates:
        if failed_sources:
            return _could_not_check("writer_failed"), failed_sources
        return _could_not_check("absent"), running_sources
    first = candidates[0][1]
    if any(interval != first for _series_id, interval in candidates[1:]):
        return _could_not_check("mixed_intervals"), [series_id for series_id, _interval in candidates]
    return first, [series_id for series_id, _interval in candidates]


def graph_store_report(events_or_rows: Any, runs_dir: pathlib.Path | str) -> dict[str, Any]:
    """Compute the observational run-level graph-store figures from generations.

    The function is deliberately total over malformed or missing series data: every
    measurement failure becomes ``could_not_check`` and never blocks summary/export.
    Ledger order selects the first-build baseline and first schema-valid all-resident
    boundary without cherry-picking a later favourable generation. Marginal is numeric
    only when those two values come from the same generation. ``source_series_ids``
    makes every scalar's generation provenance explicit. Peak lists every generation
    governing its coverage and value in ledger order, whether numeric or unavailable.
    Interval lists the generations governing either its consensus or its failure.
    """
    rows = list(events_or_rows) if isinstance(events_or_rows, (list, tuple)) else []
    details = [row.get("detail") for row in rows
               if isinstance(row, dict) and row.get("record") == "event"
               and row.get("kind") == "series_generation"]
    generations = [_load_generation(detail, pathlib.Path(runs_dir)) for detail in details]
    series_ids = [generation.series_id for generation in generations]
    if not generations:
        unavailable = _could_not_check("absent")
        return {"baseline_mib": unavailable, "peak_mib": unavailable,
                "all_resident_mib": unavailable, "marginal_per_graph_mib": unavailable,
                "interval_s": unavailable, "series_ids": [],
                "source_series_ids": {key: [] for key in ("baseline_mib", "peak_mib", "all_resident_mib",
                                                            "marginal_per_graph_mib", "interval_s")}}

    baseline, baseline_id = _baseline_candidate(generations, rows)
    all_resident, all_resident_id = _all_resident_candidate(generations, rows)
    interval_s, interval_sources = _interval_consensus(details)

    peak_candidates: list[tuple[str, float]] = []
    try:
        for generation in generations:
            peak_candidates.append((generation.series_id, _generation_peak(generation)))
    except _ReportUnavailable as exc:
        peak: float | str = _could_not_check(exc.reason)
        peak_sources: list[str] = list(series_ids)
    else:
        peak = max(value for _series_id, value in peak_candidates)
        peak_sources = list(series_ids)

    scalar_sources = [series_id for series_id in (baseline_id, all_resident_id) if series_id is not None]
    marginal_sources = list(dict.fromkeys(scalar_sources))
    if isinstance(baseline, float) and isinstance(all_resident, float):
        if baseline_id == all_resident_id:
            marginal: float | str = (all_resident - baseline) / 8
            marginal_sources = [baseline_id] if baseline_id is not None else []
        else:
            marginal = _could_not_check("different_generation")
    else:
        marginal = baseline if isinstance(baseline, str) else all_resident
    return {"baseline_mib": baseline, "peak_mib": peak, "all_resident_mib": all_resident,
            "marginal_per_graph_mib": marginal, "interval_s": interval_s,
            "series_ids": series_ids,
            "source_series_ids": {
                "baseline_mib": [baseline_id] if baseline_id is not None else [],
                "peak_mib": peak_sources,
                "all_resident_mib": [all_resident_id] if all_resident_id is not None else [],
                "marginal_per_graph_mib": marginal_sources,
                "interval_s": interval_sources,
            }}



def require_breached(sampler: object) -> None:
    """W8-3 bind-time check: a sampler the harness binds MUST carry ``breached``.

    Raises TypeError otherwise — a missing flag must never read as "not breached"."""
    if not hasattr(sampler, "breached"):
        raise TypeError(f"{type(sampler).__name__} has no required `breached` attribute (W8-3)")
