"""Fixtures for enforcement detection tests."""

import pytest


@pytest.fixture
def sample_manifest():
    """Realistic baseline manifest with 2 agents."""
    return {
        "generated_at": "2026-04-13T00:00:00Z",
        "generated_by": "test",
        "agents": {
            "main": {
                "workspace_path": "/data/services/openclaw/data",
                "repo_path": "scripts/openclaw/agents/main",
                "files": {
                    "AGENTS.md": {
                        "repo_sha256": "aaa111",
                        "office2_sha256": "aaa111",
                        "lines": 258,
                        "tracked": True,
                        "factory_default": False,
                    },
                    "TOOLS.md": {
                        "repo_sha256": "bbb222",
                        "office2_sha256": "bbb222",
                        "lines": 40,
                        "tracked": True,
                        "factory_default": True,
                    },
                    "IDENTITY.md": {
                        "repo_sha256": "ccc333",
                        "office2_sha256": "ccc333",
                        "lines": 23,
                        "tracked": True,
                        "factory_default": True,
                    },
                },
            },
            "felix-admin-tasker": {
                "workspace_path": "/data/services/openclaw/tasker-agent",
                "repo_path": "scripts/openclaw/agents/felix-admin-tasker",
                "files": {
                    "SOUL.md": {
                        "repo_sha256": "ddd444",
                        "office2_sha256": "ddd444",
                        "lines": 68,
                        "tracked": True,
                        "factory_default": False,
                    },
                },
            },
        },
    }


@pytest.fixture
def sample_factory_baselines():
    """Known factory-default hashes."""
    return {
        "openclaw_version": "2026.3.24",
        "baselines": {
            "TOOLS.md": "bbb222",
            "IDENTITY.md": {
                "template_full": "ccc333",
            },
        },
    }
