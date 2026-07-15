"""Tests for credential_health_check.vikunja_writer."""
from __future__ import annotations

import json
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from credential_health_check.vikunja_writer import (
    VikunjaWriteError,
    create_task,
    due_date_for_boundary,
    load_token,
    render_due_date_iso,
    task_description,
    task_title,
)
from credential_health_check.manifest import Credential

from scripts.common import vikunja_refs


def _registry_with_inbox(value) -> dict:
    """Build a minimal in-memory registry declaring the ``inbox`` project.

    ``value`` is the project_id (or ``None`` for an unprovisioned ref).
    """
    return {
        "schema_version": 1,
        "source_of_truth": "test",
        "last_verified_utc": "2026-07-15T00:00:00Z",
        "projects": [
            {
                "name": "inbox",
                "selector": {"kind": "project_id", "value": value},
                "title": "Inbox",
                "owner": "kent",
                "provisioned": value is not None,
            }
        ],
        "labels": [],
        "private_projects": [],
    }


_REGISTRY_NO_INBOX = {
    "schema_version": 1,
    "source_of_truth": "test",
    "last_verified_utc": "2026-07-15T00:00:00Z",
    "projects": [],
    "labels": [],
    "private_projects": [],
}


@pytest.fixture
def pinned_inbox_registry():
    """Install an in-memory registry (inbox=12) for the resolution path."""
    vikunja_refs.set_registry_for_test(_registry_with_inbox(12))
    try:
        yield 12
    finally:
        vikunja_refs.set_registry_for_test(None)


def _credential() -> Credential:
    return Credential(
        name="kg-felix-bot-pat",
        review_cadence="annual",
        storage="/home/claude/.config/gh/hosts.yml",
        expiry_notes="Rotate via gh auth.",
        type="api-token",
        last_reviewed=date(2026, 5, 11),
    )


# ---------- Pure helpers ----------


def test_due_date_for_boundary_subtracts_7_days():
    assert due_date_for_boundary(date(2027, 5, 11)) == date(2027, 5, 4)


def test_task_title_format():
    assert task_title(_credential()) == "Rotate credential: kg-felix-bot-pat"


def test_task_description_includes_github_link():
    desc = task_description(_credential(), date(2026, 5, 11), 42)
    assert "https://github.com/kentonium3/kg-automation/issues/42" in desc
    assert "2026-05-11" in desc
    assert "/home/claude/.config/gh/hosts.yml" in desc


def test_render_due_date_iso_uses_et_end_of_day():
    iso = render_due_date_iso(date(2026, 6, 1))
    # ET on 2026-06-01 is in EDT (UTC-4); end-of-day = 23:59:59-04:00.
    assert iso.startswith("2026-06-01T23:59:59")
    assert "-04:00" in iso or "-05:00" in iso  # EDT or EST depending on DST


# ---------- Token loading ----------


def test_load_token_reads_file(tmp_path: Path):
    token_path = tmp_path / "vikunja-api"
    token_path.write_text("test-token-value-12345\n")
    assert load_token(token_path) == "test-token-value-12345"


def test_load_token_strips_whitespace(tmp_path: Path):
    token_path = tmp_path / "vikunja-api"
    token_path.write_text("  test-token  \n\n")
    assert load_token(token_path) == "test-token"


def test_load_token_raises_on_missing(tmp_path: Path):
    with pytest.raises(VikunjaWriteError):
        load_token(tmp_path / "does-not-exist")


# ---------- API helpers ----------


def _mock_urlopen_response(data, code: int = 200):
    """Build a context-manager-compatible mock for urllib.request.urlopen()."""
    mock = MagicMock()
    mock.__enter__.return_value.read.return_value = json.dumps(data).encode("utf-8")
    mock.__exit__.return_value = False
    mock.code = code
    return mock


# ---------- Inbox resolution via the reference seam ----------


