"""Tests for scripts.vikunja.cutover_verify (FR-007).

Every test injects a mocked ``VikunjaClient`` (stdlib ``unittest.mock``): no live
network, no credential file, no token-seam resolution (a client is always passed
to ``main``, so ``_build_client`` / ``get_vikunja_token_path`` never run). The
fake's ``.get`` serves canned pages keyed by request path; ``.post/.put/.patch/
.delete`` stay untouched so the read-only contract can be asserted.
"""
from __future__ import annotations

import json

import pytest
from unittest import mock

from scripts.common.vikunja_client import (
    VikunjaAuthError,
    VikunjaError,
    VikunjaServerError,
)
from scripts.vikunja import cutover_verify as cv


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


def _make_client(pages_by_path=None, *, get_side_effect=None):
    """Build a ``Mock`` whose ``.get`` serves canned pages keyed by path.

    ``pages_by_path`` maps a request path (e.g. ``"/projects"``) to a list of
    pages; page N (1-indexed via the ``page`` param) returns that element, or
    ``[]`` once exhausted / for an unknown path. Pass ``get_side_effect`` to
    override with an arbitrary callable (e.g. one that raises).
    """
    client = mock.Mock(name="VikunjaClient")

    if get_side_effect is not None:
        client.get.side_effect = get_side_effect
        return client

    pages_by_path = pages_by_path or {}

    def _get(path, *, params=None, timeout=None):
        page = int(params.get("page", "1")) if params else 1
        pages = pages_by_path.get(path)
        if pages is None:
            return []
        idx = page - 1
        return pages[idx] if 0 <= idx < len(pages) else []

    client.get.side_effect = _get
    return client


def _projects_page(ids):
    return [{"id": pid, "title": f"Project {pid}"} for pid in ids]


def _assert_read_only(client):
    """No write verb was ever invoked."""
    client.post.assert_not_called()
    client.put.assert_not_called()
    client.patch.assert_not_called()
    client.delete.assert_not_called()


# ---------------------------------------------------------------------------
# inverse-probe
# ---------------------------------------------------------------------------


def test_inverse_probe_passes_when_expected_present():
    ids = list(cv.DEFAULT_EXPECT_PROJECTS) + [2, 99]
    client = _make_client({"/projects": [_projects_page(ids)]})

    result = cv.inverse_probe(client, list(cv.DEFAULT_EXPECT_PROJECTS))

    assert result.ok is True
    assert result.missing == []
    assert result.present == sorted(cv.DEFAULT_EXPECT_PROJECTS)
    _assert_read_only(client)


def test_inverse_probe_fails_loud_when_one_missing():
    present_ids = [1, 13, 16, 17, 18, 19]  # 20 deliberately absent
    client = _make_client({"/projects": [_projects_page(present_ids)]})

    result = cv.inverse_probe(client, list(cv.DEFAULT_EXPECT_PROJECTS))

    assert result.ok is False
    assert result.missing == [20]
    assert 20 not in result.present


def test_inverse_probe_ignores_negative_pseudo_projects():
    # Favorites (-1) and saved-filter shims (-2...) must not count as visible.
    page = _projects_page([1, 13, 16, 17, 18, 19, 20]) + [
        {"id": -1, "title": "Favorites"},
        {"id": -2, "title": "Today"},
    ]
    client = _make_client({"/projects": [page]})

    result = cv.inverse_probe(client, list(cv.DEFAULT_EXPECT_PROJECTS))

    assert result.ok is True
    assert all(pid > 0 for pid in result.visible)


def test_inverse_probe_custom_expect_projects_via_main(capsys):
    client = _make_client({"/projects": [_projects_page([16, 17])]})

    rc = main_json(client, ["--inverse-probe", "--expect-projects", "16,17"])

    assert rc == 0
    summary = _read_json(capsys)
    assert summary["inverse_probe"]["expected"] == [16, 17]
    assert summary["inverse_probe"]["ok"] is True


