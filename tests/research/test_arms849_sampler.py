"""Tests for GTT ceiling sampling and the run-level FalkorDB cgroup series/report."""

from __future__ import annotations

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



# Canonical timestamps are shared by the cgroup writer, report, and ledger.

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


# ---------------------------------------------------------------------------
# WP03: host cgroup generation series and run-level graph-store report
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["Rss" + "Sampler", "RssRecord", "Rss" + "SeriesHeader", "Rss" + "SeriesWriter",
     "Rss" + "SeriesSampler"],
)
def test_retired_per_attempt_graph_store_rss_api_is_absent(name):
    assert not hasattr(SM, name)


def _fake_cgroup(root: pathlib.Path, value_mib: float, container_id: str = CID) -> pathlib.Path:
    memory = root / "system.slice" / f"docker-{container_id}.scope" / "memory.current"
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text(str(int(value_mib * 1024 ** 2)) + "\n", encoding="utf-8")
    return memory


def _generation(path: pathlib.Path, *, series_id: str = "generation-1", started: datetime = T0,
                container_id: str | None = CID, interval_s: float | None = 1.0,
                writer_status: str = "running", writer_reason: str | None = None) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "series_id": series_id,
        "path": f"/runs/{path.name}" if path else None,
        "container_id": container_id,
        "interval_s": interval_s,
        "started_ts": started.isoformat(),
        "writer_status": writer_status,
    }
    if writer_reason is not None:
        detail["writer_reason"] = writer_reason
    return {"record": "event", "kind": "series_generation", "detail": detail,
            "ts": started.isoformat()}


def _boundary(kind: str, when: datetime, *, series_id: str = "generation-1", **detail: Any) -> dict[str, Any]:
    return {"record": "event", "kind": kind,
            "detail": {"ts": when.isoformat(), "series_id": series_id, **detail},
            "ts": when.isoformat()}


def _write_generation(tmp_path: pathlib.Path, readings: list[tuple[datetime, float]], *,
                      series_id: str = "generation-1", started: datetime = T0,
                      closed: datetime | None = None, container_id: str = CID,
                      interval_s: float = 1.0) -> pathlib.Path:
    path = tmp_path / f"falkordb-cgroup-{series_id}.jsonl"
    header = SM.CgroupSeriesHeader(series_id, started, "arms849-falkordb-1", container_id, interval_s)
    trailer = SM.CgroupSeriesTrailer(closed or readings[-1][0], len(readings), 0)
    path.write_text(header.to_line()
                    + "".join(SM.CgroupRecord(ts, value, container_id).to_line()
                              for ts, value in readings)
                    + trailer.to_line(), encoding="utf-8")
    return path


def _write_huge_interval_generation(tmp_path: pathlib.Path, interval_s: float = 1e308) -> pathlib.Path:
    """A ledger-valid numeric interval whose report tolerance is not representable."""
    path = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    header = {"series": SM.CGROUP_SERIES_FORMAT, "series_id": "generation-1",
              "started": T0.isoformat(), "container": "arms849-falkordb-1",
              "container_id": CID, "interval_s": interval_s}
    path.write_text(json.dumps(header) + "\n" + SM.CgroupRecord(T0, 1.0, CID).to_line()
                    + SM.CgroupSeriesTrailer(T0, 1, 0).to_line(), encoding="utf-8")
    return path


def test_cgroup_reader_uses_the_full_id_scope_and_converts_bytes_to_mib(tmp_path):
    root = tmp_path / "cgroup"
    _fake_cgroup(root, 1.5)
    assert SM.cgroup_memory_mib(CID, cgroup_root=root) == pytest.approx(1.5)
    with pytest.raises(ValueError, match="full Docker container id"):
        SM.cgroup_memory_mib("../not-an-id", cgroup_root=root)


def test_cgroup_writer_is_exclusive_and_preserves_a_preexisting_file(tmp_path):
    path = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    path.write_bytes(b"do not replace\n")
    root = tmp_path / "cgroup"
    _fake_cgroup(root, 10.0)
    writer = SM.CgroupSeriesWriter(path, "generation-1", "arms849-falkordb-1",
                                   container_id=CID, started=T0, cgroup_root=root,
                                   clock=FakeClock(), sleep=lambda _: None)
    with pytest.raises(FileExistsError):
        writer.open()
    assert path.read_bytes() == b"do not replace\n"


