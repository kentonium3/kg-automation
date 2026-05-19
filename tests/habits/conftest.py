"""Pytest conftest for habits tests.

This conftest serves two generations of habits tests:

1. Pre-Phase-3 (felix-admin-habits refactor — mission 282): tests that import
   `scripts/habits/*.py` modules by bare name (e.g. ``import
   query_active_habits``). The ``sys.path`` insertion below preserves that
   behaviour so existing tests continue to pass.

2. Phase 3 (this mission, habits-native-repeat-jsonl-state-01KS0M59): tests
   import via the canonical ``scripts.habits.*`` path. They consume the
   fixtures below for mocked Vikunja HTTP responses, sample task payloads,
   and a sandboxed state-log directory.

Available fixtures
------------------

``fake_vikunja_token`` — placeholder bearer token string.

``tmp_token_file(tmp_path, fake_vikunja_token)`` — temp file containing the
placeholder token (mode 0600). Returns the ``Path``.

``sample_habit_task_response`` — callable factory that returns a dict shaped
like the Vikunja ``GET /tasks/<id>`` response payload. Override any field
via kwargs.

``mock_urlopen(monkeypatch)`` — monkey-patches ``urllib.request.urlopen`` to
a ``MagicMock``. Tests configure ``mock_urlopen.return_value`` (or
``.side_effect``) to drive specific responses.

``mock_state_log_dir(tmp_path, monkeypatch)`` — monkey-patches
``scripts.common.state_log.STATE_DIR`` to a sandbox directory and sets the
``FELIX_STATE_LOG_DIR`` env var (so subprocess tests in later WPs see the
same sandbox). Returns the ``Path``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Legacy sys.path setup (mission 282 — tests use bare ``import <module>``)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_HABITS = REPO_ROOT / "scripts" / "habits"
if str(SCRIPTS_HABITS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_HABITS))


# ---------------------------------------------------------------------------
# Phase 3 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_vikunja_token() -> str:
    """Placeholder bearer token for tests. Never sent to a real server."""
    return "test-token-xxx"


@pytest.fixture
def tmp_token_file(tmp_path: Path, fake_vikunja_token: str) -> Path:
    """Write the placeholder token to a temp file (mode 0600) and return the path.

    macOS umask may strip group bits from the temp file's initial mode, so we
    explicitly chmod the file after creation to guarantee 0o600.
    """
    token_path = tmp_path / "token"
    token_path.write_text(fake_vikunja_token + "\n", encoding="utf-8")
    os.chmod(token_path, 0o600)
    return token_path


@pytest.fixture
def sample_habit_task_response():
    """Return a factory that builds a Vikunja ``GET /tasks/<id>`` response dict.

    Default fields are sensible for a non-workout daily habit; override via
    kwargs in the test body.
    """

    def _make(
        task_id: int,
        title: str = "Habit",
        repeat_after: int = 0,
        repeat_mode: int = 0,
        done: bool = False,
        due_date: str = "2026-05-20T08:00:00Z",
        project_id: int = 1,
        labels: list | None = None,
        is_archived: bool = False,
        done_at: str | None = None,
    ) -> dict:
        return {
            "id": task_id,
            "title": title,
            "repeat_after": repeat_after,
            "repeat_mode": repeat_mode,
            "done": done,
            "due_date": due_date,
            "project_id": project_id,
            "labels": labels or [],
            "is_archived": is_archived,
            "done_at": done_at,
        }

    return _make


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Monkey-patch ``urllib.request.urlopen`` to a ``MagicMock``.

    Tests configure responses by setting ``mock.return_value`` (single
    response) or ``mock.side_effect`` (sequence of responses or raising).

    The mock is patched in two places:
      - ``urllib.request.urlopen`` (anything that imports ``urllib.request``
        and calls ``urlopen`` on that module).
      - ``scripts.habits.identify_workout_task.urllib.request.urlopen`` for
        belt-and-suspenders (helps if a module bound the symbol locally).

    Returns the ``MagicMock`` so tests can configure return values or
    side effects.
    """
    mock = MagicMock(name="urlopen")
    monkeypatch.setattr("urllib.request.urlopen", mock)
    return mock


@pytest.fixture
def mock_state_log_dir(tmp_path: Path, monkeypatch) -> Path:
    """Sandbox ``scripts.common.state_log.STATE_DIR`` to a temp directory.

    Also sets the ``FELIX_STATE_LOG_DIR`` env var so subprocess-spawned tests
    in later WPs see the same sandbox path.

    Returns the sandbox ``Path``. The directory exists on return.
    """
    sandbox = tmp_path / "state"
    sandbox.mkdir(parents=True, exist_ok=True)

    # Late import so this conftest doesn't pull state_log at collection time.
    from scripts.common import state_log

    monkeypatch.setattr(state_log, "STATE_DIR", sandbox)
    monkeypatch.setenv("FELIX_STATE_LOG_DIR", str(sandbox))
    return sandbox
