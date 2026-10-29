"""Every declared restic-backup failure-cause code is documented (#1067, FR-009).

The alert text comes from the key ledger's ``cause.codes``; the operator's
"what to do" lives in the runbook. This keeps the two in step: a code added
to the ledger without a runbook row fails here. The non-empty assertion is
the non-vacuity guard -- removing ``cause`` from the ledger fails too.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "restic-backup-ops.md"


def _restic_cause_codes() -> dict:
    doc = json.loads(INVENTORY.read_text())
    (entry,) = [s for s in doc["services"] if s.get("name") == "restic-backup"]
    return entry["health_check"]["key_ledger"]["cause"]["codes"]


def test_every_declared_cause_code_appears_in_the_runbook():
    codes = _restic_cause_codes()
    assert codes, "restic-backup declares no failure-cause codes"
    runbook = RUNBOOK.read_text()
    missing = sorted(code for code in codes if f"`{code}`" not in runbook)
    assert not missing, f"undocumented cause codes in {RUNBOOK.name}: {missing}"
