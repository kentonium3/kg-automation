"""Live smoke test for the doc-audit driver.

Opt-in only. The tests in this module are skipped unless the operator
sets the ``LIVE_SMOKE_ENABLED=1`` environment variable.

Run via::

    LIVE_SMOKE_ENABLED=1 pytest tests/doc_audit/test_smoke_live.py

Default invocation (no env var) skips these tests cleanly — bare
``pytest tests/doc_audit/test_smoke_live.py`` exits 0 with "N skipped"
rather than the pytest-exit-5 "all tests deselected" error you'd hit
with a marker-based ``addopts`` filter.

The ``live_smoke`` pytest marker is still registered in ``pytest.ini``
and applied to each test for discoverability (``pytest --markers`` and
``-m live_smoke`` selection), but the actual gating mechanism is the
env-var ``skipif`` below.

Requires:

- Real GitHub credentials (``gh auth status`` returning ``kg-felix-bot``).
- Real Anthropic API key file readable at ``config.llm.api_key_path``
  (production: ``/data/services/openclaw/secrets/anthropic``).
- Network connectivity to ``api.anthropic.com`` and ``github.com``.
- The doc-audit driver code under ``scripts/doc_audit/`` (already
  present in the worktree).

Test pattern: run the driver against a known-empty queue (no audits
open at the start of the tick), assert the driver exits 0 and that
the tick-signal artifact reports ``status="success"`` with
``signals_seen == 0``. Then optionally (skip-by-default) file a single
synthetic audit issue, run the driver again, and assert the synthetic
audit was processed cleanly.

This test is the fidelity floor: mocked tests cover the orchestration
loop's branches in CPU; this test confirms the live integration boundary
still works (real ``gh`` shell, real ``anthropic`` SDK, real filesystem
paths on office2).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Env-var opt-in. ``LIVE_SMOKE_ENABLED=1`` is the operator handshake
# that says "I have real credentials and network and I want these
# tests to actually run". Without it the tests skip cleanly.
LIVE_SMOKE_ENABLED = os.environ.get("LIVE_SMOKE_ENABLED") == "1"

# Marker remains for discoverability (``pytest --markers``, ``-m live_smoke``).
pytestmark = pytest.mark.live_smoke


# ---------------------------------------------------------------------------
# Module-level env knobs
# ---------------------------------------------------------------------------

# Where the driver writes its tick signal in production.
DEFAULT_TICK_SIGNAL_PATH = Path(
    "/data/services/openclaw/felix-doc-auditor-driver/last-tick.json"
)

# Operator can override via env var for staging / local runs:
TICK_SIGNAL_PATH = Path(
    os.environ.get(
        "DOC_AUDIT_SMOKE_TICK_SIGNAL", str(DEFAULT_TICK_SIGNAL_PATH)
    )
)

# Where the driver lives in this worktree.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DRIVER_ENTRYPOINT = REPO_ROOT / "scripts" / "doc_audit" / "run.py"

# Audit-queue label used to scan for open audit issues.
AUDIT_LABEL = "doc-audit"

# Repo identifier passed to gh CLI for queue checks.
GH_REPO = os.environ.get("DOC_AUDIT_SMOKE_REPO", "kentonium3/kg-automation")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gh_open_audits() -> list[dict]:
    """Return open doc-audit issues via the real gh CLI."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            GH_REPO,
            "--label",
            AUDIT_LABEL,
            "--state",
            "open",
            "--json",
            "number,title,labels",
            "--limit",
            "50",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(
            f"gh CLI not available or not authenticated in this env: "
            f"{result.stderr.strip()}"
        )
    return json.loads(result.stdout or "[]")


