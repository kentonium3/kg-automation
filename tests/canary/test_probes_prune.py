"""Prune outcome and snapshot-timestamp handling in the restic health probe (#902).

Both properties here are the difference between a check that reports a failure
and one that merely records it. They are asserted through the REAL
``scripts.canary.probes.run_probe`` — a hand-rolled judge would not have caught
either defect, since both live in the judge.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.canary.probes import run_probe

MAX_AGE = 100800  # the restic-backup registration's bound


@pytest.fixture
def judge(tmp_path):
    now = datetime.now(timezone.utc)
    ptr = tmp_path / "last-backup.json"

    def _judge(payload: dict):
        ptr.write_text(json.dumps(payload))
        return run_probe(
            {"method": "state-file", "state_path": str(ptr), "max_age_seconds": MAX_AGE},
            now, http_get=None, run_cmd=None,
            read_state=lambda p: json.loads(Path(p).read_text()),
        )

    _judge.now = now
    return _judge


def fresh(now, **extra):
    base = {
        "restic_exit_code": 0,
        "snapshot_timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_id": "deadbeef",
    }
    base.update(extra)
    return base


# --------------------------------------------------------------------------- #
# The prune good-set is {0}, NOT the backup's {0, 3}
# --------------------------------------------------------------------------- #

def test_clean_prune_is_healthy(judge):
    r = judge(fresh(judge.now, prune_exit_code=0))
    assert r.ok and not r.stale


def test_failed_prune_is_unhealthy(judge):
    """The #902 case: backup fine, retention silently not applied."""
    r = judge(fresh(judge.now, prune_exit_code=1))
    assert not r.ok, f"a failed prune must not read healthy: {r.evidence}"
    assert "prune_exit_code" in r.evidence


def test_prune_exit_3_is_unhealthy(judge):
    """The trap: 3 is acceptable for a BACKUP, never for a prune.

    A careless implementation reuses _RESTIC_OK_EXIT_CODES ({0, 3}) and silently
    accepts a prune that did not apply retention.
    """
    r = judge(fresh(judge.now, prune_exit_code=3))
    assert not r.ok, f"prune_exit_code=3 must be unhealthy: {r.evidence}"


def test_prune_never_attempted_is_unhealthy(judge):
    """127 = the run exited before the prune. Retention did not happen."""
    r = judge(fresh(judge.now, prune_exit_code=127))
    assert not r.ok, f"an unattempted prune must not read healthy: {r.evidence}"


def test_non_integer_prune_value_is_ignored(judge):
    """Guarded with isinstance, matching the neighbouring checks."""
    r = judge(fresh(judge.now, prune_exit_code=None))
    assert r.ok


# --------------------------------------------------------------------------- #
# Backward compatibility (NFR-002)
# --------------------------------------------------------------------------- #

def test_legacy_pointer_without_prune_field_stays_healthy(judge):
    """Pointers written before this change must remain interpretable."""
    r = judge(fresh(judge.now))
    assert r.ok and not r.stale


def test_backup_warning_with_clean_prune_stays_healthy(judge):
    """restic_exit_code 3 is still acceptable — existing backup semantics."""
    r = judge(fresh(judge.now, restic_exit_code=3, prune_exit_code=0))
    assert r.ok


def test_backup_failure_still_unhealthy(judge):
    r = judge(fresh(judge.now, restic_exit_code=1, prune_exit_code=0))
    assert not r.ok


# --------------------------------------------------------------------------- #
# FR-009: no snapshot timestamp must not fall through and read fresh
# --------------------------------------------------------------------------- #

def test_null_snapshot_timestamp_is_unhealthy(judge):
    """Regression guard.

    Before this change the freshness probe fell through TIMESTAMP_KEYS to
    ``script_finished_at_utc``, so a run that produced no snapshot reported
    ok=True, stale=False — while the inventory asserted the snapshot timestamp
    must be non-null.
    """
    payload = fresh(judge.now, prune_exit_code=0)
    payload["snapshot_timestamp_utc"] = None
    payload["script_finished_at_utc"] = judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = judge(payload)
    assert not r.ok, f"a backup with no snapshot must not read healthy: {r.evidence}"


def test_absent_snapshot_timestamp_is_unhealthy(judge):
    payload = {"restic_exit_code": 0,
               "script_finished_at_utc": judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    r = judge(payload)
    assert not r.ok


def test_empty_snapshot_timestamp_is_unhealthy(judge):
    payload = fresh(judge.now)
    payload["snapshot_timestamp_utc"] = "   "
    r = judge(payload)
    assert not r.ok


def test_stale_snapshot_timestamp_is_stale(judge):
    """The check must still be able to go stale — not merely fail explicitly."""
    old = judge.now - timedelta(seconds=MAX_AGE + 3600)
    payload = fresh(judge.now, prune_exit_code=0)
    payload["snapshot_timestamp_utc"] = old.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = judge(payload)
    assert r.stale


# --------------------------------------------------------------------------- #
# No regression for components that are not restic
# --------------------------------------------------------------------------- #

def test_non_restic_pointer_is_unaffected(judge):
    """probes.py is shared by every component; the change must be scoped."""
    r = judge({"status": "success", "exit_code": 0,
               "completed_at_utc": judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")})
    assert r.ok and not r.stale


def test_non_restic_pointer_without_snapshot_ts_is_unaffected(judge):
    """A component with no snapshot_timestamp_utc must not be failed by FR-009."""
    r = judge({"status": "success", "exit_code": 0,
               "completed_at_utc": judge.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "has_drift": True})
    assert r.ok


def test_unparseable_snapshot_timestamp_is_unhealthy(judge):
    """Regression guard (post-review).

    A first attempt at FR-009 checked only that the value was a non-empty
    string. A malformed-but-truthy timestamp passed that guard and then fell
    through TIMESTAMP_KEYS to ``script_finished_at_utc``, reading healthy — the
    same hole, one step narrower. "Usable" must mean parseable.
    """
    payload = fresh(judge.now, prune_exit_code=0)
    payload["snapshot_timestamp_utc"] = "not-a-date"
    payload["script_finished_at_utc"] = judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = judge(payload)
    assert not r.ok, f"an unparseable snapshot timestamp must not read healthy: {r.evidence}"


def test_numeric_snapshot_timestamp_is_unhealthy(judge):
    """Truthy, wrong type, would previously have failed the isinstance check
    but is worth pinning now that the guard is parse-based."""
    payload = fresh(judge.now, prune_exit_code=0)
    payload["snapshot_timestamp_utc"] = 1787900000
    payload["script_finished_at_utc"] = judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not judge(payload).ok


def test_felix_health_check_shaped_pointer_is_unaffected(judge):
    """A real registered non-restic component: no snapshot_timestamp_utc at all.

    Named because it is the best live regression witness for the scoping claim —
    a broad version of FR-009 would flip it unhealthy.
    """
    r = judge({"status": "ALL_HEALTHY", "exit_code": 0,
               "ran_at_utc": judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")})
    assert r.ok
