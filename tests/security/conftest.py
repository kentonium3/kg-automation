"""Pytest conftest for security tests.

Adds scripts/security/ to sys.path so the credential_health_check and
anthropic_verify packages import without installation. Mirrors how the
systemd unit sets PYTHONPATH on office2.
"""
from __future__ import annotations

import sys
from pathlib import Path

import importlib

import pytest

# Repo root is two levels above this conftest (tests/security/conftest.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_SECURITY = REPO_ROOT / "scripts" / "security"
if str(SCRIPTS_SECURITY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_SECURITY))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------- #
# anthropic-verify fixture: mock office2 root
# --------------------------------------------------------------------------- #


@pytest.fixture
def tmp_office2_root(tmp_path, monkeypatch):
    """Build an empty office2-shaped layout under ``tmp_path`` and redirect
    anthropic_verify.core to it via environment variables.

    Returns a tuple ``(agents_dir, plaintext_path)`` so tests can populate the
    layout via the fixture-builder helpers in ``tests.security.fixtures``.

    Tests that need populated scenarios call ``build_fixtures.build_healthy``
    / ``build_shadow`` / ``build_drift`` against the returned ``agents_dir``
    + ``plaintext_path``.
    """
    agents_dir = tmp_path / "agents"
    plaintext_path = tmp_path / "anthropic"
    agents_dir.mkdir()
    monkeypatch.setenv("ANTHROPIC_VERIFY_AGENTS_DIR", str(agents_dir))
    monkeypatch.setenv("ANTHROPIC_VERIFY_PLAINTEXT_FILE", str(plaintext_path))
    return agents_dir, plaintext_path

_TEST_URL = "https://vikunja.test/api/v1/"

_SECURITY_MODULES = [
    "scripts.security.credential_health_check.vikunja_writer",
    # The test file imports via the sys.path-inserted path, which creates
    # a separate module object in sys.modules under this shorter key.
    "credential_health_check.vikunja_writer",
]


@pytest.fixture(autouse=True)
def isolate_reminder_state(tmp_path, monkeypatch):
    """Keep the #852 expiry-reminder ladder hermetic in every security test.

    - Redirects its JSONL firing ledger (``CREDENTIAL_HEALTH_STATE_DIR``) to a
      per-test tmp dir so no test ever reads/writes /data.
    - Ensures ``FELIX_ALERT_NTFY_TOPIC`` is unset so ``alert_bus.emit`` never
      attempts a real ntfy POST (it short-circuits to ok=False, no network).

    Returns the state dir so reminder tests can inspect the ledger.
    """
    state_dir = tmp_path / "cred-health-state"
    monkeypatch.setenv("CREDENTIAL_HEALTH_STATE_DIR", str(state_dir))
    monkeypatch.delenv("FELIX_ALERT_NTFY_TOPIC", raising=False)
    return state_dir


@pytest.fixture(autouse=True)
def mock_vikunja_base_url(monkeypatch):
    """Prevent get_vikunja_base_url() from reading the config file in tests.

    Patches the source module and from-imported namespaces.
    """
    monkeypatch.setattr(
        "scripts.common.vikunja_config.get_vikunja_base_url",
        lambda: _TEST_URL,
    )
    for _mod_path in _SECURITY_MODULES:
        try:
            _mod = importlib.import_module(_mod_path)
            monkeypatch.setattr(_mod, "get_vikunja_base_url", lambda: _TEST_URL)
        except (ImportError, AttributeError):
            pass
