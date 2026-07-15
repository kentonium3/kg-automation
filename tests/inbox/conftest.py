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

# Unify the bare ``routing_log`` and packaged ``scripts.inbox.routing_log``
# module identities. Inbox tests import the bare form (via the sys.path entry
# above) and monkeypatch ``routing_log.DEFAULT_ROUTING_LOG_PATH``, while
# ``prescan.py`` and ``route_calendar_event.py`` import the packaged form. Pin
# them to ONE module object so a monkeypatch on either is seen by both,
# regardless of which test imports which form first. Previously this identity
# held only by luck of import order; a test importing the packaged form early
# could split them and silently disable routing-log dedup in later tests.
import importlib as _importlib  # noqa: E402

_routing_log_mod = _importlib.import_module("routing_log")
sys.modules["scripts.inbox.routing_log"] = _routing_log_mod

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
