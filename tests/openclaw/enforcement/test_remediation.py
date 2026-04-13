"""Tests for remediation actions."""

import json
from unittest.mock import patch, MagicMock

from scripts.openclaw.enforcement.detection import DriftResult, DriftState
from scripts.openclaw.enforcement.remediation import (
    deploy_to_office2,
    capture_from_office2,
    process_drift_results,
    update_manifest,
)


def _make_result(state, agent="main", filename="AGENTS.md", factory=False):
    return DriftResult(
        agent_id=agent, filename=filename, state=state,
        current_repo_hash="new_repo", current_office2_hash="new_o2",
        baseline_repo_hash="old_repo", baseline_office2_hash="old_o2",
        is_factory_default=factory,
    )


class TestDeployToOffice2:
    def test_dry_run(self):
        assert deploy_to_office2("/repo/file.md", "/remote/file.md", dry_run=True) is True

    def test_success(self, tmp_path):
        # Create a real file so hash verification works
        repo_file = tmp_path / "file.md"
        repo_file.write_text("test content\n")
        scp_mock = MagicMock(returncode=0)
        # sha256sum output for "test content\n"
        import hashlib
        expected_hash = hashlib.sha256(b"test content\n").hexdigest()
        verify_mock = MagicMock(returncode=0, stdout=f"{expected_hash}  /remote/file.md\n")
        with patch("scripts.openclaw.enforcement.remediation.subprocess.run", side_effect=[scp_mock, verify_mock]):
            assert deploy_to_office2(str(repo_file), "/remote/file.md") is True

    def test_failure(self):
        mock = MagicMock(returncode=1, stderr="Permission denied")
        with patch("scripts.openclaw.enforcement.remediation.subprocess.run", return_value=mock):
            assert deploy_to_office2("/repo/file.md", "/remote/file.md") is False


class TestCaptureFromOffice2:
    def test_dry_run(self):
        assert capture_from_office2("/remote/file.md", "/repo/file.md", "main", "AGENTS.md", dry_run=True) is True

    def test_success(self):
        scp_mock = MagicMock(returncode=0)
        git_mock = MagicMock(returncode=0)
        with patch("scripts.openclaw.enforcement.remediation.subprocess.run", side_effect=[scp_mock, git_mock, git_mock]):
            assert capture_from_office2("/remote/file.md", "/repo/file.md", "main", "AGENTS.md") is True

    def test_scp_failure(self):
        mock = MagicMock(returncode=1, stderr="No such file")
        with patch("scripts.openclaw.enforcement.remediation.subprocess.run", return_value=mock):
            assert capture_from_office2("/remote/file.md", "/repo/file.md", "main", "AGENTS.md") is False


class TestUpdateManifest:
    def test_updates_both_hashes(self, tmp_path):
        manifest = {
            "agents": {
                "main": {
                    "files": {
                        "AGENTS.md": {"repo_sha256": "old", "office2_sha256": "old"}
                    }
                }
            }
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        update_manifest(str(path), "main", "AGENTS.md", "new_hash")

        updated = json.loads(path.read_text())
        assert updated["agents"]["main"]["files"]["AGENTS.md"]["repo_sha256"] == "new_hash"
        assert updated["agents"]["main"]["files"]["AGENTS.md"]["office2_sha256"] == "new_hash"


class TestProcessDriftResults:
    def _config(self):
        return {
            "ssh_host": "office2-claude",
            "agents": {
                "main": {
                    "workspace_path": "/data/services/openclaw/data",
                    "repo_path": "scripts/openclaw/agents/main",
                },
            },
        }

    def test_routes_repo_changed_to_deploy(self, tmp_path):
        manifest = {"agents": {"main": {"files": {"AGENTS.md": {"factory_default": False}}}}}
        mp = tmp_path / "manifest.json"
        mp.write_text(json.dumps(manifest))

        results = [_make_result(DriftState.REPO_CHANGED)]
        with patch("scripts.openclaw.enforcement.remediation.deploy_to_office2", return_value=True):
            actions = process_drift_results(results, self._config(), str(mp), dry_run=True)
        assert len(actions["deployed"]) == 1

    def test_routes_office2_changed_to_capture(self, tmp_path):
        manifest = {"agents": {"main": {"files": {"AGENTS.md": {"factory_default": False}}}}}
        mp = tmp_path / "manifest.json"
        mp.write_text(json.dumps(manifest))

        results = [_make_result(DriftState.OFFICE2_CHANGED)]
        with patch("scripts.openclaw.enforcement.remediation.capture_from_office2", return_value=True):
            actions = process_drift_results(results, self._config(), str(mp), dry_run=True)
        assert len(actions["captured"]) == 1

    def test_routes_conflict_to_notification(self, tmp_path):
        manifest = {"agents": {"main": {"files": {"AGENTS.md": {"factory_default": False}}}}}
        mp = tmp_path / "manifest.json"
        mp.write_text(json.dumps(manifest))

        results = [_make_result(DriftState.CONFLICT)]
        actions = process_drift_results(results, self._config(), str(mp), dry_run=True)
        assert len(actions["conflicts"]) == 1

    def test_detects_factory_transition(self, tmp_path):
        manifest = {"agents": {"main": {"files": {"AGENTS.md": {"factory_default": True}}}}}
        mp = tmp_path / "manifest.json"
        mp.write_text(json.dumps(manifest))

        # office2 hash is "new_o2" which doesn't match any factory baseline
        factory_baselines = {"baselines": {"AGENTS.md": "factory_hash"}}
        results = [_make_result(DriftState.OFFICE2_CHANGED, factory=True)]
        with patch("scripts.openclaw.enforcement.remediation.capture_from_office2", return_value=True):
            actions = process_drift_results(
                results, self._config(), str(mp), dry_run=True,
                factory_baselines=factory_baselines,
            )
        assert len(actions["captured"]) == 1
        assert len(actions["factory_transitions"]) == 1

    def test_no_transition_when_office2_still_factory(self, tmp_path):
        """If office2 is still factory default, no transition."""
        manifest = {"agents": {"main": {"files": {"AGENTS.md": {"factory_default": True}}}}}
        mp = tmp_path / "manifest.json"
        mp.write_text(json.dumps(manifest))

        # office2 hash matches factory baseline
        factory_baselines = {"baselines": {"AGENTS.md": "new_o2"}}
        results = [_make_result(DriftState.OFFICE2_CHANGED, factory=True)]
        with patch("scripts.openclaw.enforcement.remediation.capture_from_office2", return_value=True):
            actions = process_drift_results(
                results, self._config(), str(mp), dry_run=True,
                factory_baselines=factory_baselines,
            )
        assert len(actions["captured"]) == 1
        assert len(actions["factory_transitions"]) == 0
