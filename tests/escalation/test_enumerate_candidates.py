"""Tests for scripts.escalation.enumerate_candidates (WP02, #723).

Per the mission's testing mandate, ``filter_candidates`` is a pure function
exercised directly (no network); the I/O paths (``fetch_all_tasks``,
``main``) are exercised against a fake ``VikunjaClient`` — never real
``urllib``/network calls.

Authoritative contracts:
    - ``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/enumerate_candidates.md``
    - ``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/post-plan-review-resolutions.md``
      (H7 pre-candidates framing, H8 due-date normalization, H9 failure
      propagation)
"""
from __future__ import annotations

import json
import zoneinfo
from datetime import date

import pytest

from scripts.common.vikunja_client import VikunjaServerError
from scripts.escalation import enumerate_candidates as ec


ET = zoneinfo.ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Task factory
# ---------------------------------------------------------------------------


def make_task(
    task_id: int,
    *,
    title: str = "Task",
    done: bool = False,
    project_id: int = 4,
    priority: int = 3,
    due_date: str | None = "2026-07-01T00:00:00Z",
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "done": done,
        "project_id": project_id,
        "priority": priority,
        "due_date": due_date,
    }


TODAY = date(2026, 7, 12)


# ---------------------------------------------------------------------------
# normalize_due_date (H8)
# ---------------------------------------------------------------------------


class TestNormalizeDueDate:
    def test_null_rejected(self) -> None:
        assert ec.normalize_due_date(None) is None

    def test_empty_string_rejected(self) -> None:
        assert ec.normalize_due_date("") is None
        assert ec.normalize_due_date("   ") is None

    def test_sentinel_rejected(self) -> None:
        assert ec.normalize_due_date("0001-01-01T00:00:00Z") is None

    def test_sentinel_offset_variant_rejected_no_crash(self) -> None:
        """Regression guard (post-merge Codex review, #723): a sentinel
        spelled with an explicit +00:00 offset (rather than Z) must be
        excluded, not raise OverflowError from .astimezone() on a year-1
        datetime."""
        assert ec.normalize_due_date("0001-01-01T00:00:00+00:00") is None

    def test_sentinel_with_microseconds_variant_rejected_no_crash(self) -> None:
        assert ec.normalize_due_date("0001-01-01T00:00:00.000000Z") is None

    def test_sentinel_naive_variant_rejected_no_crash(self) -> None:
        """A naive (no tzinfo) year-1 timestamp is already excluded by the
        naive-datetime guard, but confirm it doesn't crash either."""
        assert ec.normalize_due_date("0001-01-01T00:00:00") is None

    def test_malformed_rejected(self) -> None:
        assert ec.normalize_due_date("not-a-date") is None
        assert ec.normalize_due_date("2026-13-40T00:00:00Z") is None

    def test_non_string_rejected(self) -> None:
        assert ec.normalize_due_date(12345) is None
        assert ec.normalize_due_date({"due": "2026-07-01"}) is None

    def test_naive_datetime_rejected(self) -> None:
        # No tzinfo at all (no Z, no offset) -- H8 requires an aware value.
        assert ec.normalize_due_date("2026-07-01T00:00:00") is None

    def test_valid_utc_parses_to_local_date(self) -> None:
        # Midday UTC unambiguously maps to the same ET calendar date.
        assert ec.normalize_due_date("2026-07-01T12:00:00Z") == date(2026, 7, 1)

    def test_boundary_23_00_utc_rolls_to_next_et_day(self) -> None:
        # 2026-07-01T23:00:00Z is 2026-07-01T19:00:00-04:00 (EDT) -- same ET day.
        # Use a later hour that actually crosses into the next UTC day's ET
        # equivalent: 2026-07-02T03:00:00Z == 2026-07-01T23:00:00-04:00 (EDT).
        assert ec.normalize_due_date("2026-07-02T03:00:00Z") == date(2026, 7, 1)

    def test_boundary_01_00_utc_is_previous_et_day(self) -> None:
        # 2026-07-02T01:00:00Z == 2026-07-01T21:00:00-04:00 (EDT) -- still Jul 1 ET.
        assert ec.normalize_due_date("2026-07-02T01:00:00Z") == date(2026, 7, 1)

    def test_dst_transition_case(self) -> None:
        # 2026-03-08 is the US DST "spring forward" date. 06:30 UTC on
        # 2026-03-08 is 01:30 EST (America/New_York still on EST until 2am
        # local, when it jumps to EDT). Confirm this still resolves to the
        # expected ET calendar date without raising.
        assert ec.normalize_due_date("2026-03-08T06:30:00Z") == date(2026, 3, 8)
        # 07:30 UTC on the same day is 03:30 EDT (post-transition) -- same
        # ET calendar date, distinct offset.
        assert ec.normalize_due_date("2026-03-08T07:30:00Z") == date(2026, 3, 8)


