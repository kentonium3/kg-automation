"""Tests for scripts/sync/diff.py (WP03 / T010).

3-way set diff outputs. Pure-function tests; no I/O mocking needed.
Synthesizes FetchedSnapshot, TaskCacheRecord, and ProjectCacheRecord fixtures
and asserts all 5 output streams.

14 scenarios per WP03 T010 spec.
"""
from __future__ import annotations

import pytest

from scripts.sync import diff as d
from scripts.sync.diff import (
    DivergenceCandidate,
    LayerSummary,
    PerLayerSummary,
    ProjectDiffEvent,
    TRACKED_TASK_FIELDS,
    compute_divergences,
)
from scripts.sync.fetch import FetchedSnapshot
from scripts.sync.state import (
    ProjectCacheEntry,
    ProjectCacheRecord,
    TaskCacheEntry,
    TaskCacheRecord,
)


TS_OBSERVED = "2026-06-04T19:25:30Z"
FETCHED_AT = "2026-06-04T19:25:00Z"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _snapshot(*tasks, projects=None) -> FetchedSnapshot:
    if projects is None:
        projects = {}
    return FetchedSnapshot(
        tasks=tuple(tasks),
        projects=projects,
        vikunja_version="0.24.6",
        fetched_at_utc=FETCHED_AT,
    )


def _task_cache(*entries) -> TaskCacheRecord:
    return TaskCacheRecord(
        last_updated_utc="2026-06-04T19:20:30Z",
        tasks={str(e.vikunja_task_id): e for e in entries},
    )


def _task_entry(
    task_id: int,
    fields: dict,
    updated: str = "2026-06-04T18:32:00Z",
) -> TaskCacheEntry:
    return TaskCacheEntry(
        vikunja_task_id=task_id,
        fields=fields,
        vikunja_updated_at=updated,
        felix_last_observed_at="2026-06-04T18:35:00Z",
    )


def _project_cache(*entries) -> ProjectCacheRecord:
    return ProjectCacheRecord(
        last_refreshed_utc="2026-06-04T19:20:00Z",
        projects={str(pid): entry for pid, entry in entries},
    )


def _project_entry(title: str, is_archived: bool = False) -> ProjectCacheEntry:
    return ProjectCacheEntry(title=title, is_archived=is_archived)


def _run_full(snapshot, task_cache, project_cache, private_ids=None):
    """All six outputs of compute_divergences, including the seeds (WP06)."""
    kwargs = {}
    if private_ids is not None:
        kwargs["private_project_ids"] = frozenset(private_ids)
    return compute_divergences(snapshot, task_cache, project_cache, TS_OBSERVED, **kwargs)


def _run(snapshot, task_cache, project_cache, private_ids=None):
    """The five pre-WP06 outputs (seeds dropped) for the legacy scenarios."""
    return _run_full(snapshot, task_cache, project_cache, private_ids)[:5]


# ===========================================================================
# Scenario 1 — Empty inputs
# ===========================================================================


class TestEmptyInputs:
    def test_empty_snapshot_and_empty_cache_produces_all_empty_outputs(self):
        snap = _snapshot(projects={})
        tc = _task_cache()
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        assert divergences == []
        assert first_obs == set()
        assert deleted == set()
        assert proj_events == []
        assert layer_summary.task_layer.added == 0
        assert layer_summary.task_layer.removed == 0
        assert layer_summary.task_layer.updated == 0
        assert layer_summary.project_layer.added == 0
        assert layer_summary.project_layer.removed == 0
        assert layer_summary.project_layer.updated == 0


# ===========================================================================
# Scenario 2 — Pure task additions
# ===========================================================================


class TestPureTaskAdditions:
    def test_three_tasks_in_snapshot_none_in_cache(self):
        snap = _snapshot(
            {"id": 1, "title": "A", "project_id": 10, "updated": "2026-06-04T18:00:00Z"},
            {"id": 2, "title": "B", "project_id": 10, "updated": "2026-06-04T18:00:00Z"},
            {"id": 3, "title": "C", "project_id": 10, "updated": "2026-06-04T18:00:00Z"},
        )
        tc = _task_cache()  # empty
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        assert divergences == []
        assert first_obs == {1, 2, 3}
        assert deleted == set()
        assert proj_events == []
        assert layer_summary.task_layer.added == 3
        assert layer_summary.task_layer.removed == 0
        assert layer_summary.task_layer.updated == 0


# ===========================================================================
# Scenario 3 — Pure task deletions
# ===========================================================================