def test_main_inverse_probe_missing_exits_nonzero(capsys):
    client = _make_client({"/projects": [_projects_page([1, 13, 16, 17, 18, 19])]})

    rc = main_json(client, ["--inverse-probe"])

    assert rc == 1
    summary = _read_json(capsys)
    assert summary["inverse_probe"]["missing"] == [20]
    assert summary["ok"] is False
    _assert_read_only(client)


# ---------------------------------------------------------------------------
# task-delta
# ---------------------------------------------------------------------------


def test_task_delta_counts_correctly():
    pages = {
        "/projects/16/tasks": [[{"id": 1}, {"id": 2}, {"id": 3}]],
        "/projects/17/tasks": [[{"id": 4}]],
        "/projects/18/tasks": [[]],
        "/projects/19/tasks": [[{"id": 5}, {"id": 6}]],
        "/projects/20/tasks": [[{"id": 7}]],
    }
    client = _make_client(pages)

    result = cv.task_delta(client, list(cv.DEFAULT_DELTA_PROJECTS))

    assert result.per_project == {16: 3, 17: 1, 18: 0, 19: 2, 20: 1}
    assert result.total == 7
    assert result.projects == [16, 17, 18, 19, 20]
    _assert_read_only(client)


def test_task_delta_pagination_accumulates_across_pages():
    full = [{"id": i} for i in range(cv._PAGE_SIZE)]  # a full page → keep paging
    tail = [{"id": 999}]
    client = _make_client({"/projects/16/tasks": [full, tail]})

    count = cv.count_project_tasks(client, 16)

    assert count == cv._PAGE_SIZE + 1


def test_task_delta_json_shape_uses_string_keys(capsys):
    pages = {
        "/projects/16/tasks": [[{"id": 1}]],
        "/projects/17/tasks": [[]],
        "/projects/18/tasks": [[]],
        "/projects/19/tasks": [[]],
        "/projects/20/tasks": [[]],
    }
    client = _make_client(pages)

    rc = main_json(client, ["--task-delta"])

    assert rc == 0
    summary = _read_json(capsys)
    assert summary["task_delta"]["per_project"]["16"] == 1
    assert summary["task_delta"]["total"] == 1


# ---------------------------------------------------------------------------
# connectivity
# ---------------------------------------------------------------------------


def test_connectivity_all_surfaces_ok():
    pages = {
        "/projects": [_projects_page([16, 17])],
        "/projects/16/tasks": [[{"id": 1}]],
        "/labels": [[{"id": 5, "title": "urgent"}]],
    }
    client = _make_client(pages)

    result = cv.connectivity_check(client)

    assert result.ok is True
    assert {s.surface for s in result.surfaces} == {"projects", "tasks", "labels"}
    assert all(s.ok for s in result.surfaces)
    _assert_read_only(client)


def test_connectivity_maps_client_error_to_nonzero(capsys):
    def _raise(path, *, params=None, timeout=None):
        raise VikunjaAuthError(path=path, status=401)

    client = _make_client(get_side_effect=_raise)

    rc = main_json(client, ["--connectivity"])

    assert rc == 1
    summary = _read_json(capsys)
    assert summary["connectivity"]["ok"] is False
    assert summary["ok"] is False
    # The projects surface failed, so the task surface is unreadable too.
    surfaces = {s["surface"]: s for s in summary["connectivity"]["surfaces"]}
    assert surfaces["projects"]["ok"] is False
    assert surfaces["projects"]["error"] is not None


def test_connectivity_partial_surface_failure_flags_not_ok():
    def _get(path, *, params=None, timeout=None):
        if path == "/labels":
            raise VikunjaServerError(path=path, status=500)
        if path == "/projects":
            return _projects_page([16])
        return []  # task page ok

    client = _make_client(get_side_effect=_get)

    result = cv.connectivity_check(client)

    assert result.ok is False
    surfaces = {s.surface: s for s in result.surfaces}
    assert surfaces["projects"].ok is True
    assert surfaces["tasks"].ok is True
    assert surfaces["labels"].ok is False


