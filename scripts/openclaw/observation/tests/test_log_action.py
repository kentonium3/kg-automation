"""Tests for log_action.py — deterministic log writer.

Test-first per TEST_FIRST directive. Added by F014.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Resolve log_action.py path
_observation_dir = Path(__file__).resolve().parent.parent
LOG_ACTION = _observation_dir / "log_action.py"

_parent = str(_observation_dir)
if _parent not in sys.path:
    sys.path.insert(0, _parent)


def _run_log_action(args, log_dir=None, registry_path=None):
    """Run log_action.py as a subprocess and return CompletedProcess."""
    cmd = [sys.executable, str(LOG_ACTION)] + args
    if log_dir:
        cmd += ["--log-dir", str(log_dir)]
    if registry_path:
        cmd += ["--registry", str(registry_path)]
    return subprocess.run(cmd, capture_output=True, text=True)


def _make_registry(tmp_path, agents=None):
    """Create a temp registry JSON and return its path."""
    if agents is None:
        agents = {
            "test-agent": {
                "autonomy_level": "assisted",
                "log_verbosity": "standard",
            }
        }
    registry = {"version": "1.0", "updated": "2026-04-04", "updated_by": "F014", "agents": agents}
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(registry))
    return reg_path


def _valid_args(agent="test-agent"):
    """Return minimal valid CLI arguments."""
    return [
        "--agent", agent,
        "--category", "routine",
        "--action", "test_action",
        "--target", "test target",
        "--outcome", "completed",
    ]


class TestSchemaValidation:
    def test_valid_entry_writes_jsonl(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        result = _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        assert result.returncode == 0
        # Find the written file
        agent_dir = log_dir / "test-agent"
        assert agent_dir.exists()
        jsonl_files = list(agent_dir.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        line = jsonl_files[0].read_text().strip()
        entry = json.loads(line)
        assert entry["agent"] == "test-agent"
        assert entry["category"] == "routine"
        assert entry["action"] == "test_action"
        assert entry["target"] == "test target"
        assert entry["outcome"] == "completed"

    def test_missing_required_field_exits_nonzero(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        # Missing --agent
        result = _run_log_action(
            ["--category", "routine", "--action", "x", "--target", "y", "--outcome", "z"],
            log_dir=log_dir, registry_path=reg,
        )
        assert result.returncode != 0
        # No file should be written
        assert not (log_dir).exists() or len(list(log_dir.rglob("*.jsonl"))) == 0

    def test_invalid_category_exits_nonzero(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        args = _valid_args()
        args[args.index("routine")] = "invalid_category"
        result = _run_log_action(args, log_dir=log_dir, registry_path=reg)
        assert result.returncode == 1
        assert "invalid" in result.stderr.lower() or "category" in result.stderr.lower()

    def test_valid_categories_accepted(self, tmp_path):
        for cat in ["routine", "flagged", "error", "security"]:
            reg = _make_registry(tmp_path)
            log_dir = tmp_path / f"logs_{cat}"
            args = _valid_args()
            args[args.index("routine")] = cat
            result = _run_log_action(args, log_dir=log_dir, registry_path=reg)
            assert result.returncode == 0, f"Category '{cat}' rejected: {result.stderr}"


class TestTimestampAndRunId:
    def test_ts_is_utc_iso8601(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        # Validate ISO-8601 UTC format
        ts = entry["ts"]
        assert ts.endswith("Z")
        datetime.fromisoformat(ts.replace("Z", "+00:00"))

    def test_run_id_format(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        # Pattern: {agent}-{YYYYMMDD}-{HHMM}
        assert re.match(r"test-agent-\d{8}-\d{4}", entry["run_id"])

    def test_ts_and_run_id_not_accepted_from_cli(self, tmp_path):
        """Even if --ts is somehow passed, log_action.py generates its own."""
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        # ts and run_id are not CLI args — argparse won't accept them
        result = _run_log_action(
            _valid_args() + ["--ts", "fake"],
            log_dir=log_dir, registry_path=reg,
        )
        # Should fail because --ts is not a valid arg
        assert result.returncode != 0


class TestFileIO:
    def test_creates_agent_subdirectory(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        assert (log_dir / "test-agent").is_dir()

    def test_appends_to_existing_file(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        jsonl_file = next((log_dir / "test-agent").glob("*.jsonl"))
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_correct_daily_filename(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        jsonl_file = next((log_dir / "test-agent").glob("*.jsonl"))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert jsonl_file.name == f"{today}.jsonl"

    def test_each_write_is_single_line(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        content = next((log_dir / "test-agent").glob("*.jsonl")).read_text()
        # Should be exactly one line (with trailing newline)
        assert content.count("\n") == 1


class TestTruncation:
    def test_short_string_unchanged(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        args = _valid_args()
        short_target = "x" * 50
        args[args.index("test target")] = short_target
        _run_log_action(args, log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        assert entry["target"] == short_target

    def test_long_string_truncated(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        args = _valid_args()
        long_target = "x" * 150
        args[args.index("test target")] = long_target
        _run_log_action(args, log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        assert len(entry["target"]) == 120 + len("[truncated]")
        assert entry["target"].endswith("[truncated]")

    def test_truncation_applies_to_all_string_fields(self, tmp_path):
        reg = _make_registry(tmp_path)
        log_dir = tmp_path / "logs"
        long_str = "y" * 150
        args = [
            "--agent", "test-agent",
            "--category", "routine",
            "--action", long_str,
            "--target", long_str,
            "--outcome", long_str,
        ]
        _run_log_action(args, log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        for field in ["action", "target", "outcome"]:
            assert entry[field].endswith("[truncated]"), f"{field} not truncated"


class TestVerbosity:
    def test_brief_strips_context_and_trace(self, tmp_path):
        agents = {"test-agent": {"autonomy_level": "assisted", "log_verbosity": "brief"}}
        reg = _make_registry(tmp_path, agents)
        log_dir = tmp_path / "logs"
        args = _valid_args() + [
            "--context", '{"project": "test"}',
            "--trace", '{"confidence": {"project": 0.9}}',
        ]
        _run_log_action(args, log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        assert "context" not in entry
        assert "trace" not in entry

    def test_standard_writes_context_strips_trace(self, tmp_path):
        agents = {"test-agent": {"autonomy_level": "assisted", "log_verbosity": "standard"}}
        reg = _make_registry(tmp_path, agents)
        log_dir = tmp_path / "logs"
        args = _valid_args() + [
            "--context", '{"project": "test"}',
            "--trace", '{"confidence": {"project": 0.9}}',
        ]
        _run_log_action(args, log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        assert entry["context"] == {"project": "test"}
        assert "trace" not in entry

    def test_verbose_writes_all(self, tmp_path):
        agents = {"test-agent": {"autonomy_level": "assisted", "log_verbosity": "verbose"}}
        reg = _make_registry(tmp_path, agents)
        log_dir = tmp_path / "logs"
        args = _valid_args() + [
            "--context", '{"project": "test"}',
            "--trace", '{"confidence": {"project": 0.9}}',
        ]
        _run_log_action(args, log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        assert entry["context"] == {"project": "test"}
        assert entry["trace"] == {"confidence": {"project": 0.9}}

    def test_no_context_at_standard_is_fine(self, tmp_path):
        agents = {"test-agent": {"autonomy_level": "assisted", "log_verbosity": "standard"}}
        reg = _make_registry(tmp_path, agents)
        log_dir = tmp_path / "logs"
        result = _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        assert result.returncode == 0
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        assert "context" not in entry


class TestAutonomyLevel:
    def test_autonomy_level_read_from_registry(self, tmp_path):
        agents = {"test-agent": {"autonomy_level": "observed", "log_verbosity": "standard"}}
        reg = _make_registry(tmp_path, agents)
        log_dir = tmp_path / "logs"
        _run_log_action(_valid_args(), log_dir=log_dir, registry_path=reg)
        entry = json.loads(next((log_dir / "test-agent").glob("*.jsonl")).read_text().strip())
        assert entry["autonomy_level"] == "observed"
