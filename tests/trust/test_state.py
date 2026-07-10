"""Tests for scripts.trust.state (WP04, #683).

Covers the seen-findings cadence (first-seen alert, 24h re-alert,
drift_resolved on disappearance), baseline-hash-versioned fingerprints,
atomic (temp+rename) writes, and fail-safe load of a missing/corrupt state
file. All time is injected via `now` — never a real clock.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.trust import state as state_mod
from scripts.trust.assertion_verifier import AssertionFinding
from scripts.trust.cron_drift_detector import CronDriftFinding

T0 = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
BASELINE_HASH_A = "hash-a"
BASELINE_HASH_B = "hash-b"


def _cron_finding(name="mystery-cron", agent_id="felix-admin-capture") -> CronDriftFinding:
    return CronDriftFinding(kind="unapproved_present", name=name, agent_id=agent_id)


def _assertion_finding(artifact_id="91") -> AssertionFinding:
    return AssertionFinding(
        kind="artifact_missing",
        agent="main",
        artifact_kind="vikunja_task",
        artifact_id=artifact_id,
        claim="Created Vikunja task",
    )


# --- fingerprint_finding: baseline-hash versioning ---------------------------


def test_fingerprint_stable_for_same_finding_and_baseline():
    finding = _cron_finding()
    fp1 = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    fp2 = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    assert fp1 == fp2


def test_fingerprint_changes_with_baseline_hash():
    finding = _cron_finding()
    fp_a = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    fp_b = state_mod.fingerprint_finding(finding, BASELINE_HASH_B)
    assert fp_a != fp_b


def test_fingerprint_differs_for_assertion_vs_cron_finding():
    cron_fp = state_mod.fingerprint_finding(_cron_finding(), BASELINE_HASH_A)
    assertion_fp = state_mod.fingerprint_finding(_assertion_finding(), BASELINE_HASH_A)
    assert cron_fp != assertion_fp


# --- reconcile: first observation --------------------------------------------


def test_reconcile_first_observation_alerts_immediately():
    finding = _cron_finding()
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], T0, state={}
    )

    assert to_alert == [finding]
    assert resolved == []
    fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    assert fingerprint in new_state
    assert new_state[fingerprint]["first_seen"] == state_mod._utc_iso(T0)
    assert new_state[fingerprint]["last_alerted"] == state_mod._utc_iso(T0)


# --- reconcile: re-alert cadence ----------------------------------------------


def test_reconcile_no_realert_before_24h():
    finding = _cron_finding()
    fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    existing_state = {
        fingerprint: {
            "first_seen": state_mod._utc_iso(T0),
            "last_seen": state_mod._utc_iso(T0),
            "last_alerted": state_mod._utc_iso(T0),
            "name": "mystery-cron",
        }
    }
    later = T0 + timedelta(hours=23, minutes=59)
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], later, state=existing_state
    )

    assert to_alert == []
    assert resolved == []
    # last_seen refreshed, last_alerted untouched
    assert new_state[fingerprint]["last_seen"] == state_mod._utc_iso(later)
    assert new_state[fingerprint]["last_alerted"] == state_mod._utc_iso(T0)


def test_reconcile_realerts_at_exactly_24h():
    finding = _cron_finding()
    fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    existing_state = {
        fingerprint: {
            "first_seen": state_mod._utc_iso(T0),
            "last_seen": state_mod._utc_iso(T0),
            "last_alerted": state_mod._utc_iso(T0),
            "name": "mystery-cron",
        }
    }
    exactly_24h = T0 + timedelta(hours=24)
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], exactly_24h, state=existing_state
    )

    assert to_alert == [finding]
    assert new_state[fingerprint]["last_alerted"] == state_mod._utc_iso(exactly_24h)
    # first_seen preserved across re-alert
    assert new_state[fingerprint]["first_seen"] == state_mod._utc_iso(T0)


def test_reconcile_realerts_after_24h():
    finding = _cron_finding()
    fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    existing_state = {
        fingerprint: {
            "first_seen": state_mod._utc_iso(T0),
            "last_seen": state_mod._utc_iso(T0),
            "last_alerted": state_mod._utc_iso(T0),
            "name": "mystery-cron",
        }
    }
    later = T0 + timedelta(hours=25)
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], later, state=existing_state
    )
    assert to_alert == [finding]


# --- reconcile: disappearance -> drift_resolved ------------------------------


def test_reconcile_disappearance_emits_drift_resolved_and_drops_entry():
    finding = _cron_finding()
    fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    existing_state = {
        fingerprint: {
            "first_seen": state_mod._utc_iso(T0),
            "last_seen": state_mod._utc_iso(T0),
            "last_alerted": state_mod._utc_iso(T0),
            "name": "mystery-cron",
        }
    }
    later = T0 + timedelta(hours=1)
    # Finding no longer present in current_findings (empty list this tick).
    to_alert, resolved, new_state = state_mod.reconcile([], later, state=existing_state)

    assert to_alert == []
    assert len(resolved) == 1
    event = resolved[0]
    assert event.fingerprint == fingerprint
    assert event.name == "mystery-cron"
    assert event.first_seen == state_mod._utc_iso(T0)
    assert event.cleared_at == state_mod._utc_iso(later)
    assert fingerprint not in new_state


# --- reconcile: baseline-hash change re-evaluates fingerprint ----------------


def test_reconcile_baseline_hash_change_reevaluates_as_first_observation():
    finding = _cron_finding()
    old_fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    existing_state = {
        old_fingerprint: {
            "first_seen": state_mod._utc_iso(T0),
            "last_seen": state_mod._utc_iso(T0),
            "last_alerted": state_mod._utc_iso(T0),
            "name": "mystery-cron",
        }
    }
    later = T0 + timedelta(minutes=5)
    # Same finding, but baseline changed -> different fingerprint.
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_B)], later, state=existing_state
    )

    new_fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_B)
    assert to_alert == [finding]  # treated as first observation under new fingerprint
    assert new_fingerprint in new_state
    # Old fingerprint entry is gone (finding "disappeared" under old hash),
    # and drift_resolved fires for it.
    assert old_fingerprint not in new_state
    assert any(event.fingerprint == old_fingerprint for event in resolved)


# --- load_state / save_state: atomic write + fail-safe load ------------------


def test_save_state_then_load_state_roundtrip(tmp_path: Path):
    path = tmp_path / "seen-findings.json"
    state = {
        "fp1": {
            "first_seen": "2026-07-10T00:00:00+00:00",
            "last_seen": "2026-07-10T00:00:00+00:00",
            "last_alerted": "2026-07-10T00:00:00+00:00",
            "name": "mystery-cron",
        }
    }
    state_mod.save_state(state, path)
    loaded = state_mod.load_state(path)
    assert loaded["fp1"]["first_seen"] == "2026-07-10T00:00:00+00:00"


def test_save_state_uses_atomic_temp_rename(tmp_path: Path):
    path = tmp_path / "seen-findings.json"
    state_mod.save_state({}, path)
    # No stray temp files left behind in the directory.
    leftovers = [p for p in tmp_path.iterdir() if p.name != path.name]
    assert leftovers == []
    assert path.exists()


def test_load_state_missing_file_returns_empty(tmp_path: Path):
    path = tmp_path / "does-not-exist.json"
    assert state_mod.load_state(path) == {}


def test_load_state_corrupt_json_returns_empty(tmp_path: Path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert state_mod.load_state(path) == {}


def test_load_state_non_object_json_returns_empty(tmp_path: Path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert state_mod.load_state(path) == {}


def test_load_state_malformed_entries_are_dropped(tmp_path: Path):
    path = tmp_path / "seen-findings.json"
    path.write_text(
        json.dumps(
            {
                "good": {
                    "first_seen": "x",
                    "last_seen": "y",
                    "last_alerted": "z",
                },
                "bad": {"first_seen": 123},
            }
        ),
        encoding="utf-8",
    )
    loaded = state_mod.load_state(path)
    assert "good" in loaded
    assert "bad" not in loaded


def test_load_state_unreadable_file_returns_empty(tmp_path: Path):
    """A directory at the expected path raises IsADirectoryError (an OSError
    subclass) on read_text — must fail safe to {} rather than raise."""
    path = tmp_path / "seen-findings.json"
    path.mkdir()  # a directory, not a file -> read_text raises IsADirectoryError
    assert state_mod.load_state(path) == {}


def test_save_state_cleans_up_temp_file_on_failure(tmp_path: Path, monkeypatch):
    """A failure during os.replace must not leak a stray .tmp file."""
    path = tmp_path / "seen-findings.json"

    def _boom(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(state_mod.os, "replace", _boom)

    with pytest.raises(OSError):
        state_mod.save_state({"a": {"first_seen": "x", "last_seen": "y", "last_alerted": "z"}}, path)

    leftovers = list(tmp_path.iterdir())
    assert leftovers == []


# --- fingerprint_finding: unsupported type -----------------------------------


def test_fingerprint_finding_rejects_unsupported_type():
    with pytest.raises(TypeError):
        state_mod.fingerprint_finding("not-a-finding", BASELINE_HASH_A)  # type: ignore[arg-type]


# --- reconcile: corrupt last_alerted timestamp treated as due for re-alert ---


def test_reconcile_corrupt_last_alerted_timestamp_forces_realert():
    finding = _cron_finding()
    fingerprint = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    existing_state = {
        fingerprint: {
            "first_seen": state_mod._utc_iso(T0),
            "last_seen": state_mod._utc_iso(T0),
            "last_alerted": "not-a-valid-timestamp",
            "name": "mystery-cron",
        }
    }
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], T0, state=existing_state
    )
    assert to_alert == [finding]
