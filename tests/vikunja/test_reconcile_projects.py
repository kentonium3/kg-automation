"""Tests for scripts.vikunja.reconcile_projects (#716).

All tests inject a fake client mirroring the real ``VikunjaClient`` surface —
``.get/.put/.delete`` with leading-slash paths, list-shaped ``GET /projects``,
per-filter ``GET /filters/{id}`` readback, empty-dict delete result, typed
exceptions for failure modes. No real network (the global conftest urlopen guard
would fail loudly otherwise — tests never construct a real client).

The fixture encodes the live traps this mission must survive:
- a felix-bot-owned ``Inbox`` (id 14) that owner-scoped matching must ignore;
- ``Habits`` (id 13), a task-bearing project that must never be written to;
- legacy filters on a NON-``1..5`` derived id, and Favorites (``-1``) which is
  never targeted; and pagination that places a create-target + a filter on
  page 2.
"""
from __future__ import annotations

import json

import pytest

from scripts.common.vikunja_client import (
    VikunjaAuthError,
    VikunjaError,
    VikunjaServerError,
    VikunjaTimeoutError,
)
from scripts.vikunja import reconcile_projects as rp

# --- Canonical target set (literal — drift here fails loudly) ---------------
EXPECTED_TARGET_TITLES = [
    "Felix / kg-automation",
    "Clients",
    "PointerHealth",
    "spec-kitty",
    "Personal",
]
EXPECTED_LEGACY = ("Today", "Upcoming", "Overdue", "Goals", "Completed")


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


class _FakeClient:
    """Records get/put/delete calls; serves canned project pages + filters.

    ``pages`` is a list of ``GET /projects`` list-pages served in order to
    successive ``GET /projects`` calls; when exhausted it yields ``[]``.
    ``filters`` maps a ``/filters/{id}`` path to a canned readback dict.
    ``put`` returns a kent-owned project by default (override via ``put_owner``
    or ``put_response``). ``get_raises`` / ``put_raises`` / ``delete_raises``
    inject typed exceptions (optionally only after N successful calls).
    """

    def __init__(
        self,
        *,
        pages=None,
        filters=None,
        put_owner="kent",
        put_response=None,
        get_raises=None,
        get_raises_after=0,
        put_raises=None,
        put_raises_after=0,
        delete_raises=None,
        next_id=2000,
    ):
        self._pages = list(pages) if pages is not None else [[]]
        self._project_get_calls = 0
        self._filters = dict(filters or {})
        self._put_owner = put_owner
        self._put_response = put_response
        self._get_raises = get_raises
        self._get_raises_after = get_raises_after
        self._get_seen = 0
        self._put_raises = put_raises
        self._put_raises_after = put_raises_after
        self._put_seen = 0
        self._delete_raises = delete_raises
        self._next_id = next_id
        self.get_calls: list[tuple[str, dict]] = []
        self.put_calls: list[tuple[str, dict]] = []
        self.delete_calls: list[str] = []

    def get(self, path, *, params=None, **_kwargs):
        self.get_calls.append((path, params or {}))
        if self._get_raises is not None:
            self._get_seen += 1
            if self._get_seen > self._get_raises_after:
                raise self._get_raises
        if path == "/projects":
            idx = self._project_get_calls
            self._project_get_calls += 1
            if idx < len(self._pages):
                return self._pages[idx]
            return []
        if path.startswith("/filters/"):
            return self._filters.get(path)
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
        return {
            "id": assigned,
            "title": json["title"],
            "parent_project_id": json["parent_project_id"],
            "is_archived": False,
            "owner": {"username": self._put_owner},
        }

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


def _inbox(pid=1, owner="kent"):
    return _project(pid, "Inbox", parent=0, owner=owner)


def _favorites():
    # Native Favorites pseudo-project: id -1, owner null. Never a target.
    return _project(-1, "Favorites", parent=0, owner=None)


# A converged live state: Inbox + all 5 targets present with correct parents,
# no legacy filters. Habits (13) and felix-bot Inbox (14) present as traps.
def _converged_projects():
    return [
        _inbox(1),
        _project(13, "Habits", parent=0, owner="kent"),
        _project(14, "Inbox", parent=0, owner="felix-bot"),  # felix-bot trap
        _project(20, "Felix / kg-automation", parent=0),
        _project(21, "Clients", parent=0),
        _project(22, "PointerHealth", parent=21),
        _project(23, "spec-kitty", parent=21),
        _project(24, "Personal", parent=0),
        _favorites(),
    ]


