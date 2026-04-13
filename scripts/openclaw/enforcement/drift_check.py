#!/usr/bin/env python3
"""Agent workspace drift enforcement script.

Detects drift between repo and office2 agent workspace files using a
three-way diff against a baseline manifest. Supports dry-run mode
for reporting without action.

Usage:
    python3 scripts/openclaw/enforcement/drift_check.py check
    python3 scripts/openclaw/enforcement/drift_check.py check --dry-run --json
    python3 scripts/openclaw/enforcement/drift_check.py report
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure repo root is on sys.path so this script can be run directly
_repo_root = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True, text=True,
).stdout.strip()
if _repo_root and _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from scripts.openclaw.enforcement.detection import (  # noqa: E402
    DriftState,
    detect_all_drift,
)
from scripts.openclaw.enforcement.remediation import process_drift_results  # noqa: E402
from scripts.openclaw.enforcement.notification import notify  # noqa: E402


def load_json(path: str) -> dict:
    """Load a JSON file, exiting with error if missing."""
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def get_repo_root() -> str:
    """Get the git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.getcwd()


def compute_local_hash(file_path: str) -> str | None:
    """SHA256 of a local file. Returns None if file missing."""
    if not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# Sentinel value for SSH transport errors — distinct from None (file missing)
SSH_ERROR = "__SSH_ERROR__"


