---
work_package_id: WP02
title: Deploy Script
dependencies:
- WP01
requirement_refs:
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
agent: "claude"
shell_pid: "15016"
history:
- date: '2026-04-10T13:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/vault/
execution_mode: code_change
owned_files:
- scripts/vault/targets.json
- scripts/vault/deploy.py
tags: []
---

# WP02: Deploy Script

## Objective

Build the deploy script that reads the registry and template files, replaces `{{VAULT_*}}` markers with resolved paths, and writes the output to target files. MVP: no template files exist yet (WP03 creates the first one), but the script must handle an empty target list gracefully and be ready to process real targets.

## Context

- Depends on WP01's `paths.json` and the general registry convention
- The deploy script lives alongside the registry in `scripts/vault/`
- It's a Python 3 script — no new dependencies
- It reads `targets.json` for a list of `.tmpl` → resolved file mappings
- Default behavior is dry-run (safety); `--apply` actually writes files
- The script is idempotent: running it twice produces the same result

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP02 --agent claude`

---

## Subtask T007: Create targets.json

**Purpose**: Create the initial empty `targets.json` that the deploy script reads. WP03 will add the first real target entry.

**Steps**:
1. Create `scripts/vault/targets.json` with this content:

```json
{
  "version": 1,
  "targets": []
}
```

**Schema notes**:
- `version` matches `paths.json` convention
- `targets` is a list of mappings. Each mapping has:
  - `template`: path to the `.tmpl` source file, relative to repo root
  - `output`: path to the resolved output file, relative to repo root
  - `office2_path` (optional): absolute path on office2 where the resolved file should be SCP'd
- Empty list is valid — deploy script should handle it with "nothing to do"

**Validation**:
- [ ] File exists at `scripts/vault/targets.json`
- [ ] JSON is valid
- [ ] Contains `version` and empty `targets` array

---

## Subtask T008: Create deploy.py

**Purpose**: The core build-time script that resolves templates and writes output files.

**Steps**:
1. Create `scripts/vault/deploy.py` with this content:

```python
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
    python3 scripts/vault/deploy.py --no-office2 # skip SCP to office2
