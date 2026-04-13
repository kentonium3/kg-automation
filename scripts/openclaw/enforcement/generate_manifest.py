#!/usr/bin/env python3
"""Generate baseline-manifest.json for agent workspace drift enforcement.

Reads drift-check-config.json, computes SHA256 hashes for all tracked
workspace files on both repo and office2, and writes the manifest.

Usage:
    python3 scripts/openclaw/enforcement/generate_manifest.py
    python3 scripts/openclaw/enforcement/generate_manifest.py --config path/to/config.json
    python3 scripts/openclaw/enforcement/generate_manifest.py --dry-run
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def compute_local_hash(file_path: str) -> tuple[str | None, int]:
    """SHA256 of a local file. Returns (hash, line_count) or (None, 0)."""
    if not os.path.exists(file_path):
        return None, 0
    with open(file_path, "rb") as f:
        content = f.read()
    sha256 = hashlib.sha256(content).hexdigest()
    lines = content.count(b"\n")
    return sha256, lines


def compute_remote_hashes(ssh_host: str, file_paths: list[str]) -> dict[str, str | None]:
    """Compute SHA256 hashes for multiple files on office2 via a single SSH call."""
    if not file_paths:
        return {}
    # Build a single command that hashes all files
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
        return {fp: None for fp in file_paths}

    hashes = {}
    for line in result.stdout.strip().split("\n"):
        if line.startswith("MISSING "):
            path = line[len("MISSING "):]
            hashes[path] = None
        elif "  " in line:
            h, path = line.split("  ", 1)
            hashes[path] = h
    return hashes


def load_factory_baselines(path: str) -> dict:
    """Load factory baselines if available."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def is_factory_default(file_hash: str | None, filename: str, baselines: dict) -> bool:
    """Check if a file's hash matches any known factory baseline."""
    if file_hash is None:
        return False
    entries = baselines.get("baselines", {}).get(filename)
    if entries is None:
        return False
    if isinstance(entries, str):
        return file_hash == entries
    if isinstance(entries, dict):
        return file_hash in entries.values()
    return False


def generate_manifest(config_path: str, dry_run: bool = False) -> dict:
    """Generate the baseline manifest from config."""
    with open(config_path) as f:
        config = json.load(f)

    ssh_host = config.get("ssh_host", "office2-claude")
    # Find repo root via git
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        repo_root = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: config is at scripts/openclaw/enforcement/drift-check-config.json
        # repo root is 4 levels up from config file
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(config_path)))))

    # Load factory baselines
    factory_path = os.path.join(os.path.dirname(config_path), config.get("factory_baselines_path", "../agents/factory-baselines.json"))
    factory_path = os.path.normpath(factory_path)
    baselines = load_factory_baselines(factory_path)

    # Collect all remote file paths for batched SSH
    remote_paths = []
    path_map = {}  # remote_path -> (agent_id, filename)
    for agent_id, agent_config in config["agents"].items():
        for filename in agent_config["tracked_files"]:
            remote_path = f"{agent_config['workspace_path']}/{filename}"
            remote_paths.append(remote_path)
            path_map[remote_path] = (agent_id, filename)

    # Batch compute remote hashes
    print(f"Computing remote hashes for {len(remote_paths)} files via {ssh_host}...")
    remote_hashes = compute_remote_hashes(ssh_host, remote_paths)

    # Build manifest
    manifest = {
        "generated_at": subprocess.run(
            ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
            capture_output=True, text=True
        ).stdout.strip(),
        "generated_by": "generate_manifest.py",
        "agents": {},
    }

    for agent_id, agent_config in config["agents"].items():
        agent_entry = {
            "workspace_path": agent_config["workspace_path"],
            "repo_path": agent_config["repo_path"],
            "files": {},
        }
        for filename in agent_config["tracked_files"]:
            repo_file = os.path.join(repo_root, agent_config["repo_path"], filename)
            repo_hash, repo_lines = compute_local_hash(repo_file)

            remote_path = f"{agent_config['workspace_path']}/{filename}"
            office2_hash = remote_hashes.get(remote_path)

            lines = repo_lines or 0
            factory = is_factory_default(repo_hash, filename, baselines)

            agent_entry["files"][filename] = {
                "repo_sha256": repo_hash,
                "office2_sha256": office2_hash,
                "lines": lines,
                "tracked": repo_hash is not None,
                "factory_default": factory,
            }
        manifest["agents"][agent_id] = agent_entry

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate baseline-manifest.json")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "drift-check-config.json"),
        help="Path to drift-check-config.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print manifest to stdout without writing")
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: ../agents/baseline-manifest.json relative to config)",
    )
    args = parser.parse_args()

    manifest = generate_manifest(args.config, dry_run=args.dry_run)

    output_path = args.output
    if output_path is None:
        config_dir = os.path.dirname(os.path.abspath(args.config))
        output_path = os.path.normpath(os.path.join(config_dir, "../agents/baseline-manifest.json"))

    manifest_json = json.dumps(manifest, indent=2) + "\n"

    if args.dry_run:
        print(manifest_json)
        print(f"\nDRY RUN: would write to {output_path}", file=sys.stderr)
    else:
        with open(output_path, "w") as f:
            f.write(manifest_json)
        print(f"Wrote manifest to {output_path}")
        # Summary
        total_files = sum(len(a["files"]) for a in manifest["agents"].values())
        matched = sum(
            1 for a in manifest["agents"].values()
            for fi in a["files"].values()
            if fi["repo_sha256"] == fi["office2_sha256"] and fi["repo_sha256"] is not None
        )
        print(f"  {len(manifest['agents'])} agents, {total_files} files, {matched} matching")


if __name__ == "__main__":
    main()
