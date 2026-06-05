"""Pytest conftest for vikunja tests.

Provides the mock_vikunja_base_url autouse fixture so vikunja tests do
not require the vikunja-base-url.txt config file deployed on the test runner.
"""
from __future__ import annotations

import importlib

import pytest

_TEST_URL = "https://vikunja.test/api/v1/"

_VIKUNJA_SCRIPT_MODULES = [
    "scripts.vikunja.provision_felix_bot",
    "scripts.vikunja.validate_felix_bot",
    "scripts.vikunja.swap_vikunja_secrets",
    "scripts.vikunja.revoke_kent_tokens",
    "scripts.vikunja.setup_goals",
    "scripts.vikunja.setup_vikunja",
]

# Short alias used by test_revoke_kent_tokens.py when it loads via importlib
# (spec_from_file_location with name="revoke_kent_tokens"). Must be patched
# in addition to the canonical module path.
_VIKUNJA_SYSMODULE_ALIASES = [
    "revoke_kent_tokens",
    "swap_vikunja_secrets",
    "validate_felix_bot",
    "provision_felix_bot",
]


@pytest.fixture(autouse=True)
def mock_vikunja_base_url(monkeypatch):
    """Prevent get_vikunja_base_url() from reading the config file in tests.

    Patches the source module and each vikunja script's local namespace
    (from-import binding), including sys.modules aliases used by importlib
    loaders in the test files.
    """
    import sys

    monkeypatch.setattr(
        "scripts.common.vikunja_config.get_vikunja_base_url",
        lambda: _TEST_URL,
    )
    for _mod_path in _VIKUNJA_SCRIPT_MODULES:
        try:
            _mod = importlib.import_module(_mod_path)
            monkeypatch.setattr(_mod, "get_vikunja_base_url", lambda: _TEST_URL)
        except (ImportError, AttributeError):
            pass
    # Patch sys.modules aliases (e.g. "revoke_kent_tokens" loaded via
    # spec_from_file_location in test_revoke_kent_tokens.py).
    for _alias in _VIKUNJA_SYSMODULE_ALIASES:
        _mod = sys.modules.get(_alias)
        if _mod is not None and hasattr(_mod, "get_vikunja_base_url"):
            monkeypatch.setattr(_mod, "get_vikunja_base_url", lambda: _TEST_URL)
