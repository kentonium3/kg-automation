"""Memory samplers (WP04 T018): the two §5 memory columns, sampled beside the request.

- :class:`GttSampler` — the inference process's GPU memory: reads the amdgpu sysfs
  counter ``mem_info_gtt_used`` at 1 Hz (the same counter WP02's ``down`` verifies)
  and exposes ``peak_gib``. Inside the runner container sysfs is read-only and
  present, so the default path works there too; the harness may pass another
  path. There is no llama.cpp ``/metrics`` fallback: the pinned image is not
  started with ``--metrics`` and a fallback that measured something else would
  be a column with a different meaning.
- :class:`RssSampler` — the graph store's process memory: ``docker stats
  --no-stream`` on the FalkorDB container at 1 Hz over the question's load +
  retrieval window, exposing ``peak_mib``.

Both are context managers that NEVER raise into the arm: a sampler that cannot
read records ``None`` with a reason (could-not-check, never a zero — Engineering
Principle 14). NFR-004: ``GttSampler`` carries the 57.5 GiB ceiling and a
``breached`` flag the harness consults before every cell.

The FalkorDB process-RSS SERIES (WP04 reopen; design-lead rulings 20260925T220551226384Z4831c24f84,
20260925T220651378865Z5316e3fceb, 20260925T223514053706Zf68055805c). This module owns the
series format and BOTH ends of it — substrate imports the definitions below, there is no
second copy:

- the record (:class:`RssRecord`, fields :data:`RSS_RECORD_FIELDS`) — one JSON line per
  reading, ``{"ts": ISO-8601 UTC, "rss_mib": float MiB of process RSS, "container_id": str}``,
  after one header line (:class:`RssSeriesHeader`) naming the format, start, container and
  interval;
- the declared interval :data:`SAMPLE_INTERVAL_S` and the tolerances as MULTIPLES of it,
  :data:`STALE_INTERVALS` and :data:`GAP_INTERVALS`;
- :class:`RssSeriesWriter` — host side: reads the container via the existing ``docker
  stats`` path and appends a flushed line per reading;
- :class:`RssSeriesSampler` — runner side: the same surface as :class:`RssSampler`
  (zero-argument factory, context manager, ``peak_mib``, ``breached``, ``sample``), so the
  harness swaps only the factory. It FAILS CLOSED — ``peak_mib`` None with ``sample.reason``,
  which the harness surfaces as ``sampler_unreadable`` — on an absent or empty series, a last
  reading older than ``STALE_INTERVALS`` intervals, a gap over ``GAP_INTERVALS`` intervals
  inside the window, or a container id other than the expected one. Could-not-check, never
  a pass and never a zero.

W8-3: every sampler the harness binds MUST carry a ``breached`` attribute. An object without
one is a ``TypeError`` at bind time (:func:`require_breached`; the harness-side call lands in
C9). RSS has no ceiling, so :class:`RssSeriesSampler` carries ``breached = False``.
"""

from __future__ import annotations

import itertools
import json
import math
import pathlib
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Self

__all__ = ["GAP_INTERVALS", "GTT_CEILING_GIB", "RSS_RECORD_FIELDS", "RSS_SERIES_FORMAT", "SAMPLE_INTERVAL_S",
           "STALE_INTERVALS", "GttSampler", "RssRecord", "RssSampler", "RssSeriesHeader", "RssSeriesSampler",
           "RssSeriesWriter", "Sample", "require_breached"]

GTT_CEILING_GIB = 57.5
DEFAULT_GTT_PATH = pathlib.Path("/sys/class/drm/card1/device/mem_info_gtt_used")
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
    # Series detail (RssSeriesSampler); additive — the 1 Hz samplers leave these None.
    window_start: str | None = None
    window_end: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None
    container_id: str | None = None
    # R2 (design lead, rubric §5 "Window reconstruction", 2026-09-26): the window's support.
    # ``in_window_readings`` counts readings with start <= ts <= end (the held one excluded);
    # ``peak_source`` is "held" only when the held pre-window reading is STRICTLY above every
    # in-window reading (or there is none) — a tie is "in_window"; ``held_ts`` is the held
    # reading's timestamp, None when no held reading was used.
    in_window_readings: int | None = None
    peak_source: str | None = None
    held_ts: str | None = None


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


