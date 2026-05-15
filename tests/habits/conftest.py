"""Pytest conftest for habits tests.

Adds scripts/habits/ to sys.path so helper modules import without installation.
Mirrors the tests/security/conftest.py precedent used for credential_health_check.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Repo root is two levels above this conftest (tests/habits/conftest.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_HABITS = REPO_ROOT / "scripts" / "habits"
if str(SCRIPTS_HABITS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_HABITS))
