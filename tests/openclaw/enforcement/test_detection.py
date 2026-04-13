"""Tests for the drift detection engine."""

from scripts.openclaw.enforcement.detection import (
    DriftState,
    classify_drift,
    detect_all_drift,
    is_factory_default,
)


class TestClassifyDrift:
    """Test the three-way diff classification."""

    def test_no_change(self):
        assert classify_drift("aaa", "aaa", "aaa", "aaa") == DriftState.NO_CHANGE

    def test_repo_changed(self):
        """Repo changed, office2 unchanged → deploy repo→office2."""
        assert classify_drift("new_hash", "aaa", "aaa", "aaa") == DriftState.REPO_CHANGED

    def test_office2_changed(self):
        """Office2 changed, repo unchanged → capture office2→repo."""
        assert classify_drift("aaa", "new_hash", "aaa", "aaa") == DriftState.OFFICE2_CHANGED

    def test_conflict(self):
        """Both sides changed → conflict, notify."""
        assert classify_drift("new_repo", "new_o2", "aaa", "aaa") == DriftState.CONFLICT

    def test_file_missing_repo(self):
        """File missing from repo."""
        assert classify_drift(None, "aaa", "aaa", "aaa") == DriftState.FILE_MISSING_REPO

    def test_file_missing_office2(self):
        """File missing from office2."""
        assert classify_drift("aaa", None, "aaa", "aaa") == DriftState.FILE_MISSING_OFFICE2

    def test_both_missing(self):
        """Both missing — treated as file_missing_repo."""
        assert classify_drift(None, None, "aaa", "aaa") == DriftState.FILE_MISSING_REPO

    def test_no_baseline_both_present(self):
        """No baseline hashes (new file on both sides) → both changed from None."""
        assert classify_drift("aaa", "aaa", None, None) == DriftState.CONFLICT

    def test_no_baseline_same_hash(self):
        """Both sides have same hash but baseline is None → both changed."""
        result = classify_drift("same", "same", None, None)
        assert result == DriftState.CONFLICT


class TestIsFactoryDefault:
    """Test factory-default detection."""

    def test_string_baseline_match(self):
        baselines = {"baselines": {"TOOLS.md": "factory_hash"}}
        assert is_factory_default("factory_hash", "TOOLS.md", baselines) is True

    def test_string_baseline_no_match(self):
        baselines = {"baselines": {"TOOLS.md": "factory_hash"}}
        assert is_factory_default("custom_hash", "TOOLS.md", baselines) is False

    def test_dict_baseline_match(self):
        baselines = {"baselines": {"IDENTITY.md": {"v1": "hash_a", "v2": "hash_b"}}}
        assert is_factory_default("hash_b", "IDENTITY.md", baselines) is True

    def test_dict_baseline_no_match(self):
        baselines = {"baselines": {"IDENTITY.md": {"v1": "hash_a"}}}
        assert is_factory_default("custom", "IDENTITY.md", baselines) is False

    def test_missing_filename(self):
        baselines = {"baselines": {"TOOLS.md": "factory_hash"}}
        assert is_factory_default("any_hash", "SOUL.md", baselines) is False

    def test_none_hash(self):
        baselines = {"baselines": {"TOOLS.md": "factory_hash"}}
        assert is_factory_default(None, "TOOLS.md", baselines) is False

    def test_empty_baselines(self):
        assert is_factory_default("any", "TOOLS.md", {}) is False


class TestDetectAllDrift:
    """Test the full detection pipeline."""

    def test_no_drift(self, sample_manifest, sample_factory_baselines):
        """All files matching baseline → all NO_CHANGE."""
        current = {
            "main": {
                "AGENTS.md": {"repo": "aaa111", "office2": "aaa111"},
                "TOOLS.md": {"repo": "bbb222", "office2": "bbb222"},
                "IDENTITY.md": {"repo": "ccc333", "office2": "ccc333"},
            },
            "felix-admin-tasker": {
                "SOUL.md": {"repo": "ddd444", "office2": "ddd444"},
            },
        }
        results = detect_all_drift(current, sample_manifest, sample_factory_baselines)
        assert len(results) == 4
        assert all(r.state == DriftState.NO_CHANGE for r in results)

    def test_mixed_drift(self, sample_manifest, sample_factory_baselines):
        """Mix of drift states."""
        current = {
            "main": {
                "AGENTS.md": {"repo": "new_repo", "office2": "aaa111"},  # repo changed
                "TOOLS.md": {"repo": "bbb222", "office2": "new_o2"},  # office2 changed
                "IDENTITY.md": {"repo": "ccc333", "office2": "ccc333"},  # no change
            },
            "felix-admin-tasker": {
                "SOUL.md": {"repo": "new_r", "office2": "new_o"},  # conflict
            },
        }
        results = detect_all_drift(current, sample_manifest, sample_factory_baselines)

        by_file = {(r.agent_id, r.filename): r for r in results}
        assert by_file[("main", "AGENTS.md")].state == DriftState.REPO_CHANGED
        assert by_file[("main", "TOOLS.md")].state == DriftState.OFFICE2_CHANGED
        assert by_file[("main", "IDENTITY.md")].state == DriftState.NO_CHANGE
        assert by_file[("felix-admin-tasker", "SOUL.md")].state == DriftState.CONFLICT

    def test_factory_default_flags(self, sample_manifest, sample_factory_baselines):
        """Factory-default files are correctly flagged."""
        current = {
            "main": {
                "AGENTS.md": {"repo": "aaa111", "office2": "aaa111"},
                "TOOLS.md": {"repo": "bbb222", "office2": "bbb222"},  # factory default
                "IDENTITY.md": {"repo": "ccc333", "office2": "ccc333"},  # factory default
            },
            "felix-admin-tasker": {
                "SOUL.md": {"repo": "ddd444", "office2": "ddd444"},
            },
        }
        results = detect_all_drift(current, sample_manifest, sample_factory_baselines)
        by_file = {(r.agent_id, r.filename): r for r in results}

        assert by_file[("main", "AGENTS.md")].is_factory_default is False
        assert by_file[("main", "TOOLS.md")].is_factory_default is True
        assert by_file[("main", "IDENTITY.md")].is_factory_default is True
        assert by_file[("felix-admin-tasker", "SOUL.md")].is_factory_default is False

    def test_factory_default_transition(self, sample_manifest, sample_factory_baselines):
        """File was factory default, now customized on office2."""
        current = {
            "main": {
                "AGENTS.md": {"repo": "aaa111", "office2": "aaa111"},
                "TOOLS.md": {"repo": "customized_hash", "office2": "bbb222"},  # repo customized
                "IDENTITY.md": {"repo": "ccc333", "office2": "ccc333"},
            },
            "felix-admin-tasker": {
                "SOUL.md": {"repo": "ddd444", "office2": "ddd444"},
            },
        }
        results = detect_all_drift(current, sample_manifest, sample_factory_baselines)
        by_file = {(r.agent_id, r.filename): r for r in results}

        tools = by_file[("main", "TOOLS.md")]
        assert tools.state == DriftState.REPO_CHANGED
        assert tools.is_factory_default is False  # No longer factory default
