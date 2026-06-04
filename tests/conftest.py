"""Top-level pytest conftest for the entire test suite.

Global test-isolation guard (mission #519): patches ``urllib.request.urlopen``
to raise ``RuntimeError`` by default.  This ensures that any test that
accidentally triggers a live HTTP call (e.g., a migrated touchpoint that
still has a direct Vikunja read lurking) fails loudly rather than silently
hitting the production server.

Tests that legitimately need to mock HTTP responses (write-side touchpoint
tests that retain direct Vikunja writes) patch over this guard using
``monkeypatch.setattr("urllib.request.urlopen", <mock>)`` AFTER this fixture
has been applied — their local patch takes precedence for the duration of
that test.
"""
from __future__ import annotations

import urllib.request

import pytest


@pytest.fixture(autouse=True)
def _block_live_http(monkeypatch):
    """Raise RuntimeError on any urllib.request.urlopen call during tests.

    This is a global guard: it applies to every test without opt-in.
    Tests that need real urlopen mocking (write-side tests) re-patch
    over this guard via monkeypatch.setattr in their own fixture or test body.
    """

    def _blocked_urlopen(*args, **kwargs):
        raise RuntimeError(
            "test attempted live HTTP — patch urllib.request.urlopen "
            "in your test or fixture instead of hitting production"
        )

    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)