class TestPureTaskDeletions:
    def test_three_tasks_in_cache_none_in_snapshot(self):
        snap = _snapshot()  # no tasks
        tc = _task_cache(
            _task_entry(10, {"title": "X"}),
            _task_entry(11, {"title": "Y"}),
            _task_entry(12, {"title": "Z"}),
        )
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        assert divergences == []
        assert first_obs == set()
        assert deleted == {10, 11, 12}
        assert proj_events == []
        assert layer_summary.task_layer.added == 0
        assert layer_summary.task_layer.removed == 3
        assert layer_summary.task_layer.updated == 0


# ===========================================================================
# Scenario 4 — Pure task updates
# ===========================================================================


class TestPureTaskUpdates:
    def test_same_task_ids_different_title_produces_divergences(self):
        snap = _snapshot(
            {"id": 5, "title": "New Title", "project_id": 1, "updated": "2026-06-04T18:00:00Z"},
            {"id": 6, "title": "Another New", "project_id": 1, "updated": "2026-06-04T18:00:00Z"},
        )
        tc = _task_cache(
            _task_entry(5, {"title": "Old Title"}),
            _task_entry(6, {"title": "Old Another"}),
        )
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        assert first_obs == set()
        assert deleted == set()
        title_divs = [c for c in divergences if c.field == "title"]
        assert len(title_divs) == 2
        assert layer_summary.task_layer.added == 0
        assert layer_summary.task_layer.removed == 0
        assert layer_summary.task_layer.updated == 2


# ===========================================================================
# Scenario 5 — Mixed task scenario
# ===========================================================================


class TestMixedTaskScenario:
    def test_one_added_one_deleted_one_updated_two_unchanged(self):
        # IDs in snapshot: 1 (new), 2 (updated title), 3 (unchanged), 4 (unchanged)
        # IDs in cache: 2, 3, 4, 5 (deleted)
        # Cache entries include project_id to prevent spurious divergences.
        snap = _snapshot(
            {"id": 1, "title": "New Task", "project_id": 10, "updated": "2026-06-04T18:00:00Z"},
            {"id": 2, "title": "Changed Title", "project_id": 10, "updated": "2026-06-04T18:00:00Z"},
            {"id": 3, "title": "Same Title", "project_id": 10, "updated": "2026-06-04T18:00:00Z"},
            {"id": 4, "title": "Also Same", "project_id": 10, "updated": "2026-06-04T18:00:00Z"},
        )
        tc = _task_cache(
            _task_entry(2, {"title": "Original Title", "project_id": 10}),
            _task_entry(3, {"title": "Same Title", "project_id": 10}),
            _task_entry(4, {"title": "Also Same", "project_id": 10}),
            _task_entry(5, {"title": "Deleted Task", "project_id": 10}),
        )
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        assert first_obs == {1}
        assert deleted == {5}
        title_divs = [c for c in divergences if c.field == "title"]
        assert len(title_divs) == 1
        assert title_divs[0].vikunja_entity_id == 2
        assert layer_summary.task_layer.added == 1
        assert layer_summary.task_layer.removed == 1
        assert layer_summary.task_layer.updated == 1


# ===========================================================================
# Scenario 5b — Private-set default now sourced from the WP01 seam (T015)
# ===========================================================================


class TestPrivateSetDefaultSource:
    def test_default_sourced_from_registry(self):
        """The module default derives from ``vikunja_refs.private_project_ids()``."""
        from scripts.common import vikunja_refs

        assert d.PRIVATE_PROJECT_IDS == vikunja_refs.private_project_ids()

    def test_default_is_empty_today(self):
        """No private project is provisioned today → empty set → behavior unchanged."""
        assert d.PRIVATE_PROJECT_IDS == frozenset()

    def test_default_path_filters_nothing_today(self):
        """With the empty default (no explicit override), a content change in any
        project still produces a divergence — the privacy filter is a no-op today.
        """
        snap = _snapshot(
            {"id": 7, "title": "New Title", "project_id": 99, "updated": "2026-06-04T18:00:00Z"},
        )
        tc = _task_cache(_task_entry(7, {"title": "Old Title", "project_id": 99}))
        pc = _project_cache()
        # Note: no private_ids passed → uses the module default.
        divergences, _, _, _, _ = _run(snap, tc, pc)
        assert [c.field for c in divergences] == ["title"]


# ===========================================================================
# Scenario 6 — Privacy filter on content events; NOT on structural ops
# ===========================================================================