def test_real_cgroup_writer_emits_bound_header_records_and_a_clean_trailer(tmp_path):
    root = tmp_path / "cgroup"
    memory = _fake_cgroup(root, 10.0)
    path = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    clock = FakeClock()
    writer = SM.CgroupSeriesWriter(path, "generation-1", "arms849-falkordb-1",
                                   container_id=CID, started=T0, cgroup_root=root,
                                   clock=clock, sleep=clock.sleep)
    writer.open()
    for n, value in enumerate((10.0, 20.0, 30.0, 40.0)):
        memory.write_text(str(int(value * 1024 ** 2)), encoding="utf-8")
        clock.set(T0 + n * STEP)
        writer.step()
    writer.close()

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert lines[0] == {"series": SM.CGROUP_SERIES_FORMAT, "series_id": "generation-1",
                        "started": T0.isoformat(), "container": "arms849-falkordb-1",
                        "container_id": CID, "interval_s": 1.0}
    assert [line["cgroup_mib"] for line in lines[1:-1]] == [10.0, 20.0, 30.0, 40.0]
    assert all(tuple(line) == SM.CGROUP_RECORD_FIELDS for line in lines[1:-1])
    assert lines[-1] == {"closed": (T0 + 3 * STEP).isoformat(), "readings": 4, "failures": 0}


def test_failed_cgroup_read_is_a_hole_and_is_counted_in_the_trailer(tmp_path):
    values = iter([10.0, RuntimeError("read failed"), 30.0])

    def read(_container_id: str) -> float:
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return value

    path = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    clock = FakeClock()
    writer = SM.CgroupSeriesWriter(path, "generation-1", "c", container_id=CID, started=T0,
                                   read=read, clock=clock, sleep=clock.sleep)
    writer.run(max_readings=3)
    writer.close()
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [line["ts"] for line in lines[1:-1]] == [T0.isoformat(), (T0 + 2 * STEP).isoformat()]
    assert lines[-1]["readings"] == 2 and lines[-1]["failures"] == 1


@pytest.mark.parametrize("value", [
    "2026-09-26T00:00:00+02:00",
    "2026-09-25T22:00:00",
    "2026-09-25T22:00:00Z",
    "2026-09-25T22:00:00.000000+00:00",
    "2026-09-25T22:00:00.0000001+00:00",
])
def test_wp03_series_timestamps_accept_only_the_writers_canonical_utc_form(value):
    with pytest.raises(ValueError):
        SM._parse_ts(value)


def test_graph_store_report_round_trips_the_real_writer_against_a_fake_cgroup(tmp_path):
    root = tmp_path / "cgroup"
    memory = _fake_cgroup(root, 10.0)
    path = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    clock = FakeClock()
    writer = SM.CgroupSeriesWriter(path, "generation-1", "arms849-falkordb-1",
                                   container_id=CID, started=T0, cgroup_root=root,
                                   clock=clock, sleep=clock.sleep)
    writer.open()
    for n, value in enumerate((10.0, 20.0, 30.0, 40.0)):
        memory.write_text(str(int(value * 1024 ** 2)), encoding="utf-8")
        clock.set(T0 + n * STEP)
        writer.step()
    writer.close()
    events = [
        _generation(path),
        _boundary("graph_store_first_build", T0 + STEP / 2, graphs_present=False),
        _boundary("graph_store_all_resident", T0 + STEP + STEP / 2, n_graphs=8),
    ]
    assert SM.graph_store_report(events, tmp_path) == {
        "baseline_mib": 10.0,
        "peak_mib": 40.0,
        "all_resident_mib": 30.0,
        "marginal_per_graph_mib": 2.5,
        "interval_s": 1.0,
        "series_ids": ["generation-1"],
        "source_series_ids": {
            "baseline_mib": ["generation-1"],
            "peak_mib": ["generation-1"],
            "all_resident_mib": ["generation-1"],
            "marginal_per_graph_mib": ["generation-1"],
            "interval_s": ["generation-1"],
        },
    }


@pytest.mark.parametrize(("delta", "expected"), [
    (5 * STEP, 1.0),
    (5 * STEP + EPS, "could_not_check: stale"),
])
def test_report_baseline_freshness_is_inclusive_at_exactly_five_intervals(tmp_path, delta, expected):
    path = _write_generation(tmp_path, [(T0, 1.0), (T0 + 6 * STEP, 2.0)],
                             closed=T0 + 6 * STEP)
    events = [_generation(path),
              _boundary("graph_store_first_build", T0 + delta, graphs_present=False)]
    assert SM.graph_store_report(events, tmp_path)["baseline_mib"] == expected


