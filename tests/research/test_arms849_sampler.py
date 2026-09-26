"""FalkorDB process-RSS series (WP04 reopen): one record format, the host-side writer, the
runner-side reader, round-tripped under an injected clock (no real sleeping).

Design-lead rulings 20260925T220551226384Z4831c24f84 / 20260925T220651378865Z5316e3fceb /
20260925T223514053706Zf68055805c; call-site constraint from the harness @f8451d1a.
"""

from __future__ import annotations

import contextlib
import functools
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import sampler as SM

CID = "f00dfacecafe" * 5 + "beef"
T0 = datetime(2026, 9, 25, 22, 0, 0, tzinfo=timezone.utc)
STEP = timedelta(seconds=SM.SAMPLE_INTERVAL_S)
EPS = timedelta(microseconds=1)


class FakeClock:
    """A shared wall clock: the writer's sleep advances it, the reader reads it."""

    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def set(self, when: datetime) -> None:
        self.now = when


def _peak(sampler: Any, attr: str) -> float | None:
    """Verbatim semantics of the harness's _peak (run_849_harness.py @f8451d1a)."""
    value = getattr(sampler, attr, None)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _writer(path: pathlib.Path, clock: FakeClock, values: list[Any]) -> SM.RssSeriesWriter:
    it = iter(values)

    def read(container_id: str) -> float:
        assert container_id == CID                              # sampled by the resolved id (cycle 18 #3)
        v = next(it)
        if isinstance(v, BaseException):
            raise v
        return v

    return SM.RssSeriesWriter(path, "arms849-falkordb-1", read=read, resolve_id=lambda name: CID,
                              clock=clock, sleep=clock.sleep)


def _series(tmp_path: pathlib.Path, values: list[Any]) -> tuple[pathlib.Path, FakeClock]:
    """Samples at T0, T0+1s, … (one per interval; an exception is a missed reading)."""
    path = tmp_path / "rss.jsonl"
    clock = FakeClock()
    w = _writer(path, clock, values)
    w.run(max_readings=len(values))
    w.close()
    return path, clock


def _window(path: pathlib.Path, clock: FakeClock, start: datetime, end: datetime,
            expected: str = CID) -> SM.RssSeriesSampler:
    s = SM.RssSeriesSampler(path, expected, clock=clock)
    clock.set(start)
    with s:
        clock.set(end)
    return s


# ---------------------------------------------------------------------------
# item 1: one definition of the record, the interval and the tolerances
# ---------------------------------------------------------------------------


def test_the_series_format_is_defined_once_with_tolerances_as_multiples_of_the_interval():
    assert SM.SAMPLE_INTERVAL_S == 1.0
    assert SM.STALE_INTERVALS == 5 and SM.GAP_INTERVALS == 5
    assert SM.RSS_RECORD_FIELDS == ("ts", "rss_mib", "container_id")
    assert SM.GTT_CEILING_GIB == 57.5                                    # unchanged
    rec = SM.RssRecord(ts=T0, rss_mib=512.25, container_id=CID)
    line = rec.to_line()
    assert line.endswith("\n") and "\n" not in line[:-1]
    obj = json.loads(line)
    assert tuple(obj) == SM.RSS_RECORD_FIELDS
    assert obj["ts"] == "2026-09-25T22:00:00+00:00"
    assert SM.RssRecord.from_obj(obj) == rec


@pytest.mark.parametrize("obj", [
    {"ts": "2026-09-25T22:00:00", "rss_mib": 1.0, "container_id": CID},          # naive ts
    {"ts": "2026-09-25T22:00:00+00:00", "rss_mib": True, "container_id": CID},   # bool is not a size
    {"ts": "2026-09-25T22:00:00+00:00", "rss_mib": -1.0, "container_id": CID},
    {"ts": "2026-09-25T22:00:00+00:00", "rss_mib": float("nan"), "container_id": CID},
    {"ts": "2026-09-25T22:00:00+00:00", "rss_mib": 1.0, "container_id": ""},
    {"ts": "2026-09-25T22:00:00+00:00", "rss_mib": 1.0},                         # missing field
    {"ts": "2026-09-25T22:00:00+00:00", "rss_mib": 1.0, "container_id": CID, "x": 1},
])
def test_a_malformed_record_is_refused(obj):
    with pytest.raises(ValueError):
        SM.RssRecord.from_obj(obj)


