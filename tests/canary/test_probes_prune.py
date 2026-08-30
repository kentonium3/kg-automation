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

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_INVENTORY = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"


@pytest.fixture
def judge(tmp_path):
    now = datetime.now(timezone.utc)
    ptr = tmp_path / "last-backup.json"

    def _judge(payload: dict, *, key_ledger: dict | None = None):
        ptr.write_text(json.dumps(payload))
        hc = {"method": "state-file", "state_path": str(ptr), "max_age_seconds": MAX_AGE}
        if key_ledger is not None:
            hc["key_ledger"] = key_ledger
        return run_probe(
            hc, now, http_get=None, run_cmd=None,
            read_state=lambda p: json.loads(Path(p).read_text()),
        )

    _judge.now = now
    return _judge


@pytest.fixture(scope="module")
def real_restic_ledger():
    """The REAL restic-backup ``key_ledger``, loaded from the actual
    ``service-inventory.json`` -- never a hand-rolled copy (SC-007). A copy
    would drift from what actually ships and prove nothing about the
    configuration the reviewer will attach by hand. Same loading pattern as
    ``tests/canary/test_inventory_health_checks.py``.
    """
    inv = json.loads(REAL_INVENTORY.read_text())
    entry = next(s for s in inv["services"] if s.get("name") == "restic-backup")
    ledger = entry["health_check"]["key_ledger"]
    # Sanity-pin the two facts the parameterised scenarios below rely on, so
    # a silent edit to the real ledger can't make these tests pass for the
    # wrong reason (review guidance #3: "a test that passes because the
    # ledger was never loaded proves nothing").
    assert ledger["adjudicated"]["snapshot_timestamp_utc"]["anchor"] is True
    assert ledger["adjudicated"]["prune_exit_code"]["good_values"] == [0]
    return ledger


def fresh(now, **extra):
    base = {
        "restic_exit_code": 0,
        "snapshot_timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_id": "deadbeef",
    }
    base.update(extra)
    return base


def fresh_ledgered(now, **extra):
    """A document satisfying every ADJUDICATED key in the real restic-backup
    ledger -- the baseline the T023 (SC-007) scenarios below start from and
    then deliberately break one field of. Unlike ``fresh()``, this must
    supply every adjudicated key: with a ledger attached, an absent
    adjudicated key is unhealthy regardless of predicate (contract
    "Absence"), so an incomplete baseline would make a scenario fail for the
    wrong reason.
    """
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    base = {
        "schema_version": 2,
        "restic_exit_code": 0,
        "prune_exit_code": 0,
        "integrity_check_passed": True,
        "snapshot_timestamp_utc": ts,
        "last_integrity_check_utc": ts,
        "snapshot_count": 5,
        "files_processed": 100,
        "source_roots_present": True,
        "repo_fs_free_bytes": 107_374_182_400,  # 100 GiB, well above the 50 GiB minimum
        # diagnostic_only keys -- not adjudicated, present for realism/parity
        # with fresh()'s snapshot_id.
        "snapshot_id": "deadbeef",
        "script_finished_at_utc": ts,
    }
    base.update(extra)
    return base


def _payload(now, with_ledger: bool, **overrides):
    """Build the scenario payload for either configuration, sharing the
    override application so a scenario's edit is expressed exactly once."""
    base = fresh_ledgered(now) if with_ledger else fresh(now)
    base.update(overrides)
    return base


#: The two configurations every SC-007 scenario below must pass under.
_WITH_LEDGER = pytest.mark.parametrize(
    "with_ledger", [False, True], ids=["ledger_free", "real_ledger"]
)


def _ledger_for(with_ledger: bool, real_restic_ledger: dict) -> dict | None:
    return real_restic_ledger if with_ledger else None


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


@_WITH_LEDGER
def test_prune_exit_3_is_unhealthy(judge, real_restic_ledger, with_ledger):
    """The trap: 3 is acceptable for a BACKUP, never for a prune.

    A careless implementation reuses _RESTIC_OK_EXIT_CODES ({0, 3}) and silently
    accepts a prune that did not apply retention. SC-007 (T023): must hold both
    ledger-free (legacy _explicit_error) and with the real ledger attached
    (prune_exit_code's declared good_values is {0}, deliberately narrower than
    restic_exit_code's {0, 3} -- #902).
    """
    payload = _payload(judge.now, with_ledger, prune_exit_code=3)
    r = judge(payload, key_ledger=_ledger_for(with_ledger, real_restic_ledger))
    assert not r.ok, f"prune_exit_code=3 must be unhealthy: {r.evidence}"