class TestPrivacyFilter:
    def test_private_task_update_produces_no_divergence(self):
        snap = _snapshot(
            {"id": 7, "title": "New Private Title", "project_id": 99, "updated": "2026-06-04T18:00:00Z"},
        )
        tc = _task_cache(
            _task_entry(7, {"title": "Old Private Title", "project_id": 99}),
        )
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(
            snap, tc, pc, private_ids={99}
        )

        # Content diff (in_both) is filtered for private project tasks.
        assert divergences == []
        # But structural ops are NOT filtered — task 7 is in in_both, so
        # neither first_obs nor deleted should contain it.
        assert 7 not in first_obs
        assert 7 not in deleted

    def test_private_task_addition_appears_in_first_observation(self):
        """A brand-new task in a private project still appears in first_observation_task_ids."""
        snap = _snapshot(
            {"id": 42, "title": "Private New Task", "project_id": 99, "updated": "2026-06-04T18:00:00Z"},
        )
        tc = _task_cache()  # empty cache
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(
            snap, tc, pc, private_ids={99}
        )

        assert divergences == []
        assert 42 in first_obs

    def test_private_task_deletion_appears_in_deleted_task_ids(self):
        """A removed task from a private project still appears in deleted_task_ids."""
        snap = _snapshot()  # empty snapshot
        tc = _task_cache(
            _task_entry(77, {"title": "Private Deleted", "project_id": 99}),
        )
        pc = _project_cache()
        divergences, first_obs, deleted, proj_events, layer_summary = _run(
            snap, tc, pc, private_ids={99}
        )

        assert divergences == []
        assert 77 in deleted


# ===========================================================================
# Scenario 7 — Project added
# ===========================================================================


class TestProjectAdded:
    def test_project_in_snapshot_not_in_cache_emits_project_added(self):
        snap = _snapshot(projects={99: {"id": 99, "title": "New Project", "is_archived": False}})
        tc = _task_cache()
        pc = _project_cache()  # empty
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        assert len(proj_events) == 1
        e = proj_events[0]
        assert e.type == "project_added"
        assert e.project_id == 99
        assert e.title == "New Project"
        assert layer_summary.project_layer.added == 1
        assert layer_summary.project_layer.removed == 0
        assert layer_summary.project_layer.updated == 0


# ===========================================================================
# Scenario 8 — Project removed
# ===========================================================================


class TestProjectRemoved:
    def test_project_in_cache_not_in_snapshot_emits_project_removed(self):
        snap = _snapshot(projects={})  # project 7 not in snapshot
        tc = _task_cache()
        pc = _project_cache((7, _project_entry("Old Project Name")))
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        assert len(proj_events) == 1
        e = proj_events[0]
        assert e.type == "project_removed"
        assert e.project_id == 7
        assert e.title == "Old Project Name"  # last-known title from cache
        assert layer_summary.project_layer.removed == 1
        assert layer_summary.project_layer.added == 0
        assert layer_summary.project_layer.updated == 0


# ===========================================================================
# Scenario 9 — Project renamed
# ===========================================================================


class TestProjectRenamed:
    def test_different_title_emits_project_renamed(self):
        snap = _snapshot(
            projects={1: {"id": 1, "title": "New Name", "is_archived": False}}
        )
        tc = _task_cache()
        pc = _project_cache((1, _project_entry("Old Name")))
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        renamed = [e for e in proj_events if e.type == "project_renamed"]
        assert len(renamed) == 1
        assert renamed[0].project_id == 1
        assert renamed[0].title == "New Name"
        assert layer_summary.project_layer.updated == 1


# ===========================================================================
# Scenario 10 — Project archived
# ===========================================================================


class TestProjectArchived:
    def test_false_to_true_emits_project_archived(self):
        snap = _snapshot(
            projects={2: {"id": 2, "title": "Work", "is_archived": True}}
        )
        tc = _task_cache()
        pc = _project_cache((2, _project_entry("Work", is_archived=False)))
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        archived = [e for e in proj_events if e.type == "project_archived"]
        assert len(archived) == 1
        assert archived[0].project_id == 2
        assert archived[0].is_archived is True
        assert layer_summary.project_layer.updated == 1


# ===========================================================================
# Scenario 11 — Project unarchived
# ===========================================================================


