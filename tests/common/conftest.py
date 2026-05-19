"""Shared fixtures for tests/common/.

Provides:

- ``REPO_ROOT`` constant — used by the CLI subprocess tests to set
  ``PYTHONPATH`` for the spawned child.
- ``state_dir`` fixture — creates an isolated temp directory and
  monkey-patches ``scripts.common.state_log.STATE_DIR`` so in-process
  tests never touch the production state path
  (``/data/services/openclaw/state``).
- ``good_habits_record`` fixture — a known-good habits record reused
  across append and read tests.

The conftest also inserts the repo root onto ``sys.path`` so test files
can ``from scripts.common import state_log`` without an installed
package (mirrors the pattern in ``tests/inbox/conftest.py`` and
``tests/habits/conftest.py``).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root is two levels above this conftest (tests/common/conftest.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Return an isolated temp state-log directory.

    Monkey-patches ``scripts.common.state_log.STATE_DIR`` to the temp
    dir, so any in-process call to ``append()`` / ``read()`` lands in
    the temp tree, never under ``/data/services/openclaw/state``.
    """
    d = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", d)
    return d


@pytest.fixture
def good_habits_record():
    """A known-good habits record matching the data-model contract."""
    return {
        "domain": "habits",
        "task_id": 14,
        "title": "Wake at 5:00 AM",
        "date": "2026-05-19",
        "state": "complete",
        "source": "whatsapp",
        "note": None,
        "timestamp": "2026-05-19T11:05:11+00:00",
    }
