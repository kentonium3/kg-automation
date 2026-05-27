#!/usr/bin/env python3
"""Re-apply the codex `--full-auto` → `-p spec-kitty-review` patch.

Spec-kitty's `spec-kitty-implement-review` skill ships with codex dispatch
lines of the shape `codex exec --full-auto …`. In codex CLI ≥ 0.133.0,
`--full-auto` is a deprecated alias for `--sandbox workspace-write`, which
silently overrides any `-p spec-kitty-review` profile (which sets
`sandbox = "danger-full-access"`) and blocks codex from writing
`.git/index.lock` during the move-task that closes a review verdict. The
orchestrator then has to replay move-task from main, inflating review-cycle
counters and violating the "workflow is authoritative" rule.

This script replaces every `--full-auto` on a `codex exec` line of the
skill files with `-p spec-kitty-review`, preserving file mode (the skill
files are normally read-only and need a temporary `chmod +w`). Idempotent;
safe to run repeatedly. Re-run after any `spec-kitty upgrade` or skill
refresh that may have restored upstream's `--full-auto` dispatch.

Tracked in:
  - GitHub: kentonium3/kg-automation#330
  - Diagnostic: docs/diagnostics/xx_codex-full-auto-overrides-spec-kitty-review-profile.md

Usage:
  repatch_codex_review_profile.py                 # apply
  repatch_codex_review_profile.py --dry-run       # preview without writing
  repatch_codex_review_profile.py --verify        # exit 1 if --full-auto still present
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

AGENT_HOMES = [
    Path.home() / ".claude",
    Path.home() / ".agents",
    Path.home() / ".qwen",
    Path.home() / ".kilocode",
]

SKILL_REL_PATHS = [
    "skills/spec-kitty-implement-review/SKILL.md",
    "skills/spec-kitty-implement-review/references/agent-dispatch-matrix.md",
]

FULL_AUTO_RE = re.compile(r"--full-auto")
CODEX_RE = re.compile(r"\bcodex\b")
REPLACEMENT = "-p spec-kitty-review"


def find_targets() -> list[Path]:
    return [home / rel for home in AGENT_HOMES for rel in SKILL_REL_PATHS if (home / rel).exists()]


def offending_lines(path: Path) -> list[tuple[int, str]]:
    hits = []
    for idx, line in enumerate(path.read_text().splitlines(), start=1):
        if FULL_AUTO_RE.search(line) and CODEX_RE.search(line):
            hits.append((idx, line.rstrip()))
    return hits


def patch_file(path: Path, dry_run: bool) -> list[int]:
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    changed_lines = []
    out = []
    for idx, line in enumerate(lines, start=1):
        if FULL_AUTO_RE.search(line) and CODEX_RE.search(line):
            out.append(FULL_AUTO_RE.sub(REPLACEMENT, line))
            changed_lines.append(idx)
        else:
            out.append(line)

    if changed_lines and not dry_run:
        original_mode = path.stat().st_mode
        try:
            os.chmod(path, original_mode | stat.S_IWUSR)
            path.write_text("".join(out))
        finally:
            os.chmod(path, original_mode)

    return changed_lines


def cmd_verify(targets: list[Path]) -> int:
    bad: list[tuple[Path, int, str]] = []
    for p in targets:
        for idx, line in offending_lines(p):
            bad.append((p, idx, line))
    if bad:
        print(f"VERIFY FAIL: {len(bad)} codex line(s) still carry --full-auto:", file=sys.stderr)
        for p, idx, line in bad:
            print(f"  {p}:{idx}  {line}", file=sys.stderr)
        return 1
    print(f"VERIFY OK: no --full-auto in codex lines across {len(targets)} skill file(s).")
    return 0


def cmd_patch(targets: list[Path], dry_run: bool) -> int:
    total = 0
    for p in targets:
        changed = patch_file(p, dry_run)
        total += len(changed)
        if changed:
            verb = "would patch" if dry_run else "patched"
            print(f"{verb} {p}: lines {changed}")
        else:
            print(f"clean   {p}")
    suffix = "needed (re-run without --dry-run to apply)" if dry_run else "applied"
    print(f"\n{total} replacement(s) {suffix} across {len(targets)} skill file(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print intended changes without writing.")
    mode.add_argument("--verify", action="store_true", help="Exit 1 if any --full-auto remains on a codex line.")
    args = parser.parse_args()

    targets = find_targets()
    if not targets:
        print("No spec-kitty-implement-review skill files found in known agent homes.", file=sys.stderr)
        return 0

    if args.verify:
        return cmd_verify(targets)
    return cmd_patch(targets, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