class TestProjectUnarchived:
    def test_true_to_false_emits_project_unarchived(self):
        snap = _snapshot(
            projects={3: {"id": 3, "title": "Personal", "is_archived": False}}
        )
        tc = _task_cache()
        pc = _project_cache((3, _project_entry("Personal", is_archived=True)))
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        unarchived = [e for e in proj_events if e.type == "project_unarchived"]
        assert len(unarchived) == 1
        assert unarchived[0].project_id == 3
        assert unarchived[0].is_archived is False
        assert layer_summary.project_layer.updated == 1


# ===========================================================================
# Scenario 12 — Type coercion: string cache key matches int snapshot key
# ===========================================================================


class TestTypeCoercion:
    def test_string_cache_key_matches_int_snapshot_key_no_spurious_events(self):
        # Cache stores project_id as string key "5"; snapshot uses int 5.
        snap = _snapshot(
            projects={5: {"id": 5, "title": "Stable Project", "is_archived": False}}
        )
        tc = _task_cache()
        # _project_cache stores with str(pid) key, which means key will be "5"
        pc = _project_cache((5, _project_entry("Stable Project")))
        divergences, first_obs, deleted, proj_events, layer_summary = _run(snap, tc, pc)

        # No add, no remove — just the same project with same title and archived=False.
        added = [e for e in proj_events if e.type == "project_added"]
        removed = [e for e in proj_events if e.type == "project_removed"]
        assert added == []
        assert removed == []


# ===========================================================================
# Scenario 13 — Deterministic ordering
# ===========================================================================


class TestDeterministicOrdering:
    def test_divergences_sorted_by_vikunja_entity_id_ascending(self):
        snap = _snapshot(
            {"id": 30, "title": "C Updated", "project_id": 1, "updated": "2026-06-04T18:00:00Z"},
            {"id": 10, "title": "A Updated", "project_id": 1, "updated": "2026-06-04T18:00:00Z"},
            {"id": 20, "title": "B Updated", "project_id": 1, "updated": "2026-06-04T18:00:00Z"},
        )
        tc = _task_cache(
            _task_entry(30, {"title": "C Old"}),
            _task_entry(10, {"title": "A Old"}),
            _task_entry(20, {"title": "B Old"}),
        )
        pc = _project_cache()
        divergences, _, _, _, _ = _run(snap, tc, pc)

        ids = [c.vikunja_entity_id for c in divergences]
        assert ids == sorted(ids)

    def test_project_events_sorted_by_project_id_then_type(self):
        snap = _snapshot(
            projects={
                50: {"id": 50, "title": "P50 New", "is_archived": False},  # renamed
                20: {"id": 20, "title": "P20", "is_archived": True},      # archived
                10: {"id": 10, "title": "P10 Added", "is_archived": False},  # added
            }
        )
        tc = _task_cache()
        pc = _project_cache(
            (50, _project_entry("P50 Old")),          # renamed
            (20, _project_entry("P20", False)),        # archived (false→true)
            (99, _project_entry("P99 Removed")),       # removed
        )
        _, _, _, proj_events, _ = _run(snap, tc, pc)

        keys = [(e.project_id, e.type) for e in proj_events]
        assert keys == sorted(keys)


# ===========================================================================
# Scenario 14 — TRACKED_TASK_FIELDS coverage
# ===========================================================================


class TestTrackedFieldsCoverage:
    def test_each_tracked_field_produces_divergence_when_changed(self):
        """Each field in TRACKED_TASK_FIELDS produces a DivergenceCandidate
        when changed in isolation. Tests that no field is silently skipped.
        """
        base_fields = {
            "title": "Base Title",
            "done": False,
            "due_date": "2026-06-10T17:00:00Z",
            "project_id": 1,
            "repeat": {"freq": "daily", "interval": 1},
            "repeats_from_current_date": False,
            "labels": [],
        }
        changed_values = {
            "title": "Changed Title",
            "done": True,
            "due_date": "2026-06-11T17:00:00Z",
            "project_id": 2,
            "repeat": {"freq": "weekly", "interval": 1, "by_day": ["mo"]},
            "repeats_from_current_date": True,
            "labels": [{"id": 1, "title": "tag"}],
        }

        for field_name in TRACKED_TASK_FIELDS:
            # Build a snapshot task with one field changed vs the cache.
            snap_fields = {**base_fields, field_name: changed_values[field_name]}
            snap_task = {
                "id": 100,
                "updated": "2026-06-04T18:00:00Z",
                **snap_fields,
            }
            snap = _snapshot(snap_task)
            tc = _task_cache(_task_entry(100, base_fields))
            pc = _project_cache()
            divergences, _, _, _, _ = _run(snap, tc, pc)

            field_divs = [c for c in divergences if c.field == field_name]
            assert len(field_divs) == 1, (
                f"Expected divergence for field '{field_name}', got {len(field_divs)}"
            )
            assert field_divs[0].vikunja_entity_id == 100
            assert field_divs[0].vikunja_value == changed_values[field_name]
            assert field_divs[0].felix_cached_value == base_fields[field_name]


