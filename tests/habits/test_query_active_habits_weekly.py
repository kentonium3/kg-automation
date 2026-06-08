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

import pytest

from scripts.common.vikunja_client import (
    VikunjaBadRequestError,
    VikunjaTimeoutError,
)
from scripts.habits import query_active_habits_weekly as helper


FIXTURES_PATH = Path(__file__).parent / "fixtures" / "weekly_report_responses.json"

# Canonical anchor matching the fixture file's _meta.window_end.
CURRENT_END = datetime(2026, 6, 8, tzinfo=timezone.utc)
CURRENT_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PRIOR_END = CURRENT_START
PRIOR_START = datetime(2026, 5, 25, tzinfo=timezone.utc)


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
    raises: Optional[Exception] = None,
) -> MagicMock:
    """Synthesize a ``VikunjaClient``-shaped mock for these tests.

    Drives ``client.get`` by inspecting its ``params`` to decide whether to
    serve a done-page or an active-page. Pagination is interleaved per
    filter — the helper requests page=1, page=2, ... for done first, then
    for active.
    """
    client = MagicMock(name="VikunjaClient")
    done_pages = done_pages or []
    active_pages = active_pages or []
    done_iter = iter(done_pages)
    active_iter = iter(active_pages)

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
# query_completion_events (aggregation)
# ---------------------------------------------------------------------------


