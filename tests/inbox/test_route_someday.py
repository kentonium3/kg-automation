"""Tests for scripts/inbox/route_someday.py — post-#745 routing model
(WP05 of mission ``vikunja-reference-seam-01KXK68Z``).

Post-reset behavior under test (SC-005 / FR-010..FR-013):

- "someday" is NOT a project. The block becomes a task carrying the
  ``q:schedule`` label with **no due date**, created in **Inbox** (id resolved
  through the reference seam ``scripts.common.vikunja_refs``) or a caller-supplied
  topic project. The retired ``find_someday_project`` / ``SOMEDAY_PROJECT_TITLE``
  by-title lookup is gone (it looked up a deleted project — the direct #743 cause).
- The task is **always created** first (anti-silent-loss #743); the ``q:schedule``
  attach is **fail-soft**: felix-bot cannot attach the kent-owned ``q:schedule``
  label (live-probe 2026-07-15 → HTTP 403, #715), so an attach failure is logged
  loudly on stderr and the route still succeeds (exit 0).
- No live ``/projects`` listing occurs — the seam resolves ids from the registry.

Resolution is injected via ``vikunja_refs.set_registry_for_test`` (network-free);
``VikunjaClient`` is patched at the module level (``rs.VikunjaClient``). The global
``_block_live_http`` guard in ``tests/conftest.py`` blows up loudly on any escape.
"""
from __future__ import annotations

import json

import pytest

from scripts.common import vikunja_refs
from scripts.common.vikunja_client import VikunjaError
from scripts.inbox import route_someday as rs


# ---------------------------------------------------------------------------
# Registry injection (network-free) — matches vikunja_refs.json shape
# ---------------------------------------------------------------------------

_TEST_REGISTRY = {
    "schema_version": 1,
    "source_of_truth": "test",
    "last_verified_utc": "2026-07-15T00:00:00Z",
    "projects": [
        {
            "name": "inbox",
            "selector": {"kind": "project_id", "value": 1},
            "title": "Inbox",
            "owner": "kent",
            "provisioned": True,
        },
        {
            "name": "personal",
            "selector": {"kind": "project_id", "value": 20},
            "title": "Personal",
            "owner": "kent",
            "provisioned": True,
        },
    ],
    "labels": [
        {
            "name": "q:schedule",
            "selector": {"kind": "label", "value": 23},
            "title": "q:schedule",
            "owner_token": "kent",
        },
    ],
    "private_projects": [],
}


@pytest.fixture(autouse=True)
def _inject_registry():
    """Install the in-memory registry for every test; clear it afterward."""
    vikunja_refs.set_registry_for_test(_TEST_REGISTRY)
    yield
    vikunja_refs.set_registry_for_test(None)


# ---------------------------------------------------------------------------
# Fake VikunjaClient
# ---------------------------------------------------------------------------


class FakeClient:
    """Records .get/.put calls; distinguishes task-create from label-attach.

    ``create_response`` is returned for a ``PUT /projects/<id>/tasks`` call.
    ``attach_error`` (if set) is raised for a ``PUT /tasks/<id>/labels`` call to
    simulate the felix-bot 403. Any ``.get`` (a live ``/projects`` listing) is a
    contract violation and blows up loudly.
    """

    def __init__(self, *, create_response=None, attach_error=None, create_error=None):
        self._create_response = create_response or {"id": 4321, "title": "t"}
        self._attach_error = attach_error
        self._create_error = create_error
        self.get_calls: list[tuple] = []
        self.create_calls: list[tuple] = []
        self.attach_calls: list[dict] = []

    def get(self, path, **kwargs):  # pragma: no cover - must never be called
        self.get_calls.append((path, kwargs))
        raise AssertionError(
            f"route_someday made a live GET {path!r}; the reference seam must "
            f"resolve ids without listing /projects"
        )

    def put(self, path, json=None, **kwargs):
        if path.endswith("/labels"):
            self.attach_calls.append({"path": path, "json": json})
            if self._attach_error is not None:
                raise self._attach_error
            return {}
        # task-create path: /projects/<id>/tasks
        self.create_calls.append((path, json))
        if self._create_error is not None:
            raise self._create_error
        return self._create_response

    # route_someday never uses .post — expose it so the C-006 assertion holds.
    def post(self, *a, **k):  # pragma: no cover - guard
        raise AssertionError("route_someday must not call POST (partial-replace, #524)")


def _install(monkeypatch, client):
    monkeypatch.setattr(rs, "VikunjaClient", lambda: client)
    return client


_ARGS = ["--title", "Try Iceland again", "--body", "Planning notes",
         "--note-filename", "2026-06-09-iceland.md"]


# ---------------------------------------------------------------------------
# Core behavior — SC-005
# ---------------------------------------------------------------------------


