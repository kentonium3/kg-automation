"""Repo-wide test guard for the off-host dead-man pings (#1077).

The canary and felix-health-check entry points now call
``scripts.common.deadman``. That module runs curl through ``subprocess``, so the
``urllib`` guard in ``tests/conftest.py`` does not reach it. That guard also
covers only ``tests/``, while the health-check suite lives under
``scripts/office2/felix_health_check/tests``.

On a machine holding the real ``/home/claude/.config/felix/deadman/env``, for
example office2, any test reaching ``main()`` would send a real ping to Kent's
production checks, and a ``/fail`` ping emails him. This autouse fixture, at the
repo root so every test tree is covered:

* points the dead-man env file at a path that never exists, so every ping is a
  no-op (``unconfigured``);
* unsets ``FELIX_ALERT_NTFY_TOPIC``, so the channel check returns
  ``topic_missing`` without running the ntfy probe.

Tests that exercise ``deadman`` itself inject their own runner, env file and
environment.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_deadman_pings(tmp_path_factory, monkeypatch):
    missing = tmp_path_factory.mktemp("deadman-guard") / "no-such-env"
    monkeypatch.setenv("FELIX_DEADMAN_ENV_FILE", str(missing))
    monkeypatch.delenv("FELIX_ALERT_NTFY_TOPIC", raising=False)