def test_a_non_utc_offset_is_normalised_to_utc():
    rec = SM.RssRecord.from_obj({"ts": "2026-09-26T00:00:00+02:00", "rss_mib": 3, "container_id": CID})
    assert rec.ts == T0 and rec.ts.utcoffset() == timedelta(0) and rec.rss_mib == 3.0


# ---------------------------------------------------------------------------
# item 2: the host-side writer
# ---------------------------------------------------------------------------


def test_writer_emits_a_header_then_one_flushed_line_per_reading(tmp_path):
    path = tmp_path / "rss.jsonl"
    clock = FakeClock()
    w = _writer(path, clock, [100.0, 200.5, 150.0])
    w.run(max_readings=2)
    lines = path.read_text().splitlines()                    # visible WITHOUT close: flushed per line
    assert len(lines) == 3
    header = json.loads(lines[0])
    assert header == {"series": SM.RSS_SERIES_FORMAT, "started": "2026-09-25T22:00:00+00:00",
                      "container": "arms849-falkordb-1", "container_id": CID,
                      "interval_s": SM.SAMPLE_INTERVAL_S}
    recs = [SM.RssRecord.from_obj(json.loads(x)) for x in lines[1:]]
    assert [r.rss_mib for r in recs] == [100.0, 200.5]
    assert [r.ts for r in recs] == [T0, T0 + STEP]           # period = the declared interval
    assert all(r.container_id == CID for r in recs)
    w.run(max_readings=1)
    w.close()
    assert len(path.read_text().splitlines()) == 4


def test_writer_skips_a_failed_reading_and_keeps_going(tmp_path):
    path, _ = _series(tmp_path, [1.0, RuntimeError("docker down"), 3.0])
    lines = path.read_text().splitlines()
    ts = [json.loads(x)["ts"] for x in lines[1:]]
    assert ts == ["2026-09-25T22:00:00+00:00", "2026-09-25T22:00:02+00:00"]   # the hole is left for the reader


def test_writer_default_reading_is_the_existing_docker_stats_path(tmp_path, monkeypatch):
    import subprocess
    calls: list[list[str]] = []

    def fake_run(argv, **kw):
        calls.append(argv)
        out = CID + "\n" if argv[1] == "inspect" else "1.5GiB / 62.5GiB"
        return type("P", (), {"stdout": out})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    clock = FakeClock()
    w = SM.RssSeriesWriter(tmp_path / "rss.jsonl", "arms849-falkordb-1", clock=clock, sleep=clock.sleep)
    w.run(max_readings=1)
    w.close()
    assert ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", CID] in calls     # by id, not name
    assert ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", "arms849-falkordb-1"] not in calls
    assert ["docker", "inspect", "--format", "{{.Id}}", "arms849-falkordb-1"] in calls
    rec = json.loads((tmp_path / "rss.jsonl").read_text().splitlines()[1])
    assert rec["rss_mib"] == pytest.approx(1536.0) and rec["container_id"] == CID


def test_writer_start_stop_runs_in_the_background(tmp_path):
    """start()/stop() as substrate will drive them (C9); the injected sleep keeps it instant."""
    import threading
    import time
    clock = FakeClock()
    lock = threading.Lock()
    gate = threading.Event()

    def sleep(s: float) -> None:
        with lock:
            clock.sleep(s)
        gate.set()
        time.sleep(0.001)                                       # trivial real yield; the clock is fake

    w = SM.RssSeriesWriter(tmp_path / "rss.jsonl", "c", read=lambda cid: 7.0, resolve_id=lambda n: CID,
                           clock=clock, sleep=sleep)
    w.start()
    assert gate.wait(5)
    w.stop()
    n = len((tmp_path / "rss.jsonl").read_text().splitlines())
    assert n >= 2
    assert len((tmp_path / "rss.jsonl").read_text().splitlines()) == n     # nothing is written after stop


# ---------------------------------------------------------------------------
# items 3 + 5: the reader and the round trip
# ---------------------------------------------------------------------------