def test_query_events_single_habit_single_completion() -> None:
    client = _build_mock_client(
        done_pages=[[{"id": 1, "title": "Meditate", "repeat_after": 86400,
                      "done_at": "2026-06-02T07:00:00Z"}]],
        active_pages=[[]],
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


def test_query_events_filters_other_kind() -> None:
    client = _build_mock_client(
        done_pages=[[
            {"id": 1, "title": "Meditate", "repeat_after": 86400,
             "done_at": "2026-06-02T07:00:00Z"},
            {"id": 2, "title": "Upload cardiac lab history", "repeat_after": 0,
             "done_at": "2026-06-03T15:00:00Z"},
        ]],
        active_pages=[[]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert "Upload cardiac lab history" not in events
    assert "Meditate" in events


def test_query_events_empty_responses_returns_empty_dict() -> None:
    client = _build_mock_client(done_pages=[[]], active_pages=[[]])
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events == {}


def test_query_events_paginates_when_page_size_exact() -> None:
    full_page = [
        {
            "id": i,
            "title": "Meditate",
            "repeat_after": 86400,
            "done_at": "2026-06-02T07:00:00Z",
        }
        for i in range(200)
    ]
    second_page = [
        {
            "id": 9000,
            "title": "Meditate",
            "repeat_after": 86400,
            "done_at": "2026-06-03T07:00:00Z",
        }
    ]
    client = _build_mock_client(
        done_pages=[full_page, second_page],
        active_pages=[[]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    # Two distinct in-window completions for the same habit; the cap-at-7
    # only happens at build_report, so events tracks the raw count here.
    assert events["Meditate"]["current_count"] == 201


def test_query_events_active_fallback_creates_zero_row() -> None:
    client = _build_mock_client(
        done_pages=[[]],
        active_pages=[[{"id": 1, "title": "Meditate", "repeat_after": 86400,
                        "done_at": None}]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 0
    assert events["Meditate"]["prior_count"] == 0


def test_query_events_active_pass_skips_other_kind() -> None:
    client = _build_mock_client(
        done_pages=[[]],
        active_pages=[[
            {"id": 1, "title": "Upload cardiac lab history", "repeat_after": 0,
             "done_at": None},
        ]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events == {}


def test_query_events_skips_done_task_with_missing_done_at(capsys) -> None:
    client = _build_mock_client(
        done_pages=[[{"id": 42, "title": "Meditate", "repeat_after": 86400,
                      "done_at": None}]],
        active_pages=[[]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    # The habit row is still created (from the bucket assignment) but no
    # window increment happened.
    assert events["Meditate"]["current_count"] == 0
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()


def test_query_events_skips_zero_date_sentinel(capsys) -> None:
    client = _build_mock_client(
        done_pages=[[{"id": 42, "title": "Meditate", "repeat_after": 86400,
                      "done_at": "0001-01-01T00:00:00Z"}]],
        active_pages=[[]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 0


def test_query_events_skips_unparseable_done_at(capsys) -> None:
    client = _build_mock_client(
        done_pages=[[{"id": 42, "title": "Meditate", "repeat_after": 86400,
                      "done_at": "not-a-date"}]],
        active_pages=[[]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 0


def test_query_events_prior_count_filled_when_prior_set() -> None:
    client = _build_mock_client(
        done_pages=[[
            {"id": 1, "title": "Meditate", "repeat_after": 86400,
             "done_at": "2026-05-26T07:00:00Z"},
            {"id": 2, "title": "Meditate", "repeat_after": 86400,
             "done_at": "2026-06-02T07:00:00Z"},
        ]],
        active_pages=[[]],
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


def test_query_events_prior_window_none_skipped() -> None:
    client = _build_mock_client(
        done_pages=[[
            {"id": 1, "title": "Meditate", "repeat_after": 86400,
             "done_at": "2026-05-26T07:00:00Z"},
        ]],
        active_pages=[[]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=None,
        prior_window_end=None,
    )
    assert events["Meditate"]["prior_count"] == 0


def test_query_events_handles_naive_done_at() -> None:
    # Vikunja occasionally returns naive datetimes; helper should treat
    # them as UTC.
    client = _build_mock_client(
        done_pages=[[{"id": 1, "title": "Meditate", "repeat_after": 86400,
                      "done_at": "2026-06-02T07:00:00"}]],
        active_pages=[[]],
    )
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events["Meditate"]["current_count"] == 1


def test_query_events_handles_non_list_response() -> None:
    client = MagicMock(name="VikunjaClient")
    client.get.return_value = {"unexpected": "shape"}
    events = helper.query_completion_events(
        client,
        window_start=CURRENT_START,
        window_end=CURRENT_END,
        prior_window_start=PRIOR_START,
        prior_window_end=PRIOR_END,
    )
    assert events == {}


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


def test_main_success_returns_zero_and_emits_json(monkeypatch, capsys) -> None:
    client = _build_mock_client(
        done_pages=[[{"id": 1, "title": "Meditate", "repeat_after": 86400,
                      "done_at": "2026-06-02T07:00:00Z"}]],
        active_pages=[[]],
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


def test_main_no_baseline_flag_strips_prior(monkeypatch, capsys) -> None:
    client = _build_mock_client(done_pages=[[]], active_pages=[[]])
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08", "--no-include-baseline"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["prior_window_start_iso"] is None
    assert payload["overall_percent_prior"] is None


def test_main_default_window_end_uses_today(monkeypatch, capsys) -> None:
    client = _build_mock_client(done_pages=[[]], active_pages=[[]])
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
# Fixture-driven end-to-end tests (FR-012)
# ---------------------------------------------------------------------------


def _run_fixture(monkeypatch, fixture_name: str, fixtures: dict, capsys) -> dict:
    scenario = fixtures[fixture_name]
    client = _build_mock_client(
        done_pages=scenario["done_responses"],
        active_pages=scenario["active_responses"],
    )
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", fixtures["_meta"]["window_end"]])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    return json.loads(captured.out)


def test_fixture_weekly_normal_data(monkeypatch, fixtures, capsys) -> None:
    payload = _run_fixture(monkeypatch, "weekly_normal_data", fixtures, capsys)
    assert payload == fixtures["weekly_normal_data"]["expected_report"]


def test_fixture_weekly_cardiac_non_habit_present(monkeypatch, fixtures, capsys) -> None:
    payload = _run_fixture(monkeypatch, "weekly_cardiac_non_habit_present", fixtures, capsys)
    assert payload == fixtures["weekly_cardiac_non_habit_present"]["expected_report"]
    # FR-012 (a): explicit assertion that the cardiac task never appears.
    titles = [h["habit_title"] for h in payload["habits"]]
    assert "Upload cardiac lab history" not in titles


def test_fixture_weekly_baseline_nonzero(monkeypatch, fixtures, capsys) -> None:
    payload = _run_fixture(monkeypatch, "weekly_baseline_nonzero", fixtures, capsys)
    assert payload == fixtures["weekly_baseline_nonzero"]["expected_report"]
    # FR-012 (c): prior baseline is non-zero — regression test for the
    # 2026-06-08 uniform-zero bug.
    assert payload["overall_percent_prior"] > 0
    assert payload["habits"][0]["percent_prior"] > 0


def test_fixture_weekly_weekday_in_title_completed_on_match(
    monkeypatch, fixtures, capsys
) -> None:
    payload = _run_fixture(
        monkeypatch, "weekly_weekday_in_title_completed_on_match", fixtures, capsys
    )
    assert payload == fixtures["weekly_weekday_in_title_completed_on_match"]["expected_report"]
    # FR-012 (b): Monday/Wednesday habit done on its weekday → 100%.
    assert payload["habits"][0]["percent_current"] == 100.0


def test_fixture_weekly_weekday_in_title_skipped(monkeypatch, fixtures, capsys) -> None:
    payload = _run_fixture(monkeypatch, "weekly_weekday_in_title_skipped", fixtures, capsys)
    assert payload == fixtures["weekly_weekday_in_title_skipped"]["expected_report"]
    assert payload["habits"][0]["percent_current"] == 0.0


def test_fixture_weekly_partial_pagination(monkeypatch, fixtures, capsys) -> None:
    # Synthesize the two-page payload deterministically; the JSON fixture
    # records only the expected shape because 200+ tasks inline bloats the
    # fixture file.
    full_page = [
        {
            "id": i,
            "title": "Meditate",
            "repeat_after": 86400,
            "done_at": f"2026-06-{(i % 7) + 1:02d}T07:00:00Z",
        }
        for i in range(200)
    ]
    second_page = [
        {
            "id": 9000 + i,
            "title": "Meditate",
            "repeat_after": 86400,
            "done_at": f"2026-06-0{(i % 7) + 1}T07:00:00Z",
        }
        for i in range(5)
    ]
    client = _build_mock_client(
        done_pages=[full_page, second_page],
        active_pages=[[]],
    )
    _patch_client_with_mock(monkeypatch, mock_client=client)
    _silence_log_action(monkeypatch)
    rc = helper.main(["--window-end", "2026-06-08"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert len(payload["habits"]) == 1
    # Capped at the scheduled-day count.
    assert payload["habits"][0]["completed_events_current"] == 7


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
