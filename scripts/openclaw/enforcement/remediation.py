"""Remediation actions for agent workspace drift enforcement.

Implements auto-deploy (repo→office2), auto-capture (office2→repo),
and the routing logic that dispatches based on drift state.
"""

import json
import logging
import os
import subprocess

from scripts.openclaw.enforcement.detection import DriftResult, DriftState, is_factory_default

logger = logging.getLogger(__name__)


def deploy_to_office2(
    repo_file: str,
    office2_path: str,
    ssh_host: str = "office2-claude",
    dry_run: bool = False,
) -> bool:
    """SCP a repo file to office2 and verify hash. Returns True on success."""
    if dry_run:
        logger.info("DRY RUN: would deploy %s → %s:%s", repo_file, ssh_host, office2_path)
        return True

    result = subprocess.run(
        ["scp", repo_file, f"{ssh_host}:{office2_path}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.error("SCP deploy failed: %s", result.stderr.strip())
        return False

    # Verify remote hash matches local
    import hashlib
    with open(repo_file, "rb") as f:
        local_hash = hashlib.sha256(f.read()).hexdigest()
    try:
        verify = subprocess.run(
            ["ssh", ssh_host, f'sha256sum "{office2_path}"'],
            capture_output=True, text=True, timeout=15,
        )
        if verify.returncode != 0 or not verify.stdout.strip():
            logger.error("Post-deploy hash verification failed: could not read remote file")
            return False
        remote_hash = verify.stdout.strip().split("  ")[0]
        if remote_hash != local_hash:
            logger.error("Post-deploy hash mismatch: local=%s remote=%s", local_hash, remote_hash)
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("Post-deploy hash verification error: %s", e)
        return False

    logger.info("Deployed %s → %s:%s (hash verified)", repo_file, ssh_host, office2_path)
    return True


def capture_from_office2(
    office2_path: str,
    repo_file: str,
    agent_id: str,
    filename: str,
    ssh_host: str = "office2-claude",
    dry_run: bool = False,
    repo_root: str = ".",
) -> bool:
    """SCP an office2 file to the repo and git commit. Returns True on success."""
    if dry_run:
        logger.info("DRY RUN: would capture %s:%s → %s", ssh_host, office2_path, repo_file)
        return True

    result = subprocess.run(
        ["scp", f"{ssh_host}:{office2_path}", repo_file],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.error("SCP capture failed: %s", result.stderr.strip())
        return False

    commit_msg = f"chore: drift-reconcile {agent_id}/{filename} (office2→repo)"
    subprocess.run(["git", "-C", repo_root, "add", repo_file], check=True, timeout=15)
    result = subprocess.run(
        ["git", "-C", repo_root, "commit", "-m", commit_msg],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        logger.warning("Git commit failed (may be no changes): %s", result.stderr.strip())

    logger.info("Captured %s:%s → %s", ssh_host, office2_path, repo_file)
    return True


def update_manifest(
    manifest_path: str,
    agent_id: str,
    filename: str,
    new_hash: str,
    factory_default: bool | None = None,
) -> None:
    """Update both repo and office2 hashes in the manifest after remediation.

    If factory_default is provided, updates that flag too (used to clear
    factory_default after a customization capture).
    """
    with open(manifest_path) as f:
        manifest = json.load(f)

    agent_data = manifest.get("agents", {}).get(agent_id, {})
    file_data = agent_data.get("files", {}).get(filename, {})
    file_data["repo_sha256"] = new_hash
    file_data["office2_sha256"] = new_hash
    if factory_default is not None:
        file_data["factory_default"] = factory_default
    manifest["agents"][agent_id]["files"][filename] = file_data

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def process_drift_results(
    results: list[DriftResult],
    config: dict,
    manifest_path: str,
    repo_root: str = ".",
    dry_run: bool = False,
    factory_baselines: dict | None = None,
) -> dict:
    """Process all drift results: remediate or collect notifications.

    Returns a dict with lists of actions taken.
    """
    ssh_host = config.get("ssh_host", "office2-claude")
    actions = {
        "deployed": [],
        "captured": [],
        "conflicts": [],
        "factory_transitions": [],
        "errors": [],
    }

    for result in results:
        agent_config = config["agents"].get(result.agent_id, {})
        repo_file = os.path.join(repo_root, agent_config.get("repo_path", ""), result.filename)
        office2_path = f"{agent_config.get('workspace_path', '')}/{result.filename}"

        if result.state == DriftState.REPO_CHANGED:
            ok = deploy_to_office2(repo_file, office2_path, ssh_host, dry_run)
            if ok:
                actions["deployed"].append(result)
                if not dry_run:
                    update_manifest(manifest_path, result.agent_id, result.filename, result.current_repo_hash)
            else:
                actions["errors"].append(result)

        elif result.state == DriftState.OFFICE2_CHANGED:
            # Check for factory-default transition: was the file factory-default
            # in the manifest, and is the office2 version now customized?
            manifest_entry = _get_manifest_entry(manifest_path, result.agent_id, result.filename)
            was_factory = manifest_entry.get("factory_default", False) if manifest_entry else False
            office2_still_factory = False
            if was_factory and factory_baselines:
                office2_still_factory = is_factory_default(
                    result.current_office2_hash, result.filename, factory_baselines,
                )

            ok = capture_from_office2(
                office2_path, repo_file, result.agent_id, result.filename,
                ssh_host, dry_run, repo_root,
            )
            if ok:
                actions["captured"].append(result)
                is_transition = was_factory and not office2_still_factory
                if not dry_run:
                    update_manifest(
                        manifest_path, result.agent_id, result.filename,
                        result.current_office2_hash,
                        factory_default=False if is_transition else None,
                    )
                if is_transition:
                    actions["factory_transitions"].append(result)
            else:
                actions["errors"].append(result)

        elif result.state == DriftState.CONFLICT:
            actions["conflicts"].append(result)

    return actions


def _get_manifest_entry(manifest_path: str, agent_id: str, filename: str) -> dict | None:
    """Read a single file entry from the manifest."""
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        return manifest.get("agents", {}).get(agent_id, {}).get("files", {}).get(filename)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
