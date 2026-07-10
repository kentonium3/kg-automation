"""Shared fixtures for the alert_bus test package.

Isolate the durable ledger (#706): every test in this package writes the ledger
to a per-test tmpdir instead of the office2 default ``/data/services/alert-bus``,
so `emit()`/CLI tests never touch real state and stay hermetic.
"""

from __future__ import annotations

import pytest

from scripts.common.alert_bus.ledger import LEDGER_DIR_ENV


@pytest.fixture(autouse=True)
def _isolate_alert_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv(LEDGER_DIR_ENV, str(tmp_path / "ledger"))
