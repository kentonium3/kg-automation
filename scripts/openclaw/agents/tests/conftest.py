"""Pytest fixtures for the openclaw agent verification tests.

These tests live four directories below the repository root:

    <repo_root>/scripts/openclaw/agents/tests/conftest.py

The `repo_root` fixture exposes the kg-automation repository root so that
test files can resolve paths to authoritative artifacts (AGENTS.md files,
fixture JSON, etc.) without hard-coded relative traversal.

Per WP01 (mission felix-calendar-subagent-extraction-01KTTA33), this
package establishes the test surface that asserts NFR-001, NFR-004, and
the openclaw.json registry contract for felix-admin-calendar.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Resolve the kg-automation repository root.

    This file is at ``scripts/openclaw/agents/tests/conftest.py``, so the
    repo root is four levels up from this file.
    """
    return Path(__file__).resolve().parents[4]
