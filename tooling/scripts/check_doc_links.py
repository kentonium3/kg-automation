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
import subprocess
import sys
from pathlib import Path

# Both markdown link forms, with an optional "title" and optional #anchor.
# Group 1 = <angle-bracket> target, group 2 = bare target.
_LINK = re.compile(r'\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+"[^"]*")?\s*\)')

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")

# Scratch that is not repo content at all. Only consulted by walk_markdown_files();
# repo_markdown_files() gets this answer from git instead (#959), which is the
# single source of truth and does not drift the way this list did.
_SCRATCH_DIRS = {".git", ".worktrees", "node_modules", ".venv", "__pycache__"}

# Ours, tracked, and deliberately not checked. Git cannot answer this one -- these
# are committed files -- so the policy lives here and applies on BOTH enumeration
# paths. Each entry is justified in the module docstring above.
_EXCLUDED_PATH_PARTS = ("kitty-specs",)
_EXCLUDED_SUBSTRINGS = ("docs/archive/", "/skills/")

_NON_FILE_SCHEMES = ("http://", "https://", "mailto:", "tel:", "#")


def is_scratch(path: Path) -> bool:
    """True for tool scratch that was never repo content.

    A small hand-maintained list, and deliberately not a substitute for
    .gitignore -- it names none of the trees that caused #959. It survives only
    to walk a directory that is NOT a git work tree (the test fixtures), where
    there is no git to ask. Production enumeration goes through
    repo_markdown_files(), which never calls this.
    """
    return any(part in _SCRATCH_DIRS for part in path.parts)


def is_excluded_content(path: Path) -> bool:
    """True for repo-owned markdown we deliberately do not check."""
    if any(part in _EXCLUDED_PATH_PARTS for part in path.parts):
        return True
    return any(s in path.as_posix() for s in _EXCLUDED_SUBSTRINGS)


def repo_markdown_files(root: Path) -> list[Path]:
    """Markdown the repository owns, as git defines it, root-relative.

    `git ls-files --cached` -- the index -- rather than a tree walk, because the
    walk had to be told what to ignore by a hand-maintained name list, and that
    list drifted: it named neither `.codex-tmp-home/` (39 findings) nor
    `.kittify/` (13), so a scan on a developer machine reported 52 broken links
    that CI could not see. The question "is this repo content?" already has an
    authoritative answer in .gitignore; asking git removes the second, drifting
    copy of it.

    Deliberately NOT `--others --exclude-standard`. `--exclude-standard` also
    consults `.git/info/exclude` and the user's global `core.excludesFile` --
    per-clone state that is never committed (this clone has 11 such entries) --
    so including untracked files would reintroduce the per-machine variance this
    function exists to remove. That reason stands on its own; an earlier draft
    also cited "measured, --others adds zero files", which was measured on a
    clean tree and so could not have come out any other way.

    The trade this makes, stated because nothing else names it: the gate now
    checks the INDEX, so a markdown file written but not yet `git add`-ed is not
    scanned. A broken link in a brand-new doc surfaces once it is staged rather
    than the moment it is saved.

    Raises RuntimeError if git cannot answer. It must not fall back to walking --
    that silently restores the 52 phantom findings -- and must not return [],
    which would make the caller unable to tell "no broken links" from "could not
    enumerate".
    """
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--cached", "-z", "--", "*.md"],
            cwd=root, capture_output=True, check=False,
        )
    except OSError as exc:  # git absent
        raise RuntimeError(f"cannot enumerate repo markdown in {root}: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed in {root}: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
    if not names:
        # `git ls-files` exits 0 with empty stdout inside a work tree whose index
        # holds no match -- so a bare returncode check would let the gate report
        # "verified clean" on a repo it never actually read. This repo can never
        # legitimately have zero tracked markdown, so treat it as a failed
        # enumeration rather than a clean result (Engineering Principle 14).
        raise RuntimeError(
            f"git ls-files returned no markdown in {root} -- refusing to report "
            "a clean scan for a repository that could not be enumerated"
        )
    # The index can name a file deleted from the working tree. It has no content
    # to scan, so it is skipped here explicitly rather than being swallowed by the
    # OSError handler in broken_links().
    return [Path(n) for n in names if (root / n).is_file() and not is_excluded_content(Path(n))]


def walk_markdown_files(root: Path) -> list[Path]:
    """Markdown under a plain directory, root-relative.

    For directories that are not git work trees -- the test fixtures. Production
    uses repo_markdown_files().
    """
    out = []
    for md in sorted(root.rglob("*.md")):
        rel = md.relative_to(root) if md.is_absolute() else md
        if is_scratch(rel) or is_excluded_content(rel):
            continue
        out.append(rel)
    return out


def strip_code(text: str) -> str:
    """Remove fenced and inline code so teaching examples are not read as links."""
    return _INLINE.sub("", _FENCED.sub("", text))


def broken_links(root: Path, files: list[Path]) -> list[tuple[str, str]]:
    """Return (file, target) for every relative link in `files` that does not resolve.

    Checks exactly what it is handed. Enumeration is the caller's decision --
    repo_markdown_files() for the repository, walk_markdown_files() for a plain
    directory -- so the mode is visible at the call site rather than inferred from
    whether `root` happens to sit inside a git work tree. An inferred mode would
    make production and the fixtures take different paths through this function,
    and would flip with $TMPDIR.

    `files` are root-relative; they are joined to `root` here, since a bare
    relative path would otherwise resolve against the process cwd.
    """
    found: list[tuple[str, str]] = []
    for rel in files:
        md = root / rel
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
    try:
        found = broken_links(root, repo_markdown_files(root))
    except RuntimeError as exc:
        # Exit 2, not 1: "could not enumerate" must not look like "found broken
        # links" to a caller reading only the exit code.
        print(f"check_doc_links: cannot enumerate -- {exc}", file=sys.stderr)
        return 2

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
