"""Tests for scripts/sync/diff.py (WP02 / T009).

Pure-function tests; no I/O mocking needed. Synthesizes FetchedDelta and
TaskCacheRecord fixtures and asserts the divergence matrix.
"""
from __future__ import annotations

import pytest

from scripts.sync import diff as d
from scripts.sync.fetch import FetchedDelta
from scripts.sync.state import TaskCacheEntry, TaskCacheRecord


TS_OBSERVED = "2026-06-04T19:25:30Z"


def _delta(*tasks) -> FetchedDelta:
    return FetchedDelta(
        tasks=tuple(tasks),
        projects={},
        vikunja_version="0.24.6",
        fetched_at_utc=TS_OBSERVED,
    )


def _cache(*entries) -> TaskCacheRecord:
    return TaskCacheRecord(
        last_updated_utc="2026-06-04T19:20:30Z",
        tasks={str(e.vikunja_task_id): e for e in entries},
    )


def _entry(task_id: int, fields: dict, updated: str = "2026-06-04T18:32:00Z") -> TaskCacheEntry:
    return TaskCacheEntry(
        vikunja_task_id=task_id,
        fields=fields,
        vikunja_updated_at=updated,
        felix_last_observed_at="2026-06-04T18:35:00Z",
    )


# ===========================================================================
# Group 1 — TRACKED_TASK_FIELDS contract
# ===========================================================================


class TestTrackedFields:
    def test_contains_expected_fields(self):
        for name in [
            "title",
            "done",
            "due_date",
            "project_id",
            "repeat_after",
            "repeat_mode",
            "labels",
        ]:
            assert name in d.TRACKED_TASK_FIELDS

    def test_is_frozenset(self):
        assert isinstance(d.TRACKED_TASK_FIELDS, frozenset)


# ===========================================================================
# Group 2 — First-observation behavior
# ===========================================================================


class TestFirstObservation:
    def test_empty_cache_all_tasks_are_first_observations(self):
        delta = _delta(
            {"id": 14, "title": "x", "done": False, "updated": "2026-06-04T18:32:00Z"},
            {"id": 15, "title": "y", "done": False, "updated": "2026-06-04T18:32:00Z"},
            {"id": 16, "title": "z", "done": False, "updated": "2026-06-04T18:32:00Z"},
        )
        cache = _cache()  # empty
        divergences, first_obs = d.compute_divergences(delta, cache, TS_OBSERVED)
        assert divergences == []
        assert sorted(first_obs) == [14, 15, 16]

    def test_partial_cache_only_new_tasks_in_first_observations(self):
        delta = _delta(
            {"id": 14, "title": "x", "done": False, "updated": "2026-06-04T18:32:00Z"},
            {"id": 15, "title": "y", "done": False, "updated": "2026-06-04T18:32:00Z"},
        )
        cache = _cache(_entry(14, {"title": "x", "done": False}))
        divergences, first_obs = d.compute_divergences(delta, cache, TS_OBSERVED)
        # Task 14 is in cache + matches → no divergence. Task 15 is new → first obs.
        assert divergences == []
        assert first_obs == [15]


# ===========================================================================
# Group 3 — Matching state produces no divergences
# ===========================================================================


