"""Three-way drift detection engine for agent workspace enforcement.

Compares current hashes (repo and office2) against a baseline manifest
to classify drift state using a "last author edits wins" strategy.
"""

from dataclasses import dataclass
from enum import Enum


class DriftState(Enum):
    """Classification of drift between repo and office2 for a single file."""

    NO_CHANGE = "no_change"
    REPO_CHANGED = "repo_changed"  # Action: deploy repo→office2
    OFFICE2_CHANGED = "office2_changed"  # Action: capture office2→repo
    CONFLICT = "conflict"  # Action: notify (both sides changed)
    FILE_MISSING_REPO = "file_missing_repo"
    FILE_MISSING_OFFICE2 = "file_missing_office2"


@dataclass
class DriftResult:
    """Result of drift classification for a single agent workspace file."""

    agent_id: str
    filename: str
    state: DriftState
    current_repo_hash: str | None
    current_office2_hash: str | None
    baseline_repo_hash: str | None
    baseline_office2_hash: str | None
    is_factory_default: bool


def classify_drift(
    current_repo: str | None,
    current_office2: str | None,
    baseline_repo: str | None,
    baseline_office2: str | None,
) -> DriftState:
    """Three-way diff classification.

    Compares current hashes on both sides against their respective baselines
    to determine which side(s) changed since the last reconciliation.
    """
    if current_repo is None and current_office2 is None:
        return DriftState.FILE_MISSING_REPO  # Both missing is unusual

    if current_repo is None:
        return DriftState.FILE_MISSING_REPO

    if current_office2 is None:
        return DriftState.FILE_MISSING_OFFICE2

    repo_changed = current_repo != baseline_repo
    office2_changed = current_office2 != baseline_office2

    if not repo_changed and not office2_changed:
        return DriftState.NO_CHANGE
    elif repo_changed and not office2_changed:
        return DriftState.REPO_CHANGED
    elif not repo_changed and office2_changed:
        return DriftState.OFFICE2_CHANGED
    else:
        return DriftState.CONFLICT


def is_factory_default(
    current_hash: str | None,
    filename: str,
    factory_baselines: dict,
) -> bool:
    """Check if a file's hash matches any known factory baseline.

    Factory baselines can be a single hash string or a dict of variant
    hashes (e.g., IDENTITY.md has template_full and template_minimal).
    """
    if current_hash is None:
        return False
    baselines = factory_baselines.get("baselines", {}).get(filename)
    if baselines is None:
        return False
    if isinstance(baselines, str):
        return current_hash == baselines
    if isinstance(baselines, dict):
        return current_hash in baselines.values()
    return False


def detect_all_drift(
    current_hashes: dict,
    manifest: dict,
    factory_baselines: dict,
) -> list[DriftResult]:
    """Classify drift state for every tracked file across all agents.

    Args:
        current_hashes: {agent_id: {filename: {"repo": hash, "office2": hash}}}
        manifest: The baseline manifest (from baseline-manifest.json)
        factory_baselines: Known factory-default hashes (from factory-baselines.json)

    Returns:
        List of DriftResult for every tracked file.
    """
    results = []

    for agent_id, agent_data in manifest.get("agents", {}).items():
        for filename, file_data in agent_data.get("files", {}).items():
            agent_hashes = current_hashes.get(agent_id, {})
            file_hashes = agent_hashes.get(filename, {})

            current_repo = file_hashes.get("repo")
            current_office2 = file_hashes.get("office2")
            baseline_repo = file_data.get("repo_sha256")
            baseline_office2 = file_data.get("office2_sha256")

            state = classify_drift(
                current_repo, current_office2,
                baseline_repo, baseline_office2,
            )

            factory = is_factory_default(
                current_repo, filename, factory_baselines,
            )

            results.append(DriftResult(
                agent_id=agent_id,
                filename=filename,
                state=state,
                current_repo_hash=current_repo,
                current_office2_hash=current_office2,
                baseline_repo_hash=baseline_repo,
                baseline_office2_hash=baseline_office2,
                is_factory_default=factory,
            ))

    return results