# A fresh live state: Inbox only (+ traps), nothing else, all 5 legacy filters
# present on NON-1..5 derived ids, plus Favorites.
def _fresh_projects_with_legacy():
    # pseudo id -> filter_id = -id - 1. Use non-1..5 filter ids: pseudo -101..-105
    # → filter ids 100..104.
    return [
        _inbox(1),
        _project(13, "Habits", parent=0, owner="kent"),
        _project(14, "Inbox", parent=0, owner="felix-bot"),
        _favorites(),
        _project(-101, "Today", owner="kent"),      # filter_id 100
        _project(-102, "Upcoming", owner="kent"),   # filter_id 101
        _project(-103, "Overdue", owner="kent"),    # filter_id 102
        _project(-104, "Goals", owner="kent"),      # filter_id 103
        _project(-105, "Completed", owner="kent"),  # filter_id 104
    ]


def _legacy_filter_readbacks():
    return {
        "/filters/100": {"id": 100, "title": "Today"},
        "/filters/101": {"id": 101, "title": "Upcoming"},
        "/filters/102": {"id": 102, "title": "Overdue"},
        "/filters/103": {"id": 103, "title": "Goals"},
        "/filters/104": {"id": 104, "title": "Completed"},
    }


# ---------------------------------------------------------------------------
# Fidelity — the declared target set
# ---------------------------------------------------------------------------


def test_target_set_matches_expected():
    titles = [t.title for t in rp.TARGET_PROJECTS]
    assert titles == EXPECTED_TARGET_TITLES


def test_clients_precedes_children_in_order():
    titles = [t.title for t in rp.TARGET_PROJECTS]
    assert titles.index("Clients") < titles.index("PointerHealth")
    assert titles.index("Clients") < titles.index("spec-kitty")


def test_children_reference_clients_parent():
    by_title = {t.title: t for t in rp.TARGET_PROJECTS}
    assert by_title["PointerHealth"].parent_title == "Clients"
    assert by_title["spec-kitty"].parent_title == "Clients"
    assert by_title["Felix / kg-automation"].parent_title is None
    assert by_title["Personal"].parent_title is None


def test_legacy_filter_titles_locked():
    assert rp.LEGACY_FILTER_TITLES == EXPECTED_LEGACY


def test_default_token_file_is_kent_credential():
    assert rp.DEFAULT_KENT_TOKEN_FILE.endswith("vikunja-api-kent")


# ---------------------------------------------------------------------------
# Create pass — fresh instance creates all 5, none for Inbox/Habits
# ---------------------------------------------------------------------------


def test_create_from_fresh_issues_five_puts_in_order():
    client = _FakeClient(pages=[[_inbox(1), _project(14, "Inbox", owner="felix-bot")]])
    outcomes, plan = rp.reconcile(client)
    assert [t for t, _ in client.put_calls] == ["/projects"] * 5
    created_titles = [body["title"] for _, body in client.put_calls]
    assert created_titles == EXPECTED_TARGET_TITLES
    # Inbox verified, not created.
    inbox_outcomes = [o for o in outcomes if o.kind == "inbox"]
    assert len(inbox_outcomes) == 1
    assert inbox_outcomes[0].action == "verified-inbox"
    assert inbox_outcomes[0].id == 1
    assert len(plan.projects_to_create) == 5


def test_children_created_under_resolved_clients_id():
    client = _FakeClient(pages=[[_inbox(1)]], next_id=500)
    rp.reconcile(client)
    bodies = {body["title"]: body for _, body in client.put_calls}
    # Clients created first with id 501 (Felix=500, Clients=501).
    clients_id = None
    for _, body in client.put_calls:
        if body["title"] == "Clients":
            # id assigned to Clients response; children must reference it.
            clients_id = 501
    assert clients_id == 501
    assert bodies["PointerHealth"]["parent_project_id"] == 501
    assert bodies["spec-kitty"]["parent_project_id"] == 501
    assert bodies["Felix / kg-automation"]["parent_project_id"] == 0
    assert bodies["Personal"]["parent_project_id"] == 0


def test_create_from_fresh_exit_zero_via_main(capsys):
    client = _FakeClient(pages=[[_inbox(1)]])
    rc = rp.main(["--json"], client=client)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed"] is False
    created = [o for o in payload["outcomes"] if o["action"] == "created"]
    assert {o["title"] for o in created} == set(EXPECTED_TARGET_TITLES)


