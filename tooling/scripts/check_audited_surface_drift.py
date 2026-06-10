#!/usr/bin/env python3
"""Soft-reminder for changes that touch audited surfaces (#557).

Reads `docs/design/architecture/data/audited-surfaces.json`, compares its
path patterns to the changed files in the current diff, and emits a
GitHub Actions-friendly warning annotation when any matches. Exit code
is always 0 — this is a reminder, not a gate.

Usage (CI):
    python3 tooling/scripts/check_audited_surface_drift.py --range origin/main...HEAD

Usage (local pre-push, optional):
    python3 tooling/scripts/check_audited_surface_drift.py --range origin/main..HEAD

Usage (single commit):
    python3 tooling/scripts/check_audited_surface_drift.py --range HEAD~1...HEAD

Without --range, defaults to the staged diff (`git diff --cached --name-only`).

Exit code is always 0 unless the audited-surfaces.json is unreadable or the
git command fails — failure modes that warrant a CI red, not silent skip.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AUDITED_SURFACES_PATH = (
    REPO_ROOT
    / "docs"
    / "design"
    / "architecture"
    / "data"
    / "audited-surfaces.json"
)


def _load_audited_surfaces() -> dict:
    if not AUDITED_SURFACES_PATH.exists():
        print(
            f"ERROR: audited-surfaces.json not found at {AUDITED_SURFACES_PATH}",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        return json.loads(AUDITED_SURFACES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: audited-surfaces.json is malformed: {exc}", file=sys.stderr)
        sys.exit(2)


def _changed_files(range_spec: str | None) -> list[str]:
    """Return the list of changed file paths for the given range.

    If range_spec is None, returns the staged diff.
    """
    if range_spec is None:
        cmd = ["git", "diff", "--cached", "--name-only"]
    else:
        cmd = ["git", "diff", "--name-only", range_spec]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, cwd=REPO_ROOT
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: git diff failed (cmd={cmd}): {exc.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(2)
    return [line for line in result.stdout.splitlines() if line.strip()]


def _file_matches_pattern(path: str, pattern: str) -> bool:
    """Glob match with `**` support.

    `fnmatch` handles `*` and `?` per shell semantics. We add `**` as a
    "zero-or-more directories" wildcard so `**/Dockerfile` matches a
    Dockerfile at any depth.
    """
    if "**" in pattern:
        # Expand `**/x` to also match `x` at top level.
        if pattern.startswith("**/"):
            tail = pattern[3:]
            if fnmatch.fnmatch(path, tail) or fnmatch.fnmatch(path, pattern):
                return True
        # Try `**` as `*/*/.../*` for fnmatch
        # fnmatch doesn't support **, so we approximate: replace ** with *
        # and accept that we'll over-match slightly (false positives are
        # acceptable for a reminder).
        normalized = pattern.replace("**/", "*/").replace("/**", "/*")
        if fnmatch.fnmatch(path, normalized):
            return True
        return False
    return fnmatch.fnmatch(path, pattern)


def _match_surfaces(changed_files: list[str], audited: dict) -> list[dict]:
    """Return surfaces whose patterns match at least one changed file.

    Each returned entry has the surface dict + a `matched_files` list.
    """
    surfaces = audited.get("audited_surfaces", [])
    matches: list[dict] = []
    for surface in surfaces:
        matched_files: list[str] = []
        for pattern in surface.get("patterns", []):
            for changed_file in changed_files:
                if _file_matches_pattern(changed_file, pattern):
                    if changed_file not in matched_files:
                        matched_files.append(changed_file)
        if matched_files:
            matches.append({**surface, "matched_files": matched_files})
    return matches


def _emit_warnings(matches: list[dict], audited: dict) -> None:
    """Emit GitHub Actions warning annotations + a plain summary."""
    rebaseline_cmd = audited.get("rebaseline_command", "(see runbook)")
    rebaseline_runbook = audited.get("rebaseline_runbook", "")

    # Plain summary (always printed)
    print("=" * 72)
    print("Audited surface drift reminder (kentonium3/kg-automation#557)")
    print("=" * 72)
    print()
    print(
        f"The diff touches {len(matches)} audited surface(s). After this change "
        f"deploys, run the security-monitor rebaseline so the daily 3 AM audit "
        f"does not alert on the now-expected state."
    )
    print()
    for match in matches:
        print(f"- **{match['id']}**: {match['description']}")
        print(f"  Affected baselines: {', '.join(match.get('affected_baselines', []))}")
        print("  Matched files:")
        for f in match["matched_files"]:
            print(f"    - {f}")
        print()

    print("Rebaseline command:")
    print(f"  {rebaseline_cmd}")
    print()
    print(f"Full runbook: {rebaseline_runbook}")
    print("=" * 72)

    # GitHub Actions annotations (only show in CI)
    for match in matches:
        for f in match["matched_files"]:
            # GHA warning annotation per file — appears in the PR/commit
            # diff view as a yellow ⚠ next to the file.
            print(
                f"::warning file={f},title=Audited surface drift "
                f"(rebaseline reminder)::"
                f"{match['id']} — after this change deploys, run: "
                f"{rebaseline_cmd}",
                file=sys.stderr,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Soft-reminder: warn when a commit touches audited surfaces "
            "(per docs/design/architecture/data/audited-surfaces.json). "
            "Always exits 0 unless setup is broken (audited-surfaces.json "
            "missing or git diff fails)."
        )
    )
    parser.add_argument(
        "--range",
        default=None,
        help=(
            "Git diff range (e.g., 'origin/main...HEAD'). Omit to use the "
            "staged diff (`git diff --cached`)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the plain-text summary; only emit GHA annotations.",
    )
    args = parser.parse_args(argv)

    audited = _load_audited_surfaces()
    changed = _changed_files(args.range)
    if not changed:
        if not args.quiet:
            print("No changed files in range; nothing to check.")
        return 0

    matches = _match_surfaces(changed, audited)
    if not matches:
        if not args.quiet:
            print(
                f"Diff covers {len(changed)} file(s); none match audited surfaces."
            )
        return 0

    if args.quiet:
        # Only annotations
        for match in matches:
            rebaseline_cmd = audited.get("rebaseline_command", "(see runbook)")
            for f in match["matched_files"]:
                print(
                    f"::warning file={f},title=Audited surface drift::"
                    f"{match['id']} → rebaseline: {rebaseline_cmd}",
                    file=sys.stderr,
                )
    else:
        _emit_warnings(matches, audited)
    return 0


if __name__ == "__main__":
    sys.exit(main())