def test_round_trip_peak_is_exactly_the_max_over_the_window(tmp_path):
    #          t=0    1      2      3      4      5      6      7      8
    values = [900.0, 10.0, 20.0, 35.5, 30.0, 25.0, 12.0, 11.0, 800.0]
    path, clock = _series(tmp_path, values)
    s = _window(path, clock, T0 + 2 * STEP, T0 + 6 * STEP)
    assert s.peak_mib == max(values[2:7]) == 35.5            # 900 before and 800 after are outside
    d = s.sample
    assert d.reason is None and d.readings == 5 and d.samples == values[2:7]
    assert d.window_start == (T0 + 2 * STEP).isoformat() and d.window_end == (T0 + 6 * STEP).isoformat()
    assert d.first_ts == (T0 + 2 * STEP).isoformat() and d.last_ts == (T0 + 6 * STEP).isoformat()
    assert d.container_id == CID and s.breached is False
    assert d.in_window_readings == 5 and d.peak_source == "in_window" and d.held_ts is None


def test_the_value_held_at_window_start_is_the_last_sample_before_it(tmp_path):
    """The series is sample-and-hold: at a start between samples the process's RSS is the last
    reading; without it the pre-arm read (window [start, start]) could never be a number."""
    values = [10.0, 99.0, 20.0, 30.0]
    path, clock = _series(tmp_path, values)
    s = _window(path, clock, T0 + STEP + STEP / 2, T0 + 3 * STEP)
    assert s.peak_mib == 99.0 and s.sample.samples == [99.0, 20.0, 30.0]
    assert s.sample.first_ts == (T0 + STEP).isoformat()
    assert s.sample.in_window_readings == 2 and s.sample.peak_source == "held"          # R2
    assert s.sample.held_ts == (T0 + STEP).isoformat()


def test_series_absent_is_unreadable(tmp_path):
    s = _window(tmp_path / "missing.jsonl", FakeClock(), T0, T0 + STEP)
    assert s.peak_mib is None and "absent" in s.sample.reason


@pytest.mark.parametrize("content", ["", SM.RssSeriesHeader(T0, "c", CID).to_line()])
def test_series_empty_is_unreadable(tmp_path, content):
    path = tmp_path / "rss.jsonl"
    path.write_text(content)
    s = _window(path, FakeClock(), T0, T0 + STEP)
    assert s.peak_mib is None and "empty" in s.sample.reason


def test_stale_by_five_intervals_plus_epsilon_is_unreadable_and_exactly_five_is_allowed(tmp_path):
    path, clock = _series(tmp_path, [1.0, 2.0, 3.0])                      # last sample at T0+2
    last = T0 + 2 * STEP
    ok = _window(path, clock, T0, last + SM.STALE_INTERVALS * STEP)
    assert ok.peak_mib == 3.0 and ok.sample.reason is None
    bad = _window(path, clock, T0, last + SM.STALE_INTERVALS * STEP + EPS)
    assert bad.peak_mib is None and "stale" in bad.sample.reason


def test_stale_at_enter_is_unreadable_before_the_arm_runs(tmp_path):
    path, clock = _series(tmp_path, [1.0])
    s = SM.RssSeriesSampler(path, CID, clock=clock)
    clock.set(T0 + SM.STALE_INTERVALS * STEP + EPS)
    with s:
        # at enter end == start, so R1 (held vs start) and staleness (last vs end) coincide; R1 reports
        assert _peak(s, "peak_mib") is None and "held reading" in s.sample.reason


def test_a_gap_over_five_intervals_inside_the_window_is_unreadable_and_exactly_five_is_allowed(tmp_path):
    miss = RuntimeError("missed")
    # samples at 0,1 then a 5-interval hole (misses at 2,3,4,5) then 6,7
    path5, clock5 = _series(tmp_path, [1.0, 2.0, miss, miss, miss, miss, 3.0, 4.0])
    ok = _window(path5, clock5, T0, T0 + 7 * STEP)
    assert ok.peak_mib == 4.0 and ok.sample.readings == 4

    sub = tmp_path / "six"; sub.mkdir()
    path6, clock6 = _series(sub, [1.0, 2.0, miss, miss, miss, miss, miss, 3.0, 4.0])   # hole of 6
    bad = _window(path6, clock6, T0, T0 + 8 * STEP)
    assert bad.peak_mib is None and "gap" in bad.sample.reason


def test_a_gap_outside_the_window_does_not_poison_it(tmp_path):
    miss = RuntimeError("missed")
    path, clock = _series(tmp_path, [1.0, miss, miss, miss, miss, miss, miss, 5.0, 6.0, 7.0])
    s = _window(path, clock, T0 + 7 * STEP, T0 + 9 * STEP)
    assert s.peak_mib == 7.0