# ---------------------------------------------------------------------------
# Idempotency — converged state issues zero mutating calls (NFR-001)
# ---------------------------------------------------------------------------


def test_idempotent_converged_zero_mutations():
    client = _FakeClient(pages=[_converged_projects()])
    outcomes, plan = rp.reconcile(client)
    assert client.put_calls == []
    assert client.delete_calls == []
    assert plan.projects_to_create == []
    verified = {o.title for o in outcomes if o.action == "already-present"}
    assert verified == set(EXPECTED_TARGET_TITLES)


def test_idempotent_converged_exit_zero_via_main():
    client = _FakeClient(pages=[_converged_projects()])
    rc = rp.main([], client=client)
    assert rc == 0
    assert client.put_calls == []
    assert client.delete_calls == []


def test_idempotent_even_with_delete_flag_no_filters_present():
    # Converged + no legacy filters → delete pass is a no-op.
    client = _FakeClient(pages=[_converged_projects()])
    rc = rp.main(["--delete-legacy", "--backup-confirmed", "restic-x"], client=client)
    assert rc == 0
    assert client.delete_calls == []


# ---------------------------------------------------------------------------
# Owner enforcement — felix-bot Inbox ignored; wrong create-owner aborts
# ---------------------------------------------------------------------------


def test_felix_bot_inbox_id14_ignored_by_matching():
    # Only felix-bot's Inbox present, no kent Inbox → hard error (Inbox native).
    client = _FakeClient(pages=[[_project(14, "Inbox", owner="felix-bot")]])
    with pytest.raises(rp.ReconcileError, match="Inbox"):
        rp.reconcile(client)


def test_create_response_wrong_owner_aborts():
    # Create returns a felix-bot-owned project → abort fail-loud (wrong token).
    client = _FakeClient(pages=[[_inbox(1)]], put_owner="felix-bot")
    with pytest.raises(rp.ReconcileError, match="owner"):
        rp.reconcile(client)
    # Only the first create attempted before abort.
    assert len(client.put_calls) == 1


def test_create_wrong_owner_exit_one_via_main(capsys):
    client = _FakeClient(pages=[[_inbox(1)]], put_owner="felix-bot")
    rc = rp.main([], client=client)
    assert rc == 1
    assert "owner" in capsys.readouterr().err.lower()


def test_multiple_kent_inbox_aborts():
    client = _FakeClient(pages=[[_inbox(1), _inbox(2)]])
    with pytest.raises(rp.ReconcileError, match="ambiguous|Multiple"):
        rp.reconcile(client)


def test_create_non_object_response_aborts():
    client = _FakeClient(pages=[[_inbox(1)]], put_response=["not", "a", "dict"])
    with pytest.raises(rp.ReconcileError, match="non-object"):
        rp.reconcile(client)


def test_create_response_missing_id_for_clients_aborts():
    # Clients create returns kent-owned but no int id → cannot parent children.
    client = _FakeClient(
        pages=[[_inbox(1)]],
        put_response={"title": "x", "owner": {"username": "kent"}, "id": None},
    )
    with pytest.raises(rp.ReconcileError, match="id"):
        rp.reconcile(client)


def test_inbox_present_only_under_felix_bot_is_hard_error():
    # kent Habits present but kent Inbox absent (felix-bot Inbox is not kent's).
    client = _FakeClient(
        pages=[[_project(13, "Habits", owner="kent"), _project(14, "Inbox", owner="felix-bot")]]
    )
    with pytest.raises(rp.ReconcileError):
        rp.reconcile(client)


# ---------------------------------------------------------------------------
# Ambiguity abort — duplicate / archived / wrong-parent (FR-014)
# ---------------------------------------------------------------------------


def test_duplicate_active_target_aborts():
    projects = [_inbox(1), _project(30, "Personal"), _project(31, "Personal")]
    client = _FakeClient(pages=[projects])
    with pytest.raises(rp.ReconcileError, match="Ambiguous"):
        rp.reconcile(client)
    assert client.put_calls == []


def test_archived_twin_collision_aborts():
    # One active Personal + an archived Personal → collision, refuse to reuse.
    projects = [
        _inbox(1),
        _project(30, "Personal"),
        _project(31, "Personal", archived=True),
    ]
    client = _FakeClient(pages=[projects])
    with pytest.raises(rp.ReconcileError, match="collide"):
        rp.reconcile(client)
    assert client.put_calls == []


