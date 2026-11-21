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
like the Vikunja v2 ``GET /api/v2/tasks/<id>`` response payload (via
``tests/common/vikunja_v2_factory.make_task``). Override any field via kwargs.

``mock_urlopen(monkeypatch)`` — monkey-patches ``urllib.request.urlopen`` to
a ``MagicMock``. Tests configure ``mock_urlopen.return_value`` (or
``.side_effect``) to drive specific responses.

``mock_state_log_dir(tmp_path, monkeypatch)`` — monkey-patches
``scripts.common.state_log.STATE_DIR`` to a sandbox directory and sets the
``FELIX_STATE_LOG_DIR`` env var (so subprocess tests in later WPs see the
same sandbox). Returns the ``Path``.

``stub_schedule(monkeypatch)`` — stubs ``sweeper.load_schedule`` so a
``*.stub.json`` schedule (rows of ``[task_id, title, [weekdays]]``) loads
without the YAML format, keeping sweeper tests independent of it. ``v2_advance_responses`` — urlopen responses for
one successful rule-driven sweeper advance (#1111).

``mock_sync_cache_fixture`` — re-exported from ``tests/common/conftest.py``
(mission #519 / WP01). Builder that synthesizes sync cache state for one
test invocation. Made available here so habits tests can use it after the
TP-03/TP-04/TP-07 cache migration (WP02).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Re-export sync cache fixture from tests/common/conftest.py so habits tests
# can use mock_sync_cache_fixture without an explicit import (pytest discovers
# fixtures from conftest files but only from the current directory upward, not
# from sibling directories).  Mission #519 / WP02 migration.
from tests.common.conftest import mock_sync_cache_fixture  # noqa: F401
from tests.common.vikunja_v2_factory import make_task

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
    """Return a factory that builds a Vikunja task response dict.

    Delegates to :func:`tests.common.vikunja_v2_factory.make_task`, so the
    body has the real v2 key set (``repeat`` / ``repeats_rrule`` /
    ``repeats_from_current_date``; the dead ``repeat_after`` /
    ``repeat_mode`` shape is gone, #1111). The default is a daily habit
    (``FREQ=DAILY;INTERVAL=1``). Any other task field can be overridden via
    keyword; ``is_archived`` is added only when given.
    """

    def _make(
        task_id: int,
        title: str = "Habit",
        *,
        done: bool = False,
        due_date: str = "2026-05-20T08:00:00Z",
        project_id: int = 1,
        labels: list | None = None,
        is_archived: bool | None = None,
        **overrides,
    ) -> dict:
        task = make_task(
            id=task_id,
            identifier=f"#{task_id}",
            index=task_id,
            title=title,
            done=done,
            due_date=due_date,
            project_id=project_id,
            labels=labels or [],
            **overrides,
        )
        if is_archived is not None:
            task["is_archived"] = is_archived
        return task

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


# ---------------------------------------------------------------------------
# WP05 migration: autouse fixture so habits tests don't require the
# vikunja-base-url.txt config file deployed on the test runner.
# Tests that need a specific URL pass --vikunja-base-url explicitly.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_vikunja_base_url(monkeypatch):
    """Prevent get_vikunja_base_url() from reading the config file in tests.

    set_due_dates.py imports the name into its own namespace (via the
    try/except import block), so we patch both the source module and the
    scripts.habits.set_due_dates namespace to cover both invocation paths.
    """
    monkeypatch.setattr(
        "scripts.common.vikunja_config.get_vikunja_base_url",
        lambda: "https://vikunja.test/api/v1/",
    )
    # Also patch from-imported namespaces for modules that do
    # ``from scripts.common.vikunja_config import get_vikunja_base_url``.
    _TEST_URL = "https://vikunja.test/api/v1/"
    for _mod_path in (
        "scripts.habits.set_due_dates",
        "scripts.habits.sweeper",
        "scripts.habits.identify_workout_task",
        "scripts.habits.exclude_completed",
        "scripts.habits.backfill_jsonl_from_comments",
    ):
        try:
            import importlib
            _mod = importlib.import_module(_mod_path)
            monkeypatch.setattr(_mod, "get_vikunja_base_url", lambda: _TEST_URL)
        except (ImportError, AttributeError):
            pass


# ---------------------------------------------------------------------------
# Sweeper fixtures (mission felix-rrule-adaptation-01M7TKNX, WP03 / #1111)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StubScheduleEntry:
    """The fields of ``schedule_loader.ScheduleEntry`` the sweeper reads."""

    task_id: int
    title: str
    designated_weekdays: tuple[str, ...] = ()


#: Suffix of a stub schedule file: a JSON list of
#: ``[task_id, title, [designated_weekdays...]]`` rows.
STUB_SCHEDULE_SUFFIX = ".stub.json"


@pytest.fixture
def stub_schedule(monkeypatch):
    """Stub ``sweeper.load_schedule`` so sweeper tests do not depend on the
    schedule YAML format (owned by ``schedule_loader``).

    A path ending in ``.stub.json`` holds a JSON list of
    ``[task_id, title, [weekday, ...]]`` rows and loads as
    :class:`StubScheduleEntry` objects; any other path goes to the real
    loader, so invalid-schedule tests still exercise it.
    """
    from scripts.habits import sweeper

    real = sweeper.load_schedule

    def _fake(path):
        path = Path(path)
        if not path.name.endswith(STUB_SCHEDULE_SUFFIX):
            return real(path)
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [
            StubScheduleEntry(task_id, title, tuple(weekdays))
            for task_id, title, weekdays in rows
        ]

    monkeypatch.setattr(sweeper, "load_schedule", _fake)


def _json_cm(payload) -> MagicMock:
    body = json.dumps(payload).encode("utf-8")
    resp = MagicMock(name="response", status=200)
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


@pytest.fixture
def v2_advance_responses():
    """Factory for the urlopen responses of one successful sweeper advance.

    ``make(task_id, occurrence)`` returns four context-manager mocks, in the
    order the sweeper calls them: GET v2 task (weekly Wednesday rule), GET
    occurrences (``[occurrence]``), PATCH ``due_date``, GET read-back.
    """

    def make(task_id: int = 76, occurrence: str = "2026-06-04T03:59:59Z") -> list:
        task = make_task(
            id=task_id,
            repeat={"freq": "weekly", "interval": 1, "by_day": ["we"]},
            due_date="2026-05-28T03:59:59Z",
        )
        moved = {**task, "due_date": occurrence}
        return [
            _json_cm(task),
            _json_cm({"occurrences": [occurrence]}),
            _json_cm(moved),
            _json_cm(moved),
        ]

    return make
