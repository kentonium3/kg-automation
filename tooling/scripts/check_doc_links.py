#!/usr/bin/env python3
"""Check that relative links in repo-owned markdown actually resolve.

Why this exists (#927, #944)
----------------------------
Two batches of broken links were found by one-off manual sweeps during unrelated
missions, months apart. Eleven of the fourteen in the second batch were the *same*
mistake: a relative path one or two directory levels too shallow — the depth from
``docs/design/architecture/`` back to ``docs/runbooks/`` is easy to get wrong, and
the error is invisible on GitHub's rendered view until somebody clicks it. Two of
them pointed at the change-control governance docs, which is exactly what a reader
following a Tier-1/Tier-2 procedure would click.

Nothing checked links, so the class recurred silently. This closes that.

Two parsing details that are NOT optional
-----------------------------------------
A naive checker produces ~73% false positives on this repo. Both causes are
addressed here, and removing either will bring the noise back:

1. **Code must be stripped first.** ``docs/runbooks/doc-maintenance.md`` is a
   document *about writing documentation*, so it legitimately contains
   ``[text](path)`` and ``./bar.md`` as teaching examples. Counting those as
   broken links is a measurement artifact, not a finding.

2. **Both link forms must be handled.** This repo widely uses the angle-bracket
   form ``[text](<path>)`` alongside plain ``[text](path)``. A pattern that only
   handles the plain form captures a bare ``<`` as the target and reports every
   angle-bracket link as broken.

What is deliberately NOT checked
--------------------------------
* ``docs/archive/`` — frozen historical artifacts; their links describe the world
  as it was, and "fixing" them would falsify the record.
* ``kitty-specs/`` — spec-kitty-owned mission artifacts, not repo documentation.
* ``**/skills/**`` — vendored spec-kitty skill files reference spec-kitty's *own*
  docs (``docs/api/bulk-edit-gate.md`` and similar), which do not exist in a
  consumer repo and never will. They are installed artifacts, not our prose.
* URLs, anchors, and ``mailto:``/``tel:`` — this checks the filesystem, not the
  network, so it stays fast and offline.

Usage
-----
    python3 tooling/scripts/check_doc_links.py [--json]

Exits non-zero when a repo-owned relative link does not resolve.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Both markdown link forms, with an optional "title" and optional #anchor.
# Group 1 = <angle-bracket> target, group 2 = bare target.
_LINK = re.compile(r'\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+"[^"]*")?\s*\)')

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")

_SKIP_DIRS = {".git", ".worktrees", "node_modules", ".venv", "__pycache__"}
_SKIP_PATH_PARTS = ("kitty-specs",)
_SKIP_SUBSTRINGS = ("docs/archive/", "/skills/")

_NON_FILE_SCHEMES = ("http://", "https://", "mailto:", "tel:", "#")


def is_repo_owned(path: Path) -> bool:
    """True when this markdown file is our documentation, not a vendored artifact."""
    if any(part in _SKIP_DIRS for part in path.parts):
        return False
    if any(part in _SKIP_PATH_PARTS for part in path.parts):
        return False
    as_posix = path.as_posix()
    return not any(s in as_posix for s in _SKIP_SUBSTRINGS)


def strip_code(text: str) -> str:
    """Remove fenced and inline code so teaching examples are not read as links."""
    return _INLINE.sub("", _FENCED.sub("", text))


def broken_links(root: Path) -> list[tuple[str, str]]:
    """Return (file, target) for every repo-owned relative link that does not resolve."""
    found: list[tuple[str, str]] = []
    for md in sorted(root.rglob("*.md")):
        rel = md.relative_to(root) if md.is_absolute() else md
        if not is_repo_owned(rel):
            continue
        try:
            text = strip_code(md.read_text(errors="ignore"))
        except OSError:
            continue
        for match in _LINK.finditer(text):
            target = (match.group(1) or match.group(2) or "").split("#")[0].strip()
            if not target or target.startswith(_NON_FILE_SCHEMES):
                continue
            if not (md.parent / target).exists():
                found.append((rel.as_posix(), target))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    found = broken_links(root)

    if args.json:
        print(json.dumps({"broken": [{"file": f, "target": t} for f, t in found]}, indent=2))
    elif found:
        print(f"check_doc_links: {len(found)} broken relative link(s)", file=sys.stderr)
        for file, target in found:
            print(f"  {file}\n      -> {target}", file=sys.stderr)
        print(
            "\nA target one or two directory levels off is the usual cause "
            "(see the module docstring).",
            file=sys.stderr,
        )
    else:
        print("check_doc_links: OK (0 broken relative links)")

    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
