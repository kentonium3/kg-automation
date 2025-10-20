#!/usr/bin/env python3
"""
sync_mermaid_views.py

Keeps Markdown view wrappers (*.view.md) in sync with Mermaid sources (*.mmd)
under docs/diagrams/.

Modes:
  --check (default): exit 1 if any wrapper is missing or out-of-sync.
  --write: (re)generate wrappers when missing or out-of-sync.

This script is intentionally self-contained (no external deps).
"""

import sys, argparse, re, os
from pathlib import Path
from datetime import date
from typing import Tuple

DIAGRAMS_DIR = Path("docs/diagrams")

FM_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
FENCE_START = "```mermaid"
FENCE_END = "```"

def title_case_from_basename(name: str) -> str:
    name = re.sub(r"[_-]+", " ", name)
    return " ".join(w.capitalize() for w in name.split())

def build_view_content(src_rel: str, src_text: str, existing_fm: str | None) -> str:
    """
    Construct the .view.md text.
    If existing_fm is provided (YAML block WITHOUT --- lines), preserve it.
    Otherwise build minimal front-matter.
    """
    if existing_fm:
        fm = existing_fm.strip()
    else:
        basename = Path(src_rel).stem
        title = f"{title_case_from_basename(basename)} (Rendered)"
        today = date.today().strftime("%Y-%m-%d")
        fm = (
            "id: " + f"{basename}-view" + "\n"
            "title: " + title + "\n"
            "doc_type: guide\n"
            "level: reference\n"
            "status: approved\n"
            "owners:\n"
            "  - \"@kentonium3\"\n"
            f"last_validated: {today}\n"
            "revision: v1.0\n"
            "audience: agents_and_humans\n"
        )

    body = (
        f"---\n{fm}\n---\n\n"
        f"{FENCE_START}\n"
        f"%% source: {src_rel}\n"
        f"{src_text.rstrip()}\n"
        f"{FENCE_END}\n"
    )
    return body

def split_fm_and_body(text: str) -> Tuple[str | None, str]:
    """
    Returns (fm_without_---, body_without_fm_block)
    """
    m = FM_PATTERN.match(text)
    if not m:
        return None, text
    fm = m.group(1)
    body = text[m.end():]
    return fm, body

def extract_fenced_mermaid(body: str) -> str | None:
    """
    Return content inside the first ```mermaid ... ``` block, or None.
    """
    if FENCE_START not in body:
        return None
    start = body.find(FENCE_START)
    end = body.find(FENCE_END, start + len(FENCE_START))
    if end == -1:
        return None
    inner = body[start + len(FENCE_START):end]
    # Strip a single leading newline if present
    if inner.startswith("\n"):
        inner = inner[1:]
    return inner

def normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").rstrip() + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate wrappers without writing")
    ap.add_argument("--write", action="store_true", help="write wrappers when missing or out-of-sync")
    args = ap.parse_args()

    if not DIAGRAMS_DIR.exists():
        print("[sync] diagrams dir not found:", DIAGRAMS_DIR, file=sys.stderr)
        sys.exit(0)

    mmd_files = sorted(DIAGRAMS_DIR.glob("*.mmd"))
    if not mmd_files:
        print("[sync] no .mmd files found")
        sys.exit(0)

    had_diff = False
    for mmd in mmd_files:
        view = mmd.with_suffix(".view.md")
        src_text = mmd.read_text(encoding="utf-8")
        src_rel = str(mmd).replace("\\", "/")

        if view.exists():
            text = view.read_text(encoding="utf-8")
            existing_fm, body = split_fm_and_body(text)
            fenced = extract_fenced_mermaid(body)
            if fenced is None:
                print(f"[sync] {view} has no mermaid fence; will regenerate.")
                had_diff = True
                if args.write:
                    new_text = build_view_content(src_rel, src_text, existing_fm)
                    view.write_text(new_text, encoding="utf-8")
                continue

            # Compare fenced content after normalizing
            expected_inner = f"%% source: {src_rel}\n{src_text.rstrip()}\n"
            if normalize_newlines(fenced) != normalize_newlines(expected_inner):
                print(f"[sync] {view} content differs from {mmd}; will update.")
                had_diff = True
                if args.write:
                    new_text = build_view_content(src_rel, src_text, existing_fm)
                    view.write_text(new_text, encoding="utf-8")
        else:
            print(f"[sync] missing wrapper for {mmd} -> {view}")
            had_diff = True
            if args.write:
                new_text = build_view_content(src_rel, src_text, None)
                view.write_text(new_text, encoding="utf-8")

    if had_diff and not args.write:
        print("[sync] differences detected. Run with --write to update wrappers.")
        sys.exit(1)

if __name__ == "__main__":
    main()