def test_the_gap_from_the_held_value_into_the_window_counts(tmp_path):
    miss = RuntimeError("missed")
    path, clock = _series(tmp_path, [1.0, miss, miss, miss, miss, miss, miss, 5.0])   # 0 then 7
    s = _window(path, clock, T0 + 3 * STEP, T0 + 7 * STEP)                           # held value from 0
    assert s.peak_mib is None and "gap" in s.sample.reason


def test_container_id_mismatch_is_unreadable(tmp_path):
    path, clock = _series(tmp_path, [1.0, 2.0])
    s = _window(path, clock, T0, T0 + STEP, expected="0" * 64)
    assert s.peak_mib is None and "container" in s.sample.reason


def test_a_record_from_another_container_inside_the_series_is_unreadable(tmp_path):
    path, clock = _series(tmp_path, [1.0, 2.0])
    with path.open("a") as fh:
        fh.write(SM.RssRecord(ts=T0 + 2 * STEP, rss_mib=3.0, container_id="other").to_line())
    s = _window(path, clock, T0, T0 + 2 * STEP)
    assert s.peak_mib is None and "container" in s.sample.reason


def test_a_malformed_or_out_of_order_line_is_unreadable_but_a_torn_tail_is_ignored(tmp_path):
    path, clock = _series(tmp_path, [1.0, 2.0])
    base = path.read_text()
    path.write_text(base + '{"ts": "2026-09-25T22:00:02+00:00", "rss_m')              # writer mid-line
    torn = _window(path, clock, T0, T0 + 2 * STEP)
    assert torn.peak_mib == 2.0
    path.write_text(base + "not json\n")
    assert "malformed" in _window(path, clock, T0, T0 + STEP).sample.reason
    path.write_text(base + SM.RssRecord(ts=T0, rss_mib=9.0, container_id=CID).to_line())
    assert "order" in _window(path, clock, T0, T0 + STEP).sample.reason


def test_a_header_whose_interval_differs_from_the_declared_one_is_unreadable(tmp_path):
    path, clock = _series(tmp_path, [1.0, 2.0])
    lines = path.read_text().splitlines(keepends=True)
    head = json.loads(lines[0]); head["interval_s"] = 2.0
    path.write_text(json.dumps(head) + "\n" + "".join(lines[1:]))
    s = _window(path, clock, T0, T0 + STEP)
    assert s.peak_mib is None and "interval" in s.sample.reason


# ---------------------------------------------------------------------------
# item 4: W8-3 — `breached` is REQUIRED on a bound sampler
# ---------------------------------------------------------------------------


def test_a_bound_sampler_without_breached_is_a_type_error(tmp_path):
    class NoFlag:
        peak_mib = 1.0
    with pytest.raises(TypeError, match="breached"):
        SM.require_breached(NoFlag())
    SM.require_breached(SM.GttSampler(tmp_path / "gtt"))
    s = SM.RssSeriesSampler(tmp_path / "rss.jsonl", CID)
    SM.require_breached(s)
    assert s.breached is False                                  # RSS has no ceiling; W8-3 is about presence


# ---------------------------------------------------------------------------
# CALL-SITE CONSTRAINT: driven exactly as run_849_harness.py @f8451d1a drives a sampler
# ---------------------------------------------------------------------------


def test_driven_as_the_harness_drives_it(tmp_path):
    path = tmp_path / "rss.jsonl"
    clock = FakeClock()
    w = _writer(path, clock, [50.0, 60.0, 70.0, 400.0, 80.0, 65.0, 999.0])
    w.run(max_readings=3)                                       # samples at 0,1,2; clock left at 3
    factory = functools.partial(SM.RssSeriesSampler, path, CID, clock=clock)   # C9's swap
    clock.set(T0 + 2 * STEP + STEP / 2)                         # the cell starts between samples
    with contextlib.ExitStack() as stack:
        rss = stack.enter_context(factory())
        before = _peak(rss, "peak_mib")                         # the pre-arm readability read
        assert before == 70.0 and getattr(rss, "breached", False) is False
        w.run(max_readings=3)                                   # the arm runs: samples at 3,4,5
        clock.set(T0 + 5 * STEP + STEP / 2)
        assert _peak(rss, "peak_mib") == 400.0                  # live read over [start, now] inside the window
    w.run(max_readings=1)                                       # a reading after the window closed
    after = _peak(rss, "peak_mib")                              # the row's falkordb_rss_peak_mib
    assert after == 400.0                                       # 999 arrived after exit
    assert rss.sample.window_end == (T0 + 5 * STEP + STEP / 2).isoformat()
    assert rss.sample.samples == [70.0, 400.0, 80.0, 65.0]


