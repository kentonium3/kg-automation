"""Tests for log_verbosity() in ObservationConfig.

Added by F014 — Felix Core Digest.
"""

import json
from pathlib import Path

import pytest

import sys

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

try:
    from scripts.openclaw.observation.config import ObservationConfig
except ImportError:
    from config import ObservationConfig


def _write_registry(tmp_path, agents):
    """Helper to write a temp registry JSON with the given agents dict."""
    registry = {
        "version": "1.0",
        "updated": "2026-04-04",
        "updated_by": "F014",
        "agents": agents,
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(registry))
    return reg_path


class TestLogVerbosity:
    def test_log_verbosity_returns_standard_for_agent(self, tmp_path):
        reg_path = _write_registry(tmp_path, {
            "test-agent": {
                "autonomy_level": "assisted",
                "log_verbosity": "standard",
            }
        })
        config = ObservationConfig(registry_path=reg_path)
        assert config.log_verbosity("test-agent") == "standard"

    def test_log_verbosity_returns_brief(self, tmp_path):
        reg_path = _write_registry(tmp_path, {
            "test-agent": {
                "autonomy_level": "assisted",
                "log_verbosity": "brief",
            }
        })
        config = ObservationConfig(registry_path=reg_path)
        assert config.log_verbosity("test-agent") == "brief"

    def test_log_verbosity_returns_verbose(self, tmp_path):
        reg_path = _write_registry(tmp_path, {
            "test-agent": {
                "autonomy_level": "assisted",
                "log_verbosity": "verbose",
            }
        })
        config = ObservationConfig(registry_path=reg_path)
        assert config.log_verbosity("test-agent") == "verbose"

    def test_log_verbosity_defaults_to_standard(self, tmp_path):
        """Agents registered before F014 may lack log_verbosity field."""
        reg_path = _write_registry(tmp_path, {
            "legacy-agent": {
                "autonomy_level": "assisted",
            }
        })
        config = ObservationConfig(registry_path=reg_path)
        assert config.log_verbosity("legacy-agent") == "standard"

    def test_log_verbosity_unknown_agent_raises_keyerror(self, tmp_path):
        reg_path = _write_registry(tmp_path, {
            "known-agent": {
                "autonomy_level": "assisted",
                "log_verbosity": "standard",
            }
        })
        config = ObservationConfig(registry_path=reg_path)
        with pytest.raises(KeyError, match="unknown.*not found"):
            config.log_verbosity("unknown")
