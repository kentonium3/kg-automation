"""Tests for scripts.vikunja.create_saved_filters (#718).

All tests inject a fake client mirroring the real ``VikunjaClient`` surface —
``.get/.put`` with leading-slash paths, list-shaped paginated ``GET /projects``
and ``GET /labels``, per-filter ``GET /filters/{id}`` readback, and per-pseudo
``GET /projects/{pseudo}/tasks`` count queries. No real network (the global
conftest urlopen guard would fail loudly; tests never construct a real client).

The fixture encodes the live traps this helper must survive:
- labels resolved by TITLE to their live ids (never hardcoded);
- saved filters surfacing as negative-id pseudo-projects (``filter_id = -id-1``);
- a felix-bot-owned pseudo-filter that per-user matching must ignore;
- Favorites (``-1``) which is never treated as an existing canonical filter;
- a task count of 0 which is legitimate, not a failure.
"""
from __future__ import annotations

import json
import os

import pytest

from scripts.common.vikunja_client import VikunjaError, VikunjaServerError
from scripts.vikunja import create_saved_filters as csf

# Canonical set (literal — drift here fails loudly).
EXPECTED_TITLES = [
    "Today",
    "Habits",
    "Upcoming",
    "High Priority",
    "Edge + Schedule",
]

# Live-verified label ids used across tests.
LABELS = {"t:habit": 26, "f:3-edge": 20, "q:schedule": 23}

EXPECTED_QUERIES = {
    # `< now/d+1d` = overdue + all of today (a task due later today must not be
    # dropped); `<= now/d` would be wrong. See design doc "Today window".
    "Today": "due_date < now/d+1d && done = false",
    "Habits": "labels in 26 && done = false",
    "Upcoming": "due_date > now/d && due_date < now+7d && done = false",
    "High Priority": "priority >= 4 && done = false",
    "Edge + Schedule": "labels in 20 && labels in 23 && done = false",
}


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


class _FakeClient:
    """Serves canned project/label pages, filter readbacks, and task counts.

    ``project_pages`` / ``label_pages`` are lists of list-pages served in order
    to successive ``GET /projects`` / ``GET /labels`` calls (``[]`` once
    exhausted). ``filters`` maps ``/filters/{id}`` -> readback dict.
    ``task_counts`` maps a pseudo-project id -> a canned task list length.
    ``put_response`` overrides the create response; ``put_raises`` (after N)
    and ``get_raises`` (after N) inject typed failures.
    """

    def __init__(
        self,
        *,
        project_pages=None,
        label_pages=None,
        filters=None,
        task_counts=None,
        put_response=None,
        put_raises=None,
        put_raises_after=0,
        get_raises=None,
        get_raises_after=0,
        tasks_raise=False,
        next_id=100,
    ):
        self._project_pages = list(project_pages) if project_pages is not None else [[]]
        self._label_pages = list(label_pages) if label_pages is not None else [[]]
        self._project_calls = 0
        self._label_calls = 0
        self._filters = dict(filters or {})
        self._task_counts = dict(task_counts or {})
        self._tasks_raise = tasks_raise
        self._put_response = put_response
        self._put_raises = put_raises
        self._put_raises_after = put_raises_after
        self._put_seen = 0
        self._get_raises = get_raises
        self._get_raises_after = get_raises_after
        self._get_seen = 0
        self._next_id = next_id
        self.get_calls: list[tuple[str, dict]] = []
        self.put_calls: list[tuple[str, dict]] = []

    def get(self, path, *, params=None, **_kwargs):
        self.get_calls.append((path, params or {}))
        if self._get_raises is not None:
            self._get_seen += 1
            if self._get_seen > self._get_raises_after:
                raise self._get_raises
        if path == "/projects":
            idx = self._project_calls
            self._project_calls += 1
            return self._project_pages[idx] if idx < len(self._project_pages) else []
        if path == "/labels":
            idx = self._label_calls
            self._label_calls += 1
            return self._label_pages[idx] if idx < len(self._label_pages) else []
        if path.startswith("/filters/"):
            return self._filters.get(path)
        if path.startswith("/projects/") and path.endswith("/tasks"):
            if self._tasks_raise:
                raise VikunjaError(path=path, status=500)
            pseudo = int(path.split("/")[2])
            count = self._task_counts.get(pseudo, 0)
            return [{"id": i} for i in range(count)]
        raise AssertionError(f"unexpected GET path {path!r}")

    def put(self, path, *, json=None, **_kwargs):  # noqa: A002 - mirror client
        self.put_calls.append((path, json))
        if self._put_raises is not None:
            self._put_seen += 1
            if self._put_seen > self._put_raises_after:
                raise self._put_raises
        if self._put_response is not None:
            return self._put_response
        assigned = self._next_id
        self._next_id += 1
        return {"id": assigned, "title": json["title"], "owner": None}


