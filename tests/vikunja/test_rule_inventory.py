"""Tests for ``scripts.vikunja.rule_inventory`` (WP10, #1111).

Synthetic sqlite snapshots are built in ``tmp_path``; Vikunja is a stateful
fake behind ``urllib.request.urlopen`` (the shared ``mock_vikunja_urlopen``
fixture is single-scenario, and these flows need per-task state). Task bodies
come from the WP01 v2 factory. No live DB, snapshot or network is touched.
"""
from __future__ import annotations

import copy
import io
import json
import re
import sqlite3
import stat
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self

import pytest

from scripts.common.vikunja_client import VikunjaClient
from scripts.common.vikunja_rule import parts_to_rrule_text, rrule_text_to_parts
from scripts.vikunja import rule_inventory as inv
from scripts.vikunja.rule_inventory import Baseline, classify
from tests.common.vikunja_v2_factory import make_task, strip_rule

BASE = "https://vikunja.test/api/v1"
TOKEN = "test-token-never-printed"
_PATH = re.compile(r"/api/v2/tasks/(\d+)$")


# ---------------------------------------------------------------------------
# Stateful fake Vikunja (shared with test_rule_repair.py)
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._buf = io.BytesIO(body)
        self.status = status

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._buf.close()


class FakeVikunja:
    """In-memory v2 task store with request recording and per-call hooks.

    ``hooks`` maps a 1-based request index or ``("PATCH", n)`` (the n-th
    PATCH) to a callable run before the request is served; it may raise.
    """

    def __init__(self, tasks: list[dict[str, Any]]) -> None:
        self.tasks = {t["id"]: copy.deepcopy(t) for t in tasks}
        self.calls: list[tuple[str, int, Any]] = []
        self.hooks: dict[Any, Callable[[], None]] = {}
        self._tick = 0

    @property
    def methods(self) -> list[str]:
        return [m for m, _, _ in self.calls]

    @property
    def patches(self) -> list[dict[str, Any]]:
        return [b for m, _, b in self.calls if m == "PATCH"]

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _Resp:
        match = _PATH.search(req.full_url)
        assert match, req.full_url
        task_id = int(match.group(1))
        body = json.loads(req.data) if req.data else None
        method = req.get_method()
        self.calls.append((method, task_id, body))
        n_patch = self.methods.count("PATCH")
        for key in (len(self.calls), (method, n_patch) if method == "PATCH" else None):
            hook = self.hooks.pop(key, None) if key is not None else None
            if hook is not None:
                hook()
        task = self.tasks.get(task_id)
        if task is None:
            raise urllib.error.HTTPError(req.full_url, 404, "nf", None,  # type: ignore[arg-type]
                                         io.BytesIO(b"{}"))
        if method == "PATCH":
            self._patch(task, body)
        return _Resp(json.dumps(task).encode())

    def _patch(self, task: dict[str, Any], body: dict[str, Any]) -> None:
        for key, value in body.items():
            if key == "repeat" and value is None:
                task["repeat"] = None
                task.pop("repeats_rrule", None)
            elif key == "repeats_rrule":
                parts = rrule_text_to_parts(value)
                task["repeat"] = parts
                task["repeats_rrule"] = parts_to_rrule_text(parts)
            else:
                task[key] = value
        self._tick += 1
        task["updated"] = f"2026-11-21T00:00:{self._tick:02d}Z"


def timeout_error() -> None:
    raise TimeoutError("simulated")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[dict[str, Any]]], FakeVikunja]:
    def install(tasks: list[dict[str, Any]]) -> FakeVikunja:
        server = FakeVikunja(tasks)
        monkeypatch.setattr("urllib.request.urlopen", server)
        return server

    return install


def client() -> VikunjaClient:
    return VikunjaClient(base_url=BASE, token=TOKEN)


