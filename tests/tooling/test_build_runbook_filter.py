"""Tests for ``tooling/scripts/build_runbook_filter.py``.

These tests synthesize a fake repo layout under ``tmp_path`` and exercise
every row of ``contracts/build_runbook_filter.md``. The live
``docs/runbooks/`` tree is intentionally never read.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# Load the script as a module without installing it.
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / 'tooling'
    / 'scripts'
    / 'build_runbook_filter.py'
)
_spec = importlib.util.spec_from_file_location('build_runbook_filter', _SCRIPT_PATH)
brf = importlib.util.module_from_spec(_spec)
sys.modules['build_runbook_filter'] = brf
assert _spec.loader is not None
_spec.loader.exec_module(brf)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

PORTAL_TEMPLATE = dedent(
    """\
    ---
    title: Developer Portal
    doc_type: index
    status: draft
    ---

    # Developer Portal

    Some preamble.

    {block}

    Closing text.
    """
)


def _runbook(title: str, audience: str | None = None, body: str = '') -> str:
    fm_lines = ['---', 'doc_type: runbook', 'status: draft']
    if title is not None:
        fm_lines.append(f'title: {title}')
    if audience is not None:
        fm_lines.append(f'audience: {audience}')
    fm_lines.append('---')
    return '\n'.join(fm_lines) + '\n\n' + body + '\n'


def _write_runbook(root: Path, name: str, **kwargs) -> Path:
    path = root / 'docs' / 'runbooks' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_runbook(**kwargs), encoding='utf-8')
    return path


def _make_portal(root: Path, block: str) -> Path:
    portal = root / 'docs' / 'DEVELOPER_PORTAL.md'
    portal.parent.mkdir(parents=True, exist_ok=True)
    portal.write_text(PORTAL_TEMPLATE.format(block=block), encoding='utf-8')
    return portal


def _empty_block() -> str:
    """The marker-bounded block as build_block emits it for no entries."""
    return brf.build_block({b: [] for b in brf.BUCKET_ORDER})


def _setup_repo(tmp_path: Path) -> Path:
    (tmp_path / 'docs' / 'runbooks').mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# T006 — Happy-path tests
# ---------------------------------------------------------------------------


def test_happy_drift_check_clean_portal(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    _write_runbook(repo, 'a.md', title='Alpha', audience='agents')
    _write_runbook(repo, 'b.md', title='Bravo', audience='humans')
    _write_runbook(repo, 'c.md', title='Charlie', audience='agents_and_humans')

    expected = brf._load_expected_block(repo)
    _make_portal(repo, expected.rstrip('\n'))

    rc = brf.check_drift(repo)
    captured = capsys.readouterr()

    assert rc == brf.EXIT_OK
    assert captured.out == ''
    assert captured.err == ''


def test_happy_drift_check_stale_block_emits_diff_and_hint(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    _write_runbook(repo, 'a.md', title='Alpha', audience='agents')
    _write_runbook(repo, 'b.md', title='Bravo', audience='humans')

    # Portal seeded with a stale empty block.
    _make_portal(repo, _empty_block().rstrip('\n'))

    rc = brf.check_drift(repo)
    captured = capsys.readouterr()

    assert rc == brf.EXIT_DRIFT
    assert 'Alpha' in captured.out
    last_line = captured.out.rstrip('\n').splitlines()[-1]
    assert last_line == brf.RUN_HINT


def test_happy_write_regenerates_stale_block(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    _write_runbook(repo, 'a.md', title='Alpha', audience='agents')
    _write_runbook(repo, 'b.md', title='Bravo', audience='humans')
    portal = _make_portal(repo, _empty_block().rstrip('\n'))

    rc = brf.write_block(repo)
    assert rc == brf.EXIT_OK

    new_text = portal.read_text(encoding='utf-8')
    expected = brf._load_expected_block(repo)
    assert expected in new_text
    # Surrounding content preserved.
    assert '# Developer Portal' in new_text
    assert 'Closing text.' in new_text

    # Idempotency check: second --write reports up to date.
    rc2 = brf.write_block(repo)
    captured = capsys.readouterr()
    assert rc2 == brf.EXIT_OK
    assert 'up to date' in captured.out


# ---------------------------------------------------------------------------
# T007 — Bucket / sort / empty-bucket tests
# ---------------------------------------------------------------------------


def test_bucket_order_is_fixed_regardless_of_discovery_order(tmp_path):
    repo = _setup_repo(tmp_path)
    # Write in a non-standard order: humans first, then agents.
    _write_runbook(repo, 'z-human.md', title='Z Human', audience='humans')
    _write_runbook(repo, 'a-agent.md', title='A Agent', audience='agents')
    _write_runbook(repo, 'm-dual.md', title='M Dual', audience='agents_and_humans')

    block = brf._load_expected_block(repo)
    pos_agent = block.index('### Agent-executable')
    pos_dual = block.index('### Dual-audience')
    pos_human = block.index('### Human-only')
    pos_uncl = block.index('### Unclassified')
    assert pos_agent < pos_dual < pos_human < pos_uncl


def test_within_bucket_alphabetization_is_case_insensitive(tmp_path):
    repo = _setup_repo(tmp_path)
    _write_runbook(repo, 'apple.md', title='apple', audience='agents')
    _write_runbook(repo, 'banana.md', title='Banana', audience='agents')
    _write_runbook(repo, 'cherry.md', title='cherry', audience='agents')

    block = brf._load_expected_block(repo)
    # Find the order in which titles appear in the block.
    idx_a = block.index('[apple]')
    idx_b = block.index('[Banana]')
    idx_c = block.index('[cherry]')
    assert idx_a < idx_b < idx_c


def test_missing_audience_lands_in_unclassified_with_suffix(tmp_path):
    repo = _setup_repo(tmp_path)
    _write_runbook(repo, 'lost.md', title='Lost Runbook')

    block = brf._load_expected_block(repo)
    # Unclassified entry should appear with the suffix.
    assert (
        '- [Lost Runbook](<./runbooks/lost.md>) — missing `audience:` frontmatter'
        in block
    )


def test_empty_bucket_renders_with_none_placeholder(tmp_path):
    repo = _setup_repo(tmp_path)
    # Only humans; the other three buckets are empty.
    _write_runbook(repo, 'h.md', title='Human Doc', audience='humans')

    block = brf._load_expected_block(repo)
    # The Agent-executable and Dual-audience and Unclassified buckets are
    # empty and must show the placeholder.
    for header in ('Agent-executable', 'Dual-audience', 'Unclassified'):
        section_start = block.index(f'### {header}')
        # Next header (or end-marker) caps the section.
        section_tail = block[section_start:]
        next_hdr_idx = section_tail.find('\n### ', 1)
        end_marker_idx = section_tail.find(brf.END_MARKER)
        cap = min(
            i for i in (next_hdr_idx, end_marker_idx) if i != -1
        )
        section_body = section_tail[:cap]
        assert '- _(none)_' in section_body, (
            f'expected placeholder in empty bucket {header!r}; got: {section_body!r}'
        )


def test_relative_paths_handle_nested_runbooks(tmp_path):
    repo = _setup_repo(tmp_path)
    _write_runbook(
        repo,
        'governance/pre-flight-checklist.md',
        title='Pre-flight Checklist',
        audience='humans',
    )
    block = brf._load_expected_block(repo)
    assert '(<./runbooks/governance/pre-flight-checklist.md>)' in block


# ---------------------------------------------------------------------------
# T008 — Error-case tests
# ---------------------------------------------------------------------------


def test_error_portal_missing_exits_2(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    # No portal created.
    rc = brf.check_drift(repo)
    captured = capsys.readouterr()
    assert rc == brf.EXIT_PORTAL_MISSING
    assert 'not found' in captured.err
    assert 'docs/DEVELOPER_PORTAL.md' in captured.err


def test_error_marker_pair_missing_exits_3(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    portal = repo / 'docs' / 'DEVELOPER_PORTAL.md'
    portal.parent.mkdir(parents=True, exist_ok=True)
    portal.write_text('# Portal with no markers\n', encoding='utf-8')

    rc = brf.check_drift(repo)
    captured = capsys.readouterr()
    assert rc == brf.EXIT_MARKER_PROBLEM
    assert 'marker pair not found' in captured.err


def test_error_duplicate_marker_pair_exits_3(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    block = _empty_block().rstrip('\n')
    portal_text = PORTAL_TEMPLATE.format(block=block) + '\n' + block + '\n'
    portal = repo / 'docs' / 'DEVELOPER_PORTAL.md'
    portal.parent.mkdir(parents=True, exist_ok=True)
    portal.write_text(portal_text, encoding='utf-8')

    rc = brf.check_drift(repo)
    captured = capsys.readouterr()
    assert rc == brf.EXIT_MARKER_PROBLEM
    assert 'duplicate marker pair' in captured.err


def test_error_invalid_audience_value_exits_4(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    _write_runbook(repo, 'bad.md', title='Bad', audience='bogus')
    _make_portal(repo, _empty_block().rstrip('\n'))

    rc = brf.check_drift(repo)
    captured = capsys.readouterr()
    assert rc == brf.EXIT_FRONTMATTER_ERROR
    assert "invalid audience 'bogus'" in captured.err
    assert 'bad.md' in captured.err


def test_error_missing_title_exits_4(tmp_path, capsys):
    repo = _setup_repo(tmp_path)
    # title=None intentionally produces frontmatter without a title key.
    _write_runbook(repo, 'untitled.md', title=None, audience='agents')
    _make_portal(repo, _empty_block().rstrip('\n'))

    rc = brf.check_drift(repo)
    captured = capsys.readouterr()
    assert rc == brf.EXIT_FRONTMATTER_ERROR
    assert 'missing title' in captured.err
    assert 'untitled.md' in captured.err


# ---------------------------------------------------------------------------
# Cycle 1 regression — T004 byte preservation outside the marker pair
# ---------------------------------------------------------------------------


def test_write_preserves_crlf_bytes_outside_marker_pair(tmp_path):
    """``--write`` must not rewrite line endings outside the marker pair.

    Regression for cycle-1 review finding: ``write_block`` previously
    normalized CRLF→LF on the entire portal file before writing,
    violating T004 (preserve every line outside the markers
    byte-for-byte).
    """
    repo = _setup_repo(tmp_path)
    _write_runbook(repo, 'a.md', title='Alpha', audience='agents')

    # Synthesize a portal with explicit CRLF line endings in the
    # preamble and suffix and a stale (empty) marker block. The block
    # itself uses LF inside the markers, mirroring how build_block
    # emits its content.
    stale_block = _empty_block().rstrip('\n')
    preamble = (
        '---\r\n'
        'title: Developer Portal\r\n'
        'doc_type: index\r\n'
        'status: draft\r\n'
        '---\r\n'
        '\r\n'
        '# Developer Portal\r\n'
        '\r\n'
        'Some preamble line one.\r\n'
        'Some preamble line two.\r\n'
        '\r\n'
    )
    suffix = (
        '\r\n'
        'Closing text one.\r\n'
        'Closing text two.\r\n'
    )
    portal_text = preamble + stale_block + suffix
    portal_path = repo / 'docs' / 'DEVELOPER_PORTAL.md'
    portal_path.parent.mkdir(parents=True, exist_ok=True)
    # Write as bytes to guarantee CRLF is not touched by universal
    # newlines translation.
    portal_path.write_bytes(portal_text.encode('utf-8'))

    rc = brf.write_block(repo)
    assert rc == brf.EXIT_OK

    new_bytes = portal_path.read_bytes()
    expected_block_bytes = brf._load_expected_block(repo).encode('utf-8')

    # 1) Bytes BEFORE the begin marker must be byte-identical to the
    #    original preamble (CRLF preserved).
    begin_marker_bytes = brf.BEGIN_MARKER.encode('utf-8')
    begin_idx = new_bytes.index(begin_marker_bytes)
    assert new_bytes[:begin_idx] == preamble.encode('utf-8'), (
        'preamble bytes outside the marker pair were modified'
    )

    # 2) The marker-bounded region must match the freshly generated
    #    block exactly (sans the block's own trailing newline, which
    #    belongs to the original portal layout outside the markers).
    end_marker_bytes = brf.END_MARKER.encode('utf-8')
    end_idx = new_bytes.index(end_marker_bytes) + len(end_marker_bytes)
    assert new_bytes[begin_idx:end_idx] == expected_block_bytes.rstrip(b'\n'), (
        'marker-bounded region does not match the expected block'
    )

    # 3) Bytes AFTER the end marker must be byte-identical to the
    #    original suffix (CRLF preserved on every line including the
    #    line terminator immediately following END_MARKER).
    actual_suffix = new_bytes[end_idx:]
    expected_suffix_bytes = suffix.encode('utf-8')
    assert actual_suffix == expected_suffix_bytes, (
        'suffix bytes outside the marker pair were modified; '
        f'expected {expected_suffix_bytes!r} got {actual_suffix!r}'
    )
