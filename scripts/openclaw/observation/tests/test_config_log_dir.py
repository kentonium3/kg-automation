"""Tests for the HOME-independent log_dir default in ObservationConfig.

Added by WP01 (observation-digest-repoint) — the raw agent log directory
default must resolve to the absolute, backed-up vault path
/home/kgale/second-brain/agents/logs regardless of the HOME environment
variable, so the deployed service account (felix-core-digest.service sets
HOME=/home/claude) no longer writes raw logs to a stray /home/claude tree.
Verifies FR-001 (HOME-independent default) and FR-007 (explicit override
still honored).
"""

import sys
from pathlib import Path

# Ensure the package parent is importable regardless of invocation form.
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

try:
    from scripts.openclaw.observation.config import ObservationConfig
except ImportError:
    from config import ObservationConfig

# Repo root: tests/ -> observation/ -> openclaw/ -> scripts/ -> repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_REGISTRY_PATH = _REPO_ROOT / "docs" / "constitution" / "agent-registry.json"


def test_log_dir_default_is_home_independent(monkeypatch, tmp_path):
    """The default log_dir must ignore HOME and resolve to the vault path."""
    monkeypatch.setenv("HOME", str(tmp_path / "arbitrary-home"))
    config = ObservationConfig(registry_path=_REGISTRY_PATH)
    assert config.log_dir == Path("/home/kgale/second-brain/agents/logs")


def test_log_dir_explicit_override_is_honored(tmp_path):
    """An explicit log_dir= argument overrides the default."""
    override = tmp_path / "custom" / "logs"
    config = ObservationConfig(registry_path=_REGISTRY_PATH, log_dir=override)
    assert config.log_dir == override
