#!/usr/bin/env python3
"""Shared audited-surface matcher (single source of truth, #618 / NFR-001).

This module holds the reusable core that decides whether a set of changed
files touches an *audited surface* per
`docs/design/architecture/data/audited-surfaces.json`. Both consumers import
it so the deploy-time check and the repo-side CI reminder cannot diverge:

- ``tooling/scripts/check_audited_surface_drift.py`` — the CI / pre-push
  soft-reminder (imports these functions; keeps its CLI + exit codes).
- ``scripts/deploy/felix-deployer/rebaseline.py`` — felix-deployer's
  deferred-confirm rebaseline engine (observes pulled-range changes).

The functions are pure / import-light (stdlib only) so either caller can use
them without dragging in CLI or notification dependencies.

**Exit-2 contract**: ``load_audited_surfaces`` and ``changed_files`` preserve
the original CI script's behaviour of printing to stderr and calling
``sys.exit(2)`` on a broken setup (missing/malformed registry, failed git
command) — a setup error warrants a CI red, not a silent skip. Callers that
need non-exiting behaviour should ensure the registry exists and pass a valid
range.
"""
from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from pathlib import Path

# tooling/scripts/audited_surfaces.py -> parent=scripts, .parent.parent=tooling,
# .parent.parent.parent=repo root. Same resolution the CI script used.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AUDITED_SURFACES_PATH = (
    REPO_ROOT
    / "docs"
    / "design"
    / "architecture"
    / "data"
    / "audited-surfaces.json"
)


def load_audited_surfaces() -> dict:
    """Load and parse the audited-surface registry.

    Preserves the exit-2 contract: prints to stderr and ``sys.exit(2)`` if the
    registry is missing or malformed.
    """
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


def changed_files(range_spec: str | None) -> list[str]:
    """Return the list of changed file paths for the given range.

    If ``range_spec`` is None, returns the staged diff
    (``git diff --cached --name-only``). Preserves the exit-2 contract on a
    failed git command.
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


def file_matches_pattern(path: str, pattern: str) -> bool:
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


def match_surfaces(changed: list[str], audited: dict) -> list[dict]:
    """Return surfaces whose patterns match at least one changed file.

    Each returned entry has the surface dict + a `matched_files` list.
    """
    surfaces = audited.get("audited_surfaces", [])
    matches: list[dict] = []
    for surface in surfaces:
        matched_files: list[str] = []
        for pattern in surface.get("patterns", []):
            for changed_file in changed:
                if file_matches_pattern(changed_file, pattern):
                    if changed_file not in matched_files:
                        matched_files.append(changed_file)
        if matched_files:
            matches.append({**surface, "matched_files": matched_files})
    return matches