@pytest.mark.parametrize(("gap", "numeric"), [(5 * STEP, True), (5 * STEP + EPS, False)])
def test_report_internal_gap_boundary_is_exactly_five_intervals(tmp_path, gap, numeric):
    path = _write_generation(tmp_path, [(T0, 1.0), (T0 + gap, 9.0)], closed=T0 + gap)
    report = SM.graph_store_report([_generation(path)], tmp_path)
    assert (report["peak_mib"] == 9.0) if numeric else (report["peak_mib"] == "could_not_check: coverage")


@pytest.mark.parametrize(("tail", "numeric"), [(5 * STEP, True), (5 * STEP + EPS, False)])
def test_report_trailing_coverage_boundary_is_exactly_five_intervals(tmp_path, tail, numeric):
    path = _write_generation(tmp_path, [(T0, 1.0), (T0 + STEP, 9.0)], closed=T0 + STEP + tail)
    report = SM.graph_store_report([_generation(path)], tmp_path)
    assert (report["peak_mib"] == 9.0) if numeric else (report["peak_mib"] == "could_not_check: coverage")


def test_report_all_resident_requires_the_first_reading_strictly_after_the_event(tmp_path):
    path = _write_generation(tmp_path, [(T0, 99.0), (T0 + STEP, 20.0), (T0 + 2 * STEP, 30.0)])
    events = [_generation(path), _boundary("graph_store_all_resident", T0 + STEP, n_graphs=8)]
    assert SM.graph_store_report(events, tmp_path)["all_resident_mib"] == 30.0


def test_report_unavailable_conditions_are_honest_and_never_raise(tmp_path):
    absent = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    assert SM.graph_store_report([_generation(absent)], tmp_path)["peak_mib"] == "could_not_check: absent"

    wrong = _write_generation(tmp_path, [(T0, 1.0)], container_id="0" * 64)
    assert SM.graph_store_report([_generation(wrong)], tmp_path)["peak_mib"] == "could_not_check: wrong_container"

    gap = _write_generation(tmp_path, [(T0, 1.0), (T0 + 5 * STEP + EPS, 2.0)])
    assert SM.graph_store_report([_generation(gap)], tmp_path)["peak_mib"] == "could_not_check: coverage"

    stale = _write_generation(tmp_path, [(T0, 1.0)], closed=T0)
    events = [_generation(stale),
              _boundary("graph_store_first_build", T0 + 5 * STEP + EPS, graphs_present=False)]
    assert SM.graph_store_report(events, tmp_path)["baseline_mib"] == "could_not_check: stale"


def test_report_refuses_header_mismatch_missing_trailer_and_graphs_present(tmp_path):
    mismatch = _write_generation(tmp_path, [(T0, 1.0)], series_id="other")
    descriptor = _generation(mismatch, series_id="generation-1")
    assert SM.graph_store_report([descriptor], tmp_path)["peak_mib"] == "could_not_check: descriptor_mismatch"

    no_trailer = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    no_trailer.write_text(SM.CgroupSeriesHeader("generation-1", T0, "c", CID).to_line()
                          + SM.CgroupRecord(T0, 1.0, CID).to_line(), encoding="utf-8")
    no_trailer_report = SM.graph_store_report(
        [_generation(no_trailer),
         _boundary("graph_store_first_build", T0, graphs_present=False)], tmp_path)
    assert no_trailer_report["baseline_mib"] == 1.0
    assert no_trailer_report["peak_mib"] == "could_not_check: coverage"
    assert no_trailer_report["source_series_ids"]["peak_mib"] == ["generation-1"]

    complete = _write_generation(tmp_path, [(T0, 1.0)])
    events = [_generation(complete),
              _boundary("graph_store_first_build", T0, graphs_present=True)]
    assert SM.graph_store_report(events, tmp_path)["baseline_mib"] == "could_not_check: graphs_present"


def test_report_marks_a_failed_generation_without_guessing(tmp_path):
    failed = _generation(tmp_path / "none", container_id=None, interval_s=None,
                         writer_status="failed", writer_reason="inspect failed")
    report = SM.graph_store_report([failed], tmp_path)
    assert report["baseline_mib"] == report["peak_mib"] == "could_not_check: writer_failed"
    assert report["source_series_ids"]["peak_mib"] == ["generation-1"]
    assert report["source_series_ids"]["interval_s"] == ["generation-1"]


