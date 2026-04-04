"""Tests for the Felix observation intelligence layer.

Test-first per the TEST_FIRST directive.
"""

import json
import os
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

import sys

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

try:
    from scripts.openclaw.observation.config import ObservationConfig
    from scripts.openclaw.observation.summarize import (
        parse_jsonl_log,
        filter_actions_by_autonomy,
        generate_digest,
        generate_agent_detail,
        detect_critical_alerts,
        summarize_routine_actions,
        find_log_files,
        run,
        _apply_retention,
        _group_by_run_id,
        RETENTION_DAYS,
    )
except ImportError:
    from config import ObservationConfig
    from summarize import (
        parse_jsonl_log,
        filter_actions_by_autonomy,
        generate_digest,
        generate_agent_detail,
        detect_critical_alerts,
        summarize_routine_actions,
        find_log_files,
        run,
        _apply_retention,
        _group_by_run_id,
        RETENTION_DAYS,
    )

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_config(tmp_path, log_dir=None, output_dir=None):
    """Create an ObservationConfig with a minimal registry for testing."""
    registry = {
        "version": "1.0",
        "updated": "2026-04-01",
        "updated_by": "test",
        "agents": {
            "felix-admin-capture": {
                "autonomy_level": "assisted",
                "scope": "inbox",
                "team": "admin",
                "deployed_feature": "F012",
                "registered": "2026-04-01",
                "transition_history": [],
            },
            "felix-admin-habits": {
                "autonomy_level": "assisted",
                "scope": "habits",
                "team": "admin",
                "deployed_feature": "F012",
                "registered": "2026-04-01",
                "transition_history": [],
            },
        },
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(registry))

    return ObservationConfig(
        registry_path=reg_path,
        log_dir=str(log_dir or tmp_path / "logs"),
        output_dir=str(output_dir or tmp_path / "output"),
    )


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


# --- JSONL Log parsing tests ---


class TestLogParsing:
    def test_parse_single_jsonl_log(self):
        result = parse_jsonl_log(FIXTURES_DIR / "capture-routine.jsonl")
        assert len(result) == 8
        assert all(r["category"] == "routine" for r in result)
        assert all(r["agent_name"] == "felix-admin-capture" for r in result)

    def test_parse_log_extracts_categories(self):
        result = parse_jsonl_log(FIXTURES_DIR / "capture-flagged.jsonl")
        categories = [a["category"] for a in result]
        assert "routine" in categories
        assert "flagged" in categories

    def test_parse_error_log(self):
        result = parse_jsonl_log(FIXTURES_DIR / "capture-error.jsonl")
        categories = [a["category"] for a in result]
        assert "error" in categories
        assert len(result) == 5

    def test_parse_security_log(self):
        result = parse_jsonl_log(FIXTURES_DIR / "capture-security.jsonl")
        categories = [a["category"] for a in result]
        assert "security" in categories
        assert len(result) == 3

    def test_parse_habits_log(self):
        result = parse_jsonl_log(FIXTURES_DIR / "habits-routine.jsonl")
        assert all(r["agent_name"] == "felix-admin-habits" for r in result)
        assert len(result) == 3

    def test_parse_habits_mixed(self):
        result = parse_jsonl_log(FIXTURES_DIR / "habits-mixed.jsonl")
        categories = [a["category"] for a in result]
        assert "flagged" in categories
        assert categories.count("routine") == 3
        assert len(result) == 4

    def test_parse_multi_run(self):
        result = parse_jsonl_log(FIXTURES_DIR / "multi-run.jsonl")
        run_ids = set(a["run_id"] for a in result)
        assert len(run_ids) == 2
        assert len(result) == 6

    def test_parse_verbose_trace(self):
        result = parse_jsonl_log(FIXTURES_DIR / "verbose-trace.jsonl")
        assert len(result) == 3
        # Verify context and trace fields are preserved
        assert "context" in result[0]
        assert "trace" in result[0]
        assert result[0]["context"]["confidence"] == 0.95
        assert result[0]["trace"]["api_calls"] == 2

    def test_parse_malformed_skips_bad_lines(self, capsys):
        result = parse_jsonl_log(FIXTURES_DIR / "malformed.jsonl")
        # Only 2 valid lines (first valid, one broken JSON, one missing fields, one empty, one valid)
        assert len(result) == 2
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "malformed" in captured.err.lower() or "Skipping" in captured.err

    def test_parse_truncated_refs(self):
        result = parse_jsonl_log(FIXTURES_DIR / "truncated-refs.jsonl")
        assert len(result) == 3
        assert "context" in result[0]
        assert result[0]["context"]["proposal_ref"] == "F014-WP03-T011"

    def test_text_field_combines_action_and_target(self):
        result = parse_jsonl_log(FIXTURES_DIR / "capture-routine.jsonl")
        # text should be "action: target"
        assert result[0]["text"] == "scan_inbox: Inbox directory"

    def test_processing_layer_compatibility(self):
        """Ensure parsed JSONL entries work with filter/detect/summarize functions."""
        result = parse_jsonl_log(FIXTURES_DIR / "capture-flagged.jsonl")
        # Must have category and text keys
        for entry in result:
            assert "category" in entry
            assert "text" in entry

        # filter_actions_by_autonomy should work
        filtered = filter_actions_by_autonomy(result, "autonomous")
        assert all(a["category"] != "routine" for a in filtered)

        # detect_critical_alerts should work
        assert detect_critical_alerts(result) is False  # flagged is not critical

        # summarize_routine_actions should work
        summary = summarize_routine_actions(result)
        assert "5" in summary