def test_wrong_parent_collision_when_no_active_match_aborts():
    # A 'Personal' under some other parent (not top-level) with no top-level
    # kent Personal → title collision, abort rather than create a duplicate.
    projects = [_inbox(1), _project(30, "Personal", parent=99)]
    client = _FakeClient(pages=[projects])
    with pytest.raises(rp.ReconcileError, match="duplicate"):
        rp.reconcile(client)
    assert client.put_calls == []


def test_clients_ambiguous_aborts_before_children():
    projects = [_inbox(1), _project(40, "Clients"), _project(41, "Clients")]
    client = _FakeClient(pages=[projects])
    with pytest.raises(rp.ReconcileError, match="Ambiguous"):
        rp.reconcile(client)
    assert client.put_calls == []


def test_child_collision_while_clients_absent_aborts():
    # spec-kitty already exists somewhere but Clients does not → ambiguous.
    projects = [_inbox(1), _project(50, "spec-kitty", parent=0)]
    client = _FakeClient(pages=[projects])
    with pytest.raises(rp.ReconcileError):
        rp.reconcile(client)


def test_existing_clients_reused_children_created_under_it():
    # Active top-level kent Clients (id 77) present; children absent.
    projects = [_inbox(1), _project(77, "Clients", parent=0)]
    client = _FakeClient(pages=[projects], next_id=800)
    outcomes, plan = rp.reconcile(client)
    assert plan.clients_existing_id == 77
    bodies = {body["title"]: body for _, body in client.put_calls}
    assert "Clients" not in bodies  # reused, not re-created
    assert bodies["PointerHealth"]["parent_project_id"] == 77
    assert bodies["spec-kitty"]["parent_project_id"] == 77
    verified = {o.title for o in outcomes if o.action == "already-present"}
    assert "Clients" in verified


# ---------------------------------------------------------------------------
# Pagination + null handling
# ---------------------------------------------------------------------------


def test_pagination_finds_target_and_filter_on_page_two():
    page1 = [_project(100 + i, f"filler-{i}", owner="kent") for i in range(50)]
    # Ensure Inbox is on page 1 so verify succeeds; replace one filler.
    page1[0] = _inbox(1)
    page1[1] = _favorites()
    page2 = [
        _project(20, "Felix / kg-automation"),
        _project(21, "Clients"),
        _project(22, "PointerHealth", parent=21),
        _project(23, "spec-kitty", parent=21),
        # Personal missing → will be created; a legacy filter also on page 2.
        _project(-105, "Completed", owner="kent"),  # filter_id 104
    ]
    client = _FakeClient(
        pages=[page1, page2, []],
        filters={"/filters/104": {"id": 104, "title": "Completed"}},
    )
    outcomes, plan = rp.reconcile(
        client, delete_legacy=True, backup_confirmed="restic-x"
    )
    project_gets = [c for c in client.get_calls if c[0] == "/projects"]
    # page1 is exactly 50 (full) → page 2 fetched; page2 has 5 (< 50) → stop.
    assert len(project_gets) == 2
    assert [c[1]["page"] for c in project_gets] == ["1", "2"]
    # Completed filter (on page 2) derived + deleted.
    assert client.delete_calls == ["/filters/104"]
    # Personal (absent) created.
    created = {o.title for o in outcomes if o.action == "created"}
    assert "Personal" in created


def test_null_body_normalized_to_empty_list():
    # First page real, second page null (Vikunja empty-collection quirk) → stop.
    page1 = [_project(100 + i, f"filler-{i}", owner="kent") for i in range(50)]
    page1[0] = _inbox(1)
    client = _FakeClient(pages=[page1, None])
    # No targets present → all 5 created; must not raise on the null page.
    outcomes, _plan = rp.reconcile(client)
    created = {o.title for o in outcomes if o.action == "created"}
    assert created == set(EXPECTED_TARGET_TITLES)