def test_resume_keeps_first_baseline_and_prior_all_resident_when_later_generation_has_no_event(tmp_path):
    one = _write_generation(tmp_path, [(T0, 1.0), (T0 + STEP, 1.0)], series_id="one")
    two = _write_generation(tmp_path, [(T0, 2.0), (T0 + STEP, 9.0)], series_id="two")
    events = [
        _generation(one, series_id="one"),
        _boundary("graph_store_first_build", T0, series_id="one", graphs_present=False),
        _boundary("graph_store_all_resident", T0 + STEP / 2, series_id="one", n_graphs=8),
        _generation(two, series_id="two"),
        _boundary("graph_store_first_build", T0, series_id="two", graphs_present=False),
    ]
    report = SM.graph_store_report(events, tmp_path)
    assert report["baseline_mib"] == report["all_resident_mib"] == 1.0
    assert report["marginal_per_graph_mib"] == 0.0
    assert report["interval_s"] == 1.0 and report["peak_mib"] == 9.0
    assert report["source_series_ids"] == {
        "baseline_mib": ["one"], "peak_mib": ["one", "two"], "all_resident_mib": ["one"],
        "marginal_per_graph_mib": ["one"], "interval_s": ["one", "two"],
    }


def test_resume_does_not_take_a_later_generations_first_build_as_the_baseline(tmp_path):
    one = _write_generation(tmp_path, [(T0, 10.0)], series_id="one")
    two = _write_generation(tmp_path, [(T0, 20.0)], series_id="two")
    events = [
        _generation(one, series_id="one"),
        _generation(two, series_id="two"),
        _boundary("graph_store_first_build", T0, series_id="two", graphs_present=False),
    ]
    report = SM.graph_store_report(events, tmp_path)
    assert report["baseline_mib"] == "could_not_check: missing_first_build"
    assert report["source_series_ids"]["baseline_mib"] == ["one"]


def test_later_all_resident_generation_cannot_be_combined_with_first_generation_baseline(tmp_path):
    one = _write_generation(tmp_path, [(T0, 10.0)], series_id="one")
    two = _write_generation(tmp_path, [(T0, 100.0), (T0 + STEP, 200.0)], series_id="two")
    events = [
        _generation(one, series_id="one"),
        _boundary("graph_store_first_build", T0, series_id="one", graphs_present=False),
        _generation(two, series_id="two"),
        _boundary("graph_store_first_build", T0, series_id="two", graphs_present=False),
        _boundary("graph_store_all_resident", T0 + STEP / 2, series_id="two", n_graphs=8),
    ]
    report = SM.graph_store_report(events, tmp_path)
    assert report["baseline_mib"] == 10.0 and report["all_resident_mib"] == 200.0
    assert report["marginal_per_graph_mib"] == "could_not_check: different_generation"
    assert report["source_series_ids"]["baseline_mib"] == ["one"]
    assert report["source_series_ids"]["all_resident_mib"] == ["two"]
    assert report["source_series_ids"]["marginal_per_graph_mib"] == ["one", "two"]


def test_scalar_selection_never_cherry_picks_a_later_favourable_generation(tmp_path):
    one = _write_generation(tmp_path, [(T0, 10.0)], series_id="one")
    two = _write_generation(tmp_path, [(T0, 20.0), (T0 + STEP, 30.0)], series_id="two")
    events = [
        _generation(one, series_id="one"),
        _boundary("graph_store_first_build", T0, series_id="one", graphs_present=True),
        _boundary("graph_store_all_resident", T0 + 6 * STEP, series_id="one", n_graphs=8),
        _generation(two, series_id="two"),
        _boundary("graph_store_first_build", T0, series_id="two", graphs_present=False),
        _boundary("graph_store_all_resident", T0 + STEP / 2, series_id="two", n_graphs=8),
    ]
    report = SM.graph_store_report(events, tmp_path)
    assert report["baseline_mib"] == "could_not_check: graphs_present"
    assert report["all_resident_mib"] == "could_not_check: stale"
    assert report["source_series_ids"]["baseline_mib"] == ["one"]
    assert report["source_series_ids"]["all_resident_mib"] == ["one"]


