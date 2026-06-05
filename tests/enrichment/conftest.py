"""Pytest conftest for enrichment tests.

Provides the mock_vikunja_base_url autouse fixture so enrichment tests do
not require the vikunja-base-url.txt config file deployed on the test runner.
"""
from __future__ import annotations

import importlib

import pytest

_TEST_URL = "https://vikunja.test/api/v1/"

_ENRICHMENT_MODULES = [
    "scripts.enrichment.record_completion",
    "scripts.enrichment.reconcile_completions",
]


@pytest.fixture(autouse=True)
def mock_vikunja_base_url(monkeypatch):
    """Prevent get_vikunja_base_url() from reading the config file in tests.

    Patches the source module and from-imported namespaces.
    """
    monkeypatch.setattr(
        "scripts.common.vikunja_config.get_vikunja_base_url",
        lambda: _TEST_URL,
    )
    for _mod_path in _ENRICHMENT_MODULES:
        try:
            _mod = importlib.import_module(_mod_path)
            monkeypatch.setattr(_mod, "get_vikunja_base_url", lambda: _TEST_URL)
        except (ImportError, AttributeError):
            pass
