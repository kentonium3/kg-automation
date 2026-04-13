"""Tests for drift_check.py CLI helpers and hash computation."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.openclaw.enforcement.drift_check import (
    SSH_ERROR,
    compute_local_hash,
    compute_remote_hashes,
    compute_all_hashes,
    format_results,
)
from scripts.openclaw.enforcement.detection import DriftResult, DriftState


class TestComputeLocalHash:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("hello world\n")
        h = compute_local_hash(str(f))
        assert h is not None
        assert len(h) == 64  # SHA256 hex

    def test_missing_file(self, tmp_path):
        assert compute_local_hash(str(tmp_path / "nope.md")) is None


class TestComputeRemoteHashes:
    def test_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123  /data/services/openclaw/data/AGENTS.md\nMISSING /data/services/openclaw/data/NOPE.md\n"
        mock_result.stderr = ""

        with patch("scripts.openclaw.enforcement.drift_check.subprocess.run", return_value=mock_result):
            result = compute_remote_hashes("office2-claude", [
                "/data/services/openclaw/data/AGENTS.md",
                "/data/services/openclaw/data/NOPE.md",
            ])

        assert result["/data/services/openclaw/data/AGENTS.md"] == "abc123"
        assert result["/data/services/openclaw/data/NOPE.md"] is None

    def test_ssh_timeout(self):
        with patch(
            "scripts.openclaw.enforcement.drift_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ssh", 30),
        ):
            result = compute_remote_hashes("office2-claude", ["/data/test.md"])

        assert result["/data/test.md"] == SSH_ERROR

    def test_ssh_connection_refused(self):
        mock_result = MagicMock()
        mock_result.returncode = 255
        mock_result.stdout = ""
        mock_result.stderr = "ssh: connect to host office2-claude: Connection refused"

        with patch("scripts.openclaw.enforcement.drift_check.subprocess.run", return_value=mock_result):
            result = compute_remote_hashes("office2-claude", ["/data/test.md"])

        assert result["/data/test.md"] == SSH_ERROR

    def test_empty_file_list(self):
        assert compute_remote_hashes("office2-claude", []) == {}


class TestComputeAllHashes:
    def test_skips_ssh_errors(self):
        config = {
            "ssh_host": "office2-claude",
            "agents": {
                "main": {
                    "workspace_path": "/data/services/openclaw/data",
                    "repo_path": "scripts/openclaw/agents/main",
                    "tracked_files": ["AGENTS.md", "SOUL.md"],
                },
            },
        }

        with patch(
            "scripts.openclaw.enforcement.drift_check.compute_remote_hashes",
            return_value={
                "/data/services/openclaw/data/AGENTS.md": SSH_ERROR,
                "/data/services/openclaw/data/SOUL.md": "abc123",
            },
        ), patch(
            "scripts.openclaw.enforcement.drift_check.compute_local_hash",
            return_value="def456",
        ):
            result = compute_all_hashes(config, "/fake/repo")

        # AGENTS.md should be skipped (SSH error)
        assert "AGENTS.md" not in result["main"]
        # SOUL.md should be present
        assert result["main"]["SOUL.md"]["repo"] == "def456"
        assert result["main"]["SOUL.md"]["office2"] == "abc123"


class TestFormatResults:
    def _make_result(self, state, agent="main", filename="AGENTS.md", factory=False):
        return DriftResult(
            agent_id=agent, filename=filename, state=state,
            current_repo_hash="a", current_office2_hash="b",
            baseline_repo_hash="c", baseline_office2_hash="d",
            is_factory_default=factory,
        )

    def test_json_output(self):
        results = [self._make_result(DriftState.NO_CHANGE)]
        output = format_results(results, as_json=True)
        import json
        data = json.loads(output)
        assert data["total"] == 1
        assert data["results"][0]["state"] == "no_change"

    def test_text_output_marks(self):
        results = [
            self._make_result(DriftState.NO_CHANGE),
            self._make_result(DriftState.REPO_CHANGED, filename="TOOLS.md"),
            self._make_result(DriftState.CONFLICT, filename="SOUL.md"),
        ]
        output = format_results(results, as_json=False)
        assert "✓" in output  # no change
        assert "→" in output  # repo changed
        assert "⚠" in output  # conflict
        assert "3 files" in output

    def test_factory_flag_in_text(self):
        results = [self._make_result(DriftState.NO_CHANGE, factory=True)]
        output = format_results(results, as_json=False)
        assert "(factory)" in output


class TestCLIEntrypoint:
    """Test the actual CLI invocation via subprocess."""

    def test_report_missing_config(self, tmp_path):
        """CLI exits with error when config is missing."""
        result = subprocess.run(
            [sys.executable, "scripts/openclaw/enforcement/drift_check.py",
             "report", "--config", str(tmp_path / "nope.json")],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[3]),  # repo root
        )
        assert result.returncode != 0
        assert "File not found" in result.stderr or "ERROR" in result.stderr

    def test_report_with_mock_config(self, tmp_path):
        """CLI loads config and manifest without SSH when using report."""
        # Create minimal config, manifest, factory baselines
        manifest = {
            "generated_at": "2026-01-01", "generated_by": "test",
            "agents": {},
        }
        factory = {"openclaw_version": "test", "baselines": {}}
        config = {
            "enforcement_mode": "last-author-wins",
            "ssh_host": "localhost",
            "agents": {},
            "factory_baselines_path": str(tmp_path / "factory.json"),
            "baseline_manifest_path": str(tmp_path / "manifest.json"),
        }

        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        (tmp_path / "factory.json").write_text(json.dumps(factory))
        (tmp_path / "config.json").write_text(json.dumps(config))

        result = subprocess.run(
            [sys.executable, "scripts/openclaw/enforcement/drift_check.py",
             "report", "--json", "--config", str(tmp_path / "config.json")],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["total"] == 0
        assert data["results"] == []