def test_non_list_body_raises():
    class _BadClient(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            return {"not": "a list"}

    with pytest.raises(VikunjaError):
        rp.list_projects(_BadClient())


# ---------------------------------------------------------------------------
# Filter delete — backup gate, readback, derivation, never -1
# ---------------------------------------------------------------------------


def test_delete_refused_without_backup_ref_exit_two_no_mutation(capsys):
    client = _FakeClient(pages=[_fresh_projects_with_legacy()], filters=_legacy_filter_readbacks())
    rc = rp.main(["--delete-legacy"], client=client)
    assert rc == 2
    assert client.delete_calls == []
    assert client.put_calls == []  # refused BEFORE any mutation
    assert "requires --backup-confirmed" in capsys.readouterr().err


def test_delete_refused_blank_backup_ref_exit_two(capsys):
    client = _FakeClient(pages=[_fresh_projects_with_legacy()], filters=_legacy_filter_readbacks())
    rc = rp.main(["--delete-legacy", "--backup-confirmed", "   "], client=client)
    assert rc == 2
    assert client.delete_calls == []


def test_delete_with_backup_ref_deletes_all_five(capsys):
    client = _FakeClient(
        pages=[_fresh_projects_with_legacy()], filters=_legacy_filter_readbacks()
    )
    rc = rp.main(
        ["--delete-legacy", "--backup-confirmed", "restic-abc123", "--json"],
        client=client,
    )
    assert rc == 0
    # Derived filter ids are the NON-1..5 set (100..104).
    assert client.delete_calls == [
        "/filters/100",
        "/filters/101",
        "/filters/102",
        "/filters/103",
        "/filters/104",
    ]
    payload = json.loads(capsys.readouterr().out)
    assert payload["backup_confirmed"] == "restic-abc123"
    deleted = {o["title"] for o in payload["outcomes"] if o["action"] == "deleted"}
    assert deleted == set(EXPECTED_LEGACY)


def test_delete_derivation_uses_non_1_to_5_ids():
    # Explicitly assert the filter ids are not the naive 1..5.
    client = _FakeClient(
        pages=[_fresh_projects_with_legacy()], filters=_legacy_filter_readbacks()
    )
    rp.reconcile(client, delete_legacy=True, backup_confirmed="ts")
    derived_ids = [int(p.rsplit("/", 1)[1]) for p in client.delete_calls]
    assert derived_ids == [100, 101, 102, 103, 104]
    assert set(derived_ids).isdisjoint({1, 2, 3, 4, 5})


def test_favorites_never_derived_or_deleted():
    # Favorites (-1) present but is NOT in the legacy title set anyway; assert
    # no /filters/0 (which -(-1)-1 = 0 would yield) is ever touched.
    projects = _converged_projects()  # includes Favorites, no legacy filters
    client = _FakeClient(pages=[projects])
    rp.reconcile(client, delete_legacy=True, backup_confirmed="ts")
    assert client.delete_calls == []
    assert all("/filters/0" != c for c in client.delete_calls)


def test_legacy_filter_owned_by_other_user_not_derived():
    # Post-merge review HIGH #2 (defense-in-depth): a legacy-titled negative-id
    # pseudo-project owned by someone other than kent must NOT be derived for
    # deletion, even though filters are per-user.
    projects = [
        _inbox(1),
        _project(20, "Felix / kg-automation", owner="kent"),
        _project(21, "Clients", owner="kent"),
        _project(22, "PointerHealth", parent=21, owner="kent"),
        _project(23, "spec-kitty", parent=21, owner="kent"),
        _project(24, "Personal", owner="kent"),
        _project(-102, "Today", owner="someone-else"),  # not kent's filter
    ]
    client = _FakeClient(pages=[projects])
    outcomes, plan = rp.reconcile(client, delete_legacy=True, backup_confirmed="ts")
    assert client.delete_calls == []
    assert "Today" in plan.filters_absent


def test_favorites_titled_as_legacy_still_skipped_by_id_guard():
    # Defensive: even if a pseudo -1 somehow carried a legacy title, id<=-2
    # filter derivation excludes it; and the pass guards pseudo_id == -1.
    projects = [
        _inbox(1),
        *[_project(pid, t, owner="kent") for pid, t in [
            (20, "Felix / kg-automation"), (21, "Clients"),
        ]],
        _project(22, "PointerHealth", parent=21),
        _project(23, "spec-kitty", parent=21),
        _project(24, "Personal"),
        _project(-1, "Today", owner=None),  # Favorites slot mislabeled Today
    ]
    client = _FakeClient(pages=[projects])
    outcomes, plan = rp.reconcile(client, delete_legacy=True, backup_confirmed="ts")
    # -1 excluded from derivation (id > -2 filter) → no delete, reported absent.
    assert client.delete_calls == []
    assert "Today" in plan.filters_absent


def test_filter_readback_mismatch_no_delete_fails_loud():
    client = _FakeClient(
        pages=[_fresh_projects_with_legacy()],
        filters={
            **_legacy_filter_readbacks(),
            "/filters/100": {"id": 100, "title": "SOMETHING ELSE"},  # mismatch
        },
    )
    with pytest.raises(rp.ReconcileError, match="readback mismatch"):
        rp.reconcile(client, delete_legacy=True, backup_confirmed="ts")
    # No delete issued for the mismatched filter (it was first).
    assert client.delete_calls == []


def test_filter_readback_mismatch_exit_one_via_main(capsys):
    client = _FakeClient(
        pages=[_fresh_projects_with_legacy()],
        filters={
            **_legacy_filter_readbacks(),
            "/filters/100": {"id": 100, "title": "WRONG"},
        },
    )
    rc = rp.main(["--delete-legacy", "--backup-confirmed", "ts"], client=client)
    assert rc == 1
    assert "readback mismatch" in capsys.readouterr().err.lower()


def test_legacy_absent_reports_already_absent():
    client = _FakeClient(pages=[_converged_projects()])
    outcomes, _plan = rp.reconcile(
        client, delete_legacy=True, backup_confirmed="ts"
    )
    absent = {o.title for o in outcomes if o.action == "already-absent"}
    assert absent == set(EXPECTED_LEGACY)
    assert client.delete_calls == []


def test_legacy_present_without_flag_skipped_no_flag():
    client = _FakeClient(
        pages=[_fresh_projects_with_legacy()], filters=_legacy_filter_readbacks()
    )
    outcomes, _plan = rp.reconcile(client)  # no delete flag
    assert client.delete_calls == []
    skipped = {o.title for o in outcomes if o.action == "skipped-no-flag"}
    assert skipped == set(EXPECTED_LEGACY)


# ---------------------------------------------------------------------------
# No project delete — ever (invariant 3 / C-004 / FR-010)
# ---------------------------------------------------------------------------


def test_no_delete_projects_endpoint_ever_called():
    # Across create, converged, and delete-legacy runs, DELETE only hits
    # /filters/*, never /projects/*.
    for args in ([], ["--delete-legacy", "--backup-confirmed", "ts"]):
        client = _FakeClient(
            pages=[_fresh_projects_with_legacy()],
            filters=_legacy_filter_readbacks(),
        )
        rp.main(args, client=client)
        assert all(
            not c.startswith("/projects") for c in client.delete_calls
        ), client.delete_calls


def test_habits_id13_never_written():
    client = _FakeClient(pages=[_converged_projects()])
    rp.reconcile(client, delete_legacy=True, backup_confirmed="ts")
    # No put/delete referencing project 13 or any /projects/ path.
    assert all(p == "/projects" for p, _ in client.put_calls)
    assert all(not c.startswith("/projects") for c in client.delete_calls)


def test_assert_no_project_delete_guard_trips_on_bad_field():
    plan = rp.ReconcilePlan()
    plan.projects_to_delete = ["Habits"]  # type: ignore[attr-defined]
    with pytest.raises(rp.ReconcileError, match="no project"):
        rp._assert_no_project_delete(plan)


# ---------------------------------------------------------------------------
# Partial failure — completed vs skipped (NFR-005)
# ---------------------------------------------------------------------------


def test_api_error_after_one_create_exit_one_shows_completed_and_skipped(capsys):
    # Fresh instance: 5 creates queued; put fails after the first succeeds.
    client = _FakeClient(
        pages=[[_inbox(1)]],
        put_raises=VikunjaServerError(path="/projects", status=503),
        put_raises_after=1,  # first put ok, second raises
    )
    rc = rp.main(["--json"], client=client)
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed"] is True
    created = [o for o in payload["outcomes"] if o["action"] == "created"]
    skipped = [o for o in payload["outcomes"] if o["action"] == "skipped"]
    assert len(created) == 1  # Felix / kg-automation created
    assert len(skipped) >= 1  # remaining targets skipped
    # The second put (Clients) was attempted and raised → 2 put calls total.
    assert len(client.put_calls) == 2


def test_partial_failure_human_summary_shows_aborted(capsys):
    client = _FakeClient(
        pages=[[_inbox(1)]],
        put_raises=VikunjaServerError(path="/projects", status=503),
        put_raises_after=1,
    )
    rc = rp.main([], client=client)
    assert rc == 1
    out = capsys.readouterr().out
    assert "ABORTED mid-run" in out
    assert "created" in out
    assert "skipped" in out


def test_delete_failure_mid_run_reports_partial(capsys):
    # Two legacy filters; delete of the first succeeds, second GET readback ok
    # but DELETE raises.
    projects = [
        _inbox(1),
        _project(20, "Felix / kg-automation"), _project(21, "Clients"),
        _project(22, "PointerHealth", parent=21),
        _project(23, "spec-kitty", parent=21), _project(24, "Personal"),
        _project(-101, "Today", owner="kent"),     # filter 100
        _project(-102, "Upcoming", owner="kent"),  # filter 101
    ]

    class _Client(_FakeClient):
        def delete(self, path, *, params=None, **_kwargs):
            self.delete_calls.append(path)
            if path == "/filters/101":
                raise VikunjaServerError(path=path, status=500)
            return {}

    client = _Client(
        pages=[projects],
        filters={
            "/filters/100": {"id": 100, "title": "Today"},
            "/filters/101": {"id": 101, "title": "Upcoming"},
        },
    )
    rc = rp.main(
        ["--delete-legacy", "--backup-confirmed", "ts", "--json"], client=client
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed"] is True
    deleted = [o for o in payload["outcomes"] if o["action"] == "deleted"]
    assert any(o["title"] == "Today" for o in deleted)  # first completed
    assert client.delete_calls == ["/filters/100", "/filters/101"]


# ---------------------------------------------------------------------------
# Generic failure modes surface non-zero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        VikunjaTimeoutError(path="/projects"),
        VikunjaAuthError(path="/projects", status=401),
        VikunjaServerError(path="/projects", status=503),
    ],
)
def test_read_failure_modes_surfaced_non_zero(exc, capsys):
    client = _FakeClient(get_raises=exc)
    rc = rp.main([], client=client)
    assert rc == 1
    assert type(exc).__name__ in capsys.readouterr().err