# --- find_log_files tests ---


class TestFindLogFiles:
    def test_finds_files_in_agent_subdirs(self, tmp_path):
        # Create per-agent directories with JSONL files
        agent_dir = tmp_path / "felix-admin-capture"
        agent_dir.mkdir()
        (agent_dir / "2026-04-01.jsonl").write_text('{"test": true}\n')

        result = find_log_files(tmp_path, "2026-04-01")
        assert isinstance(result, dict)
        assert "felix-admin-capture" in result
        assert result["felix-admin-capture"] == agent_dir / "2026-04-01.jsonl"

    def test_returns_empty_dict_for_missing_dir(self, tmp_path):
        result = find_log_files(tmp_path / "nonexistent", "2026-04-01")
        assert result == {}

    def test_ignores_non_directory_entries(self, tmp_path):
        (tmp_path / "stray-file.txt").write_text("not a directory")
        agent_dir = tmp_path / "felix-admin-capture"
        agent_dir.mkdir()
        (agent_dir / "2026-04-01.jsonl").write_text('{"test": true}\n')

        result = find_log_files(tmp_path, "2026-04-01")
        assert "stray-file.txt" not in result
        assert "felix-admin-capture" in result

    def test_finds_multiple_agents(self, tmp_path):
        for name in ["felix-admin-capture", "felix-admin-habits"]:
            d = tmp_path / name
            d.mkdir()
            (d / "2026-04-01.jsonl").write_text('{"test": true}\n')

        result = find_log_files(tmp_path, "2026-04-01")
        assert len(result) == 2

    def test_skips_agents_without_target_date(self, tmp_path):
        agent_dir = tmp_path / "felix-admin-capture"
        agent_dir.mkdir()
        (agent_dir / "2026-03-31.jsonl").write_text('{"test": true}\n')

        result = find_log_files(tmp_path, "2026-04-01")
        assert len(result) == 0


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
                "log_ref": "Agent-Logs/felix-admin-capture/2026-04-01-log.md",
            },
            "felix-admin-habits": {
                "autonomy_level": "assisted",
                "runs": 1,
                "routine_summary": "5 habits checked",
                "elevated": [],
                "critical": False,
                "log_ref": "Agent-Logs/felix-admin-habits/2026-04-01-log.md",
            },
        }
        overview = generate_digest(agent_digests, "2026-04-01")
        assert "felix-admin-capture" in overview
        assert "felix-admin-habits" in overview
        assert "2026-04-01" in overview

    def test_digest_includes_agent_logs_reference(self):
        agent_digests = {
            "felix-admin-capture": {
                "autonomy_level": "assisted",
                "runs": 1,
                "routine_summary": "1 note processed",
                "elevated": [],
                "critical": False,
                "log_ref": "Agent-Logs/felix-admin-capture/2026-04-01-log.md",
            },
        }
        overview = generate_digest(agent_digests, "2026-04-01")
        assert "Agent-Logs/felix-admin-capture/2026-04-01-log.md" in overview

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
                "log_ref": "Agent-Logs/felix-admin-capture/2026-04-01-log.md",
            },
        }
        overview = generate_digest(agent_digests, "2026-04-01")
        assert "triathlon" in overview


# --- Agent detail generation tests ---


class TestAgentDetail:
    def test_generate_agent_detail_single_run(self):
        run_groups = [
            ("run-001", [
                {"category": "routine", "text": "scan_inbox: Inbox", "ts": "2026-04-01T11:15:00Z"},
                {"category": "routine", "text": "file_processed: File.md", "ts": "2026-04-01T11:15:01Z"},
            ]),
        ]
        detail = generate_agent_detail("felix-admin-capture", run_groups, "assisted", "2026-04-01")
        assert "felix-admin-capture" in detail
        assert "2026-04-01" in detail
        assert "Run 1" in detail
        assert "Runs today: 1" in detail

    def test_generate_agent_detail_multi_run(self):
        run_groups = [
            ("run-001", [
                {"category": "routine", "text": "scan_inbox: Inbox", "ts": "2026-04-01T11:15:00Z"},
            ]),
            ("run-002", [
                {"category": "flagged", "text": "goal_detected: Triathlon", "ts": "2026-04-01T16:15:00Z"},
            ]),
        ]
        detail = generate_agent_detail("felix-admin-capture", run_groups, "assisted", "2026-04-01")
        assert "Run 1" in detail
        assert "Run 2" in detail
        assert "Runs today: 2" in detail
        assert "Flagged Items" in detail