def _labels_page(mapping=LABELS):
    return [{"id": lid, "title": title} for title, lid in mapping.items()]


def _saved_filter_project(filter_id, title, *, owner="kent"):
    """A saved filter as it appears in GET /projects (negative pseudo id)."""
    pseudo = -filter_id - 1
    owner_obj = None if owner is None else {"username": owner}
    return {"id": pseudo, "title": title, "owner": owner_obj}


def _filter_readback(query):
    return {"filters": {"filter": query, "filter_include_nulls": False}}


# ---------------------------------------------------------------------------
# Query resolution
# ---------------------------------------------------------------------------


def test_resolve_query_substitutes_label_ids():
    q = csf.resolve_query("labels in {label:t:habit} && done = false", LABELS)
    assert q == "labels in 26 && done = false"


def test_resolve_query_missing_label_fails_loud():
    with pytest.raises(csf.SavedFilterError, match="t:habit"):
        csf.resolve_query("labels in {label:t:habit}", {"f:3-edge": 20})


def test_all_canonical_queries_resolve_as_expected():
    for spec in csf.FILTER_SPECS:
        resolved = csf.resolve_query(spec.query_template, LABELS)
        assert resolved == EXPECTED_QUERIES[spec.title]


def test_someday_is_not_in_canonical_set():
    titles = [s.title for s in csf.FILTER_SPECS]
    assert titles == EXPECTED_TITLES
    assert "Someday" not in titles


def test_today_window_is_overdue_plus_today_not_start_of_day():
    # Regression: `<= now/d` silently drops tasks due later today. The canonical
    # Today query must be the `< now/d+1d` (overdue + all of today) window.
    today = next(s for s in csf.FILTER_SPECS if s.title == "Today")
    assert today.query_template == "due_date < now/d+1d && done = false"
    assert "<= now/d " not in today.query_template


# ---------------------------------------------------------------------------
# Label map
# ---------------------------------------------------------------------------


def test_build_label_map_skips_non_int_ids():
    client = _FakeClient(
        label_pages=[[{"id": "x", "title": "bad"}, {"id": 7, "title": "ok"}]]
    )
    assert csf.build_label_map(client) == {"ok": 7}


def test_build_label_map_ambiguous_title_fails():
    client = _FakeClient(
        label_pages=[[{"id": 1, "title": "dup"}, {"id": 2, "title": "dup"}]]
    )
    with pytest.raises(csf.SavedFilterError, match="Ambiguous label"):
        csf.build_label_map(client)


def test_pagination_accumulates_full_label_page():
    page1 = [{"id": i, "title": f"l{i}"} for i in range(csf._PAGE_SIZE)]
    page2 = [{"id": 999, "title": "last"}]
    client = _FakeClient(label_pages=[page1, page2])
    result = csf.build_label_map(client)
    assert result["last"] == 999
    assert len(result) == csf._PAGE_SIZE + 1


# ---------------------------------------------------------------------------
# Dry-run plan
# ---------------------------------------------------------------------------


def test_dry_run_plans_all_five_no_mutation():
    client = _FakeClient(project_pages=[[]], label_pages=[_labels_page()])
    outcomes, plan = csf.create_filters(client, dry_run=True)
    assert [o.title for o in outcomes] == EXPECTED_TITLES
    assert all(o.action == "created" for o in outcomes)
    assert len(plan.to_create) == 5
    assert client.put_calls == []  # nothing created


# ---------------------------------------------------------------------------
# Apply — create pass
# ---------------------------------------------------------------------------


def test_apply_creates_all_five_with_resolved_queries():
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        task_counts={-101: 4, -102: 8},  # first two get ids 100,101 -> pseudo -101,-102
        next_id=100,
    )
    outcomes, _ = csf.create_filters(client, dry_run=False)
    assert len(client.put_calls) == 5
    # Every created filter carried the correctly-resolved snake_case query.
    sent = {body["title"]: body["filters"]["filter"] for _p, body in client.put_calls}
    assert sent == EXPECTED_QUERIES
    # filter_include_nulls is always False (no is-null semantics available).
    assert all(
        body["filters"]["filter_include_nulls"] is False
        for _p, body in client.put_calls
    )
    assert all(o.action == "created" for o in outcomes)


