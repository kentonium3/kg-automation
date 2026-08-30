"""SC-006 acceptance test: a second producer adopts the key-ledger contract
by declaring data, never by editing ``scripts.canary.ledger`` (WP03) or
``tests.canary.ledger_reconcile`` (WP05) — see contract "Reuse by a second
producer".

Drives a *fictitious* producer — invented here, written into ``tmp_path``,
never committed as a fixture script that could drift — with an entirely
different key set and shape from ``restic-backup``'s, through **both**
shared pieces: the reconciliation helper and WP03's evaluator. An earlier
draft of this test exercised only the evaluator; that would have let SC-006
be marked satisfied on half the evidence, with the reconciliation half
untested. Both are exercised here, with zero changes to either module —
that is the property SC-006 claims.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.canary.ledger import evaluate
from tests.canary.ledger_reconcile import EmissionResult, assert_reconciles

NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)

# A ledger with a DIFFERENTLY-SHAPED contract from restic-backup's: a
# different predicate mix (no freshness/anchor at all, proving reconciliation
# doesn't secretly require one), different good-sets, different diagnostic
# keys, different key names entirely.
FICTITIOUS_LEDGER = {
    "reconciliation_harness": "tests/canary/test_ledger_reuse.py",
    "adjudicated": {
        "widget_status": {"good_values": ["green", "yellow"]},
        "widget_count": {"minimum": 3},
    },
    "diagnostic_only": {
        "widget_run_id": {"reason": "identifier only, no health meaning"},
    },
}

# `extra` lets one test simulate the fictitious producer growing an
# undeclared key, without touching the ledger or either shared module.
_FICTITIOUS_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail
extra=""
if [ -n "${WIDGET_EXTRA_KEY:-}" ]; then
  extra=', "widget_phantom": true'
fi
cat <<JSON
{
  "widget_status": "${WIDGET_STATUS:-green}",
  "widget_count": ${WIDGET_COUNT:-5},
  "widget_run_id": "run-001"$extra
}
JSON
"""


def _write_fictitious_producer(tmp_path: Path) -> Path:
    script = tmp_path / "fictitious-producer.sh"
    script.write_text(_FICTITIOUS_SCRIPT)
    script.chmod(0o755)
    return script


def _run(script: Path, **env_overrides: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_overrides}
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=False)


def test_fictitious_producer_reconciles_with_zero_changes_to_the_helper(tmp_path):
    """Drives assert_reconciles (WP05's own module) against a producer with
    a key set and shape ledger_reconcile.py has never seen."""
    script = _write_fictitious_producer(tmp_path)
    proc = _run(script)
    document = json.loads(proc.stdout)
    emitted = EmissionResult(
        process_ok=proc.returncode == 0,
        process_detail=f"exit {proc.returncode}",
        document_text=proc.stdout,
        document=document,
    )
    assert_reconciles(emitted, FICTITIOUS_LEDGER, "fictitious-widget")


def test_fictitious_producer_evaluates_with_zero_changes_to_the_evaluator(tmp_path):
    """Drives WP03's evaluate() against the same producer and ledger."""
    script = _write_fictitious_producer(tmp_path)
    proc = _run(script)
    document = json.loads(proc.stdout)
    result = evaluate(document, FICTITIOUS_LEDGER, now=NOW)
    assert result.outcome == "ok", result.evidence


def test_undeclared_key_in_fictitious_producer_fails_reconciliation(tmp_path):
    """An undeclared key from the fictitious producer must fail, by name --
    driven through the shared helper, not a hand-mutated dict."""
    script = _write_fictitious_producer(tmp_path)
    proc = _run(script, WIDGET_EXTRA_KEY="1")
    document = json.loads(proc.stdout)
    emitted = EmissionResult(
        process_ok=proc.returncode == 0,
        process_detail=f"exit {proc.returncode}",
        document_text=proc.stdout,
        document=document,
    )
    with pytest.raises(AssertionError, match="widget_phantom"):
        assert_reconciles(emitted, FICTITIOUS_LEDGER, "fictitious-widget")


def test_bad_value_against_fictitious_good_set_is_unhealthy(tmp_path):
    """A value outside the fictitious ledger's own good-set must be
    unhealthy -- driven through the shared evaluator."""
    script = _write_fictitious_producer(tmp_path)
    proc = _run(script, WIDGET_STATUS="red")
    document = json.loads(proc.stdout)
    result = evaluate(document, FICTITIOUS_LEDGER, now=NOW)
    assert result.outcome == "unhealthy"
    assert "widget_status" in result.evidence