def _read_tick_signal() -> dict:
    """Return the parsed tick-signal artifact, or skip if absent."""
    if not TICK_SIGNAL_PATH.exists():
        pytest.skip(
            f"Tick signal path {TICK_SIGNAL_PATH} not present "
            "(test likely running off-office2; set "
            "DOC_AUDIT_SMOKE_TICK_SIGNAL to override)"
        )
    return json.loads(TICK_SIGNAL_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not LIVE_SMOKE_ENABLED,
    reason="Set LIVE_SMOKE_ENABLED=1 to run live smoke tests",
)
def test_smoke_empty_queue() -> None:
    """Driver completes a tick against an empty queue end-to-end.

    Pre-condition: the doc-audit queue must already be empty
    (i.e., no audit issues with the ``doc-audit`` label in the open
    state, and no pending-approval issues from prior ticks). If the
    queue is not empty, we skip rather than fail — the smoke test
    must not interfere with production state, and re-running it on a
    quiet day will work.
    """
    if not DRIVER_ENTRYPOINT.is_file():
        pytest.skip(f"Driver entrypoint not present at {DRIVER_ENTRYPOINT}")

    open_audits = _gh_open_audits()
    if open_audits:
        pytest.skip(
            f"Pre-condition: queue must be empty for empty-queue smoke "
            f"(found {len(open_audits)} open audit issue(s); "
            f"re-run when the queue clears)"
        )

    # Run the driver from the repo root so its relative imports resolve.
    driver = subprocess.run(
        [sys.executable, str(DRIVER_ENTRYPOINT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    # Exit codes: 0 = success, 2 = partial, 1 = failure (per tick-signal
    # contract §"Field constraints"). For empty queue we require 0.
    assert driver.returncode == 0, (
        f"Driver did not exit cleanly (rc={driver.returncode}). "
        f"stderr: {driver.stderr!r}"
    )

    signal = _read_tick_signal()
    assert signal.get("schema_version") == "1.0", (
        f"Unexpected tick-signal schema_version: {signal.get('schema_version')!r}"
    )
    assert signal.get("status") == "success", (
        f"Expected status=success on empty queue; got "
        f"{signal.get('status')!r}. errors={signal.get('errors')!r}"
    )
    assert signal.get("exit_code") == 0, (
        f"Expected exit_code=0; got {signal.get('exit_code')!r}"
    )

    tick_block = signal.get("tick") or {}
    assert tick_block.get("signals_seen", -1) == 0, (
        f"Expected signals_seen=0 on empty queue; got "
        f"{tick_block.get('signals_seen')!r}"
    )
    assert tick_block.get("audits_processed") in ([], None), (
        f"Expected no audits_processed on empty queue; got "
        f"{tick_block.get('audits_processed')!r}"
    )


@pytest.mark.skipif(
    not LIVE_SMOKE_ENABLED,
    reason="Set LIVE_SMOKE_ENABLED=1 to run live smoke tests",
)
def test_smoke_synthetic_audit() -> None:
    """OPTIONAL: file a synthetic audit, run driver, verify processed cleanly.

    Marked skip-by-default so the smoke test never files test
    artifacts in production without operator opt-in. To run this:

    1. Read the implementation comment block below.
    2. Identify a safe target doc (e.g., a small reference doc whose
       ``last_validated`` is stale by >=30 days).
    3. Set ``DOC_AUDIT_SMOKE_SYNTHETIC_TARGET=<doc-path>`` env var.
    4. Remove the ``pytest.skip`` line.
    5. Run with ``pytest -m live_smoke -k synthetic`` and review the
       resulting audit + activity log on office2.

    Implementation pattern (DO NOT enable without operator review):

    - File an audit issue via the standard ``felix-file-issue.py``
      helper (or direct ``gh issue create``) with title pattern
      ``Doc audit: <sha-short> (<area>)`` and the ``doc-audit`` +
      ``area/...`` labels. Capture the issue number.
    - Run the driver: ``python3 scripts/doc_audit/run.py``.
    - Verify exit code 0 (or 2 if the audit produced a debt issue +
      otherwise-clean tick).
    - Verify the synthetic audit issue is now closed.
    - Verify the tick signal lists the synthetic audit number in
      ``tick.audits_processed``.
    - Cleanup: ensure the synthetic audit is closed (the driver
      should have done this; if not, the test should not leave it
      open).
    """
    pytest.skip(
        "Manual test — requires operator to set "
        "DOC_AUDIT_SMOKE_SYNTHETIC_TARGET and remove this skip line. "
        "See docstring for full pattern."
    )