def test_interval_consensus_and_peak_tie_provenance_follow_ledger_order(tmp_path):
    one = _write_generation(tmp_path, [(T0, 99.0)], series_id="one", interval_s=1.0)
    two = _write_generation(tmp_path, [(T0, 99.0)], series_id="two", interval_s=2.0)
    report = SM.graph_store_report(
        [_generation(one, series_id="one", interval_s=1.0),
         _generation(two, series_id="two", interval_s=2.0)], tmp_path)
    assert report["interval_s"] == "could_not_check: mixed_intervals"
    assert report["source_series_ids"]["interval_s"] == ["one", "two"]
    assert report["peak_mib"] == 99.0
    assert report["source_series_ids"]["peak_mib"] == ["one", "two"]


@pytest.mark.parametrize("interval_s", [1e308, 2e13])
def test_report_reduces_an_unrepresentable_interval_to_could_not_check(tmp_path, interval_s):
    path = _write_huge_interval_generation(tmp_path, interval_s)
    report = SM.graph_store_report([_generation(path, interval_s=interval_s)], tmp_path)
    assert report["peak_mib"] == "could_not_check: invalid_interval"
    assert report["interval_s"] == "could_not_check: invalid_interval"
    assert report["source_series_ids"]["peak_mib"] == ["generation-1"]
    assert report["source_series_ids"]["interval_s"] == ["generation-1"]


def test_series_id_is_a_safe_filename_token_and_cannot_traverse(tmp_path):
    unsafe = "../outside"
    with pytest.raises(ValueError, match="safe filename token"):
        SM.CgroupSeriesHeader(unsafe, T0, "c", CID).to_line()
    detail = _generation(tmp_path / "outside", series_id=unsafe)["detail"]
    detail["path"] = f"/runs/falkordb-cgroup-{unsafe}.jsonl"
    report = SM.graph_store_report(
        [{"record": "event", "kind": "series_generation", "detail": detail}], tmp_path)
    assert report["peak_mib"] == "could_not_check: unsafe_series_id"


def test_report_refuses_a_symlink_even_when_it_names_a_valid_series(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    target_dir = tmp_path / "elsewhere"
    target_dir.mkdir()
    target = _write_generation(target_dir, [(T0, 99.0)])
    link = runs / target.name
    link.symlink_to(target)
    report = SM.graph_store_report([_generation(link)], runs)
    assert report["peak_mib"] == "could_not_check: unsafe_path"


@pytest.mark.parametrize("series_bytes, interval_s, reason", [
    (b"not json\n", 1.0, "malformed"),
    (None, 1e308, "invalid_interval"),
    (None, 2e13, "invalid_interval"),
])
def test_report_failures_are_observational_through_summary_admin_and_export(
        tmp_path, series_bytes, interval_s, reason):
    from scripts.research.arms849 import grading
    from scripts.research.arms849 import ledger as ledger_mod
    from tests.research.test_arms849_ledger import SID, binding, ok_row, rec

    ledger_path = tmp_path / "ledger.jsonl"
    series_path = tmp_path / "falkordb-cgroup-generation-1.jsonl"
    if series_bytes is None:
        _write_huge_interval_generation(tmp_path, interval_s)
    else:
        series_path.write_bytes(series_bytes)
    detail = _generation(series_path, interval_s=interval_s)["detail"]
    with ledger_mod.open_ledger(ledger_path, binding(), blinding_seed=7, plan=72) as ledger:
        ledger.event("session_gates", {"session_id": SID, "passed": True, "skipped": False})
        key = ledger_mod.RunKey("G", "C1", 1)
        ledger.begin_attempt(key, SID)
        rec(ledger, key, "ok", ok_row())
        runs_before = ledger.run_rows()
        terminal_before = ledger.terminal(key)
        completeness_before = grading.is_complete(ledger)
        cell_before = ledger.summarise()["G", "C1"]

        ledger.event("series_generation", detail)

        summary = ledger.summarise()
        assert summary["G", "C1"] == cell_before
        assert summary.graph_store["peak_mib"] == f"could_not_check: {reason}"
        assert ledger.run_rows() == runs_before
        assert ledger.terminal(key) == terminal_before == "ok"
        assert grading.is_complete(ledger) == completeness_before

        admin = grading._admin(ledger, ledger_path.stem)
        assert len(admin["non_scored"]) == 71
        assert {cell["outcome"] for cell in admin["non_scored"]} == {None}
        assert admin["graph_store"]["peak_mib"] == f"could_not_check: {reason}"

        with pytest.raises(grading.ExportRefused, match="ledger incomplete"):
            grading.export(ledger, 7, tmp_path / "export")
    assert not (tmp_path / "export").exists()