def test_apply_reports_task_counts_including_zero():
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        task_counts={-101: 4},  # Today -> id100 -> pseudo -101 -> 4 tasks
        next_id=100,
    )
    outcomes, _ = csf.create_filters(client, dry_run=False)
    by_title = {o.title: o for o in outcomes}
    assert by_title["Today"].task_count == 4
    # Habits gets id 101 -> pseudo -102 -> not in task_counts -> 0 (legitimate).
    assert by_title["Habits"].task_count == 0


def test_verify_count_best_effort_never_fails_create():
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        tasks_raise=True,  # count query blows up
        next_id=100,
    )
    outcomes, _ = csf.create_filters(client, dry_run=False)
    assert all(o.action == "created" for o in outcomes)
    assert all(o.task_count is None for o in outcomes)  # swallowed


# ---------------------------------------------------------------------------
# Idempotency + drift
# ---------------------------------------------------------------------------


def test_idempotent_all_present_matching_queries():
    # Every canonical filter already exists (ids 10..14), each with the exact
    # canonical query -> all already-present, nothing created.
    proj_page = [
        _saved_filter_project(fid, title)
        for fid, title in zip(range(10, 15), EXPECTED_TITLES)
    ]
    filters = {
        f"/filters/{fid}": _filter_readback(EXPECTED_QUERIES[title])
        for fid, title in zip(range(10, 15), EXPECTED_TITLES)
    }
    client = _FakeClient(
        project_pages=[proj_page], label_pages=[_labels_page()], filters=filters
    )
    outcomes, plan = csf.create_filters(client, dry_run=False)
    assert plan.to_create == []
    assert all(o.action == "already-present" for o in outcomes)
    assert client.put_calls == []


def test_drift_fails_loud_never_clobbers():
    proj_page = [_saved_filter_project(10, "Today")]
    filters = {"/filters/10": _filter_readback("done = true")}  # wrong query
    client = _FakeClient(
        project_pages=[proj_page], label_pages=[_labels_page()], filters=filters
    )
    with pytest.raises(csf.SavedFilterError, match="canonical query"):
        csf.create_filters(client, dry_run=False)
    assert client.put_calls == []


def test_drift_tolerates_whitespace_differences():
    # Same query, extra spaces in the stored form -> matches (not drift).
    proj_page = [_saved_filter_project(10, "Today")]
    filters = {"/filters/10": _filter_readback("due_date  <  now/d+1d   && done = false")}
    client = _FakeClient(
        project_pages=[proj_page], label_pages=[_labels_page()], filters=filters
    )
    outcomes, _ = csf.create_filters(client, dry_run=True)
    today = next(o for o in outcomes if o.title == "Today")
    assert today.action == "already-present"


def test_readback_missing_query_fails_loud():
    proj_page = [_saved_filter_project(10, "Today")]
    filters = {"/filters/10": {"filters": {}}}  # no 'filter' key
    client = _FakeClient(
        project_pages=[proj_page], label_pages=[_labels_page()], filters=filters
    )
    with pytest.raises(csf.SavedFilterError, match="no readable query"):
        csf.create_filters(client, dry_run=True)


# ---------------------------------------------------------------------------
# Ownership + pseudo-project edge cases
# ---------------------------------------------------------------------------


def test_felix_bot_owned_filter_is_not_treated_as_existing():
    # A felix-bot-owned pseudo-filter titled 'Today' must be ignored (per-user);
    # the canonical kent-owned 'Today' is still created.
    proj_page = [_saved_filter_project(10, "Today", owner="felix-bot")]
    client = _FakeClient(project_pages=[proj_page], label_pages=[_labels_page()])
    outcomes, plan = csf.create_filters(client, dry_run=True)
    assert "Today" in [s.title for s, _q in plan.to_create]
    today = next(o for o in outcomes if o.title == "Today")
    assert today.action == "created"


def test_unresolved_owner_on_canonical_title_fails_loud():
    # A canonical-titled negative-id filter with no owner must not be silently
    # skipped (that would risk creating a duplicate) — fail loud.
    proj_page = [{"id": -11, "title": "Today", "owner": None}]
    client = _FakeClient(project_pages=[proj_page], label_pages=[_labels_page()])
    with pytest.raises(csf.SavedFilterError, match="unresolved owner"):
        csf.create_filters(client, dry_run=True)


def test_unresolved_owner_on_noncanonical_title_ignored():
    # A random unknown-owner pseudo-filter is none of this helper's business.
    proj_page = [{"id": -11, "title": "Some Other Filter", "owner": None}]
    client = _FakeClient(project_pages=[proj_page], label_pages=[_labels_page()])
    _outcomes, plan = csf.create_filters(client, dry_run=True)
    assert len(plan.to_create) == 5