def test_someday_lands_in_inbox_with_qschedule_and_no_due_date(monkeypatch, capsys):
    client = _install(monkeypatch, FakeClient(create_response={"id": 555}))
    rc = rs.main(_ARGS)
    assert rc == 0
    # Created in Inbox (id 1 via the seam), not a "Someday" project.
    assert len(client.create_calls) == 1
    path, payload = client.create_calls[0]
    assert path == "/projects/1/tasks"
    # No due date on the "someday" state.
    assert "due_date" not in payload
    assert payload["title"] == "Try Iceland again"
    assert "Source: 2026-06-09-iceland.md" in payload["description"]
    # q:schedule attach WAS attempted, by id (23), on the created task.
    assert len(client.attach_calls) == 1
    assert client.attach_calls[0]["path"] == "/tasks/555/labels"
    assert client.attach_calls[0]["json"] == {"label_id": 23}
    assert "task_id=555" in capsys.readouterr().out


def test_attach_failure_still_creates_task_and_logs_loudly(monkeypatch, capsys):
    """The #715 403 case: attach fails, task is still created, route succeeds,
    and the degraded state is logged loudly (never silently swallowed)."""
    client = _install(
        monkeypatch,
        FakeClient(
            create_response={"id": 777},
            attach_error=VikunjaError(path="/tasks/777/labels", status=403),
        ),
    )
    rc = rs.main(_ARGS)
    assert rc == 0  # route SUCCEEDS despite attach failure
    assert len(client.create_calls) == 1  # task created
    assert len(client.attach_calls) == 1  # attach attempted
    captured = capsys.readouterr()
    assert "task_id=777" in captured.out
    # Loud, structured warning on stderr — not swallowed.
    warning = json.loads(captured.err.strip().splitlines()[-1])
    assert warning["warning"] == "label_attach_failed"
    assert warning["label"] == "q:schedule"
    assert warning["task_id"] == 777


def test_no_live_projects_listing(monkeypatch, capsys):
    """The old find_someday_project GET /projects listing is gone."""
    client = _install(monkeypatch, FakeClient(create_response={"id": 1}))
    rs.main(_ARGS)
    assert client.get_calls == []


def test_uses_create_endpoint_not_partial_update(monkeypatch):
    """Create via PUT /projects/<id>/tasks — never POST /tasks/<id> (#524)."""
    client = _install(monkeypatch, FakeClient(create_response={"id": 9}))
    rs.main(_ARGS)
    assert len(client.create_calls) == 1
    path, _ = client.create_calls[0]
    assert path.startswith("/projects/")
    assert path.endswith("/tasks")


def test_topic_project_used_when_supplied(monkeypatch, capsys):
    client = _install(monkeypatch, FakeClient(create_response={"id": 3}))
    rc = rs.main(_ARGS + ["--project", "personal"])
    assert rc == 0
    path, _ = client.create_calls[0]
    assert path == "/projects/20/tasks"  # Personal, id 20 via the seam


def test_unresolved_topic_project_falls_back_to_inbox(monkeypatch, capsys):
    """Anti-silent-loss: an unresolved topic project lands the capture in Inbox
    with a loud warning rather than losing it."""
    client = _install(monkeypatch, FakeClient(create_response={"id": 4}))
    rc = rs.main(_ARGS + ["--project", "does_not_exist"])
    assert rc == 0
    path, _ = client.create_calls[0]
    assert path == "/projects/1/tasks"  # fell back to Inbox
    err = capsys.readouterr().err
    assert "does_not_exist" in err


def test_retired_symbols_are_gone():
    """find_someday_project / SOMEDAY_PROJECT_TITLE no longer exist (FR-011)."""
    assert not hasattr(rs, "find_someday_project")
    assert not hasattr(rs, "SOMEDAY_PROJECT_TITLE")


# ---------------------------------------------------------------------------
# Hard error paths — CLI contract preserved (exit 2 + vikunja_error stderr)
# ---------------------------------------------------------------------------


def test_create_task_error_exits_2(monkeypatch, capsys):
    _install(
        monkeypatch,
        FakeClient(create_error=VikunjaError(path="/projects/1/tasks", status=500)),
    )
    rc = rs.main(_ARGS)
    assert rc == 2
    assert "vikunja_error" in capsys.readouterr().err


def test_create_task_response_missing_id_exits_2(monkeypatch, capsys):
    _install(monkeypatch, FakeClient(create_response={"title": "no id"}))
    rc = rs.main(_ARGS)
    assert rc == 2
    assert "vikunja_error" in capsys.readouterr().err


def test_vikunja_unreachable_exits_2(monkeypatch, capsys):
    _install(
        monkeypatch,
        FakeClient(create_error=ConnectionError("network down")),
    )
    rc = rs.main(_ARGS)
    assert rc == 2
    assert "vikunja_error" in capsys.readouterr().err


def test_client_construction_error_exits_2(monkeypatch, capsys):
    def boom():
        raise ValueError("token file missing")

    monkeypatch.setattr(rs, "VikunjaClient", boom)
    rc = rs.main(_ARGS)
    assert rc == 2
    err = capsys.readouterr().err
    assert "vikunja_error" in err
    assert "token file missing" in err


# ---------------------------------------------------------------------------
# CLI ergonomics
# ---------------------------------------------------------------------------


def test_help_exits_0(capsys):
    with pytest.raises(SystemExit) as exc:
        rs.main(["--help"])
    assert exc.value.code == 0
    assert "route_someday" in capsys.readouterr().out


def test_missing_required_flag_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        rs.main(["--title", "x"])
    assert exc.value.code != 0