def test_harness_pre_arm_read_is_none_when_the_series_is_unusable(tmp_path):
    factory = functools.partial(SM.RssSeriesSampler, tmp_path / "never-written.jsonl", CID, clock=FakeClock())
    with contextlib.ExitStack() as stack:
        rss = stack.enter_context(factory())
        assert "absent" in (rss.sample.reason or "")              # __enter__ itself ran the checks
        assert rss.sample.window_start == T0.isoformat()
        assert _peak(rss, "peak_mib") is None and rss.sample.reason


def test_the_window_is_frozen_at_exit(tmp_path):
    path = tmp_path / "rss.jsonl"
    clock = FakeClock()
    w = _writer(path, clock, [1.0, 2.0, 3.0, 50.0])
    w.run(max_readings=3)
    s = SM.RssSeriesSampler(path, CID, clock=clock)
    clock.set(T0)
    with s:
        clock.set(T0 + 2 * STEP)
    snap = (s.peak_mib, s.sample.samples, s.sample.window_end)
    clock.set(T0 + 30 * STEP)                                   # later the series goes stale…
    w.run(max_readings=1)
    assert (s.peak_mib, s.sample.samples, s.sample.window_end) == snap   # …the closed window does not move



# ---------------------------------------------------------------------------
# cycle 18 (review-feedback-18.md): riders R1/R2 and Codex findings 2–5
# ---------------------------------------------------------------------------


def _raw_series(tmp_path: pathlib.Path, records: list[tuple[timedelta, float]]) -> pathlib.Path:
    path = tmp_path / "rss.jsonl"
    path.write_text(SM.RssSeriesHeader(T0, "c", CID).to_line()
                    + "".join(SM.RssRecord(T0 + dt, v, CID).to_line() for dt, v in records))
    return path


def test_r1_held_reading_at_exactly_five_intervals_before_start_is_allowed_and_five_plus_epsilon_refused(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 42.0)])
    start = T0 + SM.GAP_INTERVALS * STEP
    ok = _window(path, FakeClock(), start, start)
    assert ok.peak_mib == 42.0 and ok.sample.peak_source == "held" and ok.sample.in_window_readings == 0
    bad = _window(path, FakeClock(), start + EPS, start + EPS)
    assert bad.peak_mib is None and "held" in bad.sample.reason and "start" in bad.sample.reason


def test_r2_a_tie_between_held_and_in_window_is_in_window(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 50.0), (STEP, 50.0), (2 * STEP, 40.0)])
    s = _window(path, FakeClock(), T0 + STEP / 2, T0 + 2 * STEP)
    assert s.peak_mib == 50.0 and s.sample.peak_source == "in_window" and s.sample.in_window_readings == 2
    higher = _window(_raw_series(tmp_path, [(timedelta(0), 51.0), (STEP, 50.0)]), FakeClock(),
                     T0 + STEP / 2, T0 + STEP)
    assert higher.sample.peak_source == "held"


def test_2_every_record_tying_the_window_start_is_inside_the_window(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 999.0), (timedelta(0), 10.0), (STEP, 20.0)])
    s = _window(path, FakeClock(), T0, T0 + STEP)
    assert s.peak_mib == 999.0 and s.sample.in_window_readings == 3
    assert s.sample.peak_source == "in_window" and s.sample.held_ts is None


def test_2_every_record_tying_the_window_end_is_inside_the_window(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 5.0), (STEP, 20.0), (STEP, 999.0), (STEP, 1.0)])
    s = _window(path, FakeClock(), T0, T0 + STEP)
    assert s.peak_mib == 999.0 and s.sample.in_window_readings == 4


def test_2_a_held_reading_is_not_used_when_a_reading_ties_the_start(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 999.0), (STEP, 10.0), (2 * STEP, 20.0)])
    s = _window(path, FakeClock(), T0 + STEP, T0 + 2 * STEP)
    assert s.peak_mib == 20.0 and s.sample.held_ts is None


def test_3_the_writer_samples_the_resolved_immutable_id_not_the_name(tmp_path):
    seen: list[str] = []

    def read(container_id: str) -> float:
        seen.append(container_id)
        return 1.0

    clock = FakeClock()
    w = SM.RssSeriesWriter(tmp_path / "rss.jsonl", "arms849-falkordb-1", read=read,
                           resolve_id=lambda name: CID, clock=clock, sleep=clock.sleep)
    w.run(max_readings=3)
    w.close()
    assert seen == [CID, CID, CID]