def test_connectivity_no_visible_projects_marks_task_surface_failed():
    client = _make_client({"/projects": [[]], "/labels": [[{"id": 1}]]})

    result = cv.connectivity_check(client)

    surfaces = {s.surface: s for s in result.surfaces}
    assert surfaces["tasks"].ok is False
    assert "no project" in surfaces["tasks"].error
    assert result.ok is False


# ---------------------------------------------------------------------------
# main: default (all checks), output, exit codes
# ---------------------------------------------------------------------------


def test_main_default_runs_all_checks_and_passes(capsys):
    pages = {
        "/projects": [_projects_page([1, 13, 16, 17, 18, 19, 20])],
        "/projects/16/tasks": [[{"id": 1}]],
        "/labels": [[{"id": 5}]],
        "/projects/17/tasks": [[]],
        "/projects/18/tasks": [[]],
        "/projects/19/tasks": [[]],
        "/projects/20/tasks": [[]],
    }
    client = _make_client(pages)

    rc = main_json(client, [])

    assert rc == 0
    summary = _read_json(capsys)
    assert summary["checks"] == ["inverse-probe", "connectivity", "task-delta"]
    assert summary["inverse_probe"] is not None
    assert summary["connectivity"] is not None
    assert summary["task_delta"] is not None
    assert summary["ok"] is True
    _assert_read_only(client)


def test_main_human_output_has_summary_line(capsys):
    client = _make_client({"/projects": [_projects_page([16])]})

    rc = cv.main(["--inverse-probe", "--expect-projects", "16"], client=client)

    assert rc == 0
    out = capsys.readouterr().out
    assert "SUMMARY:" in out
    assert "ok=True" in out


def test_main_bad_expect_projects_is_usage_error(capsys):
    client = _make_client({})

    rc = cv.main(
        ["--inverse-probe", "--expect-projects", "16,notanint"], client=client
    )

    assert rc == 2
    err = capsys.readouterr().err
    assert "ERROR:" in err
    client.get.assert_not_called()


def test_main_api_error_during_probe_exits_one(capsys):
    def _raise(path, *, params=None, timeout=None):
        raise VikunjaError(path=path, status=500)

    client = _make_client(get_side_effect=_raise)

    rc = cv.main(["--inverse-probe", "--json"], client=client)

    assert rc == 1
    err = capsys.readouterr().err
    assert "ERROR:" in err


def test_main_token_path_null_when_client_injected(capsys):
    client = _make_client({"/projects": [_projects_page([16])]})

    main_json(client, ["--inverse-probe", "--expect-projects", "16"])

    summary = _read_json(capsys)
    assert summary["token_path"] is None


# ---------------------------------------------------------------------------
# token seam wiring (no injected client) — _build_client resolves via the seam
# ---------------------------------------------------------------------------


def test_build_client_resolves_token_via_seam(monkeypatch, tmp_path):
    token_file = tmp_path / "vikunja-api-kent"
    token_file.write_text("seam-token-value", encoding="utf-8")

    monkeypatch.setattr(cv, "get_vikunja_token_path", lambda: token_file)

    captured = {}

    class _FakeVikunjaClient:
        def __init__(self, *, base_url=None, token=None, timeout=30.0):
            captured["base_url"] = base_url
            captured["token"] = token

    monkeypatch.setattr(
        "scripts.common.vikunja_client.VikunjaClient", _FakeVikunjaClient
    )

    client, token_path = cv._build_client("https://vikunja.test/api/v1/")

    assert isinstance(client, _FakeVikunjaClient)
    assert captured["token"] == "seam-token-value"
    assert token_path == str(token_file)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def main_json(client, extra_args):
    """Run ``main`` with ``--json`` and the injected client."""
    return cv.main([*extra_args, "--json"], client=client)


def _read_json(capsys):
    out = capsys.readouterr().out.strip()
    return json.loads(out)