def compute_remote_hashes(ssh_host: str, file_paths: list[str]) -> dict[str, str | None]:
    """Compute SHA256 hashes for multiple files on office2 via a single SSH call.

    Returns a dict mapping remote path to hash string, None (file missing on
    remote), or SSH_ERROR (transport failure — file should be skipped).
    """
    if not file_paths:
        return {}
    cmds = []
    for fp in file_paths:
        cmds.append(f'if [ -f "{fp}" ]; then sha256sum "{fp}"; else echo "MISSING {fp}"; fi')
    combined = "; ".join(cmds)
    try:
        result = subprocess.run(
            ["ssh", ssh_host, combined],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"ERROR: SSH failed: {e}", file=sys.stderr)
        return {fp: SSH_ERROR for fp in file_paths}

    if result.returncode != 0 and not result.stdout.strip():
        print(f"ERROR: SSH returned exit code {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        return {fp: SSH_ERROR for fp in file_paths}

    hashes = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        if line.startswith("MISSING "):
            path = line[len("MISSING "):]
            hashes[path] = None
        elif "  " in line:
            h, path = line.split("  ", 1)
            hashes[path] = h
    return hashes


def compute_all_hashes(config: dict, repo_root: str) -> dict:
    """Compute current hashes for all tracked files on both sides."""
    ssh_host = config.get("ssh_host", "office2-claude")

    # Collect remote paths for batched SSH
    remote_paths = []
    path_index = {}  # remote_path -> (agent_id, filename)

    for agent_id, agent_config in config["agents"].items():
        for filename in agent_config["tracked_files"]:
            remote_path = f"{agent_config['workspace_path']}/{filename}"
            remote_paths.append(remote_path)
            path_index[remote_path] = (agent_id, filename)

    # Batch remote hashes
    remote_hashes = compute_remote_hashes(ssh_host, remote_paths)

    # Build result structure — skip files with SSH errors
    result = {}
    skipped = []
    for agent_id, agent_config in config["agents"].items():
        agent_hashes = {}
        for filename in agent_config["tracked_files"]:
            repo_file = os.path.join(repo_root, agent_config["repo_path"], filename)
            remote_path = f"{agent_config['workspace_path']}/{filename}"

            remote_hash = remote_hashes.get(remote_path)
            if remote_hash == SSH_ERROR:
                print(f"  SKIP {agent_id}/{filename}: SSH error (will not report as drift)", file=sys.stderr)
                skipped.append(f"{agent_id}/{filename}")
                continue

            agent_hashes[filename] = {
                "repo": compute_local_hash(repo_file),
                "office2": remote_hash,
            }
        result[agent_id] = agent_hashes

    if skipped:
        print(f"  Skipped {len(skipped)} files due to SSH errors", file=sys.stderr)

    return result


def format_results(results: list, as_json: bool = False) -> str:
    """Format drift results for display."""
    if as_json:
        output = []
        for r in results:
            output.append({
                "agent_id": r.agent_id,
                "filename": r.filename,
                "state": r.state.value,
                "is_factory_default": r.is_factory_default,
                "current_repo_hash": r.current_repo_hash,
                "current_office2_hash": r.current_office2_hash,
            })
        return json.dumps({"results": output, "total": len(results)}, indent=2)

    lines = []
    for r in results:
        if r.state == DriftState.NO_CHANGE:
            mark = "✓"
        elif r.state == DriftState.REPO_CHANGED:
            mark = "→"  # repo→office2
        elif r.state == DriftState.OFFICE2_CHANGED:
            mark = "←"  # office2→repo
        elif r.state == DriftState.CONFLICT:
            mark = "⚠"
        else:
            mark = "✗"
        factory = " (factory)" if r.is_factory_default else ""
        lines.append(f"  {mark} {r.agent_id}/{r.filename}: {r.state.value}{factory}")

    # Summary
    states = [r.state for r in results]
    summary = (
        f"\n  Total: {len(results)} files, "
        f"{states.count(DriftState.NO_CHANGE)} unchanged, "
        f"{states.count(DriftState.REPO_CHANGED)} repo→office2, "
        f"{states.count(DriftState.OFFICE2_CHANGED)} office2→repo, "
        f"{states.count(DriftState.CONFLICT)} conflicts"
    )
    return "\n".join(lines) + summary


def main():
    parser = argparse.ArgumentParser(description="Agent workspace drift enforcement")
    parser.add_argument(
        "command",
        choices=["check", "report"],
        help="'check' detects drift and takes action; 'report' is output-only",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "drift-check-config.json"),
        help="Path to drift-check-config.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    args = parser.parse_args()

    repo_root = get_repo_root()
    config = load_json(args.config)

    # Resolve manifest and factory baselines paths
    config_dir = os.path.dirname(os.path.abspath(args.config))
    manifest_path = os.path.normpath(
        os.path.join(config_dir, config.get("baseline_manifest_path", "../agents/baseline-manifest.json"))
    )
    factory_path = os.path.normpath(
        os.path.join(config_dir, config.get("factory_baselines_path", "../agents/factory-baselines.json"))
    )

    manifest = load_json(manifest_path)
    factory_baselines = load_json(factory_path)

    # Compute current hashes
    print("Computing current hashes...", file=sys.stderr)
    current_hashes = compute_all_hashes(config, repo_root)

    # Detect drift
    results = detect_all_drift(current_hashes, manifest, factory_baselines)

    has_drift = any(r.state != DriftState.NO_CHANGE for r in results)
    actions = None

    # For 'check' command: take action (remediate + notify)
    if args.command == "check" and has_drift:
        print("Executing remediation...", file=sys.stderr)
        actions = process_drift_results(
            results, config, manifest_path,
            repo_root=repo_root, dry_run=args.dry_run,
            factory_baselines=factory_baselines,
        )
        notify(actions, config, dry_run=args.dry_run)

    # Output — single JSON document or text
    if args.json_output:
        output = {
            "results": [
                {
                    "agent_id": r.agent_id,
                    "filename": r.filename,
                    "state": r.state.value,
                    "is_factory_default": r.is_factory_default,
                    "current_repo_hash": r.current_repo_hash,
                    "current_office2_hash": r.current_office2_hash,
                }
                for r in results
            ],
            "total": len(results),
            "has_drift": has_drift,
        }
        if actions is not None:
            output["actions"] = {
                "deployed": len(actions["deployed"]),
                "captured": len(actions["captured"]),
                "conflicts": len(actions["conflicts"]),
                "factory_transitions": len(actions["factory_transitions"]),
                "errors": len(actions["errors"]),
            }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(results))

    # Return exit code: 0 = clean or remediated, 1 = drift (report), 2 = errors
    if actions is not None:
        has_errors = bool(actions.get("errors"))
        sys.exit(2 if has_errors else 0)
    else:
        sys.exit(1 if has_drift else 0)


if __name__ == "__main__":
    main()
