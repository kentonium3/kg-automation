"""openclaw.json registry-entry contract tests.

These tests validate the sanitized ``openclaw-sample.json`` fixture
against the contract documented in
``kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/openclaw-json-entry.md``.

Initial (RED) state at WP01 landing:
    * ``test_openclaw_json_parses`` PASSES — fixture is well-formed JSON.
    * ``test_felix_admin_calendar_entry_present`` FAILS — the
      felix-admin-calendar entry is intentionally absent from the
      fixture (its addition is what WP02/WP04 verify).
    * The four downstream entry-shape tests FAIL with the
      ``no felix-admin-calendar entry`` message because the helper
      cannot locate the entry.

WP02 / WP04 add the felix-admin-calendar entry to the fixture (and to
the live config) which flips all five entry-shaped tests to GREEN.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

FIXTURE_RELATIVE = Path(
    "scripts/openclaw/agents/tests/fixtures/openclaw-sample.json"
)

WORKSPACE_PATTERN = re.compile(r"^/data/services/openclaw/[a-z-]+-agent$")
AGENTDIR_PATTERN = re.compile(r"^/home/claude/\.openclaw/agents/[a-z-]+/agent$")

REQUIRED_ENTRY_KEYS = ("id", "name", "workspace", "agentDir", "model")


@pytest.fixture(scope="module")
def openclaw_config(repo_root: Path) -> dict[str, Any]:
    """Parse the sanitized openclaw.json fixture into a dict."""
    fixture_path = repo_root / FIXTURE_RELATIVE
    with fixture_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _calendar_entry(cfg: dict[str, Any]) -> dict[str, Any]:
    """Locate the felix-admin-calendar entry in agents.list[].

    Raises an explicit AssertionError when the entry is absent so the
    failure message names the missing entry rather than surfacing a
    raw StopIteration.
    """
    try:
        return next(
            entry
            for entry in cfg["agents"]["list"]
            if entry.get("id") == "felix-admin-calendar"
        )
    except StopIteration as exc:  # pragma: no cover - exercised in RED state
        raise AssertionError(
            "no felix-admin-calendar entry in agents.list[]"
        ) from exc


def test_openclaw_json_parses(openclaw_config: dict[str, Any]) -> None:
    """Fixture loads as JSON and exposes the agents block."""
    assert "agents" in openclaw_config
    assert "list" in openclaw_config["agents"]
    assert isinstance(openclaw_config["agents"]["list"], list)


def test_felix_admin_calendar_entry_present(
    openclaw_config: dict[str, Any],
) -> None:
    """agents.list[] contains an entry with id == felix-admin-calendar."""
    _calendar_entry(openclaw_config)


def test_felix_admin_calendar_entry_complete(
    openclaw_config: dict[str, Any],
) -> None:
    """The felix-admin-calendar entry exposes all 5 required keys."""
    entry = _calendar_entry(openclaw_config)
    missing = [key for key in REQUIRED_ENTRY_KEYS if not entry.get(key)]
    assert not missing, f"felix-admin-calendar entry missing keys: {missing}"


def test_workspace_path_pattern(openclaw_config: dict[str, Any]) -> None:
    """felix-admin-calendar.workspace matches the documented pattern."""
    entry = _calendar_entry(openclaw_config)
    workspace = entry.get("workspace", "")
    assert WORKSPACE_PATTERN.match(workspace), (
        f"workspace {workspace!r} does not match {WORKSPACE_PATTERN.pattern}"
    )


def test_agentdir_path_pattern(openclaw_config: dict[str, Any]) -> None:
    """felix-admin-calendar.agentDir matches the documented pattern."""
    entry = _calendar_entry(openclaw_config)
    agent_dir = entry.get("agentDir", "")
    assert AGENTDIR_PATTERN.match(agent_dir), (
        f"agentDir {agent_dir!r} does not match {AGENTDIR_PATTERN.pattern}"
    )


def test_model_known(openclaw_config: dict[str, Any]) -> None:
    """felix-admin-calendar.model must be a key in agents.defaults.models."""
    entry = _calendar_entry(openclaw_config)
    known_models = openclaw_config["agents"]["defaults"]["models"].keys()
    assert entry.get("model") in known_models, (
        f"model {entry.get('model')!r} not in defaults.models {list(known_models)}"
    )
