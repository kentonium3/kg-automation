"""Tests for scripts.vikunja.migrate_tasks (#717).

All tests inject a fake client mirroring the real ``VikunjaClient`` surface —
``.get/.post/.put/.delete`` with leading-slash paths, list-shaped ``GET
/tasks/all`` / ``GET /projects`` / ``GET /labels``, per-task readback, empty-dict
delete result, typed exceptions for failure modes. No real network (the global
conftest urlopen guard fails loud otherwise — tests never construct a real
client).

The mission's load-bearing invariants under test:
- manifest fidelity vs the locked #717 sets + all static invariants;
- ``list_all_tasks`` pagination (>50 page + null body), done-inclusive;
- idempotency (empty plan over post-migration state → 0 mutations);
- move RMW payload includes the allowlist + a readback mismatch RAISES (#524);
- label attach skip-if-present;
- empty-check blocks a done-only task and a >50-task project;
- ordering: test-task deletes precede the project empty-check (H-5);
- --backup-ref required for deletes; felix-bot token path refused;
- preflight blocks a complex-state task and a wrong-owner/wrong-title project.
"""
from __future__ import annotations

import json

import pytest

from scripts.common.vikunja_client import VikunjaError
from scripts.vikunja import migrate_tasks as mt

MANIFEST_PATH = mt.DEFAULT_MANIFEST_PATH


# ---------------------------------------------------------------------------
# Locked expected sets (literal — drift here fails loudly, FR-008)
# ---------------------------------------------------------------------------

EXPECTED_TARGET_PROJECTS = {
    "personal": 20,
    "felix": 16,
    "intentional": 9,
    "habits": 13,
}

EXPECTED_MOVES = {
    # -> personal (20)
    42: "personal", 51: "personal", 54: "personal", 61: "personal",
    64: "personal", 72: "personal", 81: "personal",
    6: "personal", 29: "personal", 30: "personal", 31: "personal",
    32: "personal", 84: "personal", 85: "personal",
    59: "personal",
    5: "personal", 25: "personal", 33: "personal", 79: "personal",
    26: "personal", 34: "personal", 100: "personal",
    # -> felix (16)
    50: "felix", 11: "felix", 46: "felix",
    # -> intentional (9)
    1: "intentional", 2: "intentional", 13: "intentional", 86: "intentional",
}

EXPECTED_LABEL_HABIT = [14, 15, 16, 17, 18, 19, 20, 65, 75, 76, 77]
EXPECTED_DELETE_TASKS = [89, 44]
EXPECTED_DELETE_PROJECTS = [4, 2, 5, 15, 11, 12]


# ---------------------------------------------------------------------------
# Fake client + builders
# ---------------------------------------------------------------------------


class _FakeClient:
    """Records get/post/put/delete; serves canned task/project/label pages.

    ``task_pages`` / ``project_pages`` / ``label_pages`` are lists of list-pages
    served in order to successive ``GET /tasks/all`` / ``GET /projects`` /
    ``GET /labels`` calls; when exhausted each yields ``[]``. ``readbacks`` maps
    ``/tasks/{id}`` → a readback dict for post-move GETs. ``post_raises`` etc.
    inject typed exceptions.
    """

    def __init__(
        self,
        *,
        task_pages=None,
        project_pages=None,
        label_pages=None,
        readbacks=None,
        get_raises=None,
        post_raises=None,
        put_raises=None,
        delete_raises=None,
    ):
        self._task_pages = list(task_pages) if task_pages is not None else [[]]
        self._project_pages = (
            list(project_pages) if project_pages is not None else [[]]
        )
        self._label_pages = list(label_pages) if label_pages is not None else [[]]
        self._task_get_calls = 0
        self._project_get_calls = 0
        self._label_get_calls = 0
        self._readbacks = dict(readbacks or {})
        self._get_raises = get_raises
        self._post_raises = post_raises
        self._put_raises = put_raises
        self._delete_raises = delete_raises
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []
        self.put_calls: list[tuple[str, dict]] = []
        self.delete_calls: list[str] = []

    def get(self, path, *, params=None, **_kwargs):
        self.get_calls.append((path, params or {}))
        if self._get_raises is not None:
            raise self._get_raises
        if path == "/tasks/all":
            idx = self._task_get_calls
            self._task_get_calls += 1
            return self._task_pages[idx] if idx < len(self._task_pages) else []
        if path == "/projects":
            idx = self._project_get_calls
            self._project_get_calls += 1
            return (
                self._project_pages[idx]
                if idx < len(self._project_pages)
                else []
            )
        if path == "/labels":
            idx = self._label_get_calls
            self._label_get_calls += 1
            return self._label_pages[idx] if idx < len(self._label_pages) else []
        if path.startswith("/tasks/"):
            # readback GET
            return self._readbacks.get(path)
        raise AssertionError(f"unexpected GET path {path!r}")

    def post(self, path, *, json=None, **_kwargs):  # noqa: A002
        self.post_calls.append((path, json))
        if self._post_raises is not None:
            raise self._post_raises
        return {}

    def put(self, path, *, json=None, **_kwargs):  # noqa: A002
        self.put_calls.append((path, json))
        if self._put_raises is not None:
            raise self._put_raises
        return {}

    def delete(self, path, *, params=None, **_kwargs):
        self.delete_calls.append(path)
        if self._delete_raises is not None:
            raise self._delete_raises
        return {}


def _project(pid, title, *, parent=0, owner="kent", archived=False):
    owner_obj = None if owner is None else {"username": owner}
    return {
        "id": pid,
        "title": title,
        "parent_project_id": parent,
        "is_archived": archived,
        "owner": owner_obj,
    }


def _task(tid, project_id, *, title=None, labels=None, **extra):
    task = {
        "id": tid,
        "project_id": project_id,
        "title": title if title is not None else f"task-{tid}",
        "labels": labels or [],
    }
    task.update(extra)
    return task


def _habit_label(lid=700):
    return {"id": lid, "title": "t:habit"}