"""
import argparse
import json
import re
import shutil
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


def _diff_lines(old: str, new: str, context: int = 2) -> str:
    """Simple unified-style diff for the first few changed lines."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    changes = []
    for i, (o, n) in enumerate(zip(old_lines, new_lines)):
        if o != n:
            changes.append(f"  L{i+1}: - {o}")
            changes.append(f"  L{i+1}: + {n}")
    if len(old_lines) != len(new_lines):
        changes.append(f"  (line count changed: {len(old_lines)} -> {len(new_lines)})")
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
            "status": "error",
            "message": f"Template not found: {template_path}",
        }

    template_content = template_path.read_text()
    markers_found = _find_markers(template_content)
    resolved_content = _resolve_content(template_content, paths)

    # Determine what will change
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
        status["diff"] = _diff_lines(existing_content or "", resolved_content)

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
            print(f"  ERROR: {target.get('output', '?')}: {e}", file=sys.stderr)
            errors += 1
            continue

        marker = "✓" if status["status"] in ("applied", "would-apply", "unchanged") else "✗"
        print(f"{marker} {status['target']}")
        print(f"    template: {status['template']}")
        print(f"    markers:  {', '.join(status['markers']) if status['markers'] else '(none)'}")
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
```

**Important design notes**:
- Standard library only (`argparse`, `json`, `re`, `subprocess`, `tempfile`, `pathlib`)
- Dry-run is the default — `--apply` must be explicit
- Atomic write via temp file + rename prevents partial writes
- SCP to office2 is automatic in apply mode when `office2_path` is set; `--no-office2` skips it
- Unknown markers produce a clear error and non-zero exit
- Idempotent: if resolved content matches existing file, status is "unchanged" and no write happens

**Validation**:
- [ ] File exists at `scripts/vault/deploy.py`
- [ ] Python syntax valid: `python3 -c "import ast; ast.parse(open('scripts/vault/deploy.py').read())"`
- [ ] Executable permission not required (run via `python3 scripts/vault/deploy.py`)

---

## Subtask T009: Verify deploy.py Dry-Run and Apply Modes

**Purpose**: Confirm the deploy script handles the empty-targets case and runs without errors.

**Steps**:
1. Run dry-run: `python3 scripts/vault/deploy.py`
2. Verify output: "No targets configured in targets.json. Nothing to do."
3. Verify exit code 0: `echo $?`
4. Run with `--apply`: `python3 scripts/vault/deploy.py --apply`
5. Verify same output (empty targets → nothing to do)

**Validation**:
- [ ] Dry-run exits 0 with "nothing to do" message
- [ ] Apply mode exits 0 with same message
- [ ] No files written (empty targets list)

---

## Subtask T010: Verify Unknown Marker Error Handling

**Purpose**: Confirm the script fails loudly when a template references an unregistered marker.

**Steps**:
1. Create a temporary test template at `/tmp/test-unknown-marker.md.tmpl`:
   ```
   echo 'Path: {{VAULT_NONEXISTENT}}' > /tmp/test-unknown-marker.md.tmpl
   ```
2. Temporarily add this to `targets.json` (you can edit and revert, or use a temporary copy):
   ```json
   {
     "version": 1,
     "targets": [
       {
         "template": "../../../tmp/test-unknown-marker.md.tmpl",
         "output": "/tmp/test-unknown-marker.md"
       }
     ]
   }
   ```
   (or test with a template file inside the repo for simpler relative paths)
3. Actually, simpler: create the test template INSIDE the repo temporarily at `scripts/vault/test-unknown.md.tmpl` with content `Path: {{VAULT_NONEXISTENT}}`
4. Add target entry pointing to it
5. Run: `python3 scripts/vault/deploy.py`
6. Verify error output includes "Unknown marker {{VAULT_NONEXISTENT}}"
7. Verify exit code is non-zero
8. Clean up: remove test template and revert targets.json to empty

**Validation**:
- [ ] Unknown marker produces clear error output
- [ ] Non-zero exit code
- [ ] No output file written
- [ ] Test artifacts cleaned up (targets.json restored to empty)

---

## Definition of Done

- [ ] `scripts/vault/targets.json` created with empty targets array
- [ ] `scripts/vault/deploy.py` created with dry-run default, apply mode, SCP support, atomic writes
- [ ] Dry-run mode works with empty targets
- [ ] Apply mode works with empty targets
- [ ] Unknown marker error path verified
- [ ] All files committed to the worktree

## Risks

- **SCP silently fails during apply**: Mitigation — the script captures SCP output and raises on non-zero exit. Apply mode propagates the error.
- **Concurrent runs could race**: Not a concern for this MVP (single human user, one run at a time).
- **Temp file cleanup if atomic write fails**: Python's `NamedTemporaryFile` with `delete=False` leaves the temp file if rename fails — acceptable for manual cleanup, and the atomic write path is simple enough that failures are unlikely.

## Reviewer Guidance

- Python syntax must be valid
- Deploy logic should match: read paths → read targets → for each target, resolve content, diff, apply
- Verify the marker regex `\{\{VAULT_([A-Z_]+)\}\}` is correct
- Verify dry-run is the default (no `--apply` means no writes)
- Check that error paths are distinct from success paths (non-zero exits, stderr messages)

## Activity Log

- 2026-04-10T15:37:12Z – claude – shell_pid=15016 – Started implementation via action command
- 2026-04-10T15:38:45Z – claude – shell_pid=15016 – Deploy script complete with dry-run default, unknown marker errors, empty targets handled
- 2026-04-10T15:38:47Z – claude – shell_pid=15016 – Dry-run and apply verified; unknown marker error verified; idempotent logic in place