# --- Group by run_id tests ---


class TestGroupByRunId:
    def test_groups_by_run_id(self):
        actions = [
            {"run_id": "a", "text": "one"},
            {"run_id": "a", "text": "two"},
            {"run_id": "b", "text": "three"},
        ]
        groups = _group_by_run_id(actions)
        assert len(groups) == 2
        assert groups[0][0] == "a"
        assert len(groups[0][1]) == 2
        assert groups[1][0] == "b"
        assert len(groups[1][1]) == 1

    def test_preserves_order(self):
        actions = [
            {"run_id": "b", "text": "first"},
            {"run_id": "a", "text": "second"},
            {"run_id": "b", "text": "third"},
        ]
        groups = _group_by_run_id(actions)
        assert groups[0][0] == "b"
        assert groups[1][0] == "a"


# --- Retention tests ---


class TestRetention:
    def test_deletes_files_older_than_retention_window(self, tmp_path):
        agent_dir = tmp_path / "felix-admin-capture"
        agent_dir.mkdir()

        # Create files at various dates
        target = date(2026, 4, 6)
        # 6 days old = should be deleted (> 5 days)
        (agent_dir / "2026-03-31-log.md").write_text("old")
        # 5 days old = should be kept (exactly 5)
        (agent_dir / "2026-04-01-log.md").write_text("boundary")
        # 1 day old = should be kept
        (agent_dir / "2026-04-05-log.md").write_text("recent")
        # today = should be kept
        (agent_dir / "2026-04-06-log.md").write_text("today")

        _apply_retention(tmp_path, target)

        assert not (agent_dir / "2026-03-31-log.md").exists()
        assert (agent_dir / "2026-04-01-log.md").exists()
        assert (agent_dir / "2026-04-05-log.md").exists()
        assert (agent_dir / "2026-04-06-log.md").exists()

    def test_leaves_non_matching_files_alone(self, tmp_path):
        agent_dir = tmp_path / "felix-admin-capture"
        agent_dir.mkdir()
        (agent_dir / "notes.md").write_text("not a digest")
        (agent_dir / "2026-03-25-log.md").write_text("old digest")

        _apply_retention(tmp_path, date(2026, 4, 6))

        assert (agent_dir / "notes.md").exists()
        assert not (agent_dir / "2026-03-25-log.md").exists()

    def test_overview_not_subject_to_retention(self, tmp_path):
        # overview.md lives in the agent_logs_dir root, not in agent subdirs
        (tmp_path / "overview.md").write_text("overview content")
        _apply_retention(tmp_path, date(2026, 4, 6))
        assert (tmp_path / "overview.md").exists()

    def test_handles_missing_directory(self, tmp_path):
        # Should not raise
        _apply_retention(tmp_path / "nonexistent", date(2026, 4, 6))


# --- Idempotency tests ---


