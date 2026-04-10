#!/usr/bin/env python3
"""Vault path registry deploy script.

Reads scripts/vault/paths.json and scripts/vault/targets.json, then for each
target:
  1. Reads the .tmpl source file
  2. Finds all {{VAULT_<NAME>}} markers
  3. Validates that every marker has a corresponding registry entry
  4. Replaces markers with resolved paths
  5. Writes the resolved content to the output file (apply mode only)
  6. Optionally SCPs to office2 if office2_path is set (apply mode only)

Usage:
    python3 scripts/vault/deploy.py              # dry-run (default)
    python3 scripts/vault/deploy.py --apply      # write files
    python3 scripts/vault/deploy.py --apply --no-office2  # skip SCP to office2
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_VAULT_DIR = Path(__file__).parent
_REPO_ROOT = _VAULT_DIR.parent.parent
_PATHS_FILE = _VAULT_DIR / "paths.json"
_TARGETS_FILE = _VAULT_DIR / "targets.json"

# Pattern matches {{VAULT_SOMETHING}} where SOMETHING is uppercase/underscore
_MARKER_PATTERN = re.compile(r"\{\{VAULT_([A-Z_]+)\}\}")


class DeployError(Exception):
    """Deploy script error."""


def _load_json(path: Path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise DeployError(f"Required file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise DeployError(f"Invalid JSON in {path}: {e}") from e


def _load_paths() -> dict:
    """Load paths.json and return the paths dict (upper-cased keys)."""
    data = _load_json(_PATHS_FILE)
    raw = data.get("paths", {})
    return {name.upper(): value for name, value in raw.items()}


def _find_markers(content: str) -> set:
    """Return the set of VAULT_NAME markers found in content."""
    return set(_MARKER_PATTERN.findall(content))


def _resolve_content(content: str, paths: dict) -> str:
    """Replace all {{VAULT_*}} markers with values from paths."""
    def replace(match):
        name = match.group(1)
        if name not in paths:
            raise DeployError(
                f"Unknown marker {{{{VAULT_{name}}}}}. "
                f"Available: {', '.join(sorted(paths.keys())) or '(none)'}"
            )
        return paths[name]
    return _MARKER_PATTERN.sub(replace, content)


def _diff_summary(old: str, new: str) -> str:
    """Simple line-by-line diff summary."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    changes = []
    for i, (o, n) in enumerate(zip(old_lines, new_lines)):
        if o != n:
            changes.append(f"  L{i+1}: - {o}")
            changes.append(f"  L{i+1}: + {n}")
    if len(old_lines) != len(new_lines):
        changes.append(
            f"  (line count changed: {len(old_lines)} -> {len(new_lines)})"
        )
    return "\n".join(changes) if changes else "  (no line differences)"


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _scp_to_office2(local_path: Path, remote_path: str) -> None:
    """Copy a file to office2 via SCP."""
    result = subprocess.run(
        ["scp", str(local_path), f"office2-claude:{remote_path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DeployError(
            f"SCP to office2:{remote_path} failed: {result.stderr.strip()}"
        )


def process_target(
    target: dict,
    paths: dict,
    *,
    apply: bool,
    sync_office2: bool,
) -> dict:
    """Process one target entry. Returns a status dict."""
    template_path = _REPO_ROOT / target["template"]
    output_path = _REPO_ROOT / target["output"]
    office2_path = target.get("office2_path")

    if not template_path.exists():
        return {
            "target": target["output"],
            "template": target["template"],
            "status": "error",
            "markers": [],
            "message": f"Template not found: {template_path}",
        }

    template_content = template_path.read_text()
    markers_found = _find_markers(template_content)
    resolved_content = _resolve_content(template_content, paths)

    existing_content = output_path.read_text() if output_path.exists() else None
    changed = existing_content != resolved_content

    status = {
        "target": target["output"],
        "template": target["template"],
        "markers": sorted(markers_found),
        "changed": changed,
        "office2_synced": False,
    }

    if not changed:
        status["status"] = "unchanged"
        return status

    if apply:
        _atomic_write(output_path, resolved_content)
        if office2_path and sync_office2:
            _scp_to_office2(output_path, office2_path)
            status["office2_synced"] = True
        status["status"] = "applied"
    else:
        status["status"] = "would-apply"
        status["diff"] = _diff_summary(existing_content or "", resolved_content)

    return status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve vault path templates and write output files."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write files (default is dry-run).",
    )
    parser.add_argument(
        "--no-office2",
        action="store_true",
        help="Skip SCP to office2 even in apply mode.",
    )
    args = parser.parse_args()

    try:
        paths = _load_paths()
        targets_data = _load_json(_TARGETS_FILE)
    except DeployError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    targets = targets_data.get("targets", [])
    if not targets:
        print("No targets configured in targets.json. Nothing to do.")
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Vault deploy: {mode} ({len(targets)} target(s))")
    print()

    errors = 0
    for target in targets:
        try:
            status = process_target(
                target,
                paths,
                apply=args.apply,
                sync_office2=not args.no_office2,
            )
        except DeployError as e:
            print(
                f"  ERROR: {target.get('output', '?')}: {e}",
                file=sys.stderr,
            )
            errors += 1
            continue

        marker_char = (
            "X"
            if status["status"] == "error"
            else "-" if status["status"] == "unchanged"
            else "+"
        )
        print(f"[{marker_char}] {status['target']}")
        print(f"    template: {status['template']}")
        markers_list = ", ".join(status["markers"]) if status["markers"] else "(none)"
        print(f"    markers:  {markers_list}")
        print(f"    status:   {status['status']}")
        if status.get("office2_synced"):
            print(f"    office2:  synced")
        if status["status"] == "would-apply" and "diff" in status:
            print(f"    diff:")
            for line in status["diff"].splitlines():
                print(f"    {line}")
        print()

    if errors:
        return 1
    if not args.apply:
        print("Dry-run complete. Re-run with --apply to write files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