def make_snapshot_db(
    path: Path,
    rows: list[tuple[int, str | None, int]],
    *,
    columns: tuple[str, str] = ("repeats", "repeats_from_current_date"),
) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        f"CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, {columns[0]} TEXT, "
        f"{columns[1]} INTEGER, created_by_id INTEGER)"
    )
    conn.executemany(
        f"INSERT INTO tasks (id, title, {columns[0]}, {columns[1]}) VALUES (?, 'PRIVATE', ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return path


def run_inventory(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict, str]:
    code = inv.main(argv, client=client())
    out = capsys.readouterr().out
    return code, json.loads(out.strip().splitlines()[-1]), out


DAILY = "FREQ=DAILY;INTERVAL=1"
COUNT5 = "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO;COUNT=5"
UNTIL = "FREQ=DAILY;INTERVAL=1;UNTIL=20261201T000000Z"
FELIX_AT = "2026-11-19T11:59:30Z"


def _b(text: str, from_current: bool = False) -> Baseline:
    return Baseline(text, from_current, "snapshot:/tmp")


# ---------------------------------------------------------------------------
# classify (pure)
# ---------------------------------------------------------------------------


class TestClassify:
    def test_ok(self) -> None:
        assert classify(_b(DAILY), make_task())[0] == "ok"

    def test_progressed_lower_count(self) -> None:
        live = make_task(repeat=rrule_text_to_parts(COUNT5.replace("COUNT=5", "COUNT=3")))
        assert classify(_b(COUNT5), live)[0] == "progressed"

    def test_higher_count_is_changed(self) -> None:
        live = make_task(repeat=rrule_text_to_parts(COUNT5.replace("COUNT=5", "COUNT=7")))
        assert classify(_b(COUNT5), live)[0] == "changed"

    def test_ended_count_exhausted(self) -> None:
        live = make_task(repeat=None, done=True)
        assert classify(_b(COUNT5), live)[0] == "ended"

    def test_ended_count_exhausted_even_if_seeded_and_attributed(self) -> None:
        """Ordering (re-review new-HIGH 2): normal end before the seed override."""
        live = make_task(repeat=None, done=True)
        status = classify(_b(COUNT5), live, attribution=[FELIX_AT], seeded_no_rule=True)[0]
        assert status == "ended"

    def test_until_rule_kept_done_is_not_damage(self) -> None:
        live = make_task(repeat=rrule_text_to_parts(UNTIL), done=True)
        assert classify(_b(UNTIL), live)[0] in {"ok", "ended"}

    def test_until_rule_gone_is_removed_never_lost(self) -> None:
        live = make_task(repeat=None, done=True)
        assert classify(_b(UNTIL), live, attribution=[FELIX_AT])[0] == "removed"

    def test_seeded_finite_open_is_removed_not_lost(self) -> None:
        live = make_task(repeat=None)
        status = classify(_b(COUNT5), live, attribution=[FELIX_AT], seeded_no_rule=True)[0]
        assert status == "removed"

    def test_lost_needs_attribution(self) -> None:
        live = strip_rule(make_task())
        assert classify(_b(DAILY), live, attribution=[FELIX_AT])[0] == "lost"
        assert classify(_b(DAILY), live)[0] == "removed"

    def test_lost_with_seed_and_attribution(self) -> None:
        live = strip_rule(make_task())
        assert classify(_b(DAILY), live, attribution=[FELIX_AT], seeded_no_rule=True)[0] == "lost"

    def test_changed_rule(self) -> None:
        live = make_task(repeat={"freq": "weekly", "interval": 1})
        assert classify(_b(DAILY), live)[0] == "changed"

    def test_same_rule_different_flag_is_changed(self) -> None:
        live = make_task(repeats_from_current_date=True)
        assert classify(_b(DAILY), live)[0] == "changed"

    @pytest.mark.parametrize(
        "text",
        [
            "FREQ=DAILY;UNTIL=20261231",  # date-only UNTIL
            "FREQ=DAILY;UNTIL=20261231T235959",  # floating UNTIL
            "garbage",
            "DTSTART:20261001T000000Z\nRRULE:FREQ=DAILY",
        ],
    )
    def test_unparseable_rule_is_unresolved_not_crash(self, text: str) -> None:
        status, _, proposed = classify(_b(text), strip_rule(make_task()), attribution=[FELIX_AT])
        assert status == "unresolved"
        assert proposed is None

    def test_deleted(self) -> None:
        assert classify(_b(DAILY), None)[0] == "deleted"

    def test_proposed_restore_is_canonical(self) -> None:
        _, _, proposed = classify(_b("rrule:freq=daily;interval=1", True), make_task())
        assert proposed == {"repeats_rrule": DAILY, "repeats_from_current_date": True}


# ---------------------------------------------------------------------------
# Baseline DB
# ---------------------------------------------------------------------------


class TestBaselinePath:
    @pytest.mark.parametrize(
        "raw",
        [
            "/data/services/vikunja/data/vikunja.db",
            "/data/services/vikunja/data/other.db",
            "/data/services/vikunja/data/../data/vikunja.db",
            "/data/services/vikunja/snapshots/20261030T081520Z/vikunja.db",
        ],
    )
    def test_refuses_live_and_original_paths(self, raw: str) -> None:
        with pytest.raises(inv.RefusedPath):
            inv.check_baseline_path(raw)

    def test_refuses_symlink_to_live_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        live_dir = tmp_path / "live"
        live_dir.mkdir()
        (live_dir / "vikunja.db").write_bytes(b"")
        monkeypatch.setattr(inv, "LIVE_DATA_DIR", live_dir)
        monkeypatch.setattr(inv, "LIVE_DB_PATH", live_dir / "vikunja.db")
        link = tmp_path / "copy.db"
        link.symlink_to(live_dir / "vikunja.db")
        with pytest.raises(inv.RefusedPath):
            inv.check_baseline_path(link)

    def test_cli_refuses_live_path_exit_2_no_calls(
        self, tmp_path: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server = fake([])
        code, summary, _ = run_inventory(
            ["--baseline-db", "/data/services/vikunja/data/vikunja.db",
             "--out", str(tmp_path / "o.json")],
            capsys,
        )
        assert code == 2 and summary["ok"] is False
        assert server.calls == []
        assert not (tmp_path / "o.json").exists()


class TestReadBaseline:
    def test_pragma_discovers_columns_and_reads_rule_columns(self, tmp_path: Path) -> None:
        db = make_snapshot_db(tmp_path / "s.db", [(1, DAILY, 0), (2, "", 0), (3, None, 1)])
        rows, columns = inv.read_baseline(db)
        assert {"id", "repeats", "repeats_from_current_date"} <= set(columns)
        assert rows == {1: (DAILY, False), 2: (None, False), 3: (None, True)}

    def test_discover_columns_uses_pragma(self, tmp_path: Path) -> None:
        db = make_snapshot_db(tmp_path / "s.db", [])
        conn = sqlite3.connect(db)
        try:
            assert inv.discover_columns(conn)[:3] == ["id", "title", "repeats"]
        finally:
            conn.close()

    def test_legacy_columns_refused_with_names(self, tmp_path: Path) -> None:
        db = make_snapshot_db(
            tmp_path / "s.db", [(1, "86400", 0)], columns=("repeat_after", "repeat_mode")
        )
        with pytest.raises(ValueError, match="repeat_after"):
            inv.read_baseline(db)

    def test_opened_read_only(self, tmp_path: Path) -> None:
        db = make_snapshot_db(tmp_path / "s.db", [(1, DAILY, 0)])
        before = db.read_bytes()
        db.chmod(0o400)
        rows, _ = inv.read_baseline(db)
        assert rows[1] == (DAILY, False)
        assert db.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == ["s.db"]

    def test_missing_file_is_not_created(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            inv.read_baseline(tmp_path / "absent.db")
        assert not (tmp_path / "absent.db").exists()


# ---------------------------------------------------------------------------
# Second sources
# ---------------------------------------------------------------------------


class TestSeedLedger:
    def test_duplicates_and_malformed_lines_tolerated(self, tmp_path: Path) -> None:
        ledger = tmp_path / "seed-ledger.jsonl"
        row = {"cycle_id": "c1", "task_id": 7, "field": "repeat", "seeded_value": None,
               "at": "2026-11-20T00:00:00Z"}
        ledger.write_text(
            json.dumps(row) + "\n"
            + json.dumps({**row, "cycle_id": "c2"}) + "\n"  # retried cycle duplicate
            + "{not json\n"
            + json.dumps({"task_id": "x", "field": "repeat"}) + "\n"
            + "[1, 2]\n"
            + json.dumps({"task_id": 8, "field": "repeat", "seeded_value": {"freq": "daily"}})
            + "\n"
        )
        seeds, stats = inv.load_seed_ledger(ledger)
        assert stats == {"rows": 3, "skipped_lines": 3}
        assert seeds[7].rows == 2 and seeds[7].seeded_no_rule is True
        assert seeds[8].seeded_no_rule is False

    @pytest.mark.parametrize("bad", ["bad", [1], 7, True, {"freq": ["x"]}])
    def test_malformed_seeded_value_skipped_not_crash(self, tmp_path: Path, bad: Any) -> None:
        ledger = tmp_path / "seed-ledger.jsonl"
        good = {"task_id": 7, "field": "repeat", "seeded_value": None}
        ledger.write_text(json.dumps({"task_id": 9, "field": "repeat", "seeded_value": bad})
                          + "\n" + json.dumps(good) + "\n")
        seeds, stats = inv.load_seed_ledger(ledger)
        assert stats == {"rows": 1, "skipped_lines": 1}
        assert set(seeds) == {7}


def _jsonl(path: Path, records: list[Any]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


T = "2026-11-19T12:00:00Z"


def _sweeper_tick(**overrides: Any) -> dict[str, Any]:
    """A sweeper-ledger line in the real SweeperTickRecord.to_dict() shape."""
    tick: dict[str, Any] = {
        "schema_version": 1, "tick_id": "01TICK", "started_at_utc": T, "duration_ms": 900,
        "dry_run": False, "expired_checkin_dates_evaluated": ["2026-11-18"],
        "habits_evaluated": [], "habits_auto_skipped": [], "errors": [],
        "exit_status": "success",
    }
    tick.update(overrides)
    return tick


class TestFelixLogs:
    """Only successful, non-dry-run writes that changed the task attribute (review 1)."""

    def test_sweeper_day_specific_auto_skip_counts(self, tmp_path: Path) -> None:
        ledger = _jsonl(tmp_path / "sweeper-ledger.jsonl", [_sweeper_tick(
            habits_auto_skipped=[{"task_id": 75, "original_checkin_date_et": "2026-11-18",
                                  "original_designated_weekday": "Mon",
                                  "new_due_date_et": "2026-11-23T23:59:59-05:00"}])])
        writes, _ = inv.load_felix_writes([ledger])
        assert set(writes) == {75}

    @pytest.mark.parametrize(
        "tick",
        [
            # dry run: no PUT was sent
            _sweeper_tick(dry_run=True, habits_auto_skipped=[
                {"task_id": 75, "new_due_date_et": "2026-11-23T23:59:59-05:00"}]),
            # evaluation only (the reviewer's probe): already_resolved
            _sweeper_tick(habits_evaluated=[{"task_id": 18, "status": "already_resolved",
                                             "original_checkin_date_et": "2026-11-18"}]),
            # daily habit auto-skip: the sweeper does not write Vikunja for it
            _sweeper_tick(habits_auto_skipped=[{"task_id": 18,
                                                "original_checkin_date_et": "2026-11-18",
                                                "original_designated_weekday": None}]),
            # the PUT failed: the task is listed in errors
            _sweeper_tick(habits_auto_skipped=[
                {"task_id": 75, "new_due_date_et": "2026-11-23T23:59:59-05:00"}],
                errors=[{"task_id": 75, "error_type": "vikunja_put", "error_message": "x"}]),
            # dry_run missing or not a bool: not provably a live write
            {k: v for k, v in _sweeper_tick(habits_auto_skipped=[
                {"task_id": 75, "new_due_date_et": "2026-11-23T23:59:59-05:00"}]).items()
             if k != "dry_run"},
        ],
    )
    def test_sweeper_non_writes_never_attribute(self, tmp_path: Path, tick: dict) -> None:
        writes, _ = inv.load_felix_writes([_jsonl(tmp_path / "sweeper-ledger.jsonl", [tick])])
        assert writes == {}

    def test_habits_history_completion_counts_events_do_not(self, tmp_path: Path) -> None:
        history = _jsonl(tmp_path / "habits-history.jsonl", [
            {"domain": "habits", "task_id": 14, "title": "Wake at 5:00 AM",
             "date": "2026-11-19", "state": "complete", "source": "whatsapp", "timestamp": T},
            {"event_type": "auto_skipped", "task_id": 15, "recorded_at_utc": T,
             "tick_id": "01TICK", "original_checkin_date_et": "2026-11-18"},
            {"event_type": "task_deleted", "task_id": 16, "recorded_at_utc": T},
            {"domain": "habits", "task_id": 18, "state": "complete", "source": "whatsapp",
             "timestamp": "2026-10-01T12:00:00Z"},  # before the cutover
            {"domain": "habits", "task_id": 19, "state": "bogus", "source": "whatsapp",
             "timestamp": T},
        ])
        writes, _ = inv.load_felix_writes([history])
        assert set(writes) == {14}

    def test_escalation_only_agent_done_and_rescheduled(self, tmp_path: Path) -> None:
        esc = tmp_path / "escalation"
        esc.mkdir()
        _jsonl(esc / "project-2-escalation-history.jsonl", [
            {"domain": "escalation", "task_id": t, "project_id": 2, "title": "x",
             "date": "2026-11-19", "state": s, "source": src, "timestamp": T, "note": None}
            for t, s, src in [(1, "done", "kent_reply"), (2, "rescheduled", "kent_reply"),
                              (6, "done", "agent"), (3, "level_sent", "agent"),
                              (4, "snoozed", "kent_reply"), (5, "dismissed", "kent_reply")]
        ])
        writes, _ = inv.load_felix_writes([esc])
        assert set(writes) == {1, 2, 6}

    def test_escalation_reconcile_synthetic_rows_not_attribution(self, tmp_path: Path) -> None:
        """Real shapes from scripts/escalation/reconcile_completions.py (L895-915,
        L1004-1014, L1064-1078): appended via record_event(skip_vikunja=True)."""
        esc = tmp_path / "escalation"
        esc.mkdir()
        _jsonl(esc / "project-2-escalation-history.jsonl", [
            {"domain": "escalation", "task_id": 1, "project_id": 2, "title": "t",
             "date": "2026-11-19", "state": "done", "source": "reconcile", "timestamp": T,
             "note": "Synthesized by reconcile: Vikunja done=true, no JSONL done record."},
            {"domain": "escalation", "task_id": 2, "project_id": 2, "title": "t",
             "date": "2026-11-19", "state": "rescheduled", "source": "reconcile",
             "timestamp": T, "note": "Synthesized by reconcile: Vikunja due_date ...",
             "reschedule_to": "2026-11-25T04:59:59Z"},
            {"domain": "escalation", "task_id": 3, "project_id": 2, "title": "t",
             "date": "2026-11-19", "state": "dismissed", "source": "reconcile",
             "reason": "task_deleted_in_vikunja (detected_at_utc=...)", "timestamp": T},
            # operator/backfill sources append JSONL by hand or with --no-vikunja
            {"domain": "escalation", "task_id": 4, "project_id": 2, "state": "done",
             "source": "operator_repair", "timestamp": T, "note": "manual triage"},
            {"domain": "escalation", "task_id": 5, "project_id": 2, "state": "done",
             "source": "backfill", "timestamp": T},
            {"domain": "escalation", "task_id": 7, "project_id": 2, "state": "done",
             "timestamp": T},  # no source: no positive provenance
        ])
        writes, _ = inv.load_felix_writes([esc])
        assert writes == {}

    def test_habits_ui_reconcile_and_backfill_rows_not_attribution(self, tmp_path: Path) -> None:
        """Real shapes: scripts/habits/reconcile_completions.py L202-210 (vikunja-ui,
        Kent ticked the task in the UI; JSONL only) and
        scripts/habits/backfill_jsonl_from_comments.py (historical-backfill)."""
        history = _jsonl(tmp_path / "habits-history.jsonl", [
            {"domain": "habits", "task_id": 14, "title": "Wake at 5:00 AM",
             "date": "2026-11-19", "state": "complete", "source": "vikunja-ui", "timestamp": T},
            {"domain": "habits", "task_id": 15, "title": "Meditate", "date": "2026-11-19",
             "state": "complete", "source": "historical-backfill", "timestamp": T},
            {"domain": "habits", "task_id": 16, "date": "2026-11-19", "state": "complete",
             "source": "reconcile", "timestamp": T},
            {"domain": "habits", "task_id": 18, "date": "2026-11-19", "state": "complete",
             "timestamp": T},  # no source
        ])
        writes, _ = inv.load_felix_writes([history])
        assert writes == {}

    def test_intake_only_executed_done_write(self, tmp_path: Path) -> None:
        """``applied`` records the *requested* project/due even when unchanged
        (scripts/intake/apply_reply.py _plan_line L593-627); only ``done`` is set
        together with a task-body ``field_changes`` entry. Historical records carry
        no field_changes, so project/due are ambiguous and not attribution."""
        eod = "2026-11-20T04:59:59Z"
        intake = _jsonl(tmp_path / "intake-apply-2026-11-19.jsonl", [
            {"applied_at_utc": T, "digest_id": "d", "line": n, "task_id": t, "status": s,
             "applied": a, "notes": [], "understood": {}, "failed": []}
            for n, (t, s, a) in enumerate([
                (1, "applied", {"labels": ["q:eliminate"], "done": True}),
                # label change with unchanged project and due: zero task-body writes
                (2, "applied", {"labels": ["q:do"], "project": "Work", "due_date": eod}),
                (3, "applied", {"project": "Work"}),
                (4, "applied", {"due_date": eod}),
                (5, "applied", {"labels": ["f:2"]}),
                (6, "noop", {"project": "Work"}),
                (7, "failed", {"done": True}),
                (8, "already_done", {}),
                (9, "overload_flagged", {"labels": ["f:4-overload"]}),
                (10, "applied", {"done": "yes"}),
            ])
        ])
        writes, _ = inv.load_felix_writes([intake])
        assert set(writes) == {1}

    def test_unrecognised_files_and_records_are_not_attribution(self, tmp_path: Path) -> None:
        other = _jsonl(tmp_path / "something-else.jsonl",
                       [{"task_id": 14, "timestamp": T, "state": "done", "domain": "escalation"}])
        bare = _jsonl(tmp_path / "habits-history.jsonl", [{"task_id": 15, "timestamp": T}])
        writes, stats = inv.load_felix_writes([other, bare])
        assert writes == {}
        assert stats["unrecognised_files"] == 1

    def test_malformed_lines_and_missing_paths_counted(self, tmp_path: Path) -> None:
        history = tmp_path / "habits-history.jsonl"
        history.write_text("garbage\n[1]\n" + json.dumps(
            {"domain": "habits", "task_id": 14, "state": "complete", "source": "whatsapp",
             "timestamp": T}) + "\n")
        writes, stats = inv.load_felix_writes([history, tmp_path / "missing"])
        assert set(writes) == {14}
        assert stats["skipped_lines"] == 1 and stats["missing_paths"] == 1

    def test_schedule_second_source(self, tmp_path: Path) -> None:
        sched = tmp_path / "s.yaml"
        sched.write_text(
            "habits:\n  - task_id: 14\n    rrule: FREQ=DAILY;INTERVAL=1\n"
            "  - task_id: 15\n    repeat_after_seconds: 86400\n"
        )
        assert inv.load_schedule(sched) == {14: DAILY}


# ---------------------------------------------------------------------------
# CLI end to end
# ---------------------------------------------------------------------------


def _scenario(tmp_path: Path) -> tuple[Path, list[dict[str, Any]], Path, Path, Path]:
    rows = [
        (14, DAILY, 0),  # ok
        (15, COUNT5, 0),  # progressed
        (16, COUNT5, 0),  # ended (COUNT exhausted) though seeded no-rule + attributed
        (18, DAILY, 0),  # lost (attributed)
        (19, DAILY, 0),  # removed (no attribution)
        (20, DAILY, 0),  # changed
        (21, "FREQ=DAILY;UNTIL=20261231", 0),  # unresolved (date-only UNTIL)
        (22, DAILY, 0),  # deleted
        (30, None, 0),  # no rule, not a candidate
        (65, None, 0),  # no rule in DB but in the schedule
    ]
    db = make_snapshot_db(tmp_path / "copy.db", rows)
    updated = "2026-11-19T12:00:30Z"
    tasks = [
        make_task(id=14),
        make_task(id=15, repeat=rrule_text_to_parts(COUNT5.replace("COUNT=5", "COUNT=4"))),
        make_task(id=16, repeat=None, done=True, updated=updated),
        strip_rule(make_task(id=18, updated=updated)),
        strip_rule(make_task(id=19, updated=updated)),
        make_task(id=20, repeat={"freq": "weekly", "interval": 2}),
        strip_rule(make_task(id=21, updated=updated)),
        make_task(id=30, repeat=None, title="Secret private task"),
        strip_rule(make_task(id=65, updated=updated, title="Morning hip PT")),
    ]
    logs = tmp_path / "habits"
    logs.mkdir()
    (logs / "habits-history.jsonl").write_text(
        "".join(json.dumps({"domain": "habits", "task_id": t, "state": "complete",
                            "source": "whatsapp",
                            "timestamp": "2026-11-19T12:00:00Z"}) + "\n"
                for t in (16, 18, 21, 65))
    )
    ledger = tmp_path / "seed-ledger.jsonl"
    row = {"task_id": 16, "field": "repeat", "seeded_value": None, "cycle_id": "c"}
    ledger.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
    sched = tmp_path / "sched.yaml"
    sched.write_text("habits:\n  - task_id: 65\n    rrule: FREQ=DAILY;INTERVAL=1\n")
    return db, tasks, logs, ledger, sched


class TestCli:
    def test_end_to_end_statuses_get_only_private_out(
        self, tmp_path: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db, tasks, logs, ledger, sched = _scenario(tmp_path)
        server = fake(tasks)
        out = tmp_path / "private" / "inventory.json"
        code, summary, stdout = run_inventory(
            ["--baseline-db", str(db), "--schedule-path", str(sched),
             "--felix-logs", str(logs), "--seed-ledger", str(ledger), "--out", str(out)],
            capsys,
        )
        assert code == 0, stdout
        assert set(server.methods) == {"GET"}  # zero write calls
        assert 30 not in [tid for _, tid, _ in server.calls]
        doc = json.loads(out.read_text())
        status = {e["task_id"]: e["status"] for e in doc["entries"]}
        assert status == {14: "ok", 15: "progressed", 16: "ended", 18: "lost", 19: "removed",
                          20: "changed", 21: "unresolved", 22: "deleted", 65: "lost"}
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
        assert summary["ok"] is True and summary["checked"] == 9
        assert (summary["lost"], summary["ended"], summary["removed"]) == (2, 1, 1)
        assert summary["ids"]["lost"] == [18, 65]
        assert summary["out"] == str(out)
        entry65 = next(e for e in doc["entries"] if e["task_id"] == 65)
        assert entry65["baseline_source"] == "schedule"
        entry18 = next(e for e in doc["entries"] if e["task_id"] == 18)
        assert entry18["current_fingerprint"]["updated"] == "2026-11-19T12:00:30Z"
        assert set(entry18["current_fingerprint"]) == set(inv.FINGERPRINT_FIELDS)
        assert entry18["proposed_restore"] == {"repeats_rrule": DAILY,
                                               "repeats_from_current_date": False}
        assert next(e for e in doc["entries"] if e["task_id"] == 16)["seed_ledger"] == {
            "rows": 2, "seeded_no_rule": True}
        # Privacy: titles only for public habit ids; no private title anywhere.
        assert "Secret private task" not in out.read_text() + stdout
        assert "PRIVATE" not in out.read_text() + stdout
        assert "Morning hip PT" in stdout
        assert "@" not in stdout

    def test_attribution_outside_window_is_removed(
        self, tmp_path: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = make_snapshot_db(tmp_path / "copy.db", [(18, DAILY, 0)])
        fake([strip_rule(make_task(id=18, updated="2026-11-19T12:02:01Z"))])
        logs = tmp_path / "habits-history.jsonl"
        logs.write_text(json.dumps({"domain": "habits", "task_id": 18, "state": "complete",
                                    "source": "whatsapp",
                                    "timestamp": "2026-11-19T12:00:00Z"}) + "\n")
        code, summary, _ = run_inventory(
            ["--baseline-db", str(db), "--felix-logs", str(logs), "--out", str(tmp_path / "o")],
            capsys,
        )
        assert code == 0 and summary["removed"] == 1 and summary["lost"] == 0

    def test_vikunja_error_exit_3(
        self, tmp_path: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = make_snapshot_db(tmp_path / "copy.db", [(18, DAILY, 0)])
        server = fake([make_task(id=18)])
        server.hooks[1] = timeout_error
        code, summary, _ = run_inventory(
            ["--baseline-db", str(db), "--out", str(tmp_path / "o")], capsys
        )
        assert code == 3 and summary["ok"] is False
        assert not (tmp_path / "o").exists()

    def test_token_never_printed(
        self, tmp_path: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = make_snapshot_db(tmp_path / "copy.db", [(18, DAILY, 0)])
        fake([strip_rule(make_task(id=18))])
        out = tmp_path / "o"
        _, _, stdout = run_inventory(["--baseline-db", str(db), "--out", str(out)], capsys)
        assert TOKEN not in stdout + out.read_text()


def test_ui_removal_next_to_reconcile_rows_is_removed_not_lost(
    tmp_path: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review cycle 2 probe: an intentional UI removal of an unlimited rule, with
    only JSONL-only reconcile rows nearby, must go to Kent, never auto-repair."""
    db = make_snapshot_db(tmp_path / "copy.db", [(18, DAILY, 0), (40, DAILY, 0)])
    fake([strip_rule(make_task(id=18, updated="2026-11-19T12:00:30Z")),
          strip_rule(make_task(id=40, updated="2026-11-19T12:00:30Z"))])
    (tmp_path / "habits-history.jsonl").write_text(json.dumps(
        {"domain": "habits", "task_id": 18, "title": "Get steps in today", "date": "2026-11-19",
         "state": "complete", "source": "vikunja-ui", "timestamp": "2026-11-19T12:00:00Z"})
        + "\n")
    esc = tmp_path / "escalation"
    esc.mkdir()
    (esc / "project-2-escalation-history.jsonl").write_text(json.dumps(
        {"domain": "escalation", "task_id": 40, "project_id": 2, "state": "done",
         "source": "reconcile", "timestamp": "2026-11-19T12:00:00Z"}) + "\n")
    code, summary, _ = run_inventory(
        ["--baseline-db", str(db), "--felix-logs", str(tmp_path / "habits-history.jsonl"),
         str(esc), "--out", str(tmp_path / "o.json")], capsys)
    assert code == 0
    assert summary["lost"] == 0 and summary["ids"]["removed"] == [18, 40]