def test_3_a_replacement_container_is_a_hole_not_a_reading_under_the_old_id(tmp_path, monkeypatch):
    """docker stats by id: once A is gone the read fails (a hole), B's memory is never recorded as A's."""
    import subprocess
    state = {"replaced": False}

    def fake_run(argv, **kw):
        if argv[1] == "inspect":
            return type("P", (), {"stdout": CID + "\n"})()
        target = argv[-1]
        if state["replaced"] and target == CID:
            raise subprocess.CalledProcessError(1, argv)          # A no longer exists
        return type("P", (), {"stdout": ("999MiB" if state["replaced"] else "10MiB") + " / 62GiB"})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    clock = FakeClock()
    w = SM.RssSeriesWriter(tmp_path / "rss.jsonl", "arms849-falkordb-1", clock=clock, sleep=clock.sleep)
    w.run(max_readings=2)
    state["replaced"] = True                                     # the NAME now points at container B
    w.run(max_readings=2)
    w.close()
    recs = [json.loads(x) for x in (tmp_path / "rss.jsonl").read_text().splitlines()[1:]]
    assert [r["rss_mib"] for r in recs] == [10.0, 10.0] and w.failures == 2


@pytest.mark.parametrize("tail", [
    b"\xff\xfe not utf-8\n",                                                        # UnicodeDecodeError
    b'{"ts": "2026-09-25T22:00:02+00:00", "rss_mib": 1' + b"0" * 400 + b', "container_id": "C"}\n',
    b'{"ts": "2026-09-25T22:00:02+00:00", "rss_mib": 1e999, "container_id": "C"}\n',
    b'{"ts": "9999-12-31T23:59:59-23:59", "rss_mib": 1.0, "container_id": "C"}\n',  # UTC conversion overflows
    b'{"ts": ["2026"], "rss_mib": 1.0, "container_id": "C"}\n',
    b"[1, 2]\n",
    b'{"ts": "2026-09-25T22:00:02+00:00", "rss_mib": 1.0, "container_id": 7}\n',
    b"[" * 200_000 + b"]" * 200_000 + b"\n",                                        # RecursionError, not a ValueError
])
def test_4_every_conversion_failure_is_fail_closed_never_raised(tmp_path, tail):
    path = _raw_series(tmp_path, [(timedelta(0), 1.0), (STEP, 2.0)])
    path.write_bytes(path.read_bytes() + tail.replace(b'"C"', json.dumps(CID).encode()))
    s = SM.RssSeriesSampler(path, CID, clock=FakeClock(T0 + 2 * STEP))
    with s:                                                      # nothing escapes the context manager
        assert s.peak_mib is None and "line 4" in s.sample.reason   # the reason names the failing line
    assert s.peak_mib is None and "line 4" in s.sample.reason


def test_4_the_structural_guard_catches_what_no_parser_guard_names(tmp_path, monkeypatch):
    """A failure outside every per-line guard (here the read itself raising a non-OSError) is
    still could-not-check: the whole evaluation sits under one structural guard."""
    path = _raw_series(tmp_path, [(timedelta(0), 1.0)])

    def boom(self):
        raise RuntimeError("filesystem driver bug")

    monkeypatch.setattr(pathlib.Path, "read_bytes", boom)
    s = SM.RssSeriesSampler(path, CID, clock=FakeClock())
    with s:
        assert s.peak_mib is None and "RuntimeError" in s.sample.reason
    assert s.peak_mib is None and "RuntimeError" in s.sample.reason


def test_4_a_header_that_is_not_utf8_or_overflows_is_fail_closed(tmp_path):
    path = tmp_path / "rss.jsonl"
    for content in (b"\x80\n", b'{"series": "arms849-falkordb-rss/1", "started": "2026-09-25T22:00:00+00:00", '
                                 b'"container": "c", "container_id": "x", "interval_s": 1' + b"0" * 400 + b"}\n"):
        path.write_bytes(content)
        s = _window(path, FakeClock(), T0, T0)
        assert s.peak_mib is None and s.sample.reason


def _naive() -> datetime:
    return T0.replace(tzinfo=None)                               # deliberately naive


def _raising() -> datetime:
    raise RuntimeError("clock source gone")