# The 10 touched projects, all kent-owned, correct titles/parents. Someday(4)
# child of Everyday(2).
def _all_touched_projects():
    return [
        _project(20, "Personal"),
        _project(16, "Felix / kg-automation"),
        _project(9, "Intentional LLC"),
        _project(13, "Habits"),
        _project(4, "Someday", parent=2),
        _project(2, "Everyday"),
        _project(5, "Personal Growth & Transformation"),
        _project(15, "Household"),
        _project(11, "Goals"),
        _project(12, "Research"),
    ]


def _pre_migration_tasks():
    """Live tasks BEFORE migration: every move task in a doomed/source project,
    every label task in Habits, the two test tasks present."""
    manifest = mt.load_manifest(MANIFEST_PATH)
    # Source project per task (from the manifest comments). We just need each
    # move task NOT already in its target so build_plan emits a move.
    source_for = {
        # personal-bound
        42: 2, 51: 2, 54: 2, 61: 2, 64: 2, 72: 2, 81: 2,
        6: 4, 29: 4, 30: 4, 31: 4, 32: 4, 84: 4, 85: 4,
        59: 5,
        5: 15, 25: 15, 33: 15, 79: 15,
        26: 1, 34: 1, 100: 1,
        # felix-bound
        50: 2, 11: 12, 46: 12,
        # intentional-bound
        1: 11, 2: 11, 13: 11, 86: 4,
    }
    tasks = []
    for tid, key in manifest.moves.items():
        tasks.append(_task(tid, source_for[tid]))
    for tid in manifest.label_habit:
        tasks.append(_task(tid, 13))  # in Habits, no t:habit yet
    for tid in manifest.delete_tasks:
        # 89 in Someday(4), 44 in Inbox(1)
        tasks.append(_task(tid, 4 if tid == 89 else 1))
    return tasks


def _post_migration_tasks():
    """Live tasks AFTER a complete run: move tasks in their targets, habit tasks
    labeled, test tasks gone. Doomed projects also gone (see below)."""
    manifest = mt.load_manifest(MANIFEST_PATH)
    tasks = []
    for tid, key in manifest.moves.items():
        tasks.append(_task(tid, manifest.target_projects[key]))
    for tid in manifest.label_habit:
        tasks.append(_task(tid, 13, labels=[_habit_label()]))
    # delete_tasks absent
    return tasks


def _post_migration_projects():
    """After migration: doomed projects deleted; only targets remain."""
    return [
        _project(20, "Personal"),
        _project(16, "Felix / kg-automation"),
        _project(9, "Intentional LLC"),
        _project(13, "Habits"),
    ]


# ---------------------------------------------------------------------------
# Manifest fidelity + static invariants
# ---------------------------------------------------------------------------


def test_manifest_fidelity_exact_locked_sets():
    m = mt.load_manifest(MANIFEST_PATH)
    assert m.target_projects == EXPECTED_TARGET_PROJECTS
    assert m.moves == EXPECTED_MOVES
    assert m.label_habit == EXPECTED_LABEL_HABIT
    assert m.delete_tasks == EXPECTED_DELETE_TASKS
    assert m.delete_projects == EXPECTED_DELETE_PROJECTS


def test_manifest_counts():
    m = mt.load_manifest(MANIFEST_PATH)
    assert len(m.moves) == 29
    assert len(m.label_habit) == 11
    assert len(m.delete_tasks) == 2
    assert len(m.delete_projects) == 6


def test_manifest_delete_projects_children_first():
    m = mt.load_manifest(MANIFEST_PATH)
    assert m.delete_projects.index(4) < m.delete_projects.index(2)


def _write_manifest(tmp_path, doc):
    import yaml

    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return str(p)


def _valid_manifest_doc():
    return {
        "target_projects": dict(EXPECTED_TARGET_PROJECTS),
        "moves": dict(EXPECTED_MOVES),
        "label_habit": list(EXPECTED_LABEL_HABIT),
        "delete_tasks": list(EXPECTED_DELETE_TASKS),
        "delete_projects": list(EXPECTED_DELETE_PROJECTS),
    }