# ---------------------------------------------------------------------------
# filter_candidates -- qualification criteria (SKILL.md §1)
# ---------------------------------------------------------------------------


class TestFilterCandidatesQualification:
    def test_overdue_qualifies(self) -> None:
        task = make_task(1, due_date="2026-07-10T12:00:00Z", priority=2)
        result = ec.filter_candidates([task], TODAY, [])
        assert len(result) == 1
        assert result[0].reason == "overdue"
        assert result[0].task_id == 1

    def test_due_today_priority_high_qualifies(self) -> None:
        task = make_task(2, due_date="2026-07-12T12:00:00Z", priority=3)
        result = ec.filter_candidates([task], TODAY, [])
        assert len(result) == 1
        assert result[0].reason == "due_today_high_priority"

    def test_due_today_priority_urgent_qualifies(self) -> None:
        task = make_task(2, due_date="2026-07-12T12:00:00Z", priority=4)
        result = ec.filter_candidates([task], TODAY, [])
        assert len(result) == 1
        assert result[0].reason == "due_today_high_priority"

    def test_due_today_priority_below_3_does_not_qualify(self) -> None:
        task = make_task(3, due_date="2026-07-12T12:00:00Z", priority=2)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_due_in_future_does_not_qualify(self) -> None:
        task = make_task(4, due_date="2026-07-15T12:00:00Z", priority=4)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_priority_below_2_excluded_even_if_overdue(self) -> None:
        task = make_task(5, due_date="2026-07-01T12:00:00Z", priority=1)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_priority_zero_excluded(self) -> None:
        task = make_task(6, due_date="2026-07-01T12:00:00Z", priority=0)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_excluded_project_id_excluded(self) -> None:
        task = make_task(7, due_date="2026-07-01T12:00:00Z", priority=3, project_id=13)
        result = ec.filter_candidates([task], TODAY, [13])
        assert result == []

    def test_excluded_project_config_swap_changes_result(self) -> None:
        """Swapping the excluded-ids config changes which tasks qualify.

        Demonstrates the filter reads exclusions from its ``excluded_ids``
        parameter (which ``main()`` sources from
        ``vikunja_scope.get_escalation_excluded_project_ids()``) rather than
        a hardcoded list.
        """
        task = make_task(8, due_date="2026-07-01T12:00:00Z", priority=3, project_id=99)
        excluded_default = ec.filter_candidates([task], TODAY, [13])
        assert len(excluded_default) == 1

        excluded_swapped = ec.filter_candidates([task], TODAY, [13, 99])
        assert excluded_swapped == []

    def test_done_task_excluded(self) -> None:
        task = make_task(9, due_date="2026-07-01T12:00:00Z", priority=3, done=True)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_null_due_date_excluded(self) -> None:
        task = make_task(10, due_date=None, priority=4)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_empty_due_date_excluded(self) -> None:
        task = make_task(11, due_date="", priority=4)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_sentinel_due_date_excluded(self) -> None:
        task = make_task(12, due_date="0001-01-01T00:00:00Z", priority=4)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []

    def test_malformed_due_date_excluded(self) -> None:
        task = make_task(13, due_date="not-a-date", priority=4)
        result = ec.filter_candidates([task], TODAY, [])
        assert result == []


# ---------------------------------------------------------------------------
# filter_candidates -- day-boundary + DST (integration through the filter)
# ---------------------------------------------------------------------------