class TestMatchingState:
    def test_all_fields_equal_no_divergences(self):
        delta = _delta(
            {
                "id": 14,
                "title": "Wake",
                "done": False,
                "due_date": "2026-06-10T17:00:00Z",
                "project_id": 13,
                "repeat_after": 86400,
                "repeat_mode": 0,
                "labels": [{"id": 1, "title": "morning"}],
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(
            _entry(
                14,
                {
                    "title": "Wake",
                    "done": False,
                    "due_date": "2026-06-10T17:00:00Z",
                    "project_id": 13,
                    "repeat_after": 86400,
                    "repeat_mode": 0,
                    "labels": [{"id": 1, "title": "morning"}],
                },
            )
        )
        divergences, first_obs = d.compute_divergences(delta, cache, TS_OBSERVED)
        assert divergences == []
        assert first_obs == []


# ===========================================================================
# Group 4 — Single-field divergence
# ===========================================================================


class TestSingleFieldDivergence:
    def test_due_date_diff_emits_one_candidate(self):
        delta = _delta(
            {
                "id": 14,
                "title": "x",
                "done": False,
                "due_date": "2026-06-10T17:00:00Z",
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(
            _entry(14, {"title": "x", "done": False, "due_date": "2026-06-08T17:00:00Z"})
        )
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        assert len(divergences) == 1
        c = divergences[0]
        assert c.vikunja_entity_id == 14
        assert c.field == "due_date"
        assert c.vikunja_value == "2026-06-10T17:00:00Z"
        assert c.felix_cached_value == "2026-06-08T17:00:00Z"
        assert c.ts_observed_utc == TS_OBSERVED
        assert c.vikunja_updated_at == "2026-06-04T18:32:00Z"

    def test_done_diff_emits_one_candidate(self):
        delta = _delta({"id": 14, "title": "x", "done": True, "updated": "2026-06-04T18:32:00Z"})
        cache = _cache(_entry(14, {"title": "x", "done": False}))
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        assert len(divergences) == 1
        assert divergences[0].field == "done"
        assert divergences[0].vikunja_value is True
        assert divergences[0].felix_cached_value is False


# ===========================================================================
# Group 5 — Multi-field divergence on one task
# ===========================================================================


class TestMultiFieldDivergence:
    def test_two_fields_diverged_same_task(self):
        delta = _delta(
            {
                "id": 14,
                "title": "NewTitle",
                "done": True,
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(_entry(14, {"title": "OldTitle", "done": False}))
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        fields = {c.field for c in divergences}
        assert fields == {"title", "done"}
        assert all(c.vikunja_entity_id == 14 for c in divergences)


# ===========================================================================
# Group 6 — Canonical normalization
# ===========================================================================


class TestDatetimeNormalization:
    def test_fractional_seconds_treated_as_equal(self):
        delta = _delta(
            {
                "id": 14,
                "due_date": "2026-06-04T17:00:00.000000Z",
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(_entry(14, {"due_date": "2026-06-04T17:00:00Z"}))
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        # No divergence — canonical normalization makes them equal.
        assert [c for c in divergences if c.field == "due_date"] == []

    def test_different_minute_still_divergence(self):
        delta = _delta(
            {
                "id": 14,
                "due_date": "2026-06-04T17:01:00.000000Z",
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(_entry(14, {"due_date": "2026-06-04T17:00:00Z"}))
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        due_diffs = [c for c in divergences if c.field == "due_date"]
        assert len(due_diffs) == 1


class TestListNormalization:
    def test_labels_order_insensitive(self):
        delta = _delta(
            {
                "id": 14,
                "labels": [{"id": 2, "title": "b"}, {"id": 1, "title": "a"}],
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(_entry(14, {"labels": [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]}))
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        assert [c for c in divergences if c.field == "labels"] == []

    def test_labels_added_diverges(self):
        delta = _delta(
            {
                "id": 14,
                "labels": [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}],
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(_entry(14, {"labels": [{"id": 1, "title": "a"}]}))
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        label_diffs = [c for c in divergences if c.field == "labels"]
        assert len(label_diffs) == 1


# ===========================================================================
# Group 7 — Field-missing handling
# ===========================================================================


class TestFieldMissing:
    def test_field_missing_in_vikunja_compares_against_none(self):
        # Vikunja response omits ``repeat_after`` entirely; cache has 86400.
        delta = _delta({"id": 14, "title": "x", "updated": "2026-06-04T18:32:00Z"})
        cache = _cache(_entry(14, {"title": "x", "repeat_after": 86400}))
        divergences, _ = d.compute_divergences(delta, cache, TS_OBSERVED)
        repeat_diffs = [c for c in divergences if c.field == "repeat_after"]
        assert len(repeat_diffs) == 1
        assert repeat_diffs[0].vikunja_value is None
        assert repeat_diffs[0].felix_cached_value == 86400


# ===========================================================================
# Group 8 — Privacy boundary
# ===========================================================================


class TestPrivacyBoundary:
    def test_private_project_task_produces_no_divergence(self):
        delta = _delta(
            {
                "id": 14,
                "title": "Sensitive",
                "project_id": 7,
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(_entry(14, {"title": "OldSensitive", "project_id": 7}))
        divergences, first_obs = d.compute_divergences(
            delta, cache, TS_OBSERVED, private_project_ids=frozenset({7})
        )
        assert divergences == []
        assert first_obs == []  # neither divergence nor first-observation; skipped

    def test_non_private_project_still_diverges(self):
        # Same scenario but project 7 is not private now.
        delta = _delta(
            {
                "id": 14,
                "title": "Sensitive",
                "project_id": 7,
                "updated": "2026-06-04T18:32:00Z",
            },
        )
        cache = _cache(_entry(14, {"title": "OldSensitive", "project_id": 7}))
        divergences, _ = d.compute_divergences(
            delta, cache, TS_OBSERVED, private_project_ids=frozenset()
        )
        title_diffs = [c for c in divergences if c.field == "title"]
        assert len(title_diffs) == 1


# ===========================================================================
# Group 9 — Defensive: malformed task entries
# ===========================================================================


class TestMalformedEntry:
    def test_task_without_int_id_skipped(self):
        delta = _delta({"id": "not-an-int", "title": "x", "updated": "2026-06-04T18:32:00Z"})
        cache = _cache()
        divergences, first_obs = d.compute_divergences(delta, cache, TS_OBSERVED)
        # Skipped silently; no divergence, no first observation.
        assert divergences == []
        assert first_obs == []