def test_load_manifest_rejects_unknown_move_target(tmp_path):
    doc = _valid_manifest_doc()
    doc["moves"][42] = "bogus"
    with pytest.raises(mt.ReconcileError, match="unknown project key"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


def test_load_manifest_rejects_non_positive_id(tmp_path):
    doc = _valid_manifest_doc()
    doc["moves"][-3] = "personal"
    with pytest.raises(mt.ReconcileError, match="positive integer"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


def test_load_manifest_rejects_overlap_moves_and_label(tmp_path):
    doc = _valid_manifest_doc()
    doc["label_habit"] = list(EXPECTED_LABEL_HABIT) + [42]  # 42 is a move id
    with pytest.raises(mt.ReconcileError, match="pairwise disjoint"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


def test_load_manifest_rejects_overlap_label_and_delete(tmp_path):
    doc = _valid_manifest_doc()
    doc["delete_tasks"] = list(EXPECTED_DELETE_TASKS) + [14]  # 14 is a label id
    with pytest.raises(mt.ReconcileError, match="pairwise disjoint"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


def test_load_manifest_rejects_parent_before_child(tmp_path):
    doc = _valid_manifest_doc()
    doc["delete_projects"] = [2, 4, 5, 15, 11, 12]  # Everyday before Someday
    with pytest.raises(mt.ReconcileError, match="before its parent"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


def test_load_manifest_rejects_wrong_target_ids(tmp_path):
    doc = _valid_manifest_doc()
    doc["target_projects"]["personal"] = 999
    with pytest.raises(mt.ReconcileError, match="locked #716 ids"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


def test_load_manifest_rejects_non_mapping(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(mt.ReconcileError, match="must be a mapping"):
        mt.load_manifest(str(p))


def test_load_manifest_rejects_missing_file(tmp_path):
    with pytest.raises(mt.ReconcileError, match="could not be read"):
        mt.load_manifest(str(tmp_path / "nope.yaml"))


def test_load_manifest_rejects_bad_field_types(tmp_path):
    doc = _valid_manifest_doc()
    doc["label_habit"] = {"not": "a list"}
    with pytest.raises(mt.ReconcileError, match="'label_habit' must be a list"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


def test_load_manifest_rejects_bool_id(tmp_path):
    doc = _valid_manifest_doc()
    doc["delete_tasks"] = [True, 44]
    with pytest.raises(mt.ReconcileError, match="positive integer"):
        mt.load_manifest(_write_manifest(tmp_path, doc))


# ---------------------------------------------------------------------------
# list_all_tasks — pagination, done-inclusive, null, non-list
# ---------------------------------------------------------------------------


def test_list_all_tasks_paginates_past_50():
    page1 = [_task(i, 2) for i in range(50)]  # full page → fetch page 2
    page2 = [_task(1000, 2), _task(1001, 2)]  # short page → stop
    client = _FakeClient(task_pages=[page1, page2])
    tasks = mt.list_all_tasks(client)
    assert len(tasks) == 52
    gets = [c for c in client.get_calls if c[0] == "/tasks/all"]
    assert [c[1]["page"] for c in gets] == ["1", "2"]


def test_list_all_tasks_includes_done_tasks():
    page = [_task(1, 2, done=False), _task(2, 2, done=True)]
    client = _FakeClient(task_pages=[page])
    tasks = mt.list_all_tasks(client)
    assert {t["id"] for t in tasks} == {1, 2}


def test_list_all_tasks_null_body_is_empty():
    client = _FakeClient(task_pages=[None])
    assert mt.list_all_tasks(client) == []


def test_list_all_tasks_null_second_page_stops():
    page1 = [_task(i, 2) for i in range(50)]
    client = _FakeClient(task_pages=[page1, None])
    assert len(mt.list_all_tasks(client)) == 50


def test_list_all_tasks_non_list_raises():
    class _Bad(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            return {"not": "a list"}

    with pytest.raises(VikunjaError):
        mt.list_all_tasks(_Bad())


def test_list_all_tasks_non_dict_element_raises():
    # MED-3: a non-dict task element must fail loud, never be silently dropped.
    client = _FakeClient(task_pages=[[_task(1, 2), "not-a-dict"]])
    with pytest.raises(mt.ReconcileError, match="non-dict task element"):
        mt.list_all_tasks(client)


def test_list_all_tasks_task_missing_project_id_raises():
    # MED-3: a task lacking an integer project_id could make a doomed project
    # look empty → fail loud.
    bad = {"id": 5, "title": "no-project"}  # no project_id
    client = _FakeClient(task_pages=[[bad]])
    with pytest.raises(mt.ReconcileError, match="non-integer project_id"):
        mt.list_all_tasks(client)


def test_list_all_tasks_task_missing_id_raises():
    # MED-3: a task lacking an integer id is malformed → fail loud.
    bad = {"project_id": 2, "title": "no-id"}  # no id
    client = _FakeClient(task_pages=[[bad]])
    with pytest.raises(mt.ReconcileError, match="non-integer id"):
        mt.list_all_tasks(client)


def test_list_projects_non_dict_element_raises():
    # MED-3: a non-dict project element must fail loud.
    client = _FakeClient(project_pages=[[_project(20, "Personal"), 42]])
    with pytest.raises(mt.ReconcileError, match="non-dict project element"):
        mt.list_projects(client)


def test_list_labels_non_dict_element_raises():
    # MED-3: a non-dict label element must fail loud.
    client = _FakeClient(label_pages=[[_habit_label(), "bogus"]])
    with pytest.raises(mt.ReconcileError, match="non-dict label element"):
        mt.list_labels(client)


def test_tasks_in_project_filters():
    tasks = [_task(1, 2), _task(2, 4), _task(3, 2)]
    assert {t["id"] for t in mt.tasks_in_project(tasks, 2)} == {1, 3}


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _preflight(client_tasks, projects=None, labels=None):
    m = mt.load_manifest(MANIFEST_PATH)
    projects = projects if projects is not None else _all_touched_projects()
    labels = labels if labels is not None else [_habit_label()]
    client = _FakeClient()
    return mt.preflight(client, client_tasks, projects, labels, m), m


def test_preflight_happy_path_no_blocked():
    (habit_id, blocked), _m = _preflight(_pre_migration_tasks())
    assert habit_id == 700
    assert blocked == []


def test_preflight_missing_target_project_raises():
    projects = [p for p in _all_touched_projects() if p["id"] != 20]
    with pytest.raises(mt.ReconcileError, match="not found live"):
        _preflight(_pre_migration_tasks(), projects=projects)


def test_preflight_wrong_title_raises():
    projects = _all_touched_projects()
    projects[0] = _project(20, "WRONG TITLE")
    with pytest.raises(mt.ReconcileError, match="title mismatch"):
        _preflight(_pre_migration_tasks(), projects=projects)


def test_preflight_wrong_parent_raises():
    projects = _all_touched_projects()
    # Someday(4) should have parent 2; give it a wrong parent.
    projects[4] = _project(4, "Someday", parent=99)
    with pytest.raises(mt.ReconcileError, match="parent mismatch"):
        _preflight(_pre_migration_tasks(), projects=projects)


def test_preflight_wrong_owner_raises():
    projects = _all_touched_projects()
    projects[0] = _project(20, "Personal", owner="felix-bot")
    with pytest.raises(mt.ReconcileError, match="owner"):
        _preflight(_pre_migration_tasks(), projects=projects)


def test_preflight_archived_project_raises():
    projects = _all_touched_projects()
    projects[0] = _project(20, "Personal", archived=True)
    with pytest.raises(mt.ReconcileError, match="archived"):
        _preflight(_pre_migration_tasks(), projects=projects)


def test_preflight_habit_label_ambiguous_raises():
    with pytest.raises(mt.ReconcileError, match="exactly one"):
        _preflight(
            _pre_migration_tasks(),
            labels=[_habit_label(700), _habit_label(701)],
        )


def test_preflight_habit_label_missing_raises():
    with pytest.raises(mt.ReconcileError, match="exactly one"):
        _preflight(_pre_migration_tasks(), labels=[])


def test_preflight_habit_task_not_in_habits_raises():
    tasks = _pre_migration_tasks()
    # Move habit task 14 out of Habits(13) to some other project.
    for t in tasks:
        if t["id"] == 14:
            t["project_id"] = 999
    with pytest.raises(mt.ReconcileError, match="not Habits"):
        _preflight(tasks)


def test_preflight_habit_task_absent_raises():
    tasks = [t for t in _pre_migration_tasks() if t["id"] != 14]
    with pytest.raises(mt.ReconcileError, match="not found live"):
        _preflight(tasks)


def test_preflight_blocks_complex_state_task():
    tasks = _pre_migration_tasks()
    for t in tasks:
        if t["id"] == 42:
            t["assignees"] = [{"id": 5}]
    (_habit_id, blocked), _m = _preflight(tasks)
    assert ("move", 42, "has assignees") in blocked


def test_preflight_blocks_bucket_id():
    tasks = _pre_migration_tasks()
    for t in tasks:
        if t["id"] == 42:
            t["bucket_id"] = 8
    (_habit_id, blocked), _m = _preflight(tasks)
    assert any(tid == 42 and "bucket" in reason for _k, tid, reason in blocked)


def test_preflight_blocks_parent_link():
    tasks = _pre_migration_tasks()
    for t in tasks:
        if t["id"] == 42:
            t["parent_task_id"] = 7
    (_habit_id, blocked), _m = _preflight(tasks)
    assert any(tid == 42 and "parent" in reason for _k, tid, reason in blocked)


# ---------------------------------------------------------------------------
# build_plan — diff, idempotency
# ---------------------------------------------------------------------------


def _build_plan(tasks, projects=None, labels=None):
    m = mt.load_manifest(MANIFEST_PATH)
    projects = projects if projects is not None else _all_touched_projects()
    labels = labels if labels is not None else [_habit_label()]
    client = _FakeClient()
    habit_id, blocked = mt.preflight(client, tasks, projects, labels, m)
    return mt.build_plan(projects, tasks, labels, m, blocked, habit_id), m


def test_build_plan_pre_migration_full_plan():
    plan, _m = _build_plan(_pre_migration_tasks())
    assert len(plan.moves) == 29
    assert len(plan.labels) == 11
    assert plan.task_deletes == [89, 44]
    # All six doomed projects present + empty of unrouted tasks → all queued.
    assert [pid for pid, _t in plan.project_deletes] == [4, 2, 5, 15, 11, 12]
    assert plan.blocked == []


def test_build_plan_idempotent_over_post_state():
    # Post-migration: tasks in targets, labels present, doomed projects gone.
    plan, _m = _build_plan(
        _post_migration_tasks(), projects=_post_migration_projects()
    )
    assert plan.is_empty()
    assert plan.moves == []
    assert plan.labels == []
    assert plan.task_deletes == []
    assert plan.project_deletes == []


def test_build_plan_skips_already_correct_move():
    tasks = _pre_migration_tasks()
    # Put task 42 already in Personal(20) → skipped, not moved.
    for t in tasks:
        if t["id"] == 42:
            t["project_id"] = 20
    plan, _m = _build_plan(tasks)
    assert all(tid != 42 for tid, _f, _t in plan.moves)
    assert any(
        kind == "move" and tid == 42 for kind, tid, _r in plan.skipped
    )


def test_build_plan_skips_present_label():
    tasks = _pre_migration_tasks()
    for t in tasks:
        if t["id"] == 14:
            t["labels"] = [_habit_label()]
    plan, _m = _build_plan(tasks)
    assert all(tid != 14 for tid, _lid in plan.labels)


def test_build_plan_blocks_nonempty_doomed_project():
    tasks = _pre_migration_tasks()
    # Add an unrouted stray task to Research(12) → project delete blocked.
    tasks.append(_task(9999, 12))
    plan, _m = _build_plan(tasks)
    assert all(pid != 12 for pid, _t in plan.project_deletes)
    assert any(
        kind == "delete_project" and ident == 12 for kind, ident, _r in plan.blocked
    )


def test_build_plan_done_only_task_blocks_project():
    tasks = _pre_migration_tasks()
    # A DONE task lingering in Household(15) still counts (done-inclusive).
    tasks.append(_task(8888, 15, done=True))
    plan, _m = _build_plan(tasks)
    assert all(pid != 15 for pid, _t in plan.project_deletes)
    assert any(ident == 15 for _k, ident, _r in plan.blocked)


def test_build_plan_absent_survivor_with_doomed_present_blocks():
    # MED-4: a moves task absent from live tasks while doomed projects still
    # exist is NOT an idempotent skip — surface it BLOCKED so apply fails loud.
    tasks = [t for t in _pre_migration_tasks() if t["id"] != 42]  # drop move 42
    plan, _m = _build_plan(tasks)  # all_touched_projects → doomed still present
    assert any(
        kind == "move" and tid == 42 and reason == "survivor task absent"
        for kind, tid, reason in plan.blocked
    )
    assert all(
        not (kind == "move" and tid == 42)
        for kind, tid, _r in plan.skipped
    )


def test_build_plan_absent_survivor_with_all_doomed_gone_skips():
    # MED-4: once every doomed project is deleted (post-migration idempotent
    # state), an absent moved task is a legitimate no-op skip, not a block.
    tasks = [t for t in _post_migration_tasks() if t["id"] != 42]  # 42 gone too
    plan, _m = _build_plan(tasks, projects=_post_migration_projects())
    assert any(
        kind == "move" and tid == 42 for kind, tid, _r in plan.skipped
    )
    assert all(
        not (kind == "move" and tid == 42)
        for kind, tid, _r in plan.blocked
    )


# ---------------------------------------------------------------------------
# move_task — allowlisted RMW payload + readback
# ---------------------------------------------------------------------------


def test_move_task_payload_has_allowlist_and_project_id():
    task = _task(
        42, 2, title="Return lawn contract", description="desc",
        due_date="2026-01-01T00:00:00Z", repeat_after=86400, repeat_mode=1,
        priority=3, done=False, done_at=None, hex_color="ffaa00",
        percent_done=0.0, start_date="2026-01-01T00:00:00Z",
        end_date="2026-02-01T00:00:00Z",
    )
    readback = dict(task)
    readback["project_id"] = 20
    client = _FakeClient(readbacks={"/tasks/42": readback})
    mt.move_task(client, task, 20)
    path, payload = client.post_calls[0]
    assert path == "/tasks/42"
    assert payload["project_id"] == 20
    for f in (
        "title", "description", "due_date", "repeat_after", "repeat_mode",
        "priority", "done", "done_at", "hex_color", "percent_done",
        "start_date", "end_date",
    ):
        assert payload[f] == task[f]


def test_move_task_omits_absent_fields():
    task = _task(42, 2)  # only title + labels beyond id/project_id
    readback = dict(task)
    readback["project_id"] = 20
    client = _FakeClient(readbacks={"/tasks/42": readback})
    mt.move_task(client, task, 20)
    _path, payload = client.post_calls[0]
    assert "repeat_after" not in payload  # absent on source → not sent
    assert payload["project_id"] == 20


def test_move_task_readback_project_mismatch_raises():
    task = _task(42, 2)
    # readback still shows old project → mismatch → raise.
    client = _FakeClient(readbacks={"/tasks/42": _task(42, 2)})
    with pytest.raises(mt.ReconcileError, match="project_id is"):
        mt.move_task(client, task, 20)


def test_move_task_readback_field_changed_raises():
    task = _task(42, 2, title="Original", repeat_after=86400)
    # readback zeroed repeat_after (the #524 failure) → raise.
    readback = {"id": 42, "project_id": 20, "title": "Original", "repeat_after": 0}
    client = _FakeClient(readbacks={"/tasks/42": readback})
    with pytest.raises(mt.ReconcileError, match="repeat_after"):
        mt.move_task(client, task, 20)


def test_move_task_readback_non_object_raises():
    task = _task(42, 2)
    client = _FakeClient(readbacks={"/tasks/42": None})
    with pytest.raises(mt.ReconcileError, match="non-object"):
        mt.move_task(client, task, 20)


def test_move_task_readback_dropped_labels_raises():
    # HIGH-1: source has a label; readback shows labels: [] → the move silently
    # dropped the label → must fail loud.
    task = _task(42, 2, labels=[{"id": 7, "title": "keep-me"}])
    readback = {"id": 42, "project_id": 20, "title": "task-42", "labels": []}
    client = _FakeClient(readbacks={"/tasks/42": readback})
    with pytest.raises(mt.ReconcileError, match="label set changed"):
        mt.move_task(client, task, 20)


def test_move_task_readback_missing_labels_key_raises():
    # HIGH-1: source had labels but readback omits the 'labels' key entirely →
    # a missing/malformed labels list is a fail-loud drop.
    task = _task(42, 2, labels=[{"id": 7}])
    readback = {"id": 42, "project_id": 20, "title": "task-42"}  # no 'labels'
    client = _FakeClient(readbacks={"/tasks/42": readback})
    with pytest.raises(mt.ReconcileError, match="missing or malformed"):
        mt.move_task(client, task, 20)


def test_move_task_readback_non_dict_label_entry_raises():
    # HIGH-1: source had labels; readback labels contain a non-dict entry → the
    # shape is untrustworthy → fail loud.
    task = _task(42, 2, labels=[{"id": 7}])
    readback = {"id": 42, "project_id": 20, "title": "task-42", "labels": [7]}
    client = _FakeClient(readbacks={"/tasks/42": readback})
    with pytest.raises(mt.ReconcileError, match="missing or malformed"):
        mt.move_task(client, task, 20)


def test_move_task_readback_labels_survive_passes():
    # HIGH-1: labels present on source AND readback (same id set) → no raise.
    task = _task(42, 2, labels=[{"id": 7, "title": "keep-me"}])
    readback = {
        "id": 42,
        "project_id": 20,
        "title": "task-42",
        "labels": [{"id": 7, "title": "keep-me"}],
    }
    client = _FakeClient(readbacks={"/tasks/42": readback})
    mt.move_task(client, task, 20)  # must not raise
    assert client.post_calls[0][0] == "/tasks/42"


# ---------------------------------------------------------------------------
# apply_habit_label
# ---------------------------------------------------------------------------


def test_apply_habit_label_attaches_when_absent():
    task = _task(14, 13)
    client = _FakeClient()
    assert mt.apply_habit_label(client, task, 700) is True
    assert client.put_calls == [("/tasks/14/labels", {"label_id": 700})]


def test_apply_habit_label_skips_when_present():
    task = _task(14, 13, labels=[_habit_label()])
    client = _FakeClient()
    assert mt.apply_habit_label(client, task, 700) is False
    assert client.put_calls == []


# ---------------------------------------------------------------------------
# reconcile — full dry-run + apply, ordering, gates
# ---------------------------------------------------------------------------


def _apply_readbacks(tasks, moves):
    """Build readbacks for every move so the readback diff passes."""
    by_id = {t["id"]: t for t in tasks}
    rb = {}
    for tid, _from, to in moves:
        src = by_id[tid]
        rb[f"/tasks/{tid}"] = {**src, "project_id": to}
    return rb


def _apply_client(pre_tasks, post_tasks_for_relist):
    """Client whose /tasks/all returns pre-migration tasks on the FIRST call
    (plan) and post-migration tasks on subsequent calls (immediate re-lists at
    project delete), so the empty-check passes."""
    m = mt.load_manifest(MANIFEST_PATH)
    projects = _all_touched_projects()
    labels = [_habit_label()]

    # Compute the move set to build readbacks.
    client_probe = _FakeClient()
    habit_id, blocked = mt.preflight(client_probe, pre_tasks, projects, labels, m)
    plan = mt.build_plan(projects, pre_tasks, labels, m, blocked, habit_id)
    readbacks = _apply_readbacks(pre_tasks, plan.moves)

    class _ApplyClient(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            if path == "/tasks/all":
                idx = self._task_get_calls
                self._task_get_calls += 1
                # First /tasks/all = plan snapshot (pre). Later = re-list (post).
                return pre_tasks if idx == 0 else post_tasks_for_relist
            if path == "/projects":
                return projects
            if path == "/labels":
                return labels
            if path.startswith("/tasks/"):
                return self._readbacks.get(path)
            raise AssertionError(f"unexpected GET {path!r}")

    return _ApplyClient(readbacks=readbacks), m


def test_reconcile_dry_run_no_mutation():
    tasks = _pre_migration_tasks()

    class _C(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            if path == "/tasks/all":
                idx = self._task_get_calls
                self._task_get_calls += 1
                return tasks if idx == 0 else []
            if path == "/projects":
                return _all_touched_projects()
            if path == "/labels":
                return [_habit_label()]
            raise AssertionError(path)

    m = mt.load_manifest(MANIFEST_PATH)
    client = _C()
    plan, summary = mt.reconcile(client, m, apply=False, backup_ref=None)
    assert client.post_calls == []
    assert client.put_calls == []
    assert client.delete_calls == []
    assert summary.mode == "dry-run"
    assert len(plan.moves) == 29


def test_reconcile_apply_full_run_orders_and_counts():
    pre = _pre_migration_tasks()
    # After moves+deletes, the doomed projects are empty of any task.
    post = _post_migration_tasks()  # move tasks in targets; habit labeled; tests gone
    client, m = _apply_client(pre, post)
    plan, summary = mt.reconcile(client, m, apply=True, backup_ref="restic-abc")
    assert summary.moved == 29
    assert summary.labeled == 11
    assert summary.tasks_deleted == 2
    assert summary.projects_deleted == 6
    # Ordering: the two task-deletes happen before any project delete.
    delete_seq = client.delete_calls
    task_del_idx = [i for i, p in enumerate(delete_seq) if p.startswith("/tasks/")]
    proj_del_idx = [i for i, p in enumerate(delete_seq) if p.startswith("/projects/")]
    assert max(task_del_idx) < min(proj_del_idx)
    # Children before parents: Someday(4) deleted before Everyday(2).
    assert delete_seq.index("/projects/4") < delete_seq.index("/projects/2")


def test_reconcile_test_delete_precedes_empty_check():
    # #89 lives in Someday(4). If the empty-check ran BEFORE the test delete,
    # Someday would self-block. Prove the run succeeds (delete-first ordering).
    pre = _pre_migration_tasks()
    # Re-list AFTER deletes must show Someday empty: post has no task 89 and all
    # move tasks in targets.
    post = _post_migration_tasks()
    client, m = _apply_client(pre, post)
    _plan, summary = mt.reconcile(client, m, apply=True, backup_ref="restic-x")
    assert summary.projects_deleted == 6
    # Task 89 was deleted (a /tasks/89 DELETE issued).
    assert "/tasks/89" in client.delete_calls


def test_reconcile_apply_requires_backup_ref_for_deletes():
    pre = _pre_migration_tasks()
    post = _post_migration_tasks()
    client, m = _apply_client(pre, post)
    with pytest.raises(mt.ReconcileError, match="backup-ref is empty"):
        mt.reconcile(client, m, apply=True, backup_ref=None)
    # No mutation happened (raised before executing).
    assert client.delete_calls == []


def test_reconcile_apply_blank_backup_ref_refused():
    pre = _pre_migration_tasks()
    post = _post_migration_tasks()
    client, m = _apply_client(pre, post)
    with pytest.raises(mt.ReconcileError, match="backup-ref is empty"):
        mt.reconcile(client, m, apply=True, backup_ref="   ")


def test_reconcile_apply_blocked_raises():
    pre = _pre_migration_tasks()
    # Complex-state task 42 → blocked → apply must raise before mutating.
    for t in pre:
        if t["id"] == 42:
            t["assignees"] = [{"id": 1}]
    post = _post_migration_tasks()
    client, m = _apply_client(pre, post)
    with pytest.raises(mt.ReconcileError, match="blocked"):
        mt.reconcile(client, m, apply=True, backup_ref="restic-x")


def test_reconcile_empty_check_refuses_nonempty_at_relist():
    # Plan-time Research(12) looks empty, but the immediate pre-delete re-list
    # shows a stray task → refuse to delete (raise).
    pre = _pre_migration_tasks()
    # post re-list still has a task in project 12
    post = _post_migration_tasks() + [_task(7777, 12)]
    client, m = _apply_client(pre, post)
    with pytest.raises(mt.ReconcileError, match="still holds"):
        mt.reconcile(client, m, apply=True, backup_ref="restic-x")


def test_reconcile_empty_check_blocks_50plus_task_project():
    # A doomed project holding a >50-task set at re-list must block (proves the
    # re-list paginates and counts done-inclusive). Give Research(12) 60 tasks.
    pre = _pre_migration_tasks()
    # The 60 stray tasks appear only at the immediate pre-delete re-list (not in
    # the plan snapshot), proving the re-list paginates and counts them.
    post_relist_page1 = [_task(9000 + i, 12) for i in range(50)]
    post_relist_page2 = [_task(9050 + i, 12) for i in range(10)]

    m = mt.load_manifest(MANIFEST_PATH)
    projects = _all_touched_projects()
    labels = [_habit_label()]
    probe = _FakeClient()
    habit_id, blocked = mt.preflight(probe, pre, projects, labels, m)
    plan = mt.build_plan(projects, pre, labels, m, blocked, habit_id)
    readbacks = _apply_readbacks(pre, plan.moves)

    class _C(_FakeClient):
        def __init__(self):
            super().__init__(readbacks=readbacks)
            self._relist_pages = 0

        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            if path == "/tasks/all":
                idx = self._task_get_calls
                self._task_get_calls += 1
                if idx == 0:
                    return pre  # plan snapshot (project 12 empty of unrouted)
                # re-list: return the 60-task project 12 paginated across pages.
                page = params.get("page")
                if page == "1":
                    return post_relist_page1
                if page == "2":
                    return post_relist_page2
                return []
            if path == "/projects":
                return projects
            if path == "/labels":
                return labels
            if path.startswith("/tasks/"):
                return self._readbacks.get(path)
            raise AssertionError(path)

    client = _C()
    with pytest.raises(mt.ReconcileError, match="still holds"):
        mt.reconcile(client, m, apply=True, backup_ref="restic-x")


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------


def test_main_dry_run_exit_zero(capsys):
    tasks = _pre_migration_tasks()

    class _C(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            if path == "/tasks/all":
                idx = self._task_get_calls
                self._task_get_calls += 1
                return tasks if idx == 0 else []
            if path == "/projects":
                return _all_touched_projects()
            if path == "/labels":
                return [_habit_label()]
            raise AssertionError(path)

    rc = mt.main([], client=_C())
    assert rc == 0
    out = capsys.readouterr().out
    assert "PLAN (dry-run)" in out


def test_main_dry_run_json_exit_zero(capsys):
    tasks = _pre_migration_tasks()

    class _C(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            if path == "/tasks/all":
                idx = self._task_get_calls
                self._task_get_calls += 1
                return tasks if idx == 0 else []
            if path == "/projects":
                return _all_touched_projects()
            if path == "/labels":
                return [_habit_label()]
            raise AssertionError(path)

    rc = mt.main(["--json"], client=_C())
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["moved"] == 29


def test_main_apply_json_summary(capsys):
    pre = _pre_migration_tasks()
    post = _post_migration_tasks()
    client, _m = _apply_client(pre, post)
    rc = mt.main(
        ["--apply", "--backup-ref", "restic-abc123", "--json"], client=client
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "apply"
    assert payload["backup_ref"] == "restic-abc123"
    assert payload["projects_deleted"] == 6


def test_main_apply_human_summary_echoes_backup(capsys):
    pre = _pre_migration_tasks()
    post = _post_migration_tasks()
    client, _m = _apply_client(pre, post)
    rc = mt.main(["--apply", "--backup-ref", "ts-2026"], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "ts-2026" in out
    assert "summary (apply)" in out


def test_main_apply_missing_backup_exit_one(capsys):
    pre = _pre_migration_tasks()
    post = _post_migration_tasks()
    client, _m = _apply_client(pre, post)
    rc = mt.main(["--apply"], client=client)
    assert rc == 1
    assert "backup-ref" in capsys.readouterr().err


def test_main_felix_bot_token_path_refused_via_cli(capsys):
    rc = mt.main(["--token-file", mt.FELIX_BOT_TOKEN_FILE], client=_FakeClient())
    assert rc == 1
    assert "felix-bot" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# HIGH-2: --apply locked to the canonical kent token + endpoint (real client)
# ---------------------------------------------------------------------------


def test_apply_with_nondefault_token_file_raises(tmp_path, capsys):
    # A live --apply (real client, client is None) with a non-default token-file
    # must fail loud BEFORE building any client / touching the network.
    tf = tmp_path / "some-other-token"
    tf.write_text("whatever\n", encoding="utf-8")
    rc = mt.main(["--apply", "--backup-ref", "restic-x", "--token-file", str(tf)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "locked to the canonical kent token" in err


def test_apply_with_explicit_base_url_raises(tmp_path, monkeypatch, capsys):
    # A live --apply with the default token-file but an explicit --base-url must
    # fail loud (non-canonical endpoint) absent the escape hatch.
    tf = tmp_path / "vikunja-api-kent"
    tf.write_text("kent-secret\n", encoding="utf-8")
    monkeypatch.setattr(mt, "DEFAULT_KENT_TOKEN_FILE", str(tf))
    rc = mt.main(
        [
            "--apply",
            "--backup-ref",
            "restic-x",
            "--token-file",
            str(tf),
            "--base-url",
            "https://evil/api/v1",
        ]
    )
    assert rc == 1
    assert "canonical Vikunja base URL" in capsys.readouterr().err


def test_apply_with_default_token_proceeds(tmp_path, monkeypatch):
    # A live --apply with the default token-file and no --base-url passes the
    # HIGH-2 lock and proceeds to build + run the (monkeypatched) client.
    tf = tmp_path / "vikunja-api-kent"
    tf.write_text("kent-secret\n", encoding="utf-8")
    monkeypatch.setattr(mt, "DEFAULT_KENT_TOKEN_FILE", str(tf))

    class _FakeVC:
        def __init__(self, *, base_url=None, token=None):
            pass

        def get(self, path, *, params=None, **_kwargs):
            # Post-migration state → clean plan, no deletes, preflight passes.
            if path == "/tasks/all":
                return _post_migration_tasks()
            if path == "/projects":
                return _post_migration_projects()
            if path == "/labels":
                return [_habit_label()]
            return None

    import scripts.common.vikunja_client as vc_mod

    monkeypatch.setattr(vc_mod, "VikunjaClient", _FakeVC)
    # No deletes in a post-migration plan, so --backup-ref is not required.
    rc = mt.main(["--apply", "--token-file", str(tf)])
    assert rc == 0


def test_apply_nonstandard_endpoint_flag_permits_override(tmp_path, monkeypatch):
    # The escape hatch lets an --apply run use a non-default token-file AND an
    # explicit --base-url.
    tf = tmp_path / "some-other-token"
    tf.write_text("kent-secret\n", encoding="utf-8")

    class _FakeVC:
        def __init__(self, *, base_url=None, token=None):
            pass

        def get(self, path, *, params=None, **_kwargs):
            if path == "/tasks/all":
                return _post_migration_tasks()
            if path == "/projects":
                return _post_migration_projects()
            if path == "/labels":
                return [_habit_label()]
            return None

    import scripts.common.vikunja_client as vc_mod

    monkeypatch.setattr(vc_mod, "VikunjaClient", _FakeVC)
    rc = mt.main(
        [
            "--apply",
            "--allow-nonstandard-endpoint",
            "--token-file",
            str(tf),
            "--base-url",
            "https://x/api/v1",
        ]
    )
    assert rc == 0


def test_dry_run_with_nondefault_token_not_locked(tmp_path, monkeypatch):
    # Dry-run (read-only, no --apply) may use a non-default token-file / base URL
    # — the HIGH-2 lock only applies to a mutating --apply.
    tf = tmp_path / "some-other-token"
    tf.write_text("kent-secret\n", encoding="utf-8")

    class _FakeVC:
        def __init__(self, *, base_url=None, token=None):
            pass

        def get(self, path, *, params=None, **_kwargs):
            if path == "/tasks/all":
                return _post_migration_tasks()
            if path == "/projects":
                return _post_migration_projects()
            if path == "/labels":
                return [_habit_label()]
            return None

    import scripts.common.vikunja_client as vc_mod

    monkeypatch.setattr(vc_mod, "VikunjaClient", _FakeVC)
    rc = mt.main(
        ["--token-file", str(tf), "--base-url", "https://x/api/v1"]
    )
    assert rc == 0


def test_read_token_file_refuses_felix_bot_path():
    with pytest.raises(mt.ReconcileError, match="felix-bot"):
        mt._read_token_file(mt.FELIX_BOT_TOKEN_FILE)


def test_read_token_file_missing_names_credential(tmp_path):
    with pytest.raises(mt.ReconcileError, match="vikunja-api-kent"):
        mt._read_token_file(str(tmp_path / "absent"))


def test_read_token_file_blank_raises(tmp_path):
    blank = tmp_path / "blank"
    blank.write_text("   \n", encoding="utf-8")
    with pytest.raises(mt.ReconcileError, match="empty"):
        mt._read_token_file(str(blank))


def test_read_token_file_reads_token(tmp_path):
    tf = tmp_path / "vikunja-api-kent"
    tf.write_text("kent-secret\n", encoding="utf-8")
    assert mt._read_token_file(str(tf)) == "kent-secret\n"


def test_main_vikunja_error_exit_one(capsys):
    client = _FakeClient(get_raises=VikunjaError(path="/tasks/all", status=500))
    rc = mt.main([], client=client)
    assert rc == 1
    assert "VikunjaError" in capsys.readouterr().err


def test_main_preflight_wrong_owner_exit_one(capsys):
    tasks = _pre_migration_tasks()
    projects = _all_touched_projects()
    projects[0] = _project(20, "Personal", owner="felix-bot")

    class _C(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            if path == "/tasks/all":
                idx = self._task_get_calls
                self._task_get_calls += 1
                return tasks if idx == 0 else []
            if path == "/projects":
                return projects
            if path == "/labels":
                return [_habit_label()]
            raise AssertionError(path)

    rc = mt.main([], client=_C())
    assert rc == 1
    assert "owner" in capsys.readouterr().err.lower()


def test_list_projects_non_list_raises():
    class _Bad(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            return {"not": "a list"}

    with pytest.raises(VikunjaError):
        mt.list_projects(_Bad())


def test_list_labels_non_list_raises():
    class _Bad(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            return {"not": "a list"}

    with pytest.raises(VikunjaError):
        mt.list_labels(_Bad())


def test_main_dry_run_human_shows_skipped_and_blocked(capsys):
    tasks = _pre_migration_tasks()
    # Make task 42 already-correct (skipped) and task 51 complex-state (blocked).
    for t in tasks:
        if t["id"] == 42:
            t["project_id"] = 20
        if t["id"] == 51:
            t["assignees"] = [{"id": 1}]

    class _C(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            if path == "/tasks/all":
                idx = self._task_get_calls
                self._task_get_calls += 1
                return tasks if idx == 0 else []
            if path == "/projects":
                return _all_touched_projects()
            if path == "/labels":
                return [_habit_label()]
            raise AssertionError(path)

    rc = mt.main([], client=_C())
    assert rc == 0
    out = capsys.readouterr().out
    assert "skip" in out
    assert "BLOCK" in out


def test_main_generic_exception_exit_one(capsys):
    class _C(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            raise RuntimeError("boom")

    rc = mt.main([], client=_C())
    assert rc == 1
    assert "RuntimeError" in capsys.readouterr().err


def test_move_task_non_integer_id_raises():
    with pytest.raises(mt.ReconcileError, match="non-integer id"):
        mt.move_task(_FakeClient(), {"id": "x", "project_id": 2}, 20)


def test_apply_habit_label_non_integer_id_raises():
    with pytest.raises(mt.ReconcileError, match="non-integer id"):
        mt.apply_habit_label(_FakeClient(), {"id": None}, 700)


def test_main_builds_client_from_token_file(tmp_path, monkeypatch):
    tf = tmp_path / "vikunja-api-kent"
    tf.write_text("kent-secret-token\n", encoding="utf-8")
    captured = {}

    class _FakeVC:
        def __init__(self, *, base_url=None, token=None):
            captured["base_url"] = base_url
            captured["token"] = token

        def get(self, path, *, params=None, **_kwargs):
            if path == "/tasks/all":
                # Post-migration state → clean dry-run plan, preflight passes.
                return _post_migration_tasks()
            if path == "/projects":
                return _post_migration_projects()
            if path == "/labels":
                return [_habit_label()]
            return None

    import scripts.common.vikunja_client as vc_mod

    monkeypatch.setattr(vc_mod, "VikunjaClient", _FakeVC)
    rc = mt.main(
        ["--token-file", str(tf), "--base-url", "https://x/api/v1"]
    )
    assert rc == 0
    assert captured["token"] == "kent-secret-token\n"
    assert captured["base_url"] == "https://x/api/v1"