def test_create_response_without_int_id_fails_loud():
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        put_response={"title": "Today", "owner": None},  # no id
    )
    with pytest.raises(csf.SavedFilterError, match="no integer id"):
        csf.create_filters(client, dry_run=False)


def test_favorites_pseudo_id_never_matched():
    # Favorites at -1 titled like a canonical filter must never count as existing.
    proj_page = [{"id": -1, "title": "Today", "owner": {"username": "kent"}}]
    client = _FakeClient(project_pages=[proj_page], label_pages=[_labels_page()])
    _outcomes, plan = csf.create_filters(client, dry_run=True)
    assert "Today" in [s.title for s, _q in plan.to_create]


def test_ambiguous_existing_saved_filter_fails():
    # Two kent-owned pseudo-filters titled 'Today' with different ids.
    proj_page = [
        _saved_filter_project(10, "Today"),
        _saved_filter_project(11, "Today"),
    ]
    client = _FakeClient(project_pages=[proj_page], label_pages=[_labels_page()])
    with pytest.raises(csf.SavedFilterError, match="Ambiguous existing"):
        csf.create_filters(client, dry_run=True)


# ---------------------------------------------------------------------------
# Missing label / API contract failures
# ---------------------------------------------------------------------------


def test_missing_required_label_aborts():
    # t:habit absent -> the Habits/Edge queries cannot resolve.
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page({"f:3-edge": 20, "q:schedule": 23})],
    )
    with pytest.raises(csf.SavedFilterError, match="t:habit"):
        csf.create_filters(client, dry_run=True)


def test_non_list_projects_body_is_contract_violation():
    client = _FakeClient(project_pages=[{"not": "a list"}], label_pages=[_labels_page()])
    with pytest.raises(VikunjaError):
        csf.create_filters(client, dry_run=True)


def test_create_non_object_response_fails():
    client = _FakeClient(
        project_pages=[[]], label_pages=[_labels_page()], put_response="oops"
    )
    with pytest.raises(csf.SavedFilterError, match="non-object"):
        csf.create_filters(client, dry_run=False)


def test_partial_progress_attached_on_mid_run_failure():
    # Second create raises -> first reported created, remainder skipped.
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        put_raises=VikunjaServerError(path="/filters", status=500),
        put_raises_after=1,
        next_id=100,
    )
    with pytest.raises(VikunjaServerError) as excinfo:
        csf.create_filters(client, dry_run=False)
    partial = getattr(excinfo.value, "filter_outcomes")
    actions = {o.title: o.action for o in partial}
    assert actions["Today"] == "created"
    assert actions["Upcoming"] == "skipped"
    assert actions["Edge + Schedule"] == "skipped"


# ---------------------------------------------------------------------------
# Token-file guard
# ---------------------------------------------------------------------------


def test_felix_bot_token_path_refused():
    with pytest.raises(csf.SavedFilterError, match="felix-bot"):
        csf._read_token_file(csf.FELIX_BOT_TOKEN_FILE)


def test_symlink_to_felix_bot_token_refused(tmp_path, monkeypatch):
    # A symlink pointing at the felix-bot token must be refused (realpath guard),
    # not slip past an abspath-only comparison.
    fake_felix = tmp_path / "vikunja-api"
    fake_felix.write_text("felix-bot-tok\n")
    monkeypatch.setattr(csf, "FELIX_BOT_TOKEN_FILE", str(fake_felix))
    link = tmp_path / "sneaky"
    link.symlink_to(fake_felix)
    with pytest.raises(csf.SavedFilterError, match="felix-bot"):
        csf._read_token_file(str(link))


def test_missing_token_file_fails(tmp_path):
    with pytest.raises(csf.SavedFilterError, match="could not be read"):
        csf._read_token_file(str(tmp_path / "nope"))


def test_blank_token_file_fails(tmp_path):
    p = tmp_path / "tok"
    p.write_text("   \n")
    with pytest.raises(csf.SavedFilterError, match="empty"):
        csf._read_token_file(str(p))


def test_valid_token_file_read(tmp_path):
    p = tmp_path / "tok"
    p.write_text("tok_abc\n")
    assert csf._read_token_file(str(p)) == "tok_abc\n"


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------


def test_main_dry_run_default_no_apply(capsys):
    client = _FakeClient(project_pages=[[]], label_pages=[_labels_page()])
    rc = csf.main([], client=client)
    assert rc == 0
    assert client.put_calls == []
    out = capsys.readouterr().out
    assert "PLAN (dry-run)" in out


