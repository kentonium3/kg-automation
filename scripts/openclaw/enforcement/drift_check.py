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
import tempfile
from datetime import datetime, timezone
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


def compute_office2_hashes(ssh_host: str, file_paths: list[str]) -> dict:
    """Hash each deployed office2 workspace file, LOCAL-first (#766).

    The drift-check cron runs **on office2**, where the deployed workspace files
    (``/data/services/openclaw/…``) are on the local filesystem and the
    ``ssh_host`` alias (``office2-claude``) does NOT resolve — it is a Mac-only
    ``~/.ssh/config`` alias. An unconditional ``ssh`` therefore failed every read
    on the cron host, and the enforcement reported garbage (``file_missing_repo``
    for every agent), i.e. the whole guard was silently inert.

    Fix: if the workspace files are present on THIS host (we are on office2), read
    them directly — a genuinely-absent file then reads as ``None`` (office2
    missing), which is correct. Only when they are not local (the tool is run
    from the Mac, where the alias resolves) do we batch a single SSH. This makes
    the tool correct from both vantage points with no host flag or hostname probe.
    """
    if not file_paths:
        return {}
    on_host = any(os.path.isdir(os.path.dirname(fp)) for fp in file_paths)
    if on_host:
        return {fp: compute_local_hash(fp) for fp in file_paths}
    return compute_remote_hashes(ssh_host, file_paths)


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

    # Office2 workspace hashes — local-first, SSH only when not on-host (#766).
    remote_hashes = compute_office2_hashes(ssh_host, remote_paths)

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


#: Durable freshness pointer (#895). NOT /tmp — the previous only trace of this
#: job was /tmp/drift-check.log, which systemd-tmpfiles empties at every boot, and
#: tests/canary/test_inventory_health_checks.py pins the set of components allowed
#: to probe /tmp. Follows the established /data/services/openclaw/state/<component>/
#: convention.
LAST_TICK_PATH = "/data/services/openclaw/state/enforcement/last-tick.json"


#: Set once the freshness pointer has been written this run, so the outer failure
#: handler in main() does not double-write and does not overwrite a good pointer.
_TICK_WRITTEN = {"done": False}


def write_last_tick(path, *, status, exit_code, has_drift):
    """Atomically record that this run happened, and how it ended.

    ⚠ ``exit_code`` here means "did the RUNNER execute correctly", never "was the
    result clean". This distinction is load-bearing. ``main()`` exits 1 when it
    *finds* drift — a perfectly successful run — while the canary treats any
    non-zero ``exit_code`` in a pointer as an explicit failure that short-circuits
    ahead of freshness (scripts/canary/probes.py:267-269). Writing the process
    exit code straight into this field would make every drift-finding run page as
    a broken component, training the operator to ignore the alert. Drift is
    reported through this script's own output and alerting path; ``has_drift``
    below is diagnostic only and is deliberately named so it does NOT collide
    with the canary's explicit-error scan (error/errors/cycle_error/exit_status).

    Never fatal: losing the freshness signal beats crashing drift enforcement.
    """
    payload = {
        "status": status,
        "exit_code": exit_code,
        "completed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "has_drift": has_drift,
    }
    try:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="last-tick.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2) + "\n")
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError:
        return
    _TICK_WRITTEN["done"] = True


def _run():
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
    parser.add_argument(
        "--last-tick-path",
        default=LAST_TICK_PATH,
        help="Where the freshness pointer is written (#895).",
    )
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

    # Return exit code: 0 = clean or remediated, 1 = drift (report), 2 = errors.
    # These process exit codes are unchanged — callers and the crontab depend on
    # them. What the freshness pointer records is a DIFFERENT question: whether
    # the runner executed, not whether the result was clean. See write_last_tick.
    if actions is not None:
        has_errors = bool(actions.get("errors"))
        code = 2 if has_errors else 0
        write_last_tick(
            args.last_tick_path,
            status="error" if has_errors else "success",
            exit_code=2 if has_errors else 0,
            has_drift=None if has_errors else has_drift,
        )
        sys.exit(code)
    else:
        # `report` mode: exit 1 means "ran fine, found drift" -> healthy pointer.
        write_last_tick(
            args.last_tick_path, status="success", exit_code=0, has_drift=has_drift
        )
        sys.exit(1 if has_drift else 0)


def main():
    """Run the drift check, guaranteeing a freshness pointer on every exit path.

    Post-review hardening (#895): the pointer was previously written only in the
    normal exit block, so an early failure — a missing config via ``load_json``'s
    ``sys.exit``, a JSON decode error, or an exception from detection or
    remediation — would abort with no pointer at all. The canary would then see
    only staleness, hours later, instead of an immediate explicit error. Any
    escape now records ``status: error`` before propagating.
    """
    _TICK_WRITTEN["done"] = False
    try:
        _run()
    except BaseException:
        if not _TICK_WRITTEN["done"]:
            # argparse failures happen before the flag path is reachable with a
            # parsed value, so fall back to the default location.
            write_last_tick(
                LAST_TICK_PATH, status="error", exit_code=2, has_drift=None
            )
        raise


if __name__ == "__main__":
    main()
