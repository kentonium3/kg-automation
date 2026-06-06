#!/usr/bin/env python3
"""Privacy boundary lint — block stale `02-Growth/_private` references.

Enforces Felix Constitution privacy boundary at lint time. The constitutional
boundary is `~/second-brain/notes/04-Growth/_private/`. The OLD path
`02-Growth/_private/` was renumbered in mission 026 / #152; any active surface
that still declares the OLD path as the current rule is a stale standing
order that misprotects the wrong directory.

Scope:
  - Walk: scripts/, docs/, ai-agents/, .github/, CLAUDE.md
  - Skip: docs/archive/, docs/research/, kitty-specs/, .git/, node_modules/,
    __pycache__/, *.pyc, .obsidian/

Allowlist (per file):
  - docs/runbooks/vault-path-registry-migration.md — the migration runbook;
    intentionally documents both paths
  - scripts/openclaw/observation/tests/fixtures/*.jsonl — historical test
    fixtures with observation events captured before the renumber

Line-level allowlist (any of these markers in the same line makes the match OK):
  - "renumber" / "renumbered" — migration-history parenthetical
  - "mission 026" / "#152" — explicit migration reference
  - "RENUMBERED" / "MIGRATION" — historical context markers

Exit codes:
  0 — clean (no violations OR all matches are in allowlisted files/contexts)
  1 — at least one violation found

Usage:
  python3 tooling/scripts/validate_privacy_boundary.py
  python3 tooling/scripts/validate_privacy_boundary.py --self-test
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------

OLD_PATH_PATTERN = re.compile(r"02-Growth/_private")

# Walk these top-level paths.
WALK_PATHS = [
    "scripts",
    "docs",
    "ai-agents",
    ".github",
    "tooling",
]
# Plus these specific files at repo root.
ROOT_FILES = ["CLAUDE.md"]

# Skip these path prefixes entirely (historical / out-of-scope content).
SKIP_PREFIXES = [
    "docs/archive/",
    "docs/research/",
    "kitty-specs/",
    ".git/",
    "node_modules/",
    "__pycache__/",
    ".obsidian/",
]

# Files where ALL matches are allowed (per-file allowlist).
ALLOWLIST_FILES = [
    "docs/runbooks/vault-path-registry-migration.md",
    "scripts/openclaw/observation/tests/fixtures/capture-security.jsonl",
    # This validator itself — its own pattern strings would otherwise match.
    "tooling/scripts/validate_privacy_boundary.py",
]

# Files extensions to scan.
SCAN_EXTENSIONS = {".md", ".py", ".yml", ".yaml", ".json", ".toml", ".sh",
                   ".txt", ".tmpl", ".jsonl"}

# A line is OK if it contains any of these context markers (migration history).
LINE_OK_MARKERS = (
    "renumber",
    "renumbered",
    "mission 026",
    "#152",
    "RENUMBERED",
    "MIGRATION HISTORY",
)


# ------------------------------------------------------------------------
# Implementation
# ------------------------------------------------------------------------

def should_skip(path: Path) -> bool:
    """True if the file should be skipped entirely."""
    rel = str(path).replace("\\", "/")
    for prefix in SKIP_PREFIXES:
        if rel.startswith(prefix) or f"/{prefix}" in f"/{rel}":
            return True
    for allowed in ALLOWLIST_FILES:
        if rel == allowed:
            return True
    if path.suffix not in SCAN_EXTENSIONS:
        return True
    return False


def line_has_migration_context(line: str) -> bool:
    """True if the line contains a migration-context marker (allowlisted)."""
    lower = line.lower()
    for marker in LINE_OK_MARKERS:
        if marker.lower() in lower:
            return True
    return False


def scan_repo(repo_root: Path) -> list[tuple[str, int, str]]:
    """Return list of (relative_path, line_number, line_text) violations."""
    violations: list[tuple[str, int, str]] = []
    targets: list[Path] = []
    for name in WALK_PATHS:
        p = repo_root / name
        if p.exists():
            for f in p.rglob("*"):
                if f.is_file():
                    targets.append(f)
    for name in ROOT_FILES:
        p = repo_root / name
        if p.exists() and p.is_file():
            targets.append(p)

    for f in targets:
        rel = f.relative_to(repo_root)
        if should_skip(rel):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(content.splitlines(), start=1):
            if OLD_PATH_PATTERN.search(line):
                if line_has_migration_context(line):
                    continue
                violations.append((str(rel), lineno, line.rstrip()))
    return violations


# ------------------------------------------------------------------------
# Self-test (executable via --self-test)
# ------------------------------------------------------------------------

def self_test() -> int:
    """Build synthetic files in a temp dir and verify validator behavior."""
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "scripts").mkdir()
        (root / "docs" / "archive").mkdir(parents=True)
        (root / "docs" / "runbooks").mkdir(parents=True)

        # Case 1 — stale active reference (should FAIL).
        bad = root / "scripts" / "stale.md"
        bad.write_text(
            "# Privacy boundary\n"
            "NEVER access: ~/second-brain/notes/02-Growth/_private/\n",
            encoding="utf-8",
        )
        # Case 2 — migration-context reference (should PASS).
        ok = root / "scripts" / "migration_note.md"
        ok.write_text(
            "Path renumbered from `02-Growth/_private/` in mission 026 / #152.\n",
            encoding="utf-8",
        )
        # Case 3 — archive (should be skipped entirely).
        archive = root / "docs" / "archive" / "historical.md"
        archive.write_text(
            "Old absolute rule was 02-Growth/_private/\n", encoding="utf-8"
        )
        # Case 4 — file-allowlisted migration runbook (should be skipped).
        migration_rb = root / "docs" / "runbooks" / "vault-path-registry-migration.md"
        migration_rb.write_text(
            "Migration table:\n| 02-Growth | 04-Growth |\n", encoding="utf-8"
        )

        violations = scan_repo(root)
        rels = [v[0] for v in violations]

        if "scripts/stale.md" not in rels:
            failures.append("expected scripts/stale.md to be flagged")
        if "scripts/migration_note.md" in rels:
            failures.append(
                "scripts/migration_note.md should NOT be flagged "
                "(has migration context)"
            )
        if "docs/archive/historical.md" in rels:
            failures.append(
                "docs/archive/historical.md should NOT be flagged (in archive)"
            )
        if "docs/runbooks/vault-path-registry-migration.md" in rels:
            failures.append(
                "vault-path-registry-migration.md should NOT be flagged "
                "(file-allowlisted)"
            )

    if failures:
        for line in failures:
            print(f"SELF-TEST FAIL: {line}", file=sys.stderr)
        return 1
    print("SELF-TEST PASS")
    return 0


# ------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()

    repo_root = Path.cwd()
    violations = scan_repo(repo_root)
    if not violations:
        print("validate_privacy_boundary: OK")
        return 0
    print(
        f"validate_privacy_boundary: {len(violations)} stale "
        f"02-Growth/_private reference(s) found in active surfaces.\n"
        "Active code/docs must declare the current 04-Growth/_private "
        "boundary. Migration-context references (e.g., 'renumbered from … "
        "in mission 026 / #152') are permitted.",
        file=sys.stderr,
    )
    for rel, lineno, line in violations:
        print(f"  {rel}:{lineno}: {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
