"""Tests for ``signals.config_loader``.

Covers the validation paths the WP-01 prompt's T001 checklist asks for:
valid load, missing ``[meta]``, wrong schema version, duplicate
``signal_id``, threshold ordering, plus the per-field validators.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.observation.signals.config_loader import (  # noqa: E402
    ConfigError,
    SignalDefinition,
    load_config,
)


_VALID_BLOCK = textwrap.dedent(
    """
    [signals.test_signal]
    source_kind             = "openclaw_log"
    source_path_pattern     = "/tmp/openclaw/openclaw-*.log"
    match_pattern           = "needle"
    match_kind              = "substring"
    cycle_threshold         = 2
    rolling_window_minutes  = 60
    rolling_threshold       = 5
    dedup_strategy          = "open_issue_present"
    priority                = "P2"
    area_label              = "felix-core"
    tier_hypothesis         = "3"
    excerpt_lines           = 5
    enabled                 = true
    """
).strip()


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_loads_real_seed_config():
    seed = (
        _REPO_ROOT
        / "scripts"
        / "openclaw"
        / "observation"
        / "signals"
        / "config.toml"
    )
    defs = load_config(seed)
    assert len(defs) == 4
    assert {d.signal_id for d in defs} == {
        "whatsapp_creds_restore",
        "web_watchdog_reconnect",
        "openclaw_unhandled_error",
        "sweeper_tick",
    }
    assert all(isinstance(d, SignalDefinition) for d in defs)
    assert all(d.enabled for d in defs)


def test_load_returns_signal_definition_list(tmp_path: Path):
    body = "[meta]\nschema_version = 1\n" + _VALID_BLOCK
    defs = load_config(_write_config(tmp_path, body))
    assert len(defs) == 1
    d = defs[0]
    assert isinstance(d, SignalDefinition)
    assert d.signal_id == "test_signal"
    assert d.cycle_threshold == 2
    assert d.rolling_threshold == 5
    assert d.dedup_window_hours == 24  # default applied
    assert d.excerpt_lines == 5


def test_missing_meta_raises(tmp_path: Path):
    body = _VALID_BLOCK
    with pytest.raises(ConfigError, match=r"\[meta\]"):
        load_config(_write_config(tmp_path, body))


def test_wrong_schema_version_raises(tmp_path: Path):
    body = "[meta]\nschema_version = 2\n" + _VALID_BLOCK
    with pytest.raises(ConfigError, match="schema_version"):
        load_config(_write_config(tmp_path, body))


def test_duplicate_signal_id_rejected_by_toml_parser(tmp_path: Path):
    """tomllib rejects duplicate keys at parse time."""
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK
        + "\n"
        + _VALID_BLOCK
    )
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, body))


def test_rolling_below_cycle_rejected(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace("rolling_threshold       = 5",
                               "rolling_threshold       = 1")
    )
    with pytest.raises(ConfigError, match="rolling_threshold"):
        load_config(_write_config(tmp_path, body))


def test_cycle_threshold_must_be_positive(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace("cycle_threshold         = 2",
                               "cycle_threshold         = 0")
    )
    with pytest.raises(ConfigError, match="cycle_threshold"):
        load_config(_write_config(tmp_path, body))


def test_match_pattern_must_be_non_empty(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace('match_pattern           = "needle"',
                               'match_pattern           = ""')
    )
    with pytest.raises(ConfigError, match="match_pattern"):
        load_config(_write_config(tmp_path, body))


def test_relative_source_path_rejected(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace(
            'source_path_pattern     = "/tmp/openclaw/openclaw-*.log"',
            'source_path_pattern     = "openclaw-*.log"',
        )
    )
    with pytest.raises(ConfigError, match="absolute"):
        load_config(_write_config(tmp_path, body))


def test_unknown_source_kind_rejected(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace('source_kind             = "openclaw_log"',
                               'source_kind             = "totally_made_up"')
    )
    with pytest.raises(ConfigError, match="source_kind"):
        load_config(_write_config(tmp_path, body))


def test_unknown_tier_hypothesis_rejected(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace('tier_hypothesis         = "3"',
                               'tier_hypothesis         = "9"')
    )
    with pytest.raises(ConfigError, match="tier_hypothesis"):
        load_config(_write_config(tmp_path, body))


def test_unknown_priority_rejected(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace('priority                = "P2"',
                               'priority                = "P9"')
    )
    with pytest.raises(ConfigError, match="priority"):
        load_config(_write_config(tmp_path, body))


def test_missing_required_field_rejected(tmp_path: Path):
    block = "\n".join(
        line for line in _VALID_BLOCK.splitlines()
        if "priority" not in line
    )
    body = "[meta]\nschema_version = 1\n" + block
    with pytest.raises(ConfigError, match="priority"):
        load_config(_write_config(tmp_path, body))


def test_invalid_toml_raises(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[meta\nschema_version = 1\n")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(path)


def test_missing_file_raises_filenotfound(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")


def test_malformed_int_value_rejected(tmp_path: Path):
    body = (
        "[meta]\nschema_version = 1\n"
        + _VALID_BLOCK.replace("cycle_threshold         = 2",
                               "cycle_threshold         = \"not-an-int\"")
    )
    with pytest.raises(ConfigError, match="malformed value"):
        load_config(_write_config(tmp_path, body))


def test_signals_block_must_be_table(tmp_path: Path):
    # Top-level scalar ``signals`` (placed before [meta] so it lives at
    # the document root, not under the meta table) trips the
    # "signals block must be a dict" guard.
    body = "signals = 'oops'\n[meta]\nschema_version = 1\n"
    with pytest.raises(ConfigError, match="signals"):
        load_config(_write_config(tmp_path, body))


def test_signal_block_must_be_table(tmp_path: Path):
    # An array-of-tables creates a list, not a dict — should be
    # rejected. (Hand-built scenario; valid TOML, invalid schema.)
    body = textwrap.dedent(
        """
        [meta]
        schema_version = 1

        [[signals.test_signal]]
        source_kind = "openclaw_log"
        """
    ).strip()
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, body))
