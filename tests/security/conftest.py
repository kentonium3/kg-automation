"""Pytest conftest for security tests.

Adds scripts/security/ to sys.path so the credential_health_check package
imports without installation. Mirrors how the systemd unit sets PYTHONPATH
on office2.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Repo root is two levels above this conftest (tests/security/conftest.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_SECURITY = REPO_ROOT / "scripts" / "security"
if str(SCRIPTS_SECURITY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_SECURITY))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
