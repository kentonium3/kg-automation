"""Unit tests for ``scripts.habits.query_active_habits_weekly`` (mission WP02).

Per DIRECTIVE_034 the test surface is authored alongside the helper.
Coverage targets are enforced by:

    pytest tests/habits/test_query_active_habits_weekly.py \
        --cov=scripts.habits.query_active_habits_weekly \
        --cov-branch --cov-fail-under=90

(Note the dotted module form for ``--cov`` — the path form silently
records 0% coverage; lesson from WP01 cycle 3.)

Test groups
-----------
- HabitClassifier (parse_weekday_in_title, classify_habit, scheduled_days_for_window).
- query_completion_events (pagination, done_at filtering, active fallback).
- build_report (sort order, overall math, baseline omission, percentage cap).
- main (success, VikunjaError, internal error, CLI flag validation).
- Fixture-driven end-to-end scenarios (the 8 fixtures from
  ``contracts/query_active_habits_weekly.md`` § Test fixtures).
- FR-012 explicit regression assertions.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from scripts.common.vikunja_client import (
    VikunjaBadRequestError,
    VikunjaTimeoutError,
)
from scripts.habits import query_active_habits_weekly as helper
from tests.habits.fixtures.golden_week_jsonl import (
    DAILY_HABIT_ID,
    DAYSPEC_HABIT_ID,
    GOLDEN_WEEK_ANCHOR,
    GOLDEN_WEEK_TZ,
    WEEKLY_HABIT_ID,
    write_golden_week_jsonl,
)


FIXTURES_PATH = Path(__file__).parent / "fixtures" / "weekly_report_responses.json"

# Canonical anchor matching the fixture file's _meta.window_end.
CURRENT_END = datetime(2026, 6, 8, tzinfo=timezone.utc)
CURRENT_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PRIOR_END = CURRENT_START
PRIOR_START = datetime(2026, 5, 25, tzinfo=timezone.utc)


# Vikunja habit-task payload helper for the new path. Unlike the prior
# done_at-based tests, the new path never reads done_at — only id, title,
# repeat_after — so the mock task shape collapses to just those fields.
def _vk_task(
    *,
    habit_id: int,
    title: str,
    repeat_after: int = 86400,
) -> dict:
    """Build a minimal Vikunja-shaped task dict for the new helper path."""
    return {
        "id": habit_id,
        "title": title,
        "repeat_after": repeat_after,
        # Intentionally include a sentinel done_at to prove the new code path
        # does NOT read it. Tests in the regression group assert this.
        "done_at": "9999-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixtures() -> dict:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def _build_mock_client(
    *,
    done_pages: Optional[list[list[dict]]] = None,
    active_pages: Optional[list[list[dict]]] = None,
    tasks_pages: Optional[list[list[dict]]] = None,
    raises: Optional[Exception] = None,
) -> MagicMock:
    """Synthesize a ``VikunjaClient``-shaped mock for these tests.

    The new (canonical-store) path issues a single paginated GET
    ``/projects/13/tasks`` with NO ``filter`` param — those pages come
    from ``tasks_pages``. The legacy ``done_pages`` / ``active_pages``
    args are retained to keep the inherited mock shape compatible with
    older tests that still drive the old code paths during transition.
    """
    client = MagicMock(name="VikunjaClient")
    done_pages = done_pages or []
    active_pages = active_pages or []
    tasks_pages = tasks_pages or []
    done_iter = iter(done_pages)
    active_iter = iter(active_pages)
    tasks_iter = iter(tasks_pages)

    def _get(path, *, params=None, **_kwargs):
        if raises is not None:
            raise raises
        filt = (params or {}).get("filter", "")
        if filt == "done=true":
            try:
                return next(done_iter)
            except StopIteration:
                return []
        if filt == "done=false":
            try:
                return next(active_iter)
            except StopIteration:
                return []
        # No filter set — new (canonical-store) path. Serve from
        # tasks_pages, falling back to done_pages flattened-into-one-page
        # for ergonomic compatibility with the existing tests that
        # provided habit lists via done_pages.
        try:
            return next(tasks_iter)
        except StopIteration:
            return []

    client.get.side_effect = _get
    return client


# ---------------------------------------------------------------------------
# parse_weekday_in_title (10+ cases)
# ---------------------------------------------------------------------------


def test_parse_weekday_in_title_full_word_wednesday() -> None:
    assert helper.parse_weekday_in_title("Strength training — Wednesday") == frozenset({"WED"})


def test_parse_weekday_in_title_three_letter_prefix() -> None:
    assert helper.parse_weekday_in_title("Yoga — Mon") == frozenset({"MON"})


def test_parse_weekday_in_title_case_insensitive() -> None:
    assert helper.parse_weekday_in_title("yoga — MONDAY") == frozenset({"MON"})


def test_parse_weekday_in_title_multiple_weekdays() -> None:
    assert helper.parse_weekday_in_title("Yoga — Mon and Wed") == frozenset({"MON", "WED"})


def test_parse_weekday_in_title_full_word_saturday() -> None:
    assert helper.parse_weekday_in_title("Saturday morning swim") == frozenset({"SAT"})


def test_parse_weekday_in_title_no_weekday() -> None:
    assert helper.parse_weekday_in_title("Read 30 min minimum") == frozenset()


def test_parse_weekday_in_title_empty_string() -> None:
    assert helper.parse_weekday_in_title("") == frozenset()


def test_parse_weekday_in_title_embedded_word_does_not_match() -> None:
    # "Monday" inside a longer word like "Mondays" still matches via \b at
    # both ends only if the trailing 's' breaks the boundary; document the
    # current behavior — plural 'Mondays' DOES match because \b sits
    # between 'y' (\w) and 's' (\w)... actually no, \b is between \w and
    # non-\w. So "Mondays" has Monday then s — no \b after 'y'. Verify.
    assert helper.parse_weekday_in_title("Mondays standup") == frozenset()


def test_parse_weekday_in_title_all_seven() -> None:
    title = "Mon Tue Wed Thu Fri Sat Sun"
    assert helper.parse_weekday_in_title(title) == frozenset(
        {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
    )


def test_parse_weekday_in_title_dupe_returns_one() -> None:
    assert helper.parse_weekday_in_title("Mon Mon Mon") == frozenset({"MON"})


# ---------------------------------------------------------------------------
# classify_habit (rules + edge cases)
# ---------------------------------------------------------------------------


def test_classify_daily_repeat_after_86400() -> None:
    assert helper.classify_habit({"repeat_after": 86400, "title": "Meditate"}) == "daily"


def test_classify_weekday_in_title_repeat_after_0() -> None:
    assert (
        helper.classify_habit(
            {"repeat_after": 0, "title": "Strength training — Wednesday"}
        )
        == "weekday-in-title"
    )


def test_classify_other_cardiac_zero_repeat_no_weekday() -> None:
    assert (
        helper.classify_habit(
            {"repeat_after": 0, "title": "Upload cardiac lab history"}
        )
        == "other"
    )


def test_classify_other_unexpected_repeat_after() -> None:
    # Anything not 0 and not 86400 falls to "other" per data-model.md.
    assert helper.classify_habit({"repeat_after": 3600, "title": "Hourly check"}) == "other"
    assert helper.classify_habit({"repeat_after": 172800, "title": "Every-other-day"}) == "other"


def test_classify_other_weekday_with_daily_repeat() -> None:
    # repeat_after=86400 AND weekday-in-title → classifier prefers "other"
    # (the rule chain checks weekdays must be empty for daily; non-empty +
    # 86400 doesn't match either positive arm).
    assert (
        helper.classify_habit(
            {"repeat_after": 86400, "title": "Workout — Monday"}
        )
        == "other"
    )


def test_classify_other_missing_repeat_after_field() -> None:
    assert helper.classify_habit({"title": "Meditate"}) == "other"


def test_classify_other_missing_title_field() -> None:
    assert helper.classify_habit({"repeat_after": 86400}) == "daily"


# ---------------------------------------------------------------------------
# scheduled_days_for_window (6+ cases)
# ---------------------------------------------------------------------------


def test_scheduled_days_daily_full_week_returns_seven() -> None:
    assert helper.scheduled_days_for_window("daily", "Meditate", CURRENT_START, CURRENT_END) == 7


def test_scheduled_days_daily_three_day_window() -> None:
    end = CURRENT_START + timedelta(days=3)
    assert helper.scheduled_days_for_window("daily", "Meditate", CURRENT_START, end) == 3


def test_scheduled_days_weekday_in_title_single_match_in_week() -> None:
    assert (
        helper.scheduled_days_for_window(
            "weekday-in-title", "Strength training — Monday", CURRENT_START, CURRENT_END
        )
        == 1
    )


def test_scheduled_days_weekday_in_title_two_weekdays_in_title() -> None:
    assert (
        helper.scheduled_days_for_window(
            "weekday-in-title", "Yoga — Mon and Wed", CURRENT_START, CURRENT_END
        )
        == 2
    )


def test_scheduled_days_weekday_in_title_zero_matches_for_empty_title() -> None:
    assert (
        helper.scheduled_days_for_window(
            "weekday-in-title", "Empty title", CURRENT_START, CURRENT_END
        )
        == 0
    )


def test_scheduled_days_other_returns_zero() -> None:
    assert helper.scheduled_days_for_window("other", "Cardiac", CURRENT_START, CURRENT_END) == 0


def test_scheduled_days_inverted_window_returns_zero() -> None:
    assert helper.scheduled_days_for_window("daily", "Meditate", CURRENT_END, CURRENT_START) == 0


# ---------------------------------------------------------------------------
# query_completion_events (canonical-store path, post-trustworthy-weekly-...)
# ---------------------------------------------------------------------------
#
# The new code path reads only current-state habit metadata from Vikunja
# (id, title, repeat_after) and derives completion counts from
# ``habits-history.jsonl`` via :mod:`scripts.habits.history`. Each test
# sets up:
#   1. A ``tasks_pages`` mock so the Vikunja list call returns the habit
#      catalog.
#   2. A ``mock_state_log_dir`` writing a tailored JSONL fixture so the
#      history wrapper reads deterministic completion records.


def _write_habits_jsonl(state_dir: Path, records: list[dict]) -> Path:
    """Helper: write a JSONL file at ``<state_dir>/habits-history.jsonl``."""
    path = state_dir / "habits-history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
    else:
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )
    return path


def _habit_record(
    *,
    task_id: int,
    date_iso: str,
    timestamp_iso: str,
    title: str = "Habit",
    state: str = "complete",
) -> dict:
    return {
        "domain": "habits",
        "task_id": task_id,
        "title": title,
        "date": date_iso,
        "state": state,
        "source": "whatsapp",
        "timestamp": timestamp_iso,
    }


def test_query_events_single_habit_one_completion_from_jsonl(
    mock_state_log_dir,
) -> None:
    """One daily habit + one completion in window → current_count=1."""
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(
        mock_state_log_dir,
        [
            _habit_record(
                task_id=1,
                date_iso="2026-06-02",
                timestamp_iso="2026-06-02T07:00:00+00:00",
            )
        ],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events == {
        "Meditate": {
            "kind": "daily",
            "title": "Meditate",
            "current_count": 1,
            "prior_count": 0,
        }
    }


def test_query_events_filters_other_kind(mock_state_log_dir) -> None:
    """A non-recurring non-weekday task ('other') is excluded from events."""
    client = _build_mock_client(
        tasks_pages=[[
            _vk_task(habit_id=1, title="Meditate", repeat_after=86400),
            _vk_task(habit_id=2, title="Upload cardiac lab history", repeat_after=0),
        ]],
    )
    _write_habits_jsonl(mock_state_log_dir, [])
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert "Upload cardiac lab history" not in events
    assert "Meditate" in events


def test_query_events_empty_responses_returns_empty_dict(
    mock_state_log_dir,
) -> None:
    """No Vikunja tasks → empty events dict (no completion lookups needed)."""
    client = _build_mock_client(tasks_pages=[[]])
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events == {}


def test_query_events_dedup_by_date(mock_state_log_dir) -> None:
    """Two completions on the same date for the same habit → count = 1."""
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(
        mock_state_log_dir,
        [
            _habit_record(
                task_id=1,
                date_iso="2026-06-02",
                timestamp_iso="2026-06-02T07:00:00+00:00",
            ),
            _habit_record(
                task_id=1,
                date_iso="2026-06-02",
                timestamp_iso="2026-06-02T19:00:00+00:00",
            ),
        ],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 1


def test_query_events_pagination_no_dupe(mock_state_log_dir) -> None:
    """A habit appearing on multiple Vikunja pages (edge case) is counted once.

    Also guards the >50-task pagination path (post-plan review M10) and
    proves the fetch uses the config-sourced habit project id (#723
    T002/T004): the first page is a full ``_PAGE_SIZE`` (200) batch, so
    ``_paginate`` must request a second page rather than stopping early
    (stop-on-empty-page semantics, not a hardcoded ``len < 100`` cutoff).
    """
    full_page = [
        _vk_task(habit_id=1, title="Meditate") for _ in range(200)
    ]
    second_page = [_vk_task(habit_id=1, title="Meditate")]
    client = _build_mock_client(tasks_pages=[full_page, second_page])
    # CURRENT window is [2026-06-01 00:00 UTC, 2026-06-08 00:00 UTC).
    # Use days 1..7 at noon UTC so every record falls inside.
    _write_habits_jsonl(
        mock_state_log_dir,
        [
            _habit_record(
                task_id=1,
                date_iso=f"2026-06-{day:02d}",
                timestamp_iso=f"2026-06-{day:02d}T12:00:00+00:00",
            )
            for day in range(1, 8)
        ],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    # Single bucket (de-duped), with the 7 distinct dates from the JSONL.
    assert list(events.keys()) == ["Meditate"]
    assert events["Meditate"]["current_count"] == 7
    # Both pages were requested against the registry-sourced habit project
    # id (13 today, resolved via helper._resolve_habits_project_id() →
    # scripts.common.vikunja_scope.habit_project_id()), confirming no
    # hardcoded id was reintroduced and pagination consumed the full first
    # page before requesting the second.
    resolved_id = helper._resolve_habits_project_id()
    called_paths = [call.args[0] for call in client.get.call_args_list]
    assert called_paths == [
        f"/projects/{resolved_id}/tasks",
        f"/projects/{resolved_id}/tasks",
    ]


def test_query_events_active_no_completions_creates_zero_row(
    mock_state_log_dir,
) -> None:
    """A habit listed in Vikunja with no JSONL records → current/prior = 0."""
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(mock_state_log_dir, [])
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 0
    assert events["Meditate"]["prior_count"] == 0


def test_query_events_prior_count_filled_when_prior_set(
    mock_state_log_dir,
) -> None:
    """Completions in the prior window populate prior_count."""
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(
        mock_state_log_dir,
        [
            _habit_record(
                task_id=1,
                date_iso="2026-05-26",
                timestamp_iso="2026-05-26T07:00:00+00:00",
            ),
            _habit_record(
                task_id=1,
                date_iso="2026-06-02",
                timestamp_iso="2026-06-02T07:00:00+00:00",
            ),
        ],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 1
    assert events["Meditate"]["prior_count"] == 1


def test_query_events_prior_window_none_skipped(mock_state_log_dir) -> None:
    """prior_window_*=None disables the prior wrapper call (count stays 0)."""
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(
        mock_state_log_dir,
        [
            _habit_record(
                task_id=1,
                date_iso="2026-05-26",
                timestamp_iso="2026-05-26T07:00:00+00:00",
            ),
        ],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=None,
        prior_window_end=None,
    )
    assert events["Meditate"]["prior_count"] == 0


def test_query_events_skips_task_missing_id(mock_state_log_dir) -> None:
    """A task without an integer id is skipped (defensive against bad data)."""
    client = _build_mock_client(
        tasks_pages=[[
            {"title": "No-ID habit", "repeat_after": 86400},
            _vk_task(habit_id=1, title="Meditate"),
        ]],
    )
    _write_habits_jsonl(mock_state_log_dir, [])
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert "No-ID habit" not in events
    assert "Meditate" in events


def test_query_events_does_not_read_done_at(mock_state_log_dir) -> None:
    """Regression: even with garbage done_at, helper relies on JSONL only.

    The Vikunja task here carries ``done_at`` = year-9999 sentinel — clearly
    not a real completion. If the code path still read ``done_at`` it would
    show a completion in some window; reading from JSONL (empty) ensures it
    does not.
    """
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(mock_state_log_dir, [])
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 0
    assert events["Meditate"]["prior_count"] == 0


# ---------------------------------------------------------------------------
# build_report (sort order, baseline math, omission)
# ---------------------------------------------------------------------------


def test_build_report_sorts_daily_first_then_weekday() -> None:
    events = {
        "Yoga — Saturday": {"kind": "weekday-in-title", "title": "Yoga — Saturday",
                            "current_count": 1, "prior_count": 0},
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 5, "prior_count": 0},
        "Strength training — Monday": {"kind": "weekday-in-title",
                                        "title": "Strength training — Monday",
                                        "current_count": 1, "prior_count": 0},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    titles = [h["habit_title"] for h in report["habits"]]
    assert titles == ["Meditate", "Strength training — Monday", "Yoga — Saturday"]


def test_build_report_two_daily_alphabetical() -> None:
    events = {
        "Read": {"kind": "daily", "title": "Read",
                 "current_count": 1, "prior_count": 0},
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 1, "prior_count": 0},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert [h["habit_title"] for h in report["habits"]] == ["Meditate", "Read"]


def test_build_report_caps_completed_at_scheduled_days(monkeypatch) -> None:
    # Silence the anomaly subprocess; the cap behavior is what this test
    # exercises. Anomaly emission has dedicated tests below.
    monkeypatch.setattr(helper, "_emit_log_action", lambda **_kwargs: None)
    events = {
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 99, "prior_count": 0},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert report["habits"][0]["completed_events_current"] == 7
    assert report["habits"][0]["percent_current"] == 100.0


def _capture_emit_log_action(monkeypatch) -> list[dict]:
    """Patch ``helper._emit_log_action`` to record its kwargs.

    Returns the list mutated on each call; callers inspect it after
    running ``build_report``. Matches the existing ``_silence_log_action``
    pattern but keeps the payload for assertions.
    """
    calls: list[dict] = []

    def _record(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(helper, "_emit_log_action", _record)
    return calls


def test_build_report_emits_anomaly_when_current_count_exceeds_scheduled(
    monkeypatch,
) -> None:
    calls = _capture_emit_log_action(monkeypatch)
    events = {
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 12, "prior_count": 0},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    # Cap behavior remains: capped at scheduled (7 for a daily over the week).
    assert report["habits"][0]["completed_events_current"] == 7

    anomaly_calls = [c for c in calls if c.get("action") == "weekly_report_anomaly"]
    assert len(anomaly_calls) == 1
    call = anomaly_calls[0]
    assert call["category"] == "flagged"
    assert call["target"] == "/projects/13/tasks"
    assert call["outcome"] == "capped"
    context = call["context"]
    assert context["habit_title"] == "Meditate"
    assert context["habit_kind"] == "daily"
    assert context["window"] == "current"
    assert context["scheduled_days"] == 7
    assert context["raw_count"] == 12
    assert context["capped_count"] == 7
    assert context["window_start_iso"] == "2026-06-01T00:00:00Z"
    assert context["window_end_iso"] == "2026-06-08T00:00:00Z"


def test_build_report_emits_anomaly_when_prior_count_exceeds_scheduled(
    monkeypatch,
) -> None:
    calls = _capture_emit_log_action(monkeypatch)
    events = {
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 0, "prior_count": 9},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    # Prior cap still capped at 7.
    assert report["habits"][0]["completed_events_prior"] == 7

    anomaly_calls = [c for c in calls if c.get("action") == "weekly_report_anomaly"]
    assert len(anomaly_calls) == 1
    call = anomaly_calls[0]
    assert call["category"] == "flagged"
    assert call["target"] == "/projects/13/tasks"
    assert call["outcome"] == "capped"
    context = call["context"]
    assert context["habit_title"] == "Meditate"
    assert context["habit_kind"] == "daily"
    assert context["window"] == "prior"
    assert context["scheduled_days"] == 7
    assert context["raw_count"] == 9
    assert context["capped_count"] == 7
    assert context["window_start_iso"] == "2026-05-25T00:00:00Z"
    assert context["window_end_iso"] == "2026-06-01T00:00:00Z"


def test_build_report_emits_no_anomaly_on_normal_data(monkeypatch) -> None:
    calls = _capture_emit_log_action(monkeypatch)
    events = {
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 5, "prior_count": 3},
        "Strength training — Monday": {"kind": "weekday-in-title",
                                        "title": "Strength training — Monday",
                                        "current_count": 1, "prior_count": 1},
    }
    helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    anomaly_calls = [c for c in calls if c.get("action") == "weekly_report_anomaly"]
    assert anomaly_calls == []


def test_build_report_baseline_omission_sets_nulls() -> None:
    events = {
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 3, "prior_count": 0},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=None,
        prior_window_end=None,
    )
    assert report["prior_window_start_iso"] is None
    assert report["prior_window_end_iso"] is None
    assert report["overall_percent_prior"] is None
    assert report["habits"][0]["scheduled_days_prior"] is None
    assert report["habits"][0]["completed_events_prior"] is None
    assert report["habits"][0]["percent_prior"] is None


def test_build_report_empty_events_emits_zero_overall() -> None:
    report = helper.build_report(
        {},
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert report["habits"] == []
    assert report["overall_percent_current"] == 0.0
    assert report["overall_percent_prior"] == 0.0


def test_build_report_iso_strings_use_z_suffix() -> None:
    report = helper.build_report(
        {},
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert report["window_start_iso"].endswith("Z")
    assert report["window_end_iso"].endswith("Z")
    assert report["prior_window_start_iso"].endswith("Z")
    assert report["prior_window_end_iso"].endswith("Z")


def test_build_report_weekday_sort_by_weekday_then_title() -> None:
    events = {
        "Yoga — Monday": {"kind": "weekday-in-title", "title": "Yoga — Monday",
                          "current_count": 0, "prior_count": 0},
        "Stretching — Friday": {"kind": "weekday-in-title", "title": "Stretching — Friday",
                                "current_count": 0, "prior_count": 0},
        "Tennis — Monday": {"kind": "weekday-in-title", "title": "Tennis — Monday",
                            "current_count": 0, "prior_count": 0},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert [h["habit_title"] for h in report["habits"]] == [
        "Tennis — Monday",  # both Monday rows; Tennis < Yoga alphabetically
        "Yoga — Monday",
        "Stretching — Friday",
    ]


# ---------------------------------------------------------------------------
# main / CLI / exit codes
# ---------------------------------------------------------------------------


def _patch_client_with_mock(monkeypatch, *, mock_client):
    monkeypatch.setattr(helper, "VikunjaClient", lambda **_kwargs: mock_client)


def _silence_log_action(monkeypatch):
    monkeypatch.setattr(helper, "_emit_log_action", lambda **_kwargs: None)


def test_main_success_returns_zero_and_emits_json(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(
        mock_state_log_dir,
        [
            _habit_record(
                task_id=1,
                date_iso="2026-06-02",
                timestamp_iso="2026-06-02T07:00:00+00:00",
            )
        ],
    )
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["window_start_iso"] == "2026-06-01T00:00:00Z"
    assert payload["window_end_iso"] == "2026-06-08T00:00:00Z"
    assert payload["habits"][0]["habit_title"] == "Meditate"
    # FR-005: rendered_text is now a top-level field, additive to the
    # existing schema.
    assert "rendered_text" in payload
    assert payload["rendered_text"].startswith("*This week*")


def test_main_vikunja_error_returns_three(monkeypatch, capsys) -> None:
    client = _build_mock_client(raises=VikunjaTimeoutError(path="/projects/13/tasks"))
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08"])
    captured = capsys.readouterr()
    assert rc == 3
    assert "VikunjaTimeoutError" in captured.err
    assert "/projects/13/tasks" in captured.err


def test_main_vikunja_bad_request_returns_three(monkeypatch, capsys) -> None:
    client = _build_mock_client(
        raises=VikunjaBadRequestError(path="/projects/13/tasks", status=400)
    )
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08"])
    captured = capsys.readouterr()
    assert rc == 3
    assert "VikunjaBadRequestError" in captured.err


def test_main_unexpected_exception_returns_four(monkeypatch, capsys) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic")

    _patch_client_with_mock(monkeypatch, mock_client=MagicMock())
    monkeypatch.setattr(helper, "query_completion_events", _boom)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08"])
    captured = capsys.readouterr()
    assert rc == 4
    assert "internal error" in captured.err


def test_main_bad_window_end_returns_two(monkeypatch, capsys) -> None:
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "not-a-date"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "usage error" in captured.err.lower()


def test_main_bad_window_days_returns_two(monkeypatch, capsys) -> None:
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-days", "0"])
    captured = capsys.readouterr()
    assert rc == 2


def test_main_no_baseline_flag_strips_prior(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    client = _build_mock_client(tasks_pages=[[]])
    _write_habits_jsonl(mock_state_log_dir, [])
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08", "--no-include-baseline"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["prior_window_start_iso"] is None
    assert payload["overall_percent_prior"] is None


def test_main_default_window_end_uses_today(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    client = _build_mock_client(tasks_pages=[[]])
    _write_habits_jsonl(mock_state_log_dir, [])
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main([])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    # Should be UTC midnight of today; just confirm parseable + Z suffix.
    assert payload["window_end_iso"].endswith("Z")


def test_main_help_returns_zero(monkeypatch, capsys) -> None:
    # argparse raises SystemExit(0) on --help; main catches and returns 0.
    rc = helper.main(["--help"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "weekly" in captured.out.lower()


def test_main_argparse_error_returns_two(monkeypatch, capsys) -> None:
    rc = helper.main(["--bogus-flag"])
    assert rc == 2


# ---------------------------------------------------------------------------
# log_action subprocess shim
# ---------------------------------------------------------------------------


def test_emit_log_action_missing_binary_warns(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv("LOG_ACTION_PATH", str(tmp_path / "does-not-exist.py"))
    helper._emit_log_action(
        category="routine",
        action="weekly_report_generated",
        target="/projects/13/tasks",
        outcome="success",
        context={"habit_count": 1},
    )
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()


def test_emit_log_action_invokes_subprocess(monkeypatch, tmp_path) -> None:
    fake_bin = tmp_path / "fake_log_action.py"
    fake_bin.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(0)\n")
    monkeypatch.setenv("LOG_ACTION_PATH", str(fake_bin))

    captured = {}

    class _Proc:
        returncode = 0
        stderr = ""

    def _run(cmd, *, capture_output, text, timeout, check):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(helper.subprocess, "run", _run)
    helper._emit_log_action(
        category="routine",
        action="weekly_report_generated",
        target="/projects/13/tasks",
        outcome="success",
        context={"habit_count": 1},
    )
    assert "--action" in captured["cmd"]
    assert "weekly_report_generated" in captured["cmd"]


def test_emit_log_action_subprocess_failure_warns(monkeypatch, tmp_path, capsys) -> None:
    fake_bin = tmp_path / "fake_log_action.py"
    fake_bin.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(1)\n")
    monkeypatch.setenv("LOG_ACTION_PATH", str(fake_bin))

    class _Proc:
        returncode = 1
        stderr = "bad stuff"

    monkeypatch.setattr(
        helper.subprocess, "run", lambda *a, **k: _Proc()
    )
    helper._emit_log_action(
        category="routine",
        action="weekly_report_generated",
        target="/projects/13/tasks",
        outcome="success",
        context={"habit_count": 1},
    )
    captured = capsys.readouterr()
    assert "exited 1" in captured.err


def test_emit_log_action_subprocess_oserror_swallowed(monkeypatch, tmp_path, capsys) -> None:
    fake_bin = tmp_path / "fake_log_action.py"
    fake_bin.write_text("#!/usr/bin/env python3\n")
    monkeypatch.setenv("LOG_ACTION_PATH", str(fake_bin))

    def _raise(*a, **k):
        raise OSError("synthetic")

    monkeypatch.setattr(helper.subprocess, "run", _raise)
    helper._emit_log_action(
        category="routine",
        action="weekly_report_generated",
        target="/projects/13/tasks",
        outcome="success",
        context={"habit_count": 1},
    )
    captured = capsys.readouterr()
    assert "log_action.py invocation failed" in captured.err


# ---------------------------------------------------------------------------
# Vikunja-failure surface (FR-012 d/f)
# ---------------------------------------------------------------------------


def test_fixture_weekly_vikunja_unreachable(monkeypatch, fixtures, capsys) -> None:
    # FR-012 (d): Vikunja-unreachable produces typed exception → exit 3.
    client = _build_mock_client(raises=VikunjaTimeoutError(path="/projects/13/tasks"))
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08"])
    captured = capsys.readouterr()
    assert rc == 3
    assert "VikunjaTimeoutError" in captured.err
    # FR-012 (f): error message is redaction-safe (just class + path).
    assert "/projects/13/tasks" in captured.err


def test_fixture_weekly_bad_filter_syntax(monkeypatch, fixtures, capsys) -> None:
    client = _build_mock_client(
        raises=VikunjaBadRequestError(path="/projects/13/tasks", status=400)
    )
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08"])
    captured = capsys.readouterr()
    assert rc == 3
    assert "VikunjaBadRequestError" in captured.err
    assert "/projects/13/tasks" in captured.err


# ---------------------------------------------------------------------------
# FR-012 (e): base-URL trailing-slash normalization (covered by WP01 but
# we cross-check the helper instantiates the client without exploding).
# ---------------------------------------------------------------------------


def test_helper_strips_base_url_trailing_slash() -> None:
    # FR-012 (e): client normalizes a trailing-slash base URL. The conftest
    # autouse fixture ``mock_vikunja_base_url`` returns the URL with a
    # trailing slash; the client must strip it. Pass an explicit token to
    # avoid the on-disk default-token reader.
    from scripts.common.vikunja_client import VikunjaClient as _VC
    client = _VC(token="tok")
    assert client.base_url == "https://vikunja.test/api/v1"


# ===========================================================================
# WP02 (trustworthy-weekly-habit-report-01KV4GZ7) — new surface tests
# ===========================================================================
#
# Tests below exercise WP02-specific additions:
#   - ``--as-of`` argparse type converter (T008)
#   - ``_format_window_label`` (T010)
#   - ``_arrow_for_delta`` + ``_render_whatsapp_text`` (T009)
#   - ``--output text`` CLI mode (T009)
#   - End-to-end byte-stable JSON + rendered_text via the golden-week
#     JSONL fixture (T011 / FR-008 + FR-009 + NFR-001 + NFR-004)
#   - ``done_at`` is NOT read (regression that pins FR-002)


# ---------------------------------------------------------------------------
# _parse_as_of (T008)
# ---------------------------------------------------------------------------


def test_parse_as_of_accepts_iso_with_offset() -> None:
    parsed = helper._parse_as_of("2026-06-15T06:00:00-04:00")
    assert parsed.tzinfo is not None
    assert parsed.year == 2026
    assert parsed.month == 6
    assert parsed.day == 15


def test_parse_as_of_accepts_z_suffix() -> None:
    parsed = helper._parse_as_of("2026-06-15T10:00:00Z")
    assert parsed.tzinfo is not None


def test_parse_as_of_rejects_naive_datetime() -> None:
    import argparse as _argparse
    with pytest.raises(_argparse.ArgumentTypeError, match="tz-aware"):
        helper._parse_as_of("2026-06-15T06:00:00")


def test_parse_as_of_rejects_garbage() -> None:
    import argparse as _argparse
    with pytest.raises(_argparse.ArgumentTypeError, match="ISO 8601"):
        helper._parse_as_of("not-a-date")


def test_parse_as_of_rejects_empty() -> None:
    import argparse as _argparse
    with pytest.raises(_argparse.ArgumentTypeError):
        helper._parse_as_of("")


# ---------------------------------------------------------------------------
# _format_window_label (T010, FR-006)
# ---------------------------------------------------------------------------


def test_format_window_label_same_month_seven_days() -> None:
    """A Mon-to-next-Mon (exclusive) window over Jun 8-14 → 'Jun 8–14'."""
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    assert helper._format_window_label(start, end) == "Jun 8–14"


def test_format_window_label_cross_month_seven_days() -> None:
    """A window crossing months renders both abbreviations with en-dash."""
    start = datetime(2026, 7, 28, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    # Inclusive last day is Aug 3.
    assert helper._format_window_label(start, end) == "Jul 28 – Aug 3"


def test_format_window_label_not_eight_day_span() -> None:
    """Sanity: the label must NOT show an 8-day span (the bug we're fixing)."""
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    label = helper._format_window_label(start, end)
    assert "Jun 8–15" not in label  # 8-day span (the bug)
    assert "Jun 7–14" not in label  # other 8-day variant


# ---------------------------------------------------------------------------
# _arrow_for_delta (T009)
# ---------------------------------------------------------------------------


def test_arrow_up_when_current_clearly_above_prior() -> None:
    assert helper._arrow_for_delta(80.0, 70.0) == "↑"


def test_arrow_down_when_current_clearly_below_prior() -> None:
    assert helper._arrow_for_delta(60.0, 70.0) == "↓"


def test_arrow_empty_when_essentially_equal() -> None:
    """Epsilon prevents arrow flicker on essentially-equal rates."""
    assert helper._arrow_for_delta(70.2, 70.0) == ""
    assert helper._arrow_for_delta(69.8, 70.0) == ""


def test_arrow_empty_when_prior_is_none() -> None:
    """Without a baseline there's no arrow to draw."""
    assert helper._arrow_for_delta(70.0, None) == ""


# ---------------------------------------------------------------------------
# _render_whatsapp_text (T009, NFR-004 determinism)
# ---------------------------------------------------------------------------


def _example_report_for_render() -> dict:
    """A minimal report dict to drive renderer tests."""
    return {
        "window_start_iso": "2026-06-08T04:00:00Z",
        "window_end_iso": "2026-06-15T04:00:00Z",
        "prior_window_start_iso": "2026-06-01T04:00:00Z",
        "prior_window_end_iso": "2026-06-08T04:00:00Z",
        "habits": [
            {
                "habit_title": "Get steps in today",
                "habit_kind": "daily",
                "scheduled_days_current": 7,
                "completed_events_current": 4,
                "percent_current": 57.0,
                "scheduled_days_prior": 7,
                "completed_events_prior": 5,
                "percent_prior": 71.0,
            },
            {
                "habit_title": "Strength — Monday",
                "habit_kind": "weekday-in-title",
                "scheduled_days_current": 1,
                "completed_events_current": 1,
                "percent_current": 100.0,
                "scheduled_days_prior": 1,
                "completed_events_prior": 0,
                "percent_prior": 0.0,
            },
        ],
        # 62.6 (not 62.5) avoids banker's-rounding ambiguity for the
        # integer percent display.
        "overall_percent_current": 62.6,
        "overall_percent_prior": 45.0,
    }


def test_render_whatsapp_text_byte_stable_for_identical_input() -> None:
    """NFR-004: same report dict + same bounds → byte-identical text."""
    report = _example_report_for_render()
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    a = helper._render_whatsapp_text(report, window_start=start, window_end=end)
    b = helper._render_whatsapp_text(report, window_start=start, window_end=end)
    assert a == b


def test_render_whatsapp_text_contains_short_window() -> None:
    report = _example_report_for_render()
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    text = helper._render_whatsapp_text(
        report, window_start=start, window_end=end
    )
    assert text.startswith("*This week* (Jun 8–14):")


def test_render_whatsapp_text_includes_arrows_per_habit() -> None:
    report = _example_report_for_render()
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    text = helper._render_whatsapp_text(
        report, window_start=start, window_end=end
    )
    # First habit: 57 (was 71) → down arrow.
    assert "Get steps in today — 57% (was 71%) ↓" in text
    # Second habit: 100 (was 0) → up arrow.
    assert "Strength — Monday — 100% (was 0%) ↑" in text


def test_render_whatsapp_text_overall_line_with_arrow() -> None:
    report = _example_report_for_render()
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    text = helper._render_whatsapp_text(
        report, window_start=start, window_end=end
    )
    assert "*Overall: 63%* (was 45%) ↑" in text


def test_render_whatsapp_text_no_baseline_drops_was_clause() -> None:
    report = _example_report_for_render()
    report["overall_percent_prior"] = None
    for h in report["habits"]:
        h["percent_prior"] = None
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    text = helper._render_whatsapp_text(
        report, window_start=start, window_end=end
    )
    assert "was" not in text
    assert "*Overall: 63%*" in text


def test_render_whatsapp_text_does_not_include_identity_line() -> None:
    """FR-010: identity attribution belongs to the agent, not the helper."""
    report = _example_report_for_render()
    start = datetime(2026, 6, 8, tzinfo=GOLDEN_WEEK_TZ)
    end = start + timedelta(days=7)
    text = helper._render_whatsapp_text(
        report, window_start=start, window_end=end
    )
    assert "Sent by" not in text
    assert "felix-admin-habits" not in text


# ---------------------------------------------------------------------------
# build_report adds rendered_text additively (FR-007 + NFR-005 backward-compat)
# ---------------------------------------------------------------------------


def test_build_report_includes_rendered_text_field() -> None:
    """Additive ``rendered_text`` keeps the existing schema intact."""
    events = {
        "Meditate": {"kind": "daily", "title": "Meditate",
                     "current_count": 3, "prior_count": 2},
    }
    report = helper.build_report(
        events,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    # Old fields preserved.
    assert report["window_start_iso"] == "2026-06-01T00:00:00Z"
    assert report["habits"][0]["habit_title"] == "Meditate"
    assert report["habits"][0]["percent_current"] == round(100 * 3 / 7, 1)
    # New field added.
    assert isinstance(report["rendered_text"], str)
    assert report["rendered_text"].startswith("*This week*")


# ---------------------------------------------------------------------------
# CLI: --as-of + --output text (T008, T009)
# ---------------------------------------------------------------------------


def test_main_as_of_anchors_window_to_et_midnight(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """``--as-of`` Mon 06:00 ET anchors window to Mon 00:00 ET (7 days back)."""
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    write_golden_week_jsonl(mock_state_log_dir / "habits-history.jsonl")
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    # Monday 2026-06-15 06:00 ET — after the golden week ended.
    rc = helper.main(["--as-of", "2026-06-15T06:00:00-04:00"])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    # Window should be the golden week (Jun 8 → Jun 15 exclusive).
    # We expose UTC ISO; Jun 8 00:00 ET == Jun 8 04:00 UTC.
    assert payload["window_start_iso"] == "2026-06-08T04:00:00Z"
    assert payload["window_end_iso"] == "2026-06-15T04:00:00Z"


def test_main_output_text_emits_only_rendered_text(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """``--output text`` writes the rendered_text field only (no JSON)."""
    client = _build_mock_client(
        tasks_pages=[[_vk_task(habit_id=1, title="Meditate")]],
    )
    _write_habits_jsonl(
        mock_state_log_dir,
        [
            _habit_record(
                task_id=1,
                date_iso="2026-06-02",
                timestamp_iso="2026-06-02T07:00:00+00:00",
            )
        ],
    )
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main([
        "--window-end", "2026-06-08", "--output", "text",
    ])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    # Not valid JSON — it should be plain text.
    assert captured.out.startswith("*This week*")
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.out)


def test_main_as_of_rejects_naive_returns_two(monkeypatch, capsys) -> None:
    """argparse rejects naive --as-of with usage exit code 2."""
    _silence_log_action(monkeypatch)
    rc = helper.main(["--as-of", "2026-06-15T06:00:00"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "tz-aware" in captured.err or "as-of" in captured.err


# ---------------------------------------------------------------------------
# End-to-end golden-week regression (T011: FR-008 + FR-009)
# ---------------------------------------------------------------------------


def _golden_week_vk_tasks() -> list[dict]:
    """The Vikunja-side task catalog matching the golden-week fixture."""
    return [
        _vk_task(habit_id=DAILY_HABIT_ID, title="Daily walk", repeat_after=86400),
        _vk_task(
            habit_id=DAYSPEC_HABIT_ID,
            title="Strength training — Monday",
            repeat_after=0,
        ),
        # Weekly-review habit (week-bounded). With repeat_after=0 + no
        # weekday-in-title token the existing classifier reads "other" and
        # filters it. WP02 inherits that classifier as-is; the report
        # cardinal-3 behavior for weekly habits is covered downstream.
    ]


def test_golden_week_daily_habit_reports_four_of_seven(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """FR-009: daily habit completed 4/7 → percent_current == 4/7 * 100."""
    client = _build_mock_client(tasks_pages=[_golden_week_vk_tasks()])
    write_golden_week_jsonl(mock_state_log_dir / "habits-history.jsonl")
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--as-of", "2026-06-15T06:00:00-04:00"])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    daily = next(h for h in payload["habits"] if h["habit_title"] == "Daily walk")
    assert daily["completed_events_current"] == 4
    assert daily["scheduled_days_current"] == 7
    assert daily["percent_current"] == pytest.approx(round(100 * 4 / 7, 1))


def test_golden_week_day_specific_habit_reports_one_of_one(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """FR-009: day-specific habit completed Mon → percent_current == 100."""
    client = _build_mock_client(tasks_pages=[_golden_week_vk_tasks()])
    write_golden_week_jsonl(mock_state_log_dir / "habits-history.jsonl")
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--as-of", "2026-06-15T06:00:00-04:00"])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    dayspec = next(
        h for h in payload["habits"]
        if h["habit_title"] == "Strength training — Monday"
    )
    assert dayspec["scheduled_days_current"] == 1
    assert dayspec["completed_events_current"] == 1
    assert dayspec["percent_current"] == 100.0


def test_golden_week_byte_stable_json(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """NFR-001: same JSONL + same Vikunja + same --as-of → identical JSON."""
    client = _build_mock_client(
        tasks_pages=[_golden_week_vk_tasks(), _golden_week_vk_tasks()]
    )
    write_golden_week_jsonl(mock_state_log_dir / "habits-history.jsonl")
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)

    rc = helper.main(["--as-of", "2026-06-15T06:00:00-04:00"])
    out_a = capsys.readouterr().out
    assert rc == 0
    rc = helper.main(["--as-of", "2026-06-15T06:00:00-04:00"])
    out_b = capsys.readouterr().out
    assert rc == 0
    assert out_a == out_b


def test_golden_week_byte_stable_rendered_text(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """NFR-004: rendered_text is byte-stable for identical inputs."""
    client = _build_mock_client(
        tasks_pages=[_golden_week_vk_tasks(), _golden_week_vk_tasks()]
    )
    write_golden_week_jsonl(mock_state_log_dir / "habits-history.jsonl")
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)

    rc = helper.main([
        "--as-of", "2026-06-15T06:00:00-04:00", "--output", "text",
    ])
    text_a = capsys.readouterr().out
    assert rc == 0
    rc = helper.main([
        "--as-of", "2026-06-15T06:00:00-04:00", "--output", "text",
    ])
    text_b = capsys.readouterr().out
    assert rc == 0
    assert text_a == text_b
    # Reasonableness checks on the rendered text.
    assert text_a.startswith("*This week* (Jun 8–14):")


def test_golden_week_sunday_late_completion_captured(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """The Sunday completion (weekly review @ offset=6) lands inside the
    current window when --as-of is Monday-after at 06:00 ET. This pins the
    cron-timing fix (FR-001 partner): if the report ran Sun 22:00 ET, the
    Sunday completion captured AFTER 22:00 would be missed; running at
    Monday 06:00 ET ensures the Sunday completion is inside the window.
    """
    # The weekly-review habit is classified 'other' by the existing
    # classifier and excluded. Use the daily habit and add a Sunday entry
    # to verify the window includes Sunday completions.
    client = _build_mock_client(tasks_pages=[_golden_week_vk_tasks()])
    extra_sunday_iso = (
        GOLDEN_WEEK_ANCHOR + timedelta(days=6, hours=23, minutes=30)
    ).astimezone(ZoneInfo("UTC")).isoformat()
    extra_sunday_record = _habit_record(
        task_id=DAILY_HABIT_ID,
        date_iso=(GOLDEN_WEEK_ANCHOR + timedelta(days=6)).date().isoformat(),
        timestamp_iso=extra_sunday_iso,
        title="Daily walk",
    )
    write_golden_week_jsonl(mock_state_log_dir / "habits-history.jsonl")
    # Append an additional Sunday completion to the canonical fixture.
    existing = (mock_state_log_dir / "habits-history.jsonl").read_text(
        encoding="utf-8"
    )
    (mock_state_log_dir / "habits-history.jsonl").write_text(
        existing + json.dumps(extra_sunday_record) + "\n",
        encoding="utf-8",
    )
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--as-of", "2026-06-15T06:00:00-04:00"])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    daily = next(h for h in payload["habits"] if h["habit_title"] == "Daily walk")
    # 4 weekday completions + 1 added Sunday = 5 distinct dates.
    assert daily["completed_events_current"] == 5


def test_golden_week_does_not_read_done_at_regression(
    monkeypatch, capsys, mock_state_log_dir
) -> None:
    """Regression pin for #605: garbage done_at on Vikunja tasks must NOT
    affect the report — completion counts come from JSONL only.

    The ``_vk_task`` helper plants ``done_at = "9999-01-01"`` (clearly
    invalid). If this were still read, every habit would show 0% even
    where JSONL has completions. Asserting non-zero rates proves the
    canonical-store read path is in effect (FR-002, FR-009).
    """
    client = _build_mock_client(tasks_pages=[_golden_week_vk_tasks()])
    write_golden_week_jsonl(mock_state_log_dir / "habits-history.jsonl")
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--as-of", "2026-06-15T06:00:00-04:00"])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    daily = next(h for h in payload["habits"] if h["habit_title"] == "Daily walk")
    assert daily["completed_events_current"] == 4
    assert daily["percent_current"] > 0.0
