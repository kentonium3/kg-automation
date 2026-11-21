"""Paused habits are skipped by the morning list and the sweeper (#1111 WP12, FR-026).

The paused state lives in the task description (``manage_habit.is_paused``).
The readers get the description from the sync cache, which the sync cycle now
fills (``sync.cycle.CACHED_ONLY_TASK_FIELDS``). These tests build the cache with
the real ``_apply_cache_updates`` from v1 list-shaped task bodies, so the
whole path (sync snapshot -> cache -> reader -> predicate) is exercised.

The sweeper does not use the cache for this: it reads each habit live over v2
right before any write (review cycle 1), and fails closed when it cannot.
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.habits import manage_habit as mh
from scripts.habits import morning_checkin_list as mcl
from scripts.habits import query_active_habits_v2 as qv2
from scripts.habits import sweeper
from scripts.sync import cycle as cy
from scripts.sync import state as st
from scripts.sync.fetch import FetchedSnapshot
from tests.common.vikunja_v2_factory import make_list_task, make_task
from tests.vikunja.test_update_task import FakeVikunja, client

HABITS = qv2.HABITS_PROJECT_ID
TODAY = "2026-11-20"
DUE = "2026-11-20T12:00:00Z"
NOW = datetime(2026, 6, 2, 11, 30, tzinfo=UTC)

SCHEDULE = [(14, "Wake", []), (15, "Meditate", []), (76, "Strength — Wednesday", ["Wed"])]


def habit(task_id: int, description: str = "<p>x</p>", **overrides: Any) -> dict[str, Any]:
    return make_task(
        id=task_id,
        project_id=HABITS,
        title=overrides.pop("title", f"Habit {task_id}"),
        description=description,
        due_date=overrides.pop("due_date", DUE),
        **overrides,
    )


def write_sync_cache(monkeypatch, tmp_path: Path, tasks: list[dict[str, Any]]) -> Path:
    """Write a fresh sync cache the way a sync cycle does, from list bodies."""
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    bodies = []
    for task in tasks:
        body = make_list_task(**{k: v for k, v in task.items() if k != "repeats_rrule"})
        bodies.append(body)
    record = cy._apply_cache_updates(
        task_cache=st.TaskCacheRecord(last_updated_utc=now, tasks={}),
        snapshot=FetchedSnapshot(
            tasks=tuple(bodies), projects={}, vikunja_version=None, fetched_at_utc=now
        ),
        first_observation_task_ids={t["id"] for t in bodies},
        deleted_task_ids=set(),
        ts_observed_utc=now,
        private_project_ids=frozenset(),
    )
    st.write_task_cache(sync_dir, record)
    st.write_freshness(
        sync_dir,
        st.FreshnessPointer(
            last_updated_utc=now,
            layers={"status_and_task": st.FreshnessLayer(last_polled_utc=now)},
        ),
    )
    monkeypatch.setattr("scripts.common.sync_cache.STATE_DIR_DEFAULT", sync_dir)
    monkeypatch.setattr("scripts.sync.state.STATE_DIR_DEFAULT", sync_dir)
    return sync_dir


def listed_ids() -> set[int]:
    return {t["id"] for t in qv2.query_active_today(today=TODAY)}


# ---------------------------------------------------------------------------
# Morning list
# ---------------------------------------------------------------------------


def test_sync_cache_carries_the_description(monkeypatch, tmp_path):
    sync_dir = write_sync_cache(monkeypatch, tmp_path, [habit(14, "(PAUSED) <p>x</p>")])
    cached = st.read_task_cache(sync_dir).tasks["14"].fields
    assert cached["description"] == "(PAUSED) <p>x</p>"


def test_paused_habit_is_absent_from_the_morning_query(monkeypatch, tmp_path):
    write_sync_cache(monkeypatch, tmp_path, [habit(14, "(PAUSED) <p>x</p>"), habit(15), habit(16)])
    assert listed_ids() == {15, 16}


def test_paused_habit_is_absent_from_the_morning_list(monkeypatch, tmp_path, mock_state_log_dir):
    write_sync_cache(monkeypatch, tmp_path, [habit(14, "(PAUSED) <p>x</p>"), habit(15)])

    morning = mcl.build_morning_list(date=TODAY)

    assert [h.vikunja_task_id for h in morning.habits] == [15]


def test_title_containing_paused_is_still_listed(monkeypatch, tmp_path):
    write_sync_cache(
        monkeypatch, tmp_path, [habit(14, "<p>x</p>", title="PAUSED reading (PAUSED)")]
    )
    assert listed_ids() == {14}


def test_pause_then_resume_through_manage_habit(monkeypatch, tmp_path):
    server = FakeVikunja(habit(14), habit(15))
    monkeypatch.setattr(urllib.request, "urlopen", server)

    assert mh.manage_habit(client(), "pause", 14)["outcome"] == "paused"
    write_sync_cache(monkeypatch, tmp_path / "a", list(server.tasks.values()))
    assert listed_ids() == {15}

    assert mh.manage_habit(client(), "resume", 14)["outcome"] == "resumed"
    write_sync_cache(monkeypatch, tmp_path / "b", list(server.tasks.values()))
    assert listed_ids() == {14, 15}


# ---------------------------------------------------------------------------
# Sweeper: a live v2 read right before every write decides "paused?"
# (review cycle 1). The sync cache is not consulted, so a stale, missing or
# incomplete cache cannot switch the protection off.
# ---------------------------------------------------------------------------

SWEEPER_SOURCE = Path(sweeper.__file__).read_text(encoding="utf-8")


@pytest.fixture
def sweep(tmp_path, stub_schedule):
    schedule = tmp_path / "schedule.stub.json"
    schedule.write_text(json.dumps(SCHEDULE), encoding="utf-8")
    token = tmp_path / "token"
    token.write_text("token-not-real\n", encoding="utf-8")
    args = {
        "schedule_path": schedule,
        "state_dir": tmp_path / "state",
        "history_path": tmp_path / "history.jsonl",
        "vikunja_token_path": token,
        "vikunja_base_url": "https://vikunja.test/api/v1",
        "now_utc": NOW,
    }

    def run(
        habit_ids: list[int], dates: tuple[str, ...] = ("2026-05-30",), **overrides: Any
    ) -> sweeper.SweeperTickRecord:
        state = args["state_dir"]
        state.mkdir(parents=True, exist_ok=True)
        for date in dates:
            delivered = f"{date}T11:05:00Z"
            (state / f"morning-checkin-{date}.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "date": date,
                        "generated_at": delivered,
                        "delivered_at_utc": delivered,
                        "habits": [{"vikunja_task_id": i, "title": f"H{i}"} for i in habit_ids],
                    }
                ),
                encoding="utf-8",
            )
        return sweeper.run_sweep(**{**args, **overrides})

    run.history_path = args["history_path"]  # type: ignore[attr-defined]
    return run


def _history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _statuses(tick: sweeper.SweeperTickRecord) -> dict[int, str]:
    return {h.task_id: h.status for h in tick.habits_evaluated}


def _serve(monkeypatch, *tasks: dict[str, Any], **kwargs: Any) -> FakeVikunja:
    server = FakeVikunja(*tasks, **kwargs)
    monkeypatch.setattr(urllib.request, "urlopen", server)
    return server


def test_paused_daily_habit_is_not_swept(monkeypatch, sweep):
    server = _serve(monkeypatch, habit(14, "(PAUSED) <p>x</p>"), habit(15))

    tick = sweep([14, 15])

    assert tick.exit_status == "success"
    assert _statuses(tick) == {14: "paused", 15: "auto_skipped_this_tick"}
    assert [e["task_id"] for e in _history(sweep.history_path)] == [15]
    assert server.writes() == []


def test_pause_then_sweep_with_stale_cache_writes_nothing(monkeypatch, tmp_path, sweep):
    # Finding 1: pause succeeds, the cache still shows the old description.
    server = _serve(monkeypatch, habit(14), habit(76))
    write_sync_cache(monkeypatch, tmp_path, list(server.tasks.values()))
    for task_id in (14, 76):
        assert mh.manage_habit(client(), "pause", task_id)["outcome"] == "paused"
    patches_before = len(server.patch_bodies())

    tick = sweep([14, 76])

    assert _statuses(tick) == {14: "paused", 76: "paused"}
    assert tick.habits_auto_skipped == [] and tick.errors == []
    assert len(server.patch_bodies()) == patches_before
    assert _history(sweep.history_path) == []


def test_paused_day_specific_habit_is_read_once_and_never_written(monkeypatch, sweep):
    server = _serve(monkeypatch, habit(76, "(PAUSED) <p>x</p>"))

    tick = sweep([76])

    assert _statuses(tick) == {76: "paused"}
    assert tick.habits_auto_skipped == [] and tick.errors == []
    assert server.methods() == ["GET"]
    assert _history(sweep.history_path) == []


def test_missing_cache_file_with_fresh_pointer_does_not_disable_protection(
    monkeypatch, tmp_path, sweep
):
    # Finding 2: task-cache.json absent, freshness pointer fresh.
    sync_dir = write_sync_cache(monkeypatch, tmp_path, [habit(14)])
    (sync_dir / st.TASK_CACHE_FILENAME).unlink()
    server = _serve(monkeypatch, habit(14, "(PAUSED) <p>x</p>"))

    tick = sweep([14])

    assert _statuses(tick) == {14: "paused"}
    assert server.writes() == [] and _history(sweep.history_path) == []


@pytest.mark.parametrize("task_id", [14, 76], ids=["daily", "day-specific"])
def test_habit_absent_from_vikunja_is_paused_state_unavailable(monkeypatch, sweep, task_id):
    server = _serve(monkeypatch)  # the live read 404s

    tick = sweep([task_id])

    assert tick.exit_status == "partial"
    assert _statuses(tick) == {task_id: "paused_state_unavailable"}
    assert [e.error_type for e in tick.errors] == ["paused_state_unavailable"]
    assert server.writes() == [] and _history(sweep.history_path) == []


def test_read_without_description_is_paused_state_unavailable(monkeypatch, sweep):
    task = habit(14)
    del task["description"]
    server = _serve(monkeypatch, task)

    tick = sweep([14])

    assert tick.exit_status == "partial"
    assert _statuses(tick) == {14: "paused_state_unavailable"}
    assert server.writes() == [] and _history(sweep.history_path) == []


def test_failed_read_is_paused_state_unavailable(monkeypatch, sweep):
    server = _serve(monkeypatch, habit(14), get_status=500)

    tick = sweep([14])

    assert [e.error_type for e in tick.errors] == ["paused_state_unavailable"]
    assert server.writes() == [] and _history(sweep.history_path) == []


def test_resumed_habit_is_swept_again(monkeypatch, sweep):
    server = _serve(monkeypatch, habit(14, "(PAUSED) <p>x</p>"))
    assert mh.manage_habit(client(), "resume", 14)["outcome"] == "resumed"

    tick = sweep([14])

    assert _statuses(tick) == {14: "auto_skipped_this_tick"}
    assert [e["task_id"] for e in _history(sweep.history_path)] == [14]
    assert server.tasks[14]["description"] == "<p>x</p>"


def test_title_with_paused_is_swept(monkeypatch, sweep):
    _serve(monkeypatch, habit(14, title="(PAUSED) habit"))

    tick = sweep([14])

    assert _statuses(tick) == {14: "auto_skipped_this_tick"}


def test_dry_run_makes_no_call_and_writes_nothing(monkeypatch, sweep):
    server = _serve(monkeypatch, habit(14, "(PAUSED) <p>x</p>"))

    sweep([14], dry_run=True)

    assert server.requests == []
    assert _history(sweep.history_path) == []


def test_every_status_the_sweeper_sets_is_in_the_enum():
    assigned = set(re.findall(r'\.status = "([a-z_]+)"', SWEEPER_SOURCE))
    returned = set(
        re.findall(
            r'return "([a-z_]+)"',
            SWEEPER_SOURCE.split("def evaluate_habit_resolution")[1].split("\ndef ")[0],
        )
    )
    assert {"paused", "paused_state_unavailable", "auto_skipped_this_tick"} <= assigned
    assert assigned | returned <= sweeper.HABIT_STATUSES


def test_statuses_emitted_by_a_run_are_in_the_enum(monkeypatch, sweep):
    _serve(monkeypatch, habit(14, "(PAUSED) <p>x</p>"), habit(15))

    tick = sweep([14, 15, 99])

    produced = {h["status"] for h in tick.to_dict()["habits_evaluated"]}
    assert produced == {"paused", "auto_skipped_this_tick", "paused_state_unavailable"}
    assert produced <= sweeper.HABIT_STATUSES


class _OccurrencesFake(FakeVikunja):
    """FakeVikunja plus ``GET /api/v2/tasks/{id}/occurrences`` (one date)."""

    def __call__(self, req, timeout=None):
        path = req.full_url[len("https://vikunja.test") :].split("?", 1)[0]
        if req.get_method() == "GET" and path.endswith("/occurrences"):
            self.requests.append(("GET", path, None))
            return self._ok({"occurrences": ["2026-06-04T03:59:59Z"]})
        return super().__call__(req, timeout)


@pytest.mark.parametrize("task_id", [76, 14], ids=["day-specific", "daily"])
def test_habit_paused_before_the_tick_gets_no_write_on_the_backlog_path(
    monkeypatch, sweep, task_id
):
    # Cycle 2 finding 1 (scoped by Kent 2026-11-20): one live check per habit
    # per tick, before its first write, on every path including the backlog.
    server = _OccurrencesFake(habit(task_id, "(PAUSED) <p>x</p>", due_date="2026-05-27T03:59:59Z"))
    monkeypatch.setattr(urllib.request, "urlopen", server)

    tick = sweep([task_id], dates=("2026-05-29", "2026-05-30"))

    assert [h.status for h in tick.habits_evaluated] == ["paused", "paused"]
    assert tick.habits_auto_skipped == [] and tick.errors == []
    assert server.methods() == ["GET"]  # one check for the habit, no write
    assert _history(sweep.history_path) == []


def test_unpaused_day_specific_backlog_is_checked_once_and_advanced_once(monkeypatch, sweep):
    server = _OccurrencesFake(habit(76, due_date="2026-05-27T03:59:59Z"))
    monkeypatch.setattr(urllib.request, "urlopen", server)

    tick = sweep([76], dates=("2026-05-29", "2026-05-30"))

    assert [h.status for h in tick.habits_evaluated] == ["auto_skipped_this_tick"] * 2
    # check (the advance's pre-write read), occurrences, PATCH, readback; the
    # second entry reuses the tick's check and advance: no extra request.
    assert server.methods() == ["GET", "GET", "PATCH", "GET"]
    assert len(_history(sweep.history_path)) == 2


def test_unpaused_daily_backlog_is_checked_once(monkeypatch, sweep):
    server = _serve(monkeypatch, habit(14))

    tick = sweep([14], dates=("2026-05-29", "2026-05-30"))

    assert [h.status for h in tick.habits_evaluated] == ["auto_skipped_this_tick"] * 2
    assert server.methods() == ["GET"]
    assert len(_history(sweep.history_path)) == 2
