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
"""

from __future__ import annotations

import pathlib
import subprocess
import threading
import time
from dataclasses import dataclass, field

__all__ = ["GTT_CEILING_GIB", "GttSampler", "RssSampler", "Sample"]

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


class _Sampler:
    interval_s = 1.0

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.sample = Sample(peak=None, reason="not started")
        self._valid = True
        self._closed = False

    def read_once(self) -> float:  # pragma: no cover - overridden
        raise NotImplementedError

    def _take(self) -> None:
        try:
            value = self.read_once()
        except Exception as exc:  # noqa: BLE001 — never into the arm; the window is invalid from here
            if self._closed:
                return                      # a late failure after exit: the window was already invalidated
            self.sample.failures += 1
            self._valid = False
            self.sample.reason = f"{type(exc).__name__}: {exc}"[:200]
            self.sample.peak = None
            return
        if self._closed:
            return                          # a late success after exit must not mutate the window
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
            if self._thread.is_alive():
                # A read is still outstanding: the window cannot be called complete. Invalidate
                # it now; the late result is discarded (self._closed) when it arrives.
                self._valid = False
                self.sample.peak = None
                self.sample.reason = "a reading was still outstanding at exit; window incomplete"
        self._closed = True


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