def test_auth_error_names_no_success():
    client = _FakeClient(get_raises=VikunjaAuthError(path="/projects", status=401))
    rc = rp.main([], client=client)
    assert rc == 1


def test_generic_exception_after_create_reports_partial_json(capsys):
    # A non-typed exception mid-create still yields exit 1 + a partial summary.
    client = _FakeClient(
        pages=[[_inbox(1)]],
        put_raises=RuntimeError("boom"),
        put_raises_after=1,  # first create ok, second raises RuntimeError
    )
    rc = rp.main(["--json"], client=client)
    assert rc == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["failed"] is True
    assert any(o["action"] == "created" for o in payload["outcomes"])
    assert any(o["action"] == "skipped" for o in payload["outcomes"])
    assert "RuntimeError" in captured.err


def test_generic_exception_human_partial(capsys):
    client = _FakeClient(
        pages=[[_inbox(1)]], put_raises=RuntimeError("boom"), put_raises_after=1
    )
    rc = rp.main([], client=client)
    assert rc == 1
    out = capsys.readouterr().out
    assert "ABORTED mid-run" in out


def test_non_int_pseudo_id_filter_skipped_in_derivation():
    # A pseudo-project with a non-int id is skipped by derivation (no crash).
    projects = [
        _inbox(1),
        _project(20, "Felix / kg-automation"), _project(21, "Clients"),
        _project(22, "PointerHealth", parent=21),
        _project(23, "spec-kitty", parent=21), _project(24, "Personal"),
        {"id": None, "title": "Today", "owner": {"username": "kent"}},
    ]
    client = _FakeClient(pages=[projects])
    outcomes, plan = rp.reconcile(client, delete_legacy=True, backup_confirmed="ts")
    assert client.delete_calls == []
    # Non-int-id pseudo excluded → Today reported absent.
    assert "Today" in plan.filters_absent


