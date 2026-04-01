"""Tests for the Felix observation intelligence layer.

Test-first per the TEST_FIRST directive.
"""

import json
import tempfile
from pathlib import Path

import pytest

import sys

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

try:
    from scripts.openclaw.observation.config import ObservationConfig
    from scripts.openclaw.observation.summarize import (
        parse_log_file,
        filter_actions_by_autonomy,
        generate_digest,
        detect_critical_alerts,
        summarize_routine_actions,
    )
except ImportError:
    from config import ObservationConfig
    from summarize import (
        parse_log_file,
        filter_actions_by_autonomy,
        generate_digest,
        detect_critical_alerts,
        summarize_routine_actions,
    )

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- Config tests ---


class TestConfig:
    def test_load_registry_reads_autonomy_levels(self, tmp_path):
        registry = {
            "version": "1.0",
            "updated": "2026-04-01",
            "updated_by": "F012",
            "agents": {
                "test-agent": {
                    "autonomy_level": "assisted",
                    "scope": "test",
                    "team": "test",
                    "deployed_feature": "F000",
                    "registered": "2026-04-01",
                    "transition_history": [],
                }
            },
        }
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps(registry))

        config = ObservationConfig(registry_path=reg_path)
        assert config.autonomy_level("test-agent") == "assisted"

    def test_load_registry_handles_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Agent registry not found"):
            ObservationConfig(registry_path=tmp_path / "nonexistent.json")

    def test_load_registry_handles_invalid_format(self, tmp_path):
        bad_reg = tmp_path / "bad.json"
        bad_reg.write_text('{"version": "1.0"}')
        with pytest.raises(ValueError, match="agents.*missing"):
            ObservationConfig(registry_path=bad_reg)

    def test_autonomy_level_unknown_agent(self, tmp_path):
        registry = {
            "version": "1.0",
            "agents": {"known": {"autonomy_level": "assisted"}},
        }
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps(registry))

        config = ObservationConfig(registry_path=reg_path)
        with pytest.raises(KeyError, match="unknown.*not found"):
            config.autonomy_level("unknown")


# --- Log parsing tests ---


