"""Tests for scripts/inbox/route_someday.py (WP03 of mission
capture-d6-helpers-extraction-01KTMS5Q).

Per FR-004 + helper-cli.md `route_someday` section + C-006:

- Resolve the project named ``Someday`` via ``client.get('/projects')``.
- Create the task via ``client.put('/projects/<id>/tasks', json={...})``
  (Vikunja's CREATE endpoint is ``PUT /projects/<id>/tasks`` per the
  existing ``scripts/habits/record_completion.py`` and
  ``scripts/security/credential_health_check/vikunja_writer.py``
  precedents). The C-006 invariant is "use CREATE, not partial update of
  an existing task" — POST on an existing /tasks/<id> partial-replaces
  unstated fields, which is the bug we are avoiding.
- Body includes a ``Source: <note-filename>`` footer line.

Mocking: ``VikunjaClient`` is patched at the module level (``rs.VikunjaClient``).
No real HTTP — the global ``_block_live_http`` fixture in
``tests/conftest.py`` ensures any escape blows up loudly.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.common.vikunja_client import VikunjaError
from scripts.inbox import route_someday as rs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_fake_client(projects=None, create_response=None, raise_on=None):
    """Construct a MagicMock client with .get/.put scripted.

    - ``projects``: list returned for GET /projects
    - ``create_response``: dict returned for PUT /projects/<id>/tasks
    - ``raise_on``: optional dict mapping method ("get"|"put") to an
      exception to raise on that call
    """
    client = MagicMock()
    raise_on = raise_on or {}

    def fake_get(path, **kwargs):
        if "get" in raise_on:
            raise raise_on["get"]
        return projects if projects is not None else []

    def fake_put(path, json=None, **kwargs):
        if "put" in raise_on:
            raise raise_on["put"]
        return create_response if create_response is not None else {"id": 1234}

    client.get.side_effect = fake_get
    client.put.side_effect = fake_put
    return client


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    """Default: VikunjaClient() returns a fake client with the Someday project."""
    fake = _make_fake_client(
        projects=[
            {"id": 7, "title": "Work"},
            {"id": 99, "title": "Someday"},
            {"id": 13, "title": "Habits"},
        ],
        create_response={"id": 4321, "title": "test-task"},
    )
    monkeypatch.setattr(rs, "VikunjaClient", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# Core behavior
# ---------------------------------------------------------------------------


def test_resolves_someday_project_by_name(_patch_client, capsys):
    rc = rs.main(
        [
            "--title",
            "Try Iceland again",
            "--body",
            "Planning notes",
            "--note-filename",
            "2026-06-09-iceland.md",
        ]
    )
    assert rc == 0
    # PUT was hit on /projects/99/tasks — id 99 is the Someday project.
    args, kwargs = _patch_client.put.call_args
    assert args[0] == "/projects/99/tasks"


def test_creates_task_with_title_and_description_including_source(
    _patch_client, capsys
):
    rc = rs.main(
        [
            "--title",
            "Build greenhouse",
            "--body",
            "Need 8x12 footprint, polycarbonate panels",
            "--note-filename",
            "2026-06-09-greenhouse.md",
        ]
    )
    assert rc == 0
    args, kwargs = _patch_client.put.call_args
    payload = kwargs.get("json") or (args[1] if len(args) > 1 else None)
    assert payload is not None
    assert payload["title"] == "Build greenhouse"
    assert "Need 8x12 footprint" in payload["description"]
    assert "Source: 2026-06-09-greenhouse.md" in payload["description"]


def test_uses_create_endpoint_not_partial_update(_patch_client):
    """C-006 protection: route_someday MUST use PUT /projects/<id>/tasks
    (Vikunja CREATE endpoint), NOT POST /tasks/<id> (which partial-replaces
    on existing tasks and was the root cause of #524)."""
    rs.main(
        [
            "--title",
            "Anything",
            "--body",
            "x",
            "--note-filename",
            "n.md",
        ]
    )
    # PUT path = create. Assert .put was called, .post was not.
    assert _patch_client.put.called
    assert not _patch_client.post.called
    args, _ = _patch_client.put.call_args
    # Path matches the create-task pattern, not a /tasks/<id> partial-update path.
    assert args[0].startswith("/projects/")
    assert args[0].endswith("/tasks")


def test_emits_task_id_on_stdout(_patch_client, capsys):
    rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    out = capsys.readouterr().out
    assert "task_id=4321" in out


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_vikunja_unreachable_exits_2(monkeypatch, capsys):
    fake = _make_fake_client(
        raise_on={"get": ConnectionError("network down")},
    )
    monkeypatch.setattr(rs, "VikunjaClient", lambda: fake)
    rc = rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "vikunja_error" in err


def test_vikunja_error_exits_2(monkeypatch, capsys):
    fake = _make_fake_client(
        raise_on={"get": VikunjaError(path="/projects", status=500)},
    )
    monkeypatch.setattr(rs, "VikunjaClient", lambda: fake)
    rc = rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "vikunja_error" in err


def test_someday_project_missing_exits_2(monkeypatch, capsys):
    fake = _make_fake_client(
        projects=[
            {"id": 7, "title": "Work"},
            {"id": 13, "title": "Habits"},
        ],
    )
    monkeypatch.setattr(rs, "VikunjaClient", lambda: fake)
    rc = rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "Someday" in err
    assert "vikunja_error" in err


def test_projects_response_not_a_list_exits_2(monkeypatch, capsys):
    """Defensive: /projects MUST return a list. If it returns something else
    (server bug, schema drift), surface it as a vikunja_error not a crash."""
    fake = _make_fake_client(projects={"not": "a list"})
    monkeypatch.setattr(rs, "VikunjaClient", lambda: fake)
    rc = rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "vikunja_error" in err


def test_create_task_error_exits_2(monkeypatch, capsys):
    fake = _make_fake_client(
        projects=[{"id": 99, "title": "Someday"}],
        raise_on={"put": VikunjaError(path="/projects/99/tasks", status=500)},
    )
    monkeypatch.setattr(rs, "VikunjaClient", lambda: fake)
    rc = rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "vikunja_error" in err


def test_create_task_response_missing_id_exits_2(monkeypatch, capsys):
    fake = _make_fake_client(
        projects=[{"id": 99, "title": "Someday"}],
        create_response={"title": "no id here"},
    )
    monkeypatch.setattr(rs, "VikunjaClient", lambda: fake)
    rc = rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "vikunja_error" in err


# ---------------------------------------------------------------------------
# CLI ergonomics
# ---------------------------------------------------------------------------


def test_help_exits_0_with_usage_text(capsys):
    with pytest.raises(SystemExit) as exc:
        rs.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "route_someday" in out or "Someday" in out or "title" in out


def test_missing_required_flag_argparse_exits_nonzero(capsys):
    """argparse exits 2 on missing required args; verify our CLI declares them required."""
    with pytest.raises(SystemExit) as exc:
        rs.main(["--title", "x"])
    assert exc.value.code != 0


# ---------------------------------------------------------------------------
# Helper-function unit coverage (raises path on find_someday_project)
# ---------------------------------------------------------------------------


def test_find_someday_project_raises_when_missing():
    """The internal helper raises a domain exception when the project is absent."""
    fake = _make_fake_client(projects=[{"id": 7, "title": "Work"}])
    client = fake  # already configured
    with pytest.raises(rs.RouteSomedayError):
        rs.find_someday_project(client)


def test_find_someday_project_returns_id_when_present():
    fake = _make_fake_client(
        projects=[{"id": 7, "title": "Work"}, {"id": 99, "title": "Someday"}]
    )
    assert rs.find_someday_project(fake) == 99


def test_client_construction_error_exits_2(monkeypatch, capsys):
    """If VikunjaClient() raises ValueError (e.g., bad config), surface as
    vikunja_error with exit 2 — not as an uncaught crash."""

    def boom():
        raise ValueError("token file missing")

    monkeypatch.setattr(rs, "VikunjaClient", boom)
    rc = rs.main(
        [
            "--title",
            "x",
            "--body",
            "y",
            "--note-filename",
            "n.md",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "vikunja_error" in err
    assert "token file missing" in err