class TestFilterCandidatesDateBoundary:
    def test_23_00_utc_vs_01_00_utc_border_classified_by_et_local_date(self) -> None:
        # Both timestamps land on the ET calendar date 2026-07-11 (yesterday
        # relative to TODAY=2026-07-12), despite differing UTC calendar days.
        early = make_task(20, due_date="2026-07-12T01:00:00Z", priority=3)
        late = make_task(21, due_date="2026-07-11T23:00:00Z", priority=3)
        result = ec.filter_candidates([early, late], TODAY, [])
        reasons = {c.task_id: c.reason for c in result}
        assert reasons[20] == "overdue"
        assert reasons[21] == "overdue"

    def test_dst_transition_task_classified_correctly(self) -> None:
        dst_today = date(2026, 3, 8)
        task = make_task(22, due_date="2026-03-08T06:30:00Z", priority=3)
        result = ec.filter_candidates([task], dst_today, [])
        assert len(result) == 1
        assert result[0].reason == "due_today_high_priority"


# ---------------------------------------------------------------------------
# filter_candidates -- deterministic sort
# ---------------------------------------------------------------------------


class TestFilterCandidatesSort:
    def test_sorted_by_due_date_then_task_id(self) -> None:
        t1 = make_task(100, due_date="2026-07-05T12:00:00Z", priority=3)
        t2 = make_task(50, due_date="2026-07-01T12:00:00Z", priority=3)
        t3 = make_task(51, due_date="2026-07-01T12:00:00Z", priority=3)
        result = ec.filter_candidates([t1, t2, t3], TODAY, [])
        assert [c.task_id for c in result] == [50, 51, 100]

    def test_sort_is_stable_across_input_order(self) -> None:
        t1 = make_task(3, due_date="2026-07-01T12:00:00Z", priority=3)
        t2 = make_task(1, due_date="2026-07-01T12:00:00Z", priority=3)
        forward = ec.filter_candidates([t1, t2], TODAY, [])
        backward = ec.filter_candidates([t2, t1], TODAY, [])
        assert [c.task_id for c in forward] == [1, 3]
        assert [c.task_id for c in backward] == [1, 3]

    def test_empty_input_returns_empty_list(self) -> None:
        assert ec.filter_candidates([], TODAY, []) == []


# ---------------------------------------------------------------------------
# Fake VikunjaClient for I/O-path tests (fetch_all_tasks, main)
# ---------------------------------------------------------------------------


class FakeVikunjaClient:
    """Fake VikunjaClient: scripted per-page responses, no network."""

    def __init__(self, pages: list[list[dict]] | None = None, *, error: Exception | None = None):
        self._pages = pages if pages is not None else [[]]
        self._error = error
        self.calls: list[dict] = []

    def get(self, path: str, *, params: dict | None = None, timeout: float | None = None):
        self.calls.append({"path": path, "params": dict(params or {})})
        if self._error is not None:
            raise self._error
        page_num = int(params["page"]) if params else 1
        idx = page_num - 1
        if idx < len(self._pages):
            return self._pages[idx]
        return []


class TestFetchAllTasks:
    def test_single_page_stops_on_empty_next_page(self) -> None:
        page1 = [make_task(i) for i in range(1, 6)]
        client = FakeVikunjaClient(pages=[page1, []])
        tasks = ec.fetch_all_tasks(client)
        assert len(tasks) == 5
        assert [c["params"]["page"] for c in client.calls] == ["1", "2"]

    def test_multi_page_pagination_over_50_tasks(self) -> None:
        page1 = [make_task(i) for i in range(1, 51)]  # 50 tasks
        page2 = [make_task(i) for i in range(51, 76)]  # 25 tasks
        client = FakeVikunjaClient(pages=[page1, page2, []])
        tasks = ec.fetch_all_tasks(client)
        assert len(tasks) == 75
        assert [c["params"]["page"] for c in client.calls] == ["1", "2", "3"]
        assert all(c["params"]["per_page"] == "50" for c in client.calls)

    def test_stops_on_empty_batch_not_on_partial_full_page(self) -> None:
        """A page with exactly 50 items must NOT be treated as final.

        Regression guard for the `len(batch) < 100` bug class: with
        per_page capped at 50, a full 50-item page must trigger another
        fetch, stopping only when a page comes back genuinely empty.
        """
        page1 = [make_task(i) for i in range(1, 51)]  # exactly 50
        page2: list[dict] = []  # empty -- true stop signal
        client = FakeVikunjaClient(pages=[page1, page2])
        tasks = ec.fetch_all_tasks(client)
        assert len(tasks) == 50
        assert len(client.calls) == 2

    def test_uses_tasks_all_endpoint(self) -> None:
        client = FakeVikunjaClient(pages=[[]])
        ec.fetch_all_tasks(client)
        assert client.calls[0]["path"] == "/tasks/all"

    def test_vikunja_error_propagates(self) -> None:
        client = FakeVikunjaClient(error=VikunjaServerError("/tasks/all", status=503))
        with pytest.raises(VikunjaServerError):
            ec.fetch_all_tasks(client)