# ===========================================================================
# Scenario 15 — The recurrence rule is tracked (WP06 / #1111, FR-016)
# ===========================================================================


def _full_fields(**overrides):
    """A cache/live field set carrying every tracked key (new shape)."""
    base = {
        "title": "Wake at 5:00 AM",
        "done": False,
        "due_date": "2026-11-20T04:59:59Z",
        "project_id": 2,
        "repeat": {"freq": "daily", "interval": 1},
        "repeats_from_current_date": False,
        "labels": [],
    }
    base.update(overrides)
    return base


def _live(task_id, **fields):
    return {"id": task_id, "updated": "2026-11-19T12:00:00Z", **fields}


class TestRuleTracking:
    def test_tracked_fields_are_the_v2_shape(self):
        assert TRACKED_TASK_FIELDS == frozenset({
            "title", "done", "due_date", "project_id",
            "repeat", "repeats_from_current_date", "labels",
        })
        # The list endpoints carry no repeats_rrule (research.md R-003); the
        # dead v1 fields are gone.
        assert "repeats_rrule" not in TRACKED_TASK_FIELDS
        assert "repeat_after" not in TRACKED_TASK_FIELDS
        assert "repeat_mode" not in TRACKED_TASK_FIELDS

    @pytest.mark.parametrize(
        "cached_rule, live_rule",
        [
            # casing
            ({"freq": "WEEKLY", "interval": 1, "by_day": ["MO"]},
             {"freq": "weekly", "interval": 1, "by_day": ["mo"]}),
            # list order
            ({"freq": "weekly", "interval": 1, "by_day": ["we", "mo"]},
             {"freq": "weekly", "interval": 1, "by_day": ["mo", "we"]}),
            # response-only read_only flag
            ({"freq": "daily", "interval": 1},
             {"freq": "daily", "interval": 1, "read_only": True}),
            # zero/empty parts and default interval
            ({"freq": "daily", "interval": 0, "count": 0, "by_month": []},
             {"freq": "daily", "interval": 1}),
            # no rule spelled two ways
            (None, {}),
        ],
    )
    def test_normal_form_equal_rules_do_not_diverge(self, cached_rule, live_rule):
        snap = _snapshot(_live(100, **_full_fields(repeat=live_rule)))
        tc = _task_cache(_task_entry(100, _full_fields(repeat=cached_rule)))
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache())
        assert divergences == []
        assert seeds == []

    def test_rule_removed_is_a_divergence_with_normalised_values(self):
        cached_rule = {"freq": "WEEKLY", "interval": 1, "by_day": ["MO"], "read_only": False}
        snap = _snapshot(_live(100, **_full_fields(repeat=None)))
        tc = _task_cache(_task_entry(100, _full_fields(repeat=cached_rule)))
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache())
        assert seeds == []
        assert len(divergences) == 1
        div = divergences[0]
        assert div.field == "repeat"
        assert div.vikunja_value is None
        assert div.felix_cached_value == {"freq": "weekly", "by_day": ["mo"], "interval": 1}

    def test_rule_changed_is_a_divergence(self):
        snap = _snapshot(_live(100, **_full_fields(repeat={"freq": "weekly", "interval": 2})))
        tc = _task_cache(_task_entry(100, _full_fields()))
        divergences, _, _, _, _, _ = _run_full(snap, tc, _project_cache())
        assert [d.field for d in divergences] == ["repeat"]
        assert divergences[0].vikunja_value == {"freq": "weekly", "interval": 2}
        assert divergences[0].felix_cached_value == {"freq": "daily", "interval": 1}

    @pytest.mark.parametrize("cached, live", [(None, False), (False, None)])
    def test_from_current_date_none_equals_false(self, cached, live):
        snap = _snapshot(_live(100, **_full_fields(repeats_from_current_date=live)))
        tc = _task_cache(_task_entry(100, _full_fields(repeats_from_current_date=cached)))
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache())
        assert divergences == []
        assert seeds == []

    def test_from_current_date_flip_is_a_divergence(self):
        snap = _snapshot(_live(100, **_full_fields(repeats_from_current_date=True)))
        tc = _task_cache(_task_entry(100, _full_fields()))
        divergences, _, _, _, _, _ = _run_full(snap, tc, _project_cache())
        assert [d.field for d in divergences] == ["repeats_from_current_date"]