class TestLogParsing:
    def test_parse_single_log_file(self):
        result = parse_log_file(FIXTURES_DIR / "capture-routine.md")
        assert result["agent_name"] == "felix-admin-capture"
        assert len(result["actions"]) > 0
        assert "summary" in result

    def test_parse_log_extracts_categories(self):
        result = parse_log_file(FIXTURES_DIR / "capture-flagged.md")
        categories = [a["category"] for a in result["actions"]]
        assert "routine" in categories
        assert "flagged" in categories

    def test_parse_log_handles_missing_category_tag(self):
        """Actions without category tags default to routine."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\ndomain: resources\ntype: log\nupdated: 2026-04-01\nstatus: reference\n---\n\n")
            f.write("# Agent activity log — 2026-04-01 10:00\n\n")
            f.write("**Agent**: test-agent\n")
            f.write("**Run time**: 2026-04-01 10:00 ET\n\n")
            f.write("## Actions taken\n")
            f.write("- Did something without a tag\n\n")
            f.write("## Summary\n- Files processed: 1\n")
            f.name

        result = parse_log_file(Path(f.name))
        assert result["actions"][0]["category"] == "routine"

    def test_parse_error_log(self):
        result = parse_log_file(FIXTURES_DIR / "capture-error.md")
        categories = [a["category"] for a in result["actions"]]
        assert "error" in categories

    def test_parse_security_log(self):
        result = parse_log_file(FIXTURES_DIR / "capture-security.md")
        categories = [a["category"] for a in result["actions"]]
        assert "security" in categories

    def test_parse_habits_log(self):
        result = parse_log_file(FIXTURES_DIR / "habits-routine.md")
        assert result["agent_name"] == "felix-admin-habits"


# --- Autonomy-level filtering tests ---


class TestAutonomyFiltering:
    def _make_actions(self):
        return [
            {"category": "routine", "text": "Processed 2 files"},
            {"category": "flagged", "text": "Goal needs attention"},
            {"category": "error", "text": "File locked"},
            {"category": "security", "text": "Private path referenced"},
        ]

    def test_assisted_surfaces_all_categories(self):
        filtered = filter_actions_by_autonomy(self._make_actions(), "assisted")
        categories = [a["category"] for a in filtered]
        assert "routine" in categories
        assert "flagged" in categories
        assert "error" in categories
        assert "security" in categories

    def test_observed_surfaces_all_categories(self):
        filtered = filter_actions_by_autonomy(self._make_actions(), "observed")
        categories = [a["category"] for a in filtered]
        assert "routine" in categories
        assert "flagged" in categories
        assert "error" in categories

    def test_autonomous_omits_routine(self):
        filtered = filter_actions_by_autonomy(self._make_actions(), "autonomous")
        categories = [a["category"] for a in filtered]
        assert "routine" not in categories
        assert "flagged" in categories
        assert "error" in categories
        assert "security" in categories


# --- Critical alert tests ---


class TestCriticalAlerts:
    def test_error_triggers_critical_alert(self):
        actions = [{"category": "error", "text": "File locked"}]
        assert detect_critical_alerts(actions) is True

    def test_security_triggers_critical_alert(self):
        actions = [{"category": "security", "text": "Private path"}]
        assert detect_critical_alerts(actions) is True

    def test_routine_does_not_trigger_critical_alert(self):
        actions = [{"category": "routine", "text": "Processed file"}]
        assert detect_critical_alerts(actions) is False

    def test_flagged_does_not_trigger_critical_alert(self):
        actions = [{"category": "flagged", "text": "Goal needs review"}]
        assert detect_critical_alerts(actions) is False


# --- Digest generation tests ---


class TestDigestGeneration:
    def test_routine_summarized_as_counts(self):
        actions = [
            {"category": "routine", "text": "Processed file A"},
            {"category": "routine", "text": "Processed file B"},
            {"category": "routine", "text": "Created task #1"},
        ]
        summary = summarize_routine_actions(actions)
        assert "3" in summary  # count appears

    def test_generate_overview_consolidates_agents(self):
        agent_digests = {
            "felix-admin-capture": {
                "autonomy_level": "assisted",
                "runs": 3,
                "routine_summary": "4 notes processed, 6 tasks created",
                "elevated": [],
                "critical": False,
                "log_ref": "agents/logs/inbox-processing-2026-04-01.md",
            },
            "felix-admin-habits": {
                "autonomy_level": "assisted",
                "runs": 1,
                "routine_summary": "5 habits checked",
                "elevated": [],
                "critical": False,
                "log_ref": "agents/logs/habits-checkin-2026-04-01.md",
            },
        }
        overview = generate_digest(agent_digests, "2026-04-01")
        assert "felix-admin-capture" in overview
        assert "felix-admin-habits" in overview
        assert "2026-04-01" in overview

    def test_digest_includes_log_reference(self):
        agent_digests = {
            "felix-admin-capture": {
                "autonomy_level": "assisted",
                "runs": 1,
                "routine_summary": "1 note processed",
                "elevated": [],
                "critical": False,
                "log_ref": "agents/logs/inbox-processing-2026-04-01.md",
            },
        }
        overview = generate_digest(agent_digests, "2026-04-01")
        assert "agents/logs/inbox-processing-2026-04-01.md" in overview

    def test_flagged_items_elevated_with_detail(self):
        agent_digests = {
            "felix-admin-capture": {
                "autonomy_level": "assisted",
                "runs": 1,
                "routine_summary": "1 note processed",
                "elevated": [
                    {"category": "flagged", "text": 'Potential goal: "I want to do a triathlon"'}
                ],
                "critical": False,
                "log_ref": "agents/logs/inbox-processing-2026-04-01.md",
            },
        }
        overview = generate_digest(agent_digests, "2026-04-01")
        assert "triathlon" in overview