class RssSampler(_Sampler):
    """Peak RSS (MiB) of one container over the window, via ``docker stats --no-stream``."""

    def __init__(self, container: str = "arms849-falkordb-1") -> None:
        super().__init__()
        self.container = container

    def read_once(self) -> float:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", self.container],
            capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        # "512.3MiB / 62.5GiB" → the used part, normalised to MiB
        used = out.split("/")[0].strip()
        return _to_mib(used)

    @property
    def peak_mib(self) -> float | None:
        return self.sample.peak


_UNITS = {"B": 1 / MIB, "KIB": 1 / 1024, "KB": 1000 / MIB, "MIB": 1.0, "MB": 1e6 / MIB,
          "GIB": 1024.0, "GB": 1e9 / MIB, "TIB": 1024.0 * 1024, "TB": 1e12 / MIB}


def _to_mib(text: str) -> float:
    number = ""
    unit = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            number += ch
        else:
            unit += ch
    unit = unit.strip().upper()
    if not number or unit not in _UNITS:
        raise ValueError(f"unparseable docker memory reading {text!r}")
    return float(number) * _UNITS[unit]


def sample_once(sampler: _Sampler, hold_s: float = 0.0) -> Sample:
    """Convenience for callers that want a window as a value: enter, hold, exit, return."""
    with sampler:
        if hold_s:
            time.sleep(hold_s)
    return sampler.sample


# ---------------------------------------------------------------------------
# FalkorDB process-RSS series: format, writer, reader (WP04 reopen)
# ---------------------------------------------------------------------------

#: The series' declared sample interval (seconds). Tolerances are multiples of it.
SAMPLE_INTERVAL_S = 1.0
#: The last reading may be at most this many intervals older than the window's end (inclusive).
STALE_INTERVALS = 5
#: Consecutive readings covering the window may be at most this many intervals apart (inclusive).
GAP_INTERVALS = 5
#: The header line's ``series`` value; a reader refuses any other.
RSS_SERIES_FORMAT = "arms849-falkordb-rss/1"
#: The record's fields, in line order.
RSS_RECORD_FIELDS = ("ts", "rss_mib", "container_id")
_HEADER_FIELDS = ("series", "started", "container", "container_id", "interval_s")


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


@dataclass(frozen=True)
class RssRecord:
    """One reading: the container's process RSS in MiB at ``ts`` (tz-aware, UTC)."""

    ts: datetime
    rss_mib: float
    container_id: str

    def to_line(self) -> str:
        return json.dumps({"ts": _utc(self.ts).isoformat(), "rss_mib": float(self.rss_mib),
                           "container_id": self.container_id}) + "\n"

    @classmethod
    def from_obj(cls, obj: Any) -> RssRecord:
        if not isinstance(obj, dict) or tuple(sorted(obj)) != tuple(sorted(RSS_RECORD_FIELDS)):
            raise ValueError(f"record fields must be exactly {RSS_RECORD_FIELDS}, got {obj!r}")
        rss = _finite_float(obj["rss_mib"], "rss_mib")
        if rss < 0:
            raise ValueError(f"rss_mib must be non-negative, got {rss!r}")
        return cls(ts=_parse_ts(obj["ts"]), rss_mib=rss,
                   container_id=_nonempty_str(obj["container_id"], "container_id"))


@dataclass(frozen=True)
class RssSeriesHeader:
    """The series' first line: what it measures, since when, and at what interval."""

    started: datetime
    container: str
    container_id: str
    interval_s: float = SAMPLE_INTERVAL_S

    def to_line(self) -> str:
        return json.dumps({"series": RSS_SERIES_FORMAT, "started": _utc(self.started).isoformat(),
                           "container": self.container, "container_id": self.container_id,
                           "interval_s": float(self.interval_s)}) + "\n"

    @classmethod
    def from_obj(cls, obj: Any) -> RssSeriesHeader:
        if not isinstance(obj, dict) or tuple(sorted(obj)) != tuple(sorted(_HEADER_FIELDS)):
            raise ValueError(f"header fields must be exactly {_HEADER_FIELDS}, got {obj!r}")
        if obj["series"] != RSS_SERIES_FORMAT:
            raise ValueError(f"series format {obj['series']!r} is not {RSS_SERIES_FORMAT!r}")
        interval = _finite_float(obj["interval_s"], "interval_s")
        return cls(started=_parse_ts(obj["started"]), container=_nonempty_str(obj["container"], "container"),
                   container_id=_nonempty_str(obj["container_id"], "container_id"), interval_s=float(interval))


