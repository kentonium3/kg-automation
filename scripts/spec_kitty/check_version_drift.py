"""Spec-kitty per-repo version-drift check (kentonium3/kg-automation#599).

Surfaces the drift class #599 identified: spec-kitty-initialized repos fall
behind the installed CLI because the per-repo ``spec-kitty upgrade`` run is
ad-hoc — some repos get it, some don't, and nothing surfaces the gap. Each
kittified repo records the template version it was last upgraded to in
``.kittify/metadata.yaml`` (``spec_kitty.version``); the installed CLI has its
own version. When they diverge, missions run on stale templates against a newer
CLI runtime — the #597 friction (protected-branch refusals, split-authority
traps, merge crashes).

This deterministic helper discovers kittified repos under a root, reads each
recorded version, compares to the expected (installed-CLI) version, and reports
drift. It is **detection only** — it never runs ``spec-kitty upgrade``. The
routine that consumes it is ``docs/runbooks/spec-kitty-per-repo-upgrade.md``.

CLI::

    python3 -m scripts.spec_kitty.check_version_drift [--repos-root DIR]
        [--expected-version VER] [--json]

``--repos-root``       directory whose immediate children are candidate repos
                       (default: the parent of this checkout, i.e. ``~/repos``).
``--expected-version`` the version to compare against (default: parse the
                       installed ``spec-kitty --version``).
``--json``             emit machine-readable JSON (default: a human table).

Exit codes::

    0  no drift — every kittified repo matches the expected version
    1  drift found — at least one repo behind/ahead/unreadable
    2  usage / IO error — no repos-root, or expected version undeterminable

Standard library + PyYAML only. Pure and deterministic given
``(repos_root, expected_version)``: the same filesystem state and the same
expected version always yield the same report.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

#: Location of the version marker inside each kittified repo.
METADATA_REL = Path(".kittify") / "metadata.yaml"

#: A spec-kitty version token, e.g. ``3.2.6`` or ``3.2.0rc18``.
_VERSION_RE = re.compile(r"\b(\d+\.\d+\.\d+(?:rc\d+)?)\b")

#: Per-repo drift status values.
STATUS_CURRENT = "current"
STATUS_DRIFT = "drift"
STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class RepoVersion:
    """The recorded spec-kitty version and drift status of one kittified repo."""

    repo: str
    path: str
    recorded_version: str | None  # None when metadata is missing/unreadable
    status: str  # STATUS_CURRENT | STATUS_DRIFT | STATUS_UNKNOWN


def parse_recorded_version(metadata_path: Path) -> str | None:
    """Return ``spec_kitty.version`` from a ``.kittify/metadata.yaml``, or None.

    Returns None (rather than raising) on any read/parse failure or unexpected
    shape, so a single malformed repo never aborts the fleet scan.
    """
    try:
        data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    spec_kitty = data.get("spec_kitty")
    if isinstance(spec_kitty, dict):
        version = spec_kitty.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    return None


def discover_kittified_repos(repos_root: Path) -> list[Path]:
    """Return the immediate child dirs of ``repos_root`` that are standalone kittified repos.

    A candidate qualifies when it is a non-hidden directory carrying
    ``.kittify/metadata.yaml``. Two look-alikes are excluded so the fleet count
    reflects independent repos only:

    * hidden / scratch dirs (name starts with ``.``) — e.g. a ``.autopilot-wt``
      worktree checkout;
    * linked git worktrees (``.git`` is a *file* pointing at the parent repo, not
      a directory) — a second checkout of an already-counted repo.
    """
    if not repos_root.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(repos_root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not (d / METADATA_REL).is_file():
            continue
        if (d / ".git").is_file():  # a linked worktree, not a standalone repo
            continue
        out.append(d)
    return out


def detect_cli_version() -> str | None:
    """Parse the installed ``spec-kitty --version``; None if unavailable."""
    try:
        completed = subprocess.run(
            ["spec-kitty", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = f"{completed.stdout}\n{completed.stderr}"
    # Prefer an explicit ``... version X`` line (avoids matching a stray token).
    for line in text.splitlines():
        if "version" in line.lower():
            match = _VERSION_RE.search(line)
            if match:
                return match.group(1)
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def build_report(repos_root: Path, expected_version: str) -> list[RepoVersion]:
    """Classify every kittified repo under ``repos_root`` against ``expected_version``."""
    reports: list[RepoVersion] = []
    for repo in discover_kittified_repos(repos_root):
        recorded = parse_recorded_version(repo / METADATA_REL)
        if recorded is None:
            status = STATUS_UNKNOWN
        elif recorded == expected_version:
            status = STATUS_CURRENT
        else:
            status = STATUS_DRIFT
        reports.append(RepoVersion(repo.name, str(repo), recorded, status))
    return reports


def has_drift(reports: list[RepoVersion]) -> bool:
    """True if any repo is not ``current`` (drifted or unreadable)."""
    return any(r.status != STATUS_CURRENT for r in reports)


def _default_repos_root() -> Path:
    """The parent of this checkout — i.e. ``~/repos`` when at ``~/repos/kg-automation``.

    Resolved from this module's location (``scripts/spec_kitty/…``), not the cwd,
    so the default is stable regardless of where the helper is invoked from.
    """
    return Path(__file__).resolve().parents[3]


def _render_human(reports: list[RepoVersion], expected: str) -> str:
    lines = [f"Expected spec-kitty version: {expected}", ""]
    if not reports:
        lines.append("No kittified repos found.")
        return "\n".join(lines)
    width = max(len(r.repo) for r in reports)
    for r in reports:
        mark = {STATUS_CURRENT: "✓", STATUS_DRIFT: "✗", STATUS_UNKNOWN: "?"}[r.status]
        recorded = r.recorded_version or "(unreadable)"
        lines.append(f"  {mark} {r.repo.ljust(width)}  {recorded}  [{r.status}]")
    drifted = [r.repo for r in reports if r.status != STATUS_CURRENT]
    lines.append("")
    if drifted:
        lines.append(f"DRIFT: {len(drifted)}/{len(reports)} repo(s) not at {expected}: {', '.join(drifted)}")
    else:
        lines.append(f"OK: all {len(reports)} kittified repo(s) at {expected}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repos-root",
        type=Path,
        default=None,
        help="Directory whose immediate children are candidate repos (default: parent of this checkout).",
    )
    parser.add_argument(
        "--expected-version",
        default=None,
        help="Version to compare against (default: parse installed `spec-kitty --version`).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    repos_root = (args.repos_root or _default_repos_root()).expanduser()
    if not repos_root.is_dir():
        print(f"error: repos-root is not a directory: {repos_root}", file=sys.stderr)
        return 2

    expected = (args.expected_version.strip() if args.expected_version else None) or detect_cli_version()
    if not expected:
        print(
            "error: could not determine expected version — pass --expected-version "
            "or ensure `spec-kitty --version` is on PATH.",
            file=sys.stderr,
        )
        return 2

    reports = build_report(repos_root, expected)
    drift = has_drift(reports)

    if args.json:
        payload = {
            "expected_version": expected,
            "repos_root": str(repos_root),
            "drift": drift,
            "repo_count": len(reports),
            "drift_count": sum(1 for r in reports if r.status != STATUS_CURRENT),
            "repos": [asdict(r) for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_render_human(reports, expected))

    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