def test_create_task_resolves_inbox_via_registry(pinned_inbox_registry):
    """With no explicit inbox_project_id, the writer resolves it through the
    registry (network-free) and targets that project — no by-title GET."""
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _mock_urlopen_response({"id": 7})

    with patch(
        "credential_health_check.vikunja_writer.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        create_task(
            _credential(),
            date(2026, 6, 1),
            github_issue_number=42,
            token="test-token",
        )

    # Resolution was registry-backed (inbox=12) — the only HTTP call is the
    # task PUT, never a GET /projects list.
    assert f"/projects/{pinned_inbox_registry}/tasks" in captured["url"]


def test_create_task_fails_loud_when_inbox_undeclared():
    """SC-002: a deleted/undeclared inbox ref raises VikunjaRefError rather
    than silently mis-routing or returning a falsy id."""
    vikunja_refs.set_registry_for_test(_REGISTRY_NO_INBOX)
    try:
        with pytest.raises(vikunja_refs.VikunjaRefError):
            create_task(
                _credential(),
                date(2026, 6, 1),
                github_issue_number=42,
                token="test-token",
            )
    finally:
        vikunja_refs.set_registry_for_test(None)


def test_create_task_fails_loud_when_inbox_unprovisioned():
    """SC-002: a declared-but-unprovisioned inbox ref (value null) fails loud."""
    vikunja_refs.set_registry_for_test(_registry_with_inbox(None))
    try:
        with pytest.raises(vikunja_refs.VikunjaRefError):
            create_task(
                _credential(),
                date(2026, 6, 1),
                github_issue_number=42,
                token="test-token",
            )
    finally:
        vikunja_refs.set_registry_for_test(None)


# ---------- create_task ----------


def test_create_task_returns_id_from_response():
    response = {"id": 88, "title": "Rotate credential: kg-felix-bot-pat"}
    with patch(
        "credential_health_check.vikunja_writer.urllib.request.urlopen",
        return_value=_mock_urlopen_response(response),
    ):
        assert (
            create_task(
                _credential(),
                date(2026, 6, 1),
                github_issue_number=42,
                token="test-token",
                inbox_project_id=12,
            )
            == 88
        )


def test_create_task_constructs_expected_payload():
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["data"] = req.data
        captured["headers"] = dict(req.header_items())
        return _mock_urlopen_response({"id": 1})

    with patch(
        "credential_health_check.vikunja_writer.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        create_task(
            _credential(),
            date(2026, 6, 1),
            github_issue_number=42,
            token="test-token",
            inbox_project_id=12,
        )

    assert "/projects/12/tasks" in captured["url"]
    assert captured["method"] == "PUT"
    body = json.loads(captured["data"])
    assert body["title"] == "Rotate credential: kg-felix-bot-pat"
    assert "2026-05-25T23:59:59" in body["due_date"]  # boundary 2026-06-01 minus 7 days
    # Auth header normalized (note: urllib lowercases header names in headers).
    auth_header_keys = {k.lower() for k in captured["headers"].keys()}
    assert "authorization" in auth_header_keys


def test_create_task_raises_on_http_error():
    err = urllib.error.HTTPError(
        url="x", code=500, msg="boom", hdrs=None, fp=None
    )
    with patch(
        "credential_health_check.vikunja_writer.urllib.request.urlopen",
        side_effect=err,
    ):
        with pytest.raises(VikunjaWriteError):
            create_task(
                _credential(),
                date(2026, 6, 1),
                github_issue_number=42,
                token="test-token",
                inbox_project_id=12,
            )


def test_create_task_raises_on_url_error():
    with patch(
        "credential_health_check.vikunja_writer.urllib.request.urlopen",
        side_effect=urllib.error.URLError("network down"),
    ):
        with pytest.raises(VikunjaWriteError):
            create_task(
                _credential(),
                date(2026, 6, 1),
                github_issue_number=42,
                token="test-token",
                inbox_project_id=12,
            )


def test_create_task_raises_when_response_missing_id():
    with patch(
        "credential_health_check.vikunja_writer.urllib.request.urlopen",
        return_value=_mock_urlopen_response({"title": "no id field"}),
    ):
        with pytest.raises(VikunjaWriteError):
            create_task(
                _credential(),
                date(2026, 6, 1),
                github_issue_number=42,
                token="test-token",
                inbox_project_id=12,
            )