def _docker_rss_mib(container_id: str) -> float:
    """The existing ``docker stats`` reading, addressed by the IMMUTABLE container id."""
    return RssSampler(container_id).read_once()


def _docker_container_id(container: str) -> str:
    return subprocess.run(["docker", "inspect", "--format", "{{.Id}}", container],
                          capture_output=True, text=True, timeout=10, check=True).stdout.strip()


class RssSeriesWriter:
    """Host side: append one flushed :class:`RssRecord` line per reading of ``container``.

    ``resolve_id`` (default ``docker inspect``) turns the container NAME into its immutable id
    once, at open; every reading is then ``read(container_id)`` — by id, never by name (cycle 18
    #3), so a replacement container under the same name is a failed read (a hole), never its
    memory recorded under the old id. ``read`` defaults to the existing ``docker stats
    --no-stream`` path (:meth:`RssSampler.read_once`) on that id; ``clock`` (tz-aware UTC datetimes) and ``sleep`` are
    injectable so the series can be produced deterministically. A reading that raises is
    SKIPPED — no line — so the hole is visible to the reader's gap rule; it is counted in
    ``failures`` / ``last_error``. Opening (first ``run``/``start``) truncates ``path`` and writes
    the header: one writer, one series."""

    def __init__(self, path: pathlib.Path | str, container: str, interval_s: float = SAMPLE_INTERVAL_S, *,
                 read: Callable[[str], float] | None = None, resolve_id: Callable[[str], str] | None = None,
                 clock: Callable[[], datetime] = _utc_now, sleep: Callable[[float], Any] | None = None) -> None:
        self.path = pathlib.Path(path)
        self.container = container
        self.interval_s = float(interval_s)
        self._read = read if read is not None else _docker_rss_mib
        self._resolve_id = resolve_id if resolve_id is not None else _docker_container_id
        self._clock = clock
        self._stop = threading.Event()
        self._sleep = sleep if sleep is not None else self._stop.wait
        self._fh: Any = None
        self._thread: threading.Thread | None = None
        self._started: datetime | None = None
        self._k = 0
        self.container_id: str | None = None
        self.readings = 0
        self.failures = 0
        self.last_error: str | None = None

    def open(self) -> None:
        if self._fh is not None:
            return
        self.container_id = _nonempty_str(self._resolve_id(self.container).strip(), "container_id")
        self._started = _utc(self._clock())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")
        self._write(RssSeriesHeader(self._started, self.container, self.container_id, self.interval_s).to_line())

    def _write(self, line: str) -> None:
        self._fh.write(line)
        self._fh.flush()

    def step(self) -> None:
        """Wait for the next due slot (start + k·interval), then take one reading."""
        assert self._started is not None and self.container_id is not None
        due = self._started + timedelta(seconds=self._k * self.interval_s)
        now = _utc(self._clock())
        if now > due + timedelta(seconds=self.interval_s):               # fell behind: skip whole slots
            self._k += int((now - due) / timedelta(seconds=self.interval_s))
            due = self._started + timedelta(seconds=self._k * self.interval_s)
        wait = (due - now).total_seconds()
        if wait > 0:
            self._sleep(min(wait, self.interval_s))
        self._k += 1
        if self._stop.is_set():
            return
        try:
            value = float(self._read(self.container_id))
        except Exception as exc:  # noqa: BLE001 — a missed reading is a hole, never a zero
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return
        self._write(RssRecord(ts=_utc(self._clock()), rss_mib=value, container_id=self.container_id).to_line())
        self.readings += 1

    def run(self, max_readings: int | None = None) -> None:
        """Take readings until ``stop()`` (or ``max_readings`` slots, for tests and one-shot use)."""
        self.open()
        n = 0
        while not self._stop.is_set() and (max_readings is None or n < max_readings):
            self.step()
            n += 1

    def start(self) -> None:
        self.open()
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, name="RssSeriesWriter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s * 3 + 10)
        self.close()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class _Unreadable(Exception):
    pass


