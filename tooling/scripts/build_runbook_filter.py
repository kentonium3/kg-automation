#!/usr/bin/env python3
"""Build the runbook-filter block embedded in ``docs/DEVELOPER_PORTAL.md``.

This helper walks ``docs/runbooks/**/*.md``, reads YAML frontmatter from
each file, groups runbooks by ``audience:`` value, and emits a deterministic
markdown block between the marker pair:

    <!-- begin:runbook-filter (generated; do not edit) -->
    ...
    <!-- end:runbook-filter -->

Behavior contract:
    kitty-specs/documentation-developer-portal-01KSJ75K/contracts/build_runbook_filter.md

Modes:
    (default)      Drift check. Exit 0 if the embedded block matches what
                   would be generated, 1 with a unified diff on stdout if
                   they differ. The last line on drift is literally
                   ``run: python tooling/scripts/build_runbook_filter.py --write``.
    --check-only   Explicit alias for default mode.
    --write        Rewrite the block in place; exit 0. If the file is
                   already up to date, print ``up to date`` and exit 0.
    --help         Standard argparse help.

Exit codes:
    0  Clean (or --write succeeded)
    1  Drift detected (default mode only)
    2  Portal file ``docs/DEVELOPER_PORTAL.md`` missing
    3  Marker pair missing or duplicated in portal
    4  Invalid ``audience:`` value or missing ``title:`` in a runbook
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import yaml
except Exception:  # pragma: no cover - exercised manually if PyYAML missing
    print('Missing deps: pip install pyyaml', file=sys.stderr)
    sys.exit(1)


# Mirror of ``ALLOWED_VALUES['audience']`` in
# ``tooling/scripts/validate_docs.py``. The validator is the source of truth
# for the canonical enum; importing it directly is not viable because that
# module executes its full validation pipeline at import time. Keep this
# literal in sync with ``validate_docs.py``.
ALLOWED_AUDIENCE = {'agents', 'humans', 'agents_and_humans'}

AUDIENCE_TO_BUCKET = {
    'agents': 'Agent-executable',
    'agents_and_humans': 'Dual-audience',
    'humans': 'Human-only',
}
UNCLASSIFIED_BUCKET = 'Unclassified'

# Fixed bucket order for emission.
BUCKET_ORDER = (
    'Agent-executable',
    'Dual-audience',
    'Human-only',
    UNCLASSIFIED_BUCKET,
)

BEGIN_MARKER = '<!-- begin:runbook-filter (generated; do not edit) -->'
END_MARKER = '<!-- end:runbook-filter -->'

RUN_HINT = 'run: python tooling/scripts/build_runbook_filter.py --write'

PORTAL_REL = Path('docs') / 'DEVELOPER_PORTAL.md'
RUNBOOKS_REL = Path('docs') / 'runbooks'

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_PORTAL_MISSING = 2
EXIT_MARKER_PROBLEM = 3
EXIT_FRONTMATTER_ERROR = 4


# ---------------------------------------------------------------------------
# Frontmatter parsing (mirrors validate_docs.py strategy)
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> Optional[Dict]:
    """Return the parsed YAML frontmatter dict, or ``None`` if absent.

    Uses the same top-of-file ``---`` block convention as
    ``tooling/scripts/validate_docs.py``. Returns ``None`` when no
    frontmatter block is present so the caller can warn and skip.
    """
    txt = path.read_text(encoding='utf-8', errors='ignore')
    txt = txt.replace('\r\n', '\n').lstrip('﻿ \t\r\n')
    if not txt.startswith('---'):
        return None
    lines = txt.splitlines()
    end = None
    for i in range(1, min(len(lines), 500)):
        if lines[i].strip() == '---':
            end = i
            break
    if end is None:
        return None
    try:
        data = yaml.safe_load('\n'.join(lines[1:end])) or {}
    except Exception:
        return None
    return data if isinstance(data, dict) else {}


def read_runbook_frontmatter(
    root: Path,
) -> Iterable[Tuple[Path, Optional[Dict]]]:
    """Yield ``(path, frontmatter)`` for every ``.md`` file under ``root``.

    ``root`` is expected to be ``<repo>/docs/runbooks``. Files lacking a
    frontmatter block emit a stderr warning and are yielded with ``None``
    so callers can exclude them from buckets. Non-``.md`` files are
    skipped silently.
    """
    if not root.exists():
        return
    for md in sorted(root.rglob('*.md')):
        if not md.is_file():
            continue
        fm = _parse_frontmatter(md)
        if fm is None:
            print(
                f'warning: no frontmatter in {md}; excluded from filter',
                file=sys.stderr,
            )
        yield md, fm


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------

class FrontmatterError(Exception):
    """Raised for invalid/missing required frontmatter fields."""

    def __init__(self, message: str, exit_code: int = EXIT_FRONTMATTER_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


def _relative_to_portal(runbook_path: Path, repo_root: Path) -> str:
    """Return the path from ``docs/DEVELOPER_PORTAL.md`` to ``runbook_path``.

    The portal lives at ``docs/DEVELOPER_PORTAL.md`` and runbooks live under
    ``docs/runbooks/``; the rendered link should therefore be
    ``runbooks/...``.
    """
    rel = runbook_path.resolve().relative_to((repo_root / 'docs').resolve())
    return str(PurePosixPath(*rel.parts))


def assign_buckets(
    entries: Iterable[Tuple[Path, Optional[Dict]]],
    repo_root: Path,
) -> Dict[str, List[Tuple[str, str]]]:
    """Group frontmatter entries into the four bucket lists.

    Returns a dict ``{bucket_name: [(title, relative_path), ...]}``. All
    four bucket keys are always present (possibly empty). Raises
    :class:`FrontmatterError` on invalid ``audience:`` or missing
    ``title:`` fields.
    """
    buckets: Dict[str, List[Tuple[str, str]]] = {b: [] for b in BUCKET_ORDER}

    for path, fm in entries:
        if fm is None:
            continue
        title = fm.get('title')
        if not title or not isinstance(title, str):
            raise FrontmatterError(f"error: missing title in {path}")

        rel_path = _relative_to_portal(path, repo_root)

        audience = fm.get('audience')
        if audience is None:
            buckets[UNCLASSIFIED_BUCKET].append((title, rel_path))
            continue
        if audience not in ALLOWED_AUDIENCE:
            raise FrontmatterError(
                f"error: invalid audience '{audience}' in {path}"
            )
        bucket = AUDIENCE_TO_BUCKET[audience]
        buckets[bucket].append((title, rel_path))

    return buckets


# ---------------------------------------------------------------------------
# Block emission
# ---------------------------------------------------------------------------

def build_block(buckets: Dict[str, List[Tuple[str, str]]]) -> str:
    """Emit the marker-wrapped block as a single string.

    Output shape (one blank line between buckets; markers separated from
    inner content by blank lines on the outside as well):

        <!-- begin:runbook-filter (generated; do not edit) -->

        ### Agent-executable
        - [title](runbooks/foo.md)

        ### Dual-audience
        - _(none)_

        ...

        <!-- end:runbook-filter -->
    """
    lines: List[str] = [BEGIN_MARKER, '']
    for idx, bucket in enumerate(BUCKET_ORDER):
        lines.append(f'### {bucket}')
        entries = sorted(buckets.get(bucket, []), key=lambda e: e[0].lower())
        if not entries:
            lines.append('- _(none)_')
        else:
            for title, rel_path in entries:
                # Repo convention (matches docs/INDEX.md and the markdownlint
                # auto-format applied across docs/**): wrap relative URLs as
                # `<./path>`. Plain `path` form gets rewritten by the linter
                # post-write, which previously caused the script's output to
                # disagree with the on-disk portal and tripped the drift check.
                link = f'<./{rel_path}>'
                if bucket == UNCLASSIFIED_BUCKET:
                    lines.append(
                        f'- [{title}]({link}) — missing `audience:` frontmatter'
                    )
                else:
                    lines.append(f'- [{title}]({link})')
        if idx < len(BUCKET_ORDER) - 1:
            lines.append('')
    lines.append('')
    lines.append(END_MARKER)
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Portal I/O and marker location
# ---------------------------------------------------------------------------

def _locate_markers(portal_text: str) -> Tuple[int, int]:
    """Return ``(begin_index, end_index)`` of the marker pair in ``portal_text``.

    Indices are character offsets such that ``portal_text[begin:end]``
    spans from the start of the begin marker line through the end of the
    end marker line (excluding the trailing newline of the end marker).

    Raises :class:`FrontmatterError` (exit code 3) if the marker pair is
    missing or duplicated.
    """
    begin_count = portal_text.count(BEGIN_MARKER)
    end_count = portal_text.count(END_MARKER)
    if begin_count == 0 or end_count == 0:
        raise FrontmatterError(
            'error: marker pair not found in portal',
            exit_code=EXIT_MARKER_PROBLEM,
        )
    if begin_count > 1 or end_count > 1:
        raise FrontmatterError(
            'error: duplicate marker pair in portal',
            exit_code=EXIT_MARKER_PROBLEM,
        )

    begin_idx = portal_text.index(BEGIN_MARKER)
    end_idx = portal_text.index(END_MARKER) + len(END_MARKER)
    if end_idx <= begin_idx:
        raise FrontmatterError(
            'error: marker pair not found in portal',
            exit_code=EXIT_MARKER_PROBLEM,
        )
    return begin_idx, end_idx


def _extract_current_block(portal_text: str) -> str:
    begin_idx, end_idx = _locate_markers(portal_text)
    block = portal_text[begin_idx:end_idx]
    # Normalize so comparison is line-ending-agnostic and trailing-newline-stable.
    block = block.replace('\r\n', '\n')
    if not block.endswith('\n'):
        block += '\n'
    return block


def _resolve_repo_root(start: Optional[Path] = None) -> Path:
    """Resolve the repository root using the same strategy as validate_docs.py.

    The script walks upward from its own location until it finds a
    directory containing ``docs/``. Callers can override ``start`` for
    tests.
    """
    if start is not None:
        return start
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / 'docs').is_dir():
            return parent
    # Fallback: current working directory.
    return Path.cwd()


# ---------------------------------------------------------------------------
# Drift check and write modes
# ---------------------------------------------------------------------------

def _load_expected_block(repo_root: Path) -> str:
    entries = list(read_runbook_frontmatter(repo_root / RUNBOOKS_REL))
    buckets = assign_buckets(entries, repo_root)
    return build_block(buckets)


def check_drift(repo_root: Path) -> int:
    """Default-mode drift check. Returns exit code."""
    portal_path = repo_root / PORTAL_REL
    if not portal_path.exists():
        print(
            f'error: {PORTAL_REL.as_posix()} not found',
            file=sys.stderr,
        )
        return EXIT_PORTAL_MISSING

    portal_text = portal_path.read_text(encoding='utf-8').replace('\r\n', '\n')
    try:
        current = _extract_current_block(portal_text)
        expected = _load_expected_block(repo_root)
    except FrontmatterError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    if current == expected:
        return EXIT_OK

    diff_lines = list(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile='portal (current)',
            tofile='portal (expected)',
        )
    )
    sys.stdout.write(''.join(diff_lines))
    if diff_lines and not diff_lines[-1].endswith('\n'):
        sys.stdout.write('\n')
    sys.stdout.write(RUN_HINT + '\n')
    return EXIT_DRIFT


def write_block(repo_root: Path) -> int:
    """``--write`` mode. Returns exit code.

    T004 contract: preserve every line *outside* the marker pair
    byte-for-byte. We therefore keep the original portal text (including
    any CRLF line endings) for splicing the prefix and suffix, and only
    normalize line endings on the marker-bounded substring for the
    drift comparison. The replacement block is generated by this script
    and uses LF endings deterministically — that's the only content
    inside the markers, so external bytes are never touched unless they
    were already inside the marker span.
    """
    portal_path = repo_root / PORTAL_REL
    if not portal_path.exists():
        print(
            f'error: {PORTAL_REL.as_posix()} not found',
            file=sys.stderr,
        )
        return EXIT_PORTAL_MISSING

    # Preserve the original portal text (do NOT normalize line endings
    # globally) so that bytes outside the marker pair are written back
    # exactly as they were read. We pass ``newline=''`` to disable
    # Python's universal-newlines translation on both read and write,
    # which would otherwise silently rewrite CRLF→LF.
    with open(portal_path, 'r', encoding='utf-8', newline='') as fh:
        portal_text = fh.read()
    try:
        begin_idx, end_idx = _locate_markers(portal_text)
        expected = _load_expected_block(repo_root)
    except FrontmatterError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    current = portal_text[begin_idx:end_idx]
    # Normalize only the substring used for the up-to-date comparison.
    current_normalized = current.replace('\r\n', '\n')
    if not current_normalized.endswith('\n'):
        current_normalized = current_normalized + '\n'
    if current_normalized == expected:
        print('up to date')
        return EXIT_OK

    # Splice: prefix (unchanged bytes) + new block (without its trailing
    # newline, since the original portal already carries whatever
    # newline convention follows END_MARKER) + suffix (unchanged bytes).
    # This guarantees that every byte outside the marker pair is
    # written back exactly as it was read, including CRLF line endings
    # on the line immediately after END_MARKER.
    suffix = portal_text[end_idx:]
    block_to_write = expected
    if block_to_write.endswith('\n'):
        block_to_write = block_to_write[:-1]
    new_text = portal_text[:begin_idx] + block_to_write + suffix
    with open(portal_path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(new_text)
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='build_runbook_filter.py',
        description=(
            'Drift-check or regenerate the runbook-filter block in '
            'docs/DEVELOPER_PORTAL.md.'
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--write',
        action='store_true',
        help='Rewrite the block in place to match runbook frontmatter.',
    )
    mode.add_argument(
        '--check-only',
        action='store_true',
        help='Explicit alias for the default drift-check behavior.',
    )
    return parser


def main(argv: Optional[List[str]] = None, repo_root: Optional[Path] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = _resolve_repo_root(repo_root)
    if args.write:
        return write_block(root)
    return check_drift(root)


if __name__ == '__main__':  # pragma: no cover - exercised via subprocess + tests
    sys.exit(main())