@_WITH_LEDGER
def test_prune_never_attempted_is_unhealthy(judge, real_restic_ledger, with_ledger):
    """127 = the run exited before the prune. Retention did not happen.
    SC-007 (T023): must hold ledger-free and with the real ledger attached.
    """
    payload = _payload(judge.now, with_ledger, prune_exit_code=127)
    r = judge(payload, key_ledger=_ledger_for(with_ledger, real_restic_ledger))
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


@_WITH_LEDGER
def test_backup_warning_with_clean_prune_stays_healthy(judge, real_restic_ledger, with_ledger):
    """restic_exit_code 3 is still acceptable — existing backup semantics.
    SC-007 (T023): must hold ledger-free and with the real ledger attached
    (restic_exit_code's declared good_values is {0, 3}).
    """
    payload = _payload(judge.now, with_ledger, restic_exit_code=3, prune_exit_code=0)
    r = judge(payload, key_ledger=_ledger_for(with_ledger, real_restic_ledger))
    assert r.ok, f"restic_exit_code=3 must stay healthy: {r.evidence}"


def test_backup_failure_still_unhealthy(judge):
    r = judge(fresh(judge.now, restic_exit_code=1, prune_exit_code=0))
    assert not r.ok


# --------------------------------------------------------------------------- #
# FR-009: no snapshot timestamp must not fall through and read fresh
# --------------------------------------------------------------------------- #

@_WITH_LEDGER
def test_null_snapshot_timestamp_is_unhealthy(judge, real_restic_ledger, with_ledger):
    """Regression guard -- THE named #902/FR-009 regression, re-asserted
    with the real ledger attached (SC-007, T023 point 3): a run that produces
    no snapshot, with restic_exit_code=0 and a fresh script_finished_at_utc,
    must read unhealthy in BOTH configurations.

    Before FR-009 the freshness probe fell through TIMESTAMP_KEYS to
    ``script_finished_at_utc``, so a run that produced no snapshot reported
    ok=True, stale=False — while the inventory asserted the snapshot timestamp
    must be non-null. WP04's first-draft ledger integration would have
    reopened exactly this by suppressing the whole ``restic_exit_code``
    rule-block (timestamp guard included) once the ledger declared
    ``restic_exit_code`` -- this is the test the post-plan review named to
    prove that stayed closed.
    """
    payload = _payload(judge.now, with_ledger, prune_exit_code=0)
    payload["snapshot_timestamp_utc"] = None
    payload["script_finished_at_utc"] = judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = judge(payload, key_ledger=_ledger_for(with_ledger, real_restic_ledger))
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


@_WITH_LEDGER
def test_unparseable_snapshot_timestamp_is_unhealthy(judge, real_restic_ledger, with_ledger):
    """Regression guard (post-review). SC-007 (T023): must hold ledger-free
    and with the real ledger attached.

    A first attempt at FR-009 checked only that the value was a non-empty
    string. A malformed-but-truthy timestamp passed that guard and then fell
    through TIMESTAMP_KEYS to ``script_finished_at_utc``, reading healthy — the
    same hole, one step narrower. "Usable" must mean parseable. With the
    ledger attached, the anchor-resolution path (T021) must reject it the
    same way rather than falling through to another TIMESTAMP_KEYS candidate.
    """
    payload = _payload(judge.now, with_ledger, prune_exit_code=0)
    payload["snapshot_timestamp_utc"] = "not-a-date"
    payload["script_finished_at_utc"] = judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = judge(payload, key_ledger=_ledger_for(with_ledger, real_restic_ledger))
    assert not r.ok, f"an unparseable snapshot timestamp must not read healthy: {r.evidence}"


@_WITH_LEDGER
def test_numeric_snapshot_timestamp_is_unhealthy(judge, real_restic_ledger, with_ledger):
    """Truthy, wrong type, would previously have failed the isinstance check
    but is worth pinning now that the guard is parse-based. SC-007 (T023):
    must hold ledger-free and with the real ledger attached."""
    payload = _payload(judge.now, with_ledger, prune_exit_code=0)
    payload["snapshot_timestamp_utc"] = 1787900000
    payload["script_finished_at_utc"] = judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = judge(payload, key_ledger=_ledger_for(with_ledger, real_restic_ledger))
    assert not r.ok, f"a numeric snapshot timestamp must not read healthy: {r.evidence}"


def test_felix_health_check_shaped_pointer_is_unaffected(judge):
    """A real registered non-restic component: no snapshot_timestamp_utc at all.

    Named because it is the best live regression witness for the scoping claim —
    a broad version of FR-009 would flip it unhealthy.
    """
    r = judge({"status": "ALL_HEALTHY", "exit_code": 0,
               "ran_at_utc": judge.now.strftime("%Y-%m-%dT%H:%M:%SZ")})
    assert r.ok
