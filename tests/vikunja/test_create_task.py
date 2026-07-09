"""Tests for scripts.vikunja.create_task (issue #686).

All tests inject a fake client — no network, no token, no base-url config.
"""
from __future__ import annotations

import json

import pytest

from scripts.vikunja import create_task as ct


class _FakeClient:
    """Records get/put calls and returns canned responses."""

    def __init__(self, *, projects=None, put_result=None):
        self._projects = projects if projects is not None else []
        self._put_result = put_result if put_result is not None else {}
        self.put_calls: list[tuple[str, dict]] = []
        self.get_calls: list[str] = []

    def get(self, path, **_kwargs):
        self.get_calls.append(path)
        if path == "/projects":
            return self._projects
        raise AssertionError(f"unexpected GET {path}")

    def put(self, path, *, json=None, **_kwargs):  # noqa: A002 - mirror client API
        self.put_calls.append((path, json))
        return self._put_result


# --- build_payload ---------------------------------------------------------


def test_build_payload_title_only():
    assert ct.build_payload("Buy milk") == {"title": "Buy milk"}


def test_build_payload_strips_title():
    assert ct.build_payload("  Buy milk  ") == {"title": "Buy milk"}


def test_build_payload_all_fields():
    payload = ct.build_payload(
        "T", due_date="2026-07-16T14:00:00Z", description="d", priority=3
    )
    assert payload == {
        "title": "T",
        "due_date": "2026-07-16T14:00:00Z",
        "description": "d",
        "priority": 3,
    }


def test_build_payload_omits_empty_optionals():
    # Empty/None optionals must not leak nulls into the create body.
    payload = ct.build_payload("T", due_date=None, description="")
    assert payload == {"title": "T"}


def test_build_payload_empty_title_raises():
    with pytest.raises(ValueError):
        ct.build_payload("   ")


# --- resolve_project_id ----------------------------------------------------


def test_resolve_numeric_passthrough():
    client = _FakeClient()
    assert ct.resolve_project_id(client, "14") == 14
    assert client.get_calls == []  # no /projects fetch for a numeric id


def test_resolve_name_single_match():
    client = _FakeClient(projects=[{"id": 7, "title": "Work"}, {"id": 3, "title": "Home"}])
    assert ct.resolve_project_id(client, "work") == 7  # case-insensitive


def test_resolve_name_multi_match_lowest_id_wins():
    # Two "Inbox" projects (id 1 and 14) — deterministic tie-break to 1.
    client = _FakeClient(
        projects=[{"id": 14, "title": "Inbox"}, {"id": 1, "title": "Inbox"}]
    )
    assert ct.resolve_project_id(client, "Inbox") == 1


def test_resolve_name_no_match_raises():
    client = _FakeClient(projects=[{"id": 1, "title": "Inbox"}])
    with pytest.raises(ValueError):
        ct.resolve_project_id(client, "Nonexistent")


# --- create_task -----------------------------------------------------------


def test_create_task_uses_put_projects_tasks():
    client = _FakeClient(put_result={"id": 98, "identifier": "#38"})
    result = ct.create_task(client, 1, {"title": "T"})
    assert result == {"id": 98, "identifier": "#38"}
    assert client.put_calls == [("/projects/1/tasks", {"title": "T"})]


# --- main ------------------------------------------------------------------


def test_main_success_human_output(capsys):
    client = _FakeClient(put_result={"id": 98, "identifier": "#38", "title": "T", "due_date": "2026-07-16T14:00:00Z"})
    rc = ct.main(["--title", "T", "--project", "1", "--due", "2026-07-16T14:00:00Z"], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "identifier=#38" in out and "id=98" in out and "title: T" in out
    assert client.put_calls == [
        ("/projects/1/tasks", {"title": "T", "due_date": "2026-07-16T14:00:00Z"})
    ]


def test_main_json_output(capsys):
    client = _FakeClient(put_result={"id": 98, "identifier": "#38"})
    rc = ct.main(["--title", "T", "--json"], client=client)
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"id": 98, "identifier": "#38"}


def test_main_defaults_to_inbox_project_1():
    client = _FakeClient(put_result={"id": 1})
    ct.main(["--title", "T"], client=client)
    assert client.put_calls[0][0] == "/projects/1/tasks"


def test_main_reports_failure_and_returns_1(capsys):
    class _Boom(_FakeClient):
        def put(self, path, *, json=None, **_kwargs):
            raise RuntimeError("api down")

    rc = ct.main(["--title", "T"], client=_Boom())
    assert rc == 1
    assert "ERROR:" in capsys.readouterr().err