# ---------------------------------------------------------------------------
# main() -- CLI integration (fake client injected via monkeypatch)
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_vikunja_client(monkeypatch):
    """Monkeypatch VikunjaClient construction to return a FakeVikunjaClient."""

    def _install(fake_client: FakeVikunjaClient) -> None:
        monkeypatch.setattr(ec, "VikunjaClient", lambda **kwargs: fake_client)

    return _install


@pytest.fixture
def patch_excluded_ids(monkeypatch):
    """Monkeypatch get_escalation_excluded_project_ids used by main()."""

    def _install(ids: list[int]) -> None:
        monkeypatch.setattr(ec, "get_escalation_excluded_project_ids", lambda: list(ids))

    return _install


class TestMainCli:
    def test_success_empty_result_prints_empty_array(
        self, capsys, patch_vikunja_client, patch_excluded_ids
    ) -> None:
        patch_vikunja_client(FakeVikunjaClient(pages=[[]]))
        patch_excluded_ids([])
        exit_code = ec.main(["--date", "2026-07-12"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert json.loads(out) == []

    def test_success_with_candidates_sorted_json(
        self, capsys, patch_vikunja_client, patch_excluded_ids
    ) -> None:
        tasks = [
            make_task(2, due_date="2026-07-01T12:00:00Z", priority=3),
            make_task(1, due_date="2026-07-01T12:00:00Z", priority=3),
        ]
        patch_vikunja_client(FakeVikunjaClient(pages=[tasks, []]))
        patch_excluded_ids([])
        exit_code = ec.main(["--date", "2026-07-12"])
        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert [c["task_id"] for c in payload] == [1, 2]
        assert payload[0]["reason"] == "overdue"
        assert set(payload[0].keys()) == {
            "task_id",
            "project_id",
            "title",
            "due_date",
            "priority",
            "reason",
        }

    def test_vikunja_error_exits_1_and_prints_nothing_to_stdout(
        self, capsys, patch_vikunja_client, patch_excluded_ids
    ) -> None:
        patch_vikunja_client(FakeVikunjaClient(error=VikunjaServerError("/tasks/all", status=503)))
        patch_excluded_ids([])
        exit_code = ec.main(["--date", "2026-07-12"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err != ""

    def test_invalid_date_flag_exits_3(self, capsys) -> None:
        exit_code = ec.main(["--date", "not-a-date"])
        assert exit_code == 3
        assert capsys.readouterr().out == ""

    def test_default_date_uses_today_et_when_omitted(
        self, capsys, patch_vikunja_client, patch_excluded_ids, monkeypatch
    ) -> None:
        from datetime import datetime as real_datetime

        class _FrozenDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime(2026, 7, 12, 9, 0, 0, tzinfo=tz)

        monkeypatch.setattr(ec, "datetime", _FrozenDatetime)
        task = make_task(1, due_date="2026-07-12T12:00:00Z", priority=3)
        patch_vikunja_client(FakeVikunjaClient(pages=[[task], []]))
        patch_excluded_ids([])
        exit_code = ec.main([])
        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 1
        assert payload[0]["reason"] == "due_today_high_priority"

    def test_reads_exclusions_from_vikunja_scope(
        self, capsys, patch_vikunja_client, monkeypatch
    ) -> None:
        """main() sources exclusions from vikunja_scope, not a hardcoded list."""
        task = make_task(1, due_date="2026-07-01T12:00:00Z", priority=3, project_id=42)
        patch_vikunja_client(FakeVikunjaClient(pages=[[task], []]))

        calls: list[None] = []

        def _fake_get_excluded() -> list[int]:
            calls.append(None)
            return [42]

        monkeypatch.setattr(ec, "get_escalation_excluded_project_ids", _fake_get_excluded)
        exit_code = ec.main(["--date", "2026-07-12"])
        assert exit_code == 0
        assert calls, "main() must call get_escalation_excluded_project_ids()"
        payload = json.loads(capsys.readouterr().out)
        assert payload == []
