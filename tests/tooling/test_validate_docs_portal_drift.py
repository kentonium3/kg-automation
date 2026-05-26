"""Smoke tests for the portal drift check integrated into ``validate_docs.py``.

These tests synthesize a minimal repo layout under ``tmp_path`` and run
``validate_docs.py`` as a subprocess with ``cwd=tmp_path``. The live
``docs/runbooks/`` tree is never read.

Three scenarios are covered:

* T012-1 — fresh portal block: validate_docs exits 0
* T012-2 — tampered portal block: validate_docs exits non-zero and the output
  contains the run-hint line
* T012-3 — portal file absent: validate_docs exits 0 (drift check is gated)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# Resolve script paths from the live repo. The tests do not invoke the live
# scripts against the live tree; they ``cwd`` into ``tmp_path`` so the
# scripts walk the synthetic tree instead.
REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATE_DOCS_SRC = REPO_ROOT / 'tooling' / 'scripts' / 'validate_docs.py'
BUILD_FILTER_SRC = REPO_ROOT / 'tooling' / 'scripts' / 'build_runbook_filter.py'

RUN_HINT = 'run: python tooling/scripts/build_runbook_filter.py --write'


def _seed_repo(tmp_path: Path, *, with_portal: bool, with_runbooks: bool = True) -> Path:
    """Build a minimal repo layout under ``tmp_path``.

    Always includes a copy of ``tooling/scripts/`` so ``validate_docs.py`` is
    runnable. When ``with_portal`` is True, writes a portal containing the
    marker pair and, by default, a single runbook so the filter has a
    deterministic expected block.
    """
    # tooling/scripts copy — the drift check shells out to build_runbook_filter.
    scripts_dir = tmp_path / 'tooling' / 'scripts'
    scripts_dir.mkdir(parents=True)
    shutil.copy2(VALIDATE_DOCS_SRC, scripts_dir / 'validate_docs.py')
    shutil.copy2(BUILD_FILTER_SRC, scripts_dir / 'build_runbook_filter.py')

    docs = tmp_path / 'docs'
    runbooks = docs / 'runbooks'
    if with_runbooks:
        runbooks.mkdir(parents=True)
        # Single deterministic runbook so we can synthesize a matching block.
        (runbooks / 'alpha.md').write_text(
            dedent(
                """\
                ---
                title: Alpha Runbook
                doc_type: runbook
                status: draft
                audience: agents
                ---

                # Alpha Runbook
                """
            ),
            encoding='utf-8',
        )

    if with_portal:
        docs.mkdir(parents=True, exist_ok=True)
        # Use build_runbook_filter --write to populate the marker block from
        # the synthetic runbook(s). That guarantees Test 1 starts in-sync.
        portal = docs / 'DEVELOPER_PORTAL.md'
        portal.write_text(
            dedent(
                """\
                ---
                title: Test Portal
                doc_type: index
                status: draft
                ---

                # Test Portal

                <!-- begin:runbook-filter (generated; do not edit) -->
                <!-- end:runbook-filter -->
                """
            ),
            encoding='utf-8',
        )
        # Populate the block so it is fresh.
        rc = subprocess.run(
            [sys.executable, 'tooling/scripts/build_runbook_filter.py', '--write'],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert rc.returncode == 0, (
            f'build_runbook_filter --write failed during fixture setup: '
            f'stdout={rc.stdout!r} stderr={rc.stderr!r}'
        )

    return tmp_path


def _run_validate(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, 'tooling/scripts/validate_docs.py'],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Test 1 — fresh portal block: validate_docs.py exits 0
# ---------------------------------------------------------------------------


def test_portal_block_in_sync_passes(tmp_path):
    repo = _seed_repo(tmp_path, with_portal=True)
    result = _run_validate(repo)
    assert result.returncode == 0, (
        f'expected exit 0, got {result.returncode}; '
        f'stdout={result.stdout!r} stderr={result.stderr!r}'
    )
    # The portal-drift error message must NOT appear.
    assert 'runbook-filter block is stale' not in result.stdout


# ---------------------------------------------------------------------------
# Test 2 — tampered portal block: validate_docs.py exits non-zero with hint
# ---------------------------------------------------------------------------


def test_portal_block_tampered_fails_with_run_hint(tmp_path):
    repo = _seed_repo(tmp_path, with_portal=True)
    portal = repo / 'docs' / 'DEVELOPER_PORTAL.md'

    # Tamper: replace the inner block with the empty marker pair so the
    # generated and embedded blocks differ.
    text = portal.read_text(encoding='utf-8')
    begin = '<!-- begin:runbook-filter (generated; do not edit) -->'
    end = '<!-- end:runbook-filter -->'
    bidx = text.index(begin)
    eidx = text.index(end) + len(end)
    tampered = text[:bidx] + begin + '\n' + end + text[eidx:]
    assert tampered != text, 'sanity: tampered text differs from original'
    portal.write_text(tampered, encoding='utf-8')

    result = _run_validate(repo)

    assert result.returncode != 0, (
        f'expected non-zero exit on drift, got {result.returncode}; '
        f'stdout={result.stdout!r} stderr={result.stderr!r}'
    )
    combined = result.stdout + result.stderr
    assert RUN_HINT in combined, (
        f'expected run-hint line in validator output; got: {combined!r}'
    )


# ---------------------------------------------------------------------------
# Test 3 — portal file absent: validate_docs.py exits 0 (drift check is gated)
# ---------------------------------------------------------------------------


def test_portal_absent_skips_drift_check(tmp_path):
    repo = _seed_repo(tmp_path, with_portal=False, with_runbooks=False)
    # Sanity: no portal on disk.
    assert not (repo / 'docs' / 'DEVELOPER_PORTAL.md').exists()

    result = _run_validate(repo)

    assert result.returncode == 0, (
        f'expected exit 0 when portal absent, got {result.returncode}; '
        f'stdout={result.stdout!r} stderr={result.stderr!r}'
    )
    # The drift-check branch should not have produced its error message.
    assert 'runbook-filter block is stale' not in result.stdout
