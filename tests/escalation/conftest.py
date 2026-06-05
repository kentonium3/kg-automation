"""Pytest conftest for escalation tests (Phase 6).

Shared fixtures consumed by WP01 schema tests and the downstream helper-test
WPs (WP02-WP06). Mirrors the shape of ``tests/habits/conftest.py`` (Phase 3
precedent).

Available fixtures
------------------

``fake_vikunja_token`` — placeholder bearer token string.

``tmp_token_file(tmp_path, fake_vikunja_token)`` — temp file (mode 0600)
containing the placeholder token. Returns the ``Path``.

``sample_vikunja_task`` — callable factory for a Vikunja-API-shaped task
dict. Override defaults via kwargs.

``make_felix_comment`` — callable factory for a Vikunja comment dict (used
by the backfill helper tests in later WPs).

``make_jsonl_record`` — callable factory for an escalation JSONL record dict
matching data-model Entity 1. Default ``state="level_sent"``, override any
field (or add extra params like ``level``, ``snooze_days``, etc.) via kwargs.

``mock_state_log_dir(tmp_path, monkeypatch)`` — monkey-patches
``scripts.common.state_log.STATE_DIR`` to a sandbox under ``tmp_path/state``
and creates ``state/escalation/`` for direct JSONL writes. Returns the
sandbox ``Path``.

``mock_urlopen(monkeypatch)`` — monkey-patches ``urllib.request.urlopen`` to
a ``MagicMock``. Tests configure ``mock.return_value`` (single response) or
``mock.side_effect`` (sequence or raising).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Token + auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_vikunja_token() -> str:
    """Placeholder bearer token for tests. Never sent to a real server."""
    return "test-token-xxx"


@pytest.fixture
def tmp_token_file(tmp_path: Path, fake_vikunja_token: str) -> Path:
    """Write the placeholder token to a temp file (mode 0600) and return it.

    macOS umask may strip group bits from the temp file's initial mode, so we
    explicitly chmod the file after creation to guarantee 0o600.
    """
    token_path = tmp_path / "token"
    token_path.write_text(fake_vikunja_token + "\n", encoding="utf-8")
    os.chmod(token_path, 0o600)
    return token_path


# ---------------------------------------------------------------------------
# Vikunja payload factories
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_vikunja_task():
    """Return a factory that builds a Vikunja ``GET /tasks/<id>`` response dict.

    Defaults represent an open escalation-candidate task; override via kwargs.
    """

    def _make(
        task_id: int,
        title: str = "Task",
        done: bool = False,
        project_id: int = 4,
        priority: int = 3,
        due_date: str = "2026-05-15T00:00:00Z",
        comments: list | None = None,
    ) -> dict:
        return {
            "id": task_id,
            "title": title,
            "done": done,
            "project_id": project_id,
            "priority": priority,
            "due_date": due_date,
            "comments": comments or [],
        }

    return _make


@pytest.fixture
def make_felix_comment():
    """Return a factory that builds a Vikunja-API-shaped comment dict."""

    def _make(
        comment_text: str,
        comment_id: int = 1,
        created: str = "2026-05-15T08:00:00Z",
    ) -> dict:
        return {
            "id": comment_id,
            "comment": comment_text,
            "created": created,
        }

    return _make


# ---------------------------------------------------------------------------
# JSONL record factory (matches data-model Entity 1)
# ---------------------------------------------------------------------------


@pytest.fixture
def make_jsonl_record():
    """Return a factory that builds an escalation JSONL record dict.

    Defaults produce a minimally-valid ``level_sent`` record for ``task_id=1234``
    in ``project_id=4``. Extra structured parameters (``level``,
    ``snooze_days``, ``snooze_until``, ``reschedule_to``, ``reason``, ...) are
    passed via ``**params`` and merged into the returned dict. Override
    ``state``, ``date``, ``title``, ``source``, etc. via explicit kwargs.
    """

    def _make(
        task_id: int = 1234,
        project_id: int = 4,
        state: str = "level_sent",
        date: str = "2026-05-21",
        source: str = "agent",
        title: str = "Task",
        note: str | None = None,
        **params,
    ) -> dict:
        record = {
            "domain": "escalation",
            "task_id": task_id,
            "title": title,
            "date": date,
            "state": state,
            "source": source,
            "timestamp": f"{date}T12:00:00+00:00",
            "note": note,
            "project_id": project_id,
        }
        record.update(params)
        return record

    return _make


# ---------------------------------------------------------------------------
# State-log sandbox + HTTP mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_state_log_dir(tmp_path: Path, monkeypatch) -> Path:
    """Sandbox ``scripts.common.state_log.STATE_DIR`` to a temp directory.

    Creates ``<tmp_path>/state/escalation/`` for direct JSONL writes from
    later-WP helper tests. Also sets the ``FELIX_STATE_LOG_DIR`` env var so
    subprocess-spawned tests see the same sandbox.

    Returns the sandbox ``Path`` (``<tmp_path>/state``).
    """
    sandbox = tmp_path / "state"
    (sandbox / "escalation").mkdir(parents=True, exist_ok=True)

    # Late import so this conftest does not pull state_log at collection time.
    from scripts.common import state_log

    monkeypatch.setattr(state_log, "STATE_DIR", sandbox)
    monkeypatch.setenv("FELIX_STATE_LOG_DIR", str(sandbox))
    return sandbox


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Monkey-patch ``urllib.request.urlopen`` to a ``MagicMock``.

    Tests configure responses by setting ``mock.return_value`` (single
    response) or ``mock.side_effect`` (sequence of responses or raising).
    """
    mock = MagicMock(name="urlopen")
    monkeypatch.setattr("urllib.request.urlopen", mock)
    return mock


# ---------------------------------------------------------------------------
# Autouse: prevent get_vikunja_base_url() from reading the config file
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_vikunja_base_url(monkeypatch):
    """Prevent get_vikunja_base_url() from reading the config file in tests.

    Patches the source module and from-imported namespaces.
    """
    import importlib

    _TEST_URL = "https://vikunja.test/api/v1/"

    monkeypatch.setattr(
        "scripts.common.vikunja_config.get_vikunja_base_url",
        lambda: _TEST_URL,
    )
    for _mod_path in (
        "scripts.escalation.record_completion",
    ):
        try:
            _mod = importlib.import_module(_mod_path)
            monkeypatch.setattr(_mod, "get_vikunja_base_url", lambda: _TEST_URL)
        except (ImportError, AttributeError):
            pass