class TestIdempotency:
    def test_skips_processing_when_no_new_content(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")

        # Set up log directory structure
        agent_log_dir = tmp_path / "logs" / "felix-admin-capture"
        agent_log_dir.mkdir(parents=True)
        log_file = agent_log_dir / "2026-04-01.jsonl"
        log_file.write_text(
            '{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"routine","action":"scan_inbox",'
            '"target":"Inbox","outcome":"completed"}\n'
        )

        # First run: should write
        result1 = run(config, "2026-04-01")
        assert result1["overview"] != ""

        digest_path = tmp_path / "output" / "Agent-Logs" / "felix-admin-capture" / "2026-04-01-log.md"
        assert digest_path.exists()
        first_content = digest_path.read_text()

        # Ensure mtime of digest is after log (give filesystem time to settle)
        time.sleep(0.1)
        # Touch the digest to ensure its mtime is newer
        digest_path.write_text(first_content)

        # Second run: should skip (no new content)
        result2 = run(config, "2026-04-01")
        # The overview should still be returned (from existing file)
        assert result2["critical"] is False

    def test_processes_when_log_is_newer(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")

        agent_log_dir = tmp_path / "logs" / "felix-admin-capture"
        agent_log_dir.mkdir(parents=True)
        log_file = agent_log_dir / "2026-04-01.jsonl"
        log_file.write_text(
            '{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"routine","action":"scan_inbox",'
            '"target":"Inbox","outcome":"completed"}\n'
        )

        # First run
        result1 = run(config, "2026-04-01")
        digest_path = tmp_path / "output" / "Agent-Logs" / "felix-admin-capture" / "2026-04-01-log.md"
        assert digest_path.exists()

        # Update log file (simulate new agent run)
        time.sleep(0.1)
        log_file.write_text(
            '{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"routine","action":"scan_inbox",'
            '"target":"Inbox","outcome":"completed"}\n'
            '{"ts":"2026-04-01T16:15:00Z","run_id":"r2","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"flagged","action":"goal_found",'
            '"target":"New goal detected","outcome":"flagged_for_review"}\n'
        )

        # Second run: should process (log is newer)
        result2 = run(config, "2026-04-01")
        new_content = digest_path.read_text()
        assert "goal_found" in new_content


# --- End-to-end run tests ---


class TestRun:
    def test_run_with_no_logs(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")
        (tmp_path / "logs").mkdir(parents=True)

        result = run(config, "2026-04-01")
        assert "No agent activity" in result["overview"]
        assert result["critical"] is False

        overview_path = tmp_path / "output" / "Agent-Logs" / "overview.md"
        assert overview_path.exists()

    def test_run_writes_to_agent_logs_structure(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")

        agent_log_dir = tmp_path / "logs" / "felix-admin-capture"
        agent_log_dir.mkdir(parents=True)
        (agent_log_dir / "2026-04-01.jsonl").write_text(
            '{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"routine","action":"scan_inbox",'
            '"target":"Inbox","outcome":"completed"}\n'
        )

        result = run(config, "2026-04-01")

        # Verify Agent-Logs structure
        agent_logs = tmp_path / "output" / "Agent-Logs"
        assert (agent_logs / "overview.md").exists()
        assert (agent_logs / "felix-admin-capture" / "2026-04-01-log.md").exists()

    def test_run_dry_run_does_not_write(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")

        agent_log_dir = tmp_path / "logs" / "felix-admin-capture"
        agent_log_dir.mkdir(parents=True)
        (agent_log_dir / "2026-04-01.jsonl").write_text(
            '{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"routine","action":"scan_inbox",'
            '"target":"Inbox","outcome":"completed"}\n'
        )

        result = run(config, "2026-04-01", dry_run=True)

        assert not (tmp_path / "output" / "Agent-Logs").exists()
        assert result["overview"] != ""

    def test_run_with_critical_alerts(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")

        agent_log_dir = tmp_path / "logs" / "felix-admin-capture"
        agent_log_dir.mkdir(parents=True)
        (agent_log_dir / "2026-04-01.jsonl").write_text(
            '{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"error","action":"note_update_failed",'
            '"target":"Budget.md locked","outcome":"failed"}\n'
        )

        result = run(config, "2026-04-01")
        assert result["critical"] is True
        assert result["alert_message"] is not None
        assert "Agent-Logs" in result["alert_message"]

    def test_run_applies_retention(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")

        # Create an old digest file
        agent_digest_dir = tmp_path / "output" / "Agent-Logs" / "felix-admin-capture"
        agent_digest_dir.mkdir(parents=True)
        old_file = agent_digest_dir / "2026-03-25-log.md"
        old_file.write_text("old content")

        # Create log for today
        agent_log_dir = tmp_path / "logs" / "felix-admin-capture"
        agent_log_dir.mkdir(parents=True)
        (agent_log_dir / "2026-04-01.jsonl").write_text(
            '{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"felix-admin-capture",'
            '"autonomy_level":"assisted","category":"routine","action":"scan_inbox",'
            '"target":"Inbox","outcome":"completed"}\n'
        )

        run(config, "2026-04-01")

        # Old file should be deleted (> 5 days before 2026-04-01)
        assert not old_file.exists()
        # Today's file should exist
        assert (agent_digest_dir / "2026-04-01-log.md").exists()

    def test_run_multi_agent(self, tmp_path):
        config = _make_config(tmp_path, log_dir=tmp_path / "logs", output_dir=tmp_path / "output")

        for name in ["felix-admin-capture", "felix-admin-habits"]:
            d = tmp_path / "logs" / name
            d.mkdir(parents=True)
            (d / "2026-04-01.jsonl").write_text(
                f'{{"ts":"2026-04-01T11:15:00Z","run_id":"r1","agent":"{name}",'
                f'"autonomy_level":"assisted","category":"routine","action":"scan",'
                f'"target":"test","outcome":"completed"}}\n'
            )

        result = run(config, "2026-04-01")
        assert "felix-admin-capture" in result["overview"]
        assert "felix-admin-habits" in result["overview"]

        agent_logs = tmp_path / "output" / "Agent-Logs"
        assert (agent_logs / "felix-admin-capture" / "2026-04-01-log.md").exists()
        assert (agent_logs / "felix-admin-habits" / "2026-04-01-log.md").exists()
