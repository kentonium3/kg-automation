"""Pytest bootstrap for inbox tests.

Adds scripts/inbox/ to sys.path so test files can `import routing_log`
without an installed package. Exposes FIXTURES_DIR as a module attribute
for the fixture-loading tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_INBOX = REPO_ROOT / "scripts" / "inbox"
if str(SCRIPTS_INBOX) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_INBOX))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
