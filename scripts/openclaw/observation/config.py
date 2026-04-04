"""Configuration module for the Felix observation intelligence layer.

Loads agent-registry.json and resolves paths for log reading and digest output.
"""

import json
from pathlib import Path


class ObservationConfig:
    """Configuration for the observation intelligence layer."""

    def __init__(self, registry_path=None, log_dir=None, output_dir=None):
        """Load config with optional path overrides (useful for testing).

        Args:
            registry_path: Path to agent-registry.json. Defaults to
                docs/constitution/agent-registry.json relative to repo root.
            log_dir: Path to agent log directory. Defaults to
                ~/second-brain/agents/logs/
            output_dir: Path to Obsidian digest output directory. Defaults to
                ~/second-brain/notes/00-System/agent-activity/
        """
        if registry_path is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            registry_path = repo_root / "docs" / "constitution" / "agent-registry.json"

        self._registry_path = Path(registry_path)
        self._log_dir = Path(log_dir) if log_dir else Path.home() / "second-brain" / "agents" / "logs"
        self._output_dir = Path(output_dir) if output_dir else Path.home() / "second-brain" / "notes" / "00-System" / "agent-activity"

        self._registry = self._load_registry()

    def _load_registry(self):
        """Load and validate agent-registry.json."""
        if not self._registry_path.exists():
            raise FileNotFoundError(
                f"Agent registry not found at {self._registry_path}. "
                "Ensure docs/constitution/agent-registry.json exists."
            )

        with open(self._registry_path) as f:
            data = json.load(f)

        if "agents" not in data:
            raise ValueError(
                f"Invalid registry format: 'agents' key missing in {self._registry_path}"
            )

        return data

    @property
    def agents(self):
        """Return dict of agent entries from the registry."""
        return self._registry["agents"]

    @property
    def log_dir(self):
        """Resolved log directory path."""
        return self._log_dir

    @property
    def output_dir(self):
        """Resolved Obsidian output directory path."""
        return self._output_dir

    def autonomy_level(self, agent_name):
        """Return autonomy level for the given agent.

        Raises KeyError if the agent is not in the registry.
        """
        if agent_name not in self._registry["agents"]:
            raise KeyError(
                f"Agent '{agent_name}' not found in registry. "
                f"Registered agents: {list(self._registry['agents'].keys())}"
            )
        return self._registry["agents"][agent_name]["autonomy_level"]

    def log_verbosity(self, agent_name):
        """Return log verbosity level for the given agent.

        Returns 'standard' if the agent exists but has no log_verbosity field
        (graceful degradation for agents registered before F014).

        Raises KeyError if the agent is not in the registry.
        """
        if agent_name not in self._registry["agents"]:
            raise KeyError(
                f"Agent '{agent_name}' not found in registry. "
                f"Registered agents: {list(self._registry['agents'].keys())}"
            )
        return self._registry["agents"][agent_name].get("log_verbosity", "standard")