# ---------------------------------------------------------------------------
# Dry-run — plan only, no mutation
# ---------------------------------------------------------------------------


def test_dry_run_zero_mutations_exit_zero(capsys):
    client = _FakeClient(
        pages=[_fresh_projects_with_legacy()], filters=_legacy_filter_readbacks()
    )
    rc = rp.main(
        ["--dry-run", "--delete-legacy", "--backup-confirmed", "dry"], client=client
    )
    assert rc == 0
    assert client.put_calls == []
    assert client.delete_calls == []
    out = capsys.readouterr().out
    assert "PLAN (dry-run)" in out


def test_dry_run_plan_lists_creates_and_deletes():
    client = _FakeClient(
        pages=[_fresh_projects_with_legacy()], filters=_legacy_filter_readbacks()
    )
    outcomes, plan = rp.reconcile(
        client, delete_legacy=True, backup_confirmed="dry", dry_run=True
    )
    assert client.put_calls == []
    assert client.delete_calls == []
    created = [o for o in outcomes if o.action == "created"]
    assert {o.title for o in created} == set(EXPECTED_TARGET_TITLES)
    assert all(o.id is None for o in created)  # no ids assigned in dry-run
    deleted = [o for o in outcomes if o.action == "deleted"]
    assert {o.title for o in deleted} == set(EXPECTED_LEGACY)