class RssSeriesSampler:
    """Runner side: the peak FalkorDB process RSS (MiB) over the window, from the host's series.

    Same surface as :class:`RssSampler`: the harness binds a zero-argument factory
    (``functools.partial(RssSeriesSampler, path, container_id)``), enters it as a context
    manager, and reads ``peak_mib`` twice — just after ``__enter__`` (None ⇒ the cell is not
    started) and after the window. The window is ``[enter, now]`` while open and ``[enter,
    exit]`` once closed; the closed window is computed once at exit and never moves.

    Window reconstruction is SAMPLE-AND-HOLD (design lead, rubric §5, main @5665aa94). Every
    reading with ``start <= ts <= end`` is IN the window — a reading tying either bound is never
    dropped (cycle 18 #2). When no reading ties the start, the value in effect at the start is the
    HELD reading: the latest readings before the start (all of them, if several share that ts).
    ``peak_mib`` is the max over held + in-window readings; ``sample`` records the support (R2):
    ``in_window_readings``, the window bounds, ``held_ts``, and ``peak_source`` — "held" only when
    the held value is strictly above every in-window reading, a tie being "in_window".

    FAIL CLOSED — ``peak_mib`` None with ``sample.reason``, never an exception — when:
    the series is absent or empty, undecodable, malformed or out of order (a torn final line is
    ignored); its interval or container id is not the declared/expected one; the window is
    inverted (end < start, e.g. a backward clock step — cycle 18 #5); the held reading is more
    than ``GAP_INTERVALS`` intervals before the start (R1); the last reading is more than
    ``STALE_INTERVALS`` intervals before the end; or consecutive readings are more than
    ``GAP_INTERVALS`` intervals apart. Exactly the tolerance is allowed.

    Every failure of the clock, the read, the decode and the parse is caught STRUCTURALLY
    (``except Exception``) and becomes a reason (cycle 18 #4). Only BaseExceptions that are not
    Exceptions — KeyboardInterrupt, SystemExit, GeneratorExit — escape, deliberately: they are
    requests to stop the process, not measurements."""

    def __init__(self, path: pathlib.Path | str, container_id_expected: str, *,
                 clock: Callable[[], datetime] = _utc_now) -> None:
        self.path = pathlib.Path(path)
        self.container_id_expected = container_id_expected
        self._clock = clock
        self.breached = False                      # W8-3: required; RSS has no ceiling
        self._start: datetime | None = None
        self._closed: Sample | None = None
        self.sample = Sample(peak=None, reason="not started")

    def __enter__(self) -> Self:
        self._closed = None
        self._start = None
        try:
            self._start = self._now()
        except _Unreadable as exc:
            self.sample = Sample(peak=None, reason=str(exc))
            return self
        self.sample = self._evaluate(self._start)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._closed is None:
            self._closed = self._current()
            self.sample = self._closed

    @property
    def peak_mib(self) -> float | None:
        if self._closed is None:
            self.sample = self._current()
        return self.sample.peak

    def _now(self) -> datetime:
        try:
            return _utc(self._clock())
        except Exception as exc:  # noqa: BLE001 — a clock that cannot answer is could-not-check
            raise _Unreadable(f"clock failed: {type(exc).__name__}: {exc}"[:200]) from None

    def _current(self) -> Sample:
        if self._start is None:
            return self.sample                     # enter failed (or never ran): keep its reason
        try:
            end = self._now()
        except _Unreadable as exc:
            return Sample(peak=None, reason=str(exc), window_start=self._start.isoformat())
        return self._evaluate(end)

    def _evaluate(self, end: datetime) -> Sample:
        start = self._start
        detail = Sample(peak=None)
        try:
            assert start is not None
            detail.window_start, detail.window_end = start.isoformat(), end.isoformat()
            if end < start:
                raise _Unreadable(f"inverted window: end {end.isoformat()} is before start {start.isoformat()}")
            header, records = self._load()
            self._check(header, records, start, end, detail)
        except _Unreadable as exc:
            detail.peak = None
            detail.reason = str(exc)
        except Exception as exc:  # noqa: BLE001 — structural guard: any conversion failure is unreadable
            detail.peak = None
            detail.reason = f"series unreadable: {type(exc).__name__}: {exc}"[:200]
        return detail

    def _load(self) -> tuple[RssSeriesHeader, list[RssRecord]]:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            raise _Unreadable(f"series absent: {self.path}") from None
        except OSError as exc:
            raise _Unreadable(f"series unreadable: {type(exc).__name__}: {exc}"[:200]) from None
        lines = raw.split(b"\n")
        lines.pop()                                # the torn tail (a line still being written), or b""
        if not lines:
            raise _Unreadable("series empty: no header")
        try:
            header = RssSeriesHeader.from_obj(json.loads(lines[0].decode("utf-8")))
        except Exception as exc:  # noqa: BLE001 — decode, JSON, number and timestamp failures alike
            raise _Unreadable(f"series malformed header: {type(exc).__name__}: {exc}"[:200]) from None
        records: list[RssRecord] = []
        for n, line in enumerate(lines[1:], start=2):
            try:
                rec = RssRecord.from_obj(json.loads(line.decode("utf-8")))
            except Exception as exc:  # noqa: BLE001 — decode, JSON, number and timestamp failures alike
                raise _Unreadable(f"series malformed at line {n}: {type(exc).__name__}: {exc}"[:200]) from None
            if records and rec.ts < records[-1].ts:
                raise _Unreadable(f"series out of order at line {n}")
            records.append(rec)
        return header, records

    def _check(self, header: RssSeriesHeader, records: list[RssRecord], start: datetime, end: datetime,
               detail: Sample) -> None:
        detail.container_id = header.container_id
        if header.interval_s != SAMPLE_INTERVAL_S:
            raise _Unreadable(f"series interval {header.interval_s}s is not the declared {SAMPLE_INTERVAL_S}s")
        if header.container_id != self.container_id_expected:
            raise _Unreadable(f"container id {header.container_id!r} is not the expected "
                              f"{self.container_id_expected!r}")
        if not records:
            raise _Unreadable("series empty: no readings")
        stray = next((r for r in records if r.container_id != header.container_id), None)
        if stray is not None:
            raise _Unreadable(f"container id {stray.container_id!r} at {stray.ts.isoformat()} differs "
                              f"from the series' {header.container_id!r}")
        interval = timedelta(seconds=SAMPLE_INTERVAL_S)
        in_window = [r for r in records if start <= r.ts <= end]
        before = [r for r in records if r.ts < start]
        held: list[RssRecord] = []
        if before and not (in_window and in_window[0].ts == start):
            held = [r for r in before if r.ts == before[-1].ts]          # every reading tying the held ts
        used = held + in_window
        if not used:
            raise _Unreadable(f"no reading at or before the window end {end.isoformat()}")
        detail.first_ts, detail.last_ts = used[0].ts.isoformat(), used[-1].ts.isoformat()
        detail.in_window_readings = len(in_window)
        detail.held_ts = held[0].ts.isoformat() if held else None
        if held and start - held[0].ts > GAP_INTERVALS * interval:
            raise _Unreadable(f"held reading {(start - held[0].ts).total_seconds():.3f}s before the window start "
                              f"(> {GAP_INTERVALS} × {SAMPLE_INTERVAL_S}s)")
        age = end - used[-1].ts
        if age > STALE_INTERVALS * interval:
            raise _Unreadable(f"series stale: last reading {age.total_seconds():.3f}s before the window end "
                              f"(> {STALE_INTERVALS} × {SAMPLE_INTERVAL_S}s)")
        if not held and used[0].ts - start > GAP_INTERVALS * interval:
            raise _Unreadable(f"series gap: first reading {(used[0].ts - start).total_seconds():.3f}s "
                              f"after the window start")
        for a, b in itertools.pairwise(used):
            if b.ts - a.ts > GAP_INTERVALS * interval:
                raise _Unreadable(f"series gap of {(b.ts - a.ts).total_seconds():.3f}s after {a.ts.isoformat()} "
                                  f"(> {GAP_INTERVALS} × {SAMPLE_INTERVAL_S}s)")
        detail.samples = [r.rss_mib for r in used]
        detail.readings = len(used)
        detail.peak = max(detail.samples)
        held_peak = max((r.rss_mib for r in held), default=None)
        in_peak = max((r.rss_mib for r in in_window), default=None)
        detail.peak_source = ("held" if held_peak is not None and (in_peak is None or held_peak > in_peak)
                              else "in_window")


def require_breached(sampler: object) -> None:
    """W8-3 bind-time check: a sampler the harness binds MUST carry ``breached``.

    Raises TypeError otherwise — a missing flag must never read as "not breached"."""
    if not hasattr(sampler, "breached"):
        raise TypeError(f"{type(sampler).__name__} has no required `breached` attribute (W8-3)")