@pytest.mark.parametrize("bad_clock", [_naive, _raising])
def test_4_a_failing_clock_is_fail_closed_never_raised(tmp_path, bad_clock):
    path = _raw_series(tmp_path, [(timedelta(0), 1.0)])
    s = SM.RssSeriesSampler(path, CID, clock=bad_clock)
    with s:
        assert s.peak_mib is None and "clock" in s.sample.reason
    assert s.peak_mib is None


def test_4_a_clock_failing_mid_window_is_fail_closed(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 1.0)])
    calls = iter([T0])

    def clock() -> datetime:
        return next(calls)                                       # StopIteration after the first call

    s = SM.RssSeriesSampler(path, CID, clock=clock)
    with s:
        assert s.sample.peak == 1.0                              # enter succeeded
        assert s.peak_mib is None and "clock" in s.sample.reason
    assert s.peak_mib is None and "clock" in s.sample.reason


def test_5_an_inverted_window_is_unreadable(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 1.0), (STEP, 2.0)])
    s = _window(path, FakeClock(), T0 + STEP, T0)                # a backward clock step during the cell
    assert s.peak_mib is None and "inverted" in s.sample.reason
    clock = FakeClock(T0 + STEP)
    live = SM.RssSeriesSampler(path, CID, clock=clock)
    with live:
        clock.set(T0)
        assert live.peak_mib is None and "inverted" in live.sample.reason


def test_2_every_record_tying_the_held_timestamp_is_held(tmp_path):
    path = _raw_series(tmp_path, [(timedelta(0), 999.0), (timedelta(0), 10.0), (STEP, 20.0)])
    s = _window(path, FakeClock(), T0 + STEP / 2, T0 + STEP)
    assert s.peak_mib == 999.0 and s.sample.peak_source == "held" and s.sample.samples == [999.0, 10.0, 20.0]


# ---------------------------------------------------------------------------
# cycle 19: sub-microsecond timestamps are unreadable, never truncated
# ---------------------------------------------------------------------------


def test_c19_a_sub_microsecond_record_timestamp_is_unreadable_not_truncated(tmp_path):
    """Codex c18: fromisoformat truncated 00:00:01.0000009 to 00:00:01, pulling a reading taken
    AFTER the window end into the window. The writer never emits >6 fractional digits, so such a
    line is unreadable (fail-closed) rather than silently moved."""
    path, clock = _series(tmp_path, [10.0, 10.0])
    late = (T0 + STEP).isoformat().replace("+00:00", ".0000009+00:00")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": late, "rss_mib": 999.0, "container_id": CID}) + "\n")
    s = _window(path, clock, T0, T0 + STEP)
    assert s.peak_mib is None
    assert "canonical" in (s.sample.reason or "")


def test_c19_a_sub_microsecond_header_timestamp_is_unreadable(tmp_path):
    path, clock = _series(tmp_path, [10.0, 10.0])
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["started"] = T0.isoformat().replace("+00:00", ".1234567+00:00")
    path.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8")
    s = _window(path, clock, T0, T0 + STEP)
    assert s.peak_mib is None and "canonical" in (s.sample.reason or "")


@pytest.mark.parametrize("frac", ["", ".500000", ".123456"])
def test_c19_canonical_timestamps_still_parse(frac):
    ts = SM._parse_ts(T0.isoformat().replace("+00:00", f"{frac}+00:00"))
    assert ts.tzinfo is not None


@pytest.mark.parametrize("value", [
    "2026-09-25T22:00:01.0000009+00:00",      # sub-microsecond: truncated by fromisoformat
    "2026-09-25T22:00:01,1234567+00:00",
    "2026-09-25 22:00:01.1234567+00:00",      # space separator
    "20260925T220001.0000009+0000",           # compact (basic) form: no colons, still truncated
    "20260925T220001,0000009Z",
    "2026-W39-5T22:00:01+00:00",              # week date
    "2026-09-25T22:00:01Z",                   # exact, but not the form the writer emits
    "2026-09-25T22:00:01.000000+00:00",       # six zero digits: isoformat() drops them
    "2026-09-25T2200.5+00:00",
])
def test_c19_only_the_canonical_isoformat_form_is_accepted(value):
    """Codex c18/c19: fromisoformat accepts many ISO forms and silently truncates what it cannot
    hold; only the exact isoformat() round trip the writer emits is accepted."""
    with pytest.raises(ValueError, match="canonical"):
        SM._parse_ts(value)