def test_dry_run_json_output(capsys):
    client = _FakeClient(pages=[[_inbox(1)]])
    rc = rp.main(["--dry-run", "--json"], client=client)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed"] is False


# ---------------------------------------------------------------------------
# reconcile() function-boundary backup gate (mirrors #715)
# ---------------------------------------------------------------------------


def test_reconcile_delete_legacy_requires_backup_ref():
    client = _FakeClient(pages=[_converged_projects()])
    with pytest.raises(ValueError):
        rp.reconcile(client, delete_legacy=True)
    with pytest.raises(ValueError):
        rp.reconcile(client, delete_legacy=True, backup_confirmed="   ")
    assert client.delete_calls == []


# ---------------------------------------------------------------------------
# Token file loading — kent credential, no felix-bot fallback
# ---------------------------------------------------------------------------


def test_token_file_read_and_passed_to_client(tmp_path, monkeypatch):
    token_file = tmp_path / "vikunja-api-kent"
    token_file.write_text("kent-secret-token\n", encoding="utf-8")
    captured = {}

    class _FakeVC:
        def __init__(self, *, base_url=None, token=None):
            captured["base_url"] = base_url
            captured["token"] = token

        def get(self, path, *, params=None, **_kwargs):
            if path == "/projects":
                return [_inbox(1)]
            return None

        def put(self, path, *, json=None, **_kwargs):
            return {
                "id": 1,
                "title": json["title"],
                "parent_project_id": json["parent_project_id"],
                "owner": {"username": "kent"},
            }

    import scripts.common.vikunja_client as vc_mod

    monkeypatch.setattr(vc_mod, "VikunjaClient", _FakeVC)
    rc = rp.main(["--token-file", str(token_file), "--base-url", "https://x/api/v1"])
    assert rc == 0
    assert captured["token"] == "kent-secret-token\n"
    assert captured["base_url"] == "https://x/api/v1"


def test_missing_token_file_names_credential_exit_one(tmp_path, capsys):
    missing = tmp_path / "nope"
    rc = rp.main(["--token-file", str(missing)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "vikunja-api-kent" in err


def test_blank_token_file_exit_one(tmp_path, capsys):
    blank = tmp_path / "blank"
    blank.write_text("   \n", encoding="utf-8")
    rc = rp.main(["--token-file", str(blank)])
    assert rc == 1
    assert "vikunja-api-kent" in capsys.readouterr().err


def test_read_token_file_helper_missing_raises(tmp_path):
    with pytest.raises(rp.ReconcileError, match="vikunja-api-kent"):
        rp._read_token_file(str(tmp_path / "absent"))


def test_felix_bot_token_path_refused():
    # Post-merge review HIGH #1: the known felix-bot token path is refused as a
    # source before any read/mutation, independent of the create-response owner
    # assertion (which would not fire on a converged/delete-only run).
    with pytest.raises(rp.ReconcileError, match="felix-bot"):
        rp._read_token_file(rp.FELIX_BOT_TOKEN_FILE)


def test_felix_bot_token_path_refused_via_cli_exit_one(capsys):
    rc = rp.main(["--token-file", rp.FELIX_BOT_TOKEN_FILE])
    assert rc == 1
    assert "felix-bot" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Human summary rendering
# ---------------------------------------------------------------------------


def test_human_summary_renders_buckets(capsys):
    client = _FakeClient(pages=[[_inbox(1)]])
    rc = rp.main([], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "RECONCILE" in out
    assert "summary" in out
    assert "created" in out
    assert "verified" in out


def test_summarize_groups_actions():
    outcomes = [
        rp.ReconcileOutcome("inbox", "Inbox", "verified-inbox", id=1),
        rp.ReconcileOutcome("project", "Clients", "already-present", id=2),
        rp.ReconcileOutcome("project", "Personal", "created", id=3),
        rp.ReconcileOutcome("filter", "Today", "deleted", filter_id=100),
        rp.ReconcileOutcome("filter", "Upcoming", "skipped"),
    ]
    buckets = rp._summarize(outcomes)
    assert buckets["created"] == ["Personal"]
    assert set(buckets["verified"]) == {"Inbox", "Clients"}
    assert buckets["deleted"] == ["Today"]
    assert buckets["skipped"] == ["Upcoming"]
