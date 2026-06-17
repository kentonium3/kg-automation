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

The surface-matching core (load / changed-files / glob-match / match-surfaces)
lives in the shared module `tooling/scripts/audited_surfaces.py` so
felix-deployer's rebaseline engine and this reminder consume one source of
truth (#618, NFR-001).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the sibling shared module is importable whether this file is run as a
# script (CI: `python3 tooling/scripts/check_audited_surface_drift.py`) or
# imported by tests via importlib.spec_from_file_location.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audited_surfaces import (  # noqa: E402  (intentional: after sys.path bootstrap)
    changed_files,
    load_audited_surfaces,
    match_surfaces,
)


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

    audited = load_audited_surfaces()
    changed = changed_files(args.range)
    if not changed:
        if not args.quiet:
            print("No changed files in range; nothing to check.")
        return 0

    matches = match_surfaces(changed, audited)
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