def test_main_apply_creates(capsys):
    client = _FakeClient(
        project_pages=[[]], label_pages=[_labels_page()], next_id=100
    )
    rc = csf.main(["--apply"], client=client)
    assert rc == 0
    assert len(client.put_calls) == 5
    assert "CREATE SAVED FILTERS" in capsys.readouterr().out


def test_main_json_output(capsys):
    client = _FakeClient(project_pages=[[]], label_pages=[_labels_page()])
    rc = csf.main(["--json"], client=client)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed"] is False
    assert len(payload["outcomes"]) == 5


def test_main_failure_returns_1_and_reports_partial(capsys):
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page({"f:3-edge": 20})],  # missing t:habit
    )
    rc = csf.main(["--json"], client=client)
    assert rc == 1
    err = capsys.readouterr()
    assert "ERROR: SavedFilterError" in err.err


def test_main_apply_and_dry_run_mutually_exclusive():
    with pytest.raises(SystemExit):
        csf.main(["--apply", "--dry-run"])


# ---------------------------------------------------------------------------
# Additional branch coverage
# ---------------------------------------------------------------------------


def test_paginate_stops_on_null_page():
    # Vikunja returns JSON null for an exhausted/empty collection.
    client = _FakeClient(project_pages=[None], label_pages=[_labels_page()])
    _outcomes, plan = csf.create_filters(client, dry_run=True)
    assert len(plan.to_create) == 5  # empty project set -> all created


def test_non_int_pseudo_id_ignored():
    proj_page = [{"id": "weird", "title": "Today", "owner": {"username": "kent"}}]
    client = _FakeClient(project_pages=[proj_page], label_pages=[_labels_page()])
    _outcomes, plan = csf.create_filters(client, dry_run=True)
    assert "Today" in [s.title for s, _q in plan.to_create]


def test_existing_filter_non_str_title_ignored():
    proj_page = [{"id": -11, "title": 123, "owner": {"username": "kent"}}]
    client = _FakeClient(project_pages=[proj_page], label_pages=[_labels_page()])
    _outcomes, plan = csf.create_filters(client, dry_run=True)
    assert len(plan.to_create) == 5


def test_readback_non_dict_fails_loud():
    proj_page = [_saved_filter_project(10, "Today")]
    filters = {"/filters/10": "not-a-dict"}
    client = _FakeClient(
        project_pages=[proj_page], label_pages=[_labels_page()], filters=filters
    )
    with pytest.raises(csf.SavedFilterError, match="non-object response"):
        csf.create_filters(client, dry_run=True)


def test_main_apply_human_mixed_present_and_created(capsys):
    # Today already present (matching); the rest created with counts.
    proj_page = [_saved_filter_project(10, "Today")]
    filters = {"/filters/10": _filter_readback(EXPECTED_QUERIES["Today"])}
    client = _FakeClient(
        project_pages=[proj_page],
        label_pages=[_labels_page()],
        filters=filters,
        task_counts={-101: 8},
        next_id=100,
    )
    rc = csf.main(["--apply"], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "already-present" in out
    assert "filter_id=" in out
    assert "tasks=" in out
    assert "verified  (1)" in out
    assert "note:" in out


def test_main_failure_human_mode_prints_partial(capsys):
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        put_raises=VikunjaServerError(path="/filters", status=500),
        put_raises_after=1,
        next_id=100,
    )
    rc = csf.main(["--apply"], client=client)
    assert rc == 1
    out = capsys.readouterr().out
    assert "ABORTED mid-run" in out
    assert "skipped" in out


def test_main_json_apply_includes_counts(capsys):
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        task_counts={-101: 4},
        next_id=100,
    )
    rc = csf.main(["--apply", "--json"], client=client)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    today = next(o for o in payload["outcomes"] if o["title"] == "Today")
    assert today["task_count"] == 4
    assert today["filter_id"] == 100
    assert today["query"] == EXPECTED_QUERIES["Today"]


def test_main_json_failure_emits_partial(capsys):
    client = _FakeClient(
        project_pages=[[]],
        label_pages=[_labels_page()],
        put_raises=VikunjaServerError(path="/filters", status=500),
        put_raises_after=1,
        next_id=100,
    )
    rc = csf.main(["--apply", "--json"], client=client)
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed"] is True
    actions = {o["title"]: o["action"] for o in payload["outcomes"]}
    assert actions["Today"] == "created"
    assert actions["Edge + Schedule"] == "skipped"