# ===========================================================================
# Scenario 16 — Seed on a missing key (WP06 / R-008, post-plan finding 9)
# ===========================================================================


def _old_shape(**overrides):
    """A pre-upgrade cache entry: v1 keys, no repeat / repeats_from_current_date."""
    fields = {
        "title": "Wake at 5:00 AM",
        "done": False,
        "due_date": "2026-11-20T04:59:59Z",
        "project_id": 2,
        "repeat_after": 86400,
        "repeat_mode": 0,
        "labels": [],
    }
    fields.update(overrides)
    return fields


class TestSeedOnMissingKey:
    def test_absent_keys_seed_without_divergence(self):
        snap = _snapshot(_live(100, **_full_fields(
            repeat={"freq": "WEEKLY", "interval": 1, "by_day": ["MO"], "read_only": False},
            repeats_from_current_date=None,
        )))
        tc = _task_cache(_task_entry(100, _old_shape()))
        divergences, _, _, _, summary, seeds = _run_full(snap, tc, _project_cache())
        assert divergences == []
        assert summary.task_layer.updated == 0
        assert sorted((s.vikunja_entity_id, s.field, s.seeded_value) for s in seeds) == [
            (100, "repeat", {"freq": "weekly", "by_day": ["mo"], "interval": 1}),
            (100, "repeats_from_current_date", False),
        ]

    def test_absent_key_with_no_live_rule_seeds_none(self):
        """Finding 9: a task first observed with no rule seeds ``None``."""
        snap = _snapshot(_live(100, **_full_fields(repeat=None)))
        tc = _task_cache(_task_entry(100, _old_shape()))
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache())
        assert divergences == []
        repeat_seeds = [s for s in seeds if s.field == "repeat"]
        assert len(repeat_seeds) == 1
        assert repeat_seeds[0].seeded_value is None

    def test_present_none_is_compared_not_seeded(self):
        """A key PRESENT with value None is a real cached value: no seed."""
        snap = _snapshot(_live(100, **_full_fields()))
        tc = _task_cache(_task_entry(100, _full_fields(repeat=None)))
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache())
        assert seeds == []
        assert [d.field for d in divergences] == ["repeat"]

    def test_absent_key_seed_does_not_hide_other_divergences(self):
        snap = _snapshot(_live(100, **_full_fields(title="Renamed")))
        tc = _task_cache(_task_entry(100, _old_shape()))
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache())
        assert [d.field for d in divergences] == ["title"]
        assert {s.field for s in seeds} == {"repeat", "repeats_from_current_date"}

    def test_many_old_shape_tasks_zero_divergences(self):
        """Conflict-storm guard: N pre-upgrade entries, 0 divergences, 2N seeds."""
        n = 50
        live = [
            _live(i, **_full_fields(
                repeat={"freq": "daily", "interval": 1} if i % 2 else None,
            ))
            for i in range(1, n + 1)
        ]
        snap = _snapshot(*live)
        tc = _task_cache(*[_task_entry(i, _old_shape()) for i in range(1, n + 1)])
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache())
        assert divergences == []
        assert len(seeds) == 2 * n

    def test_private_tasks_produce_no_seeds(self):
        snap = _snapshot(_live(100, **_full_fields(project_id=99)))
        tc = _task_cache(_task_entry(100, {}))
        divergences, _, _, _, _, seeds = _run_full(snap, tc, _project_cache(), private_ids={99})
        assert divergences == []
        assert seeds == []

    def test_first_observation_tasks_produce_no_seeds(self):
        snap = _snapshot(_live(100, **_full_fields()))
        _divergences, first_obs, _, _, _, seeds = _run_full(snap, _task_cache(), _project_cache())
        assert first_obs == {100}
        assert seeds == []

    def test_seeds_sorted_deterministically(self):
        snap = _snapshot(_live(2, **_full_fields()), _live(1, **_full_fields()))
        tc = _task_cache(_task_entry(2, _old_shape()), _task_entry(1, _old_shape()))
        *_, seeds = _run_full(snap, tc, _project_cache())
        assert [(s.vikunja_entity_id, s.field) for s in seeds] == [
            (1, "repeat"), (1, "repeats_from_current_date"),
            (2, "repeat"), (2, "repeats_from_current_date"),
        ]
