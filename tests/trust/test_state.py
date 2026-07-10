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


# --- F2: assertion resolution routing + outstanding re-verify seeding --------


def test_reconcile_assertion_finding_carries_source_and_identity():
    finding = _assertion_finding(artifact_id="91")
    _, _, new_state = state_mod.reconcile([(finding, BASELINE_HASH_A)], T0, state={})
    fp = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    entry = new_state[fp]
    assert entry["source"] == "assertion"
    assert entry["assertion_kind"] == "artifact_missing"
    assert entry["artifact_kind"] == "vikunja_task"
    assert entry["artifact_id"] == "91"


def test_reconcile_disappeared_assertion_resolves_as_assertion_source():
    finding = _assertion_finding(artifact_id="91")
    fp = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    existing = {
        fp: {
            "first_seen": state_mod._utc_iso(T0),
            "last_seen": state_mod._utc_iso(T0),
            "last_alerted": state_mod._utc_iso(T0),
            "name": "vikunja_task:91",
            "source": "assertion",
            "assertion_kind": "artifact_missing",
            "artifact_kind": "vikunja_task",
            "artifact_id": "91",
            "agent": "main",
            "claim": "c",
        }
    }
    _, resolved, _ = state_mod.reconcile([], T0 + timedelta(hours=1), state=existing)
    assert len(resolved) == 1
    assert resolved[0].source == "assertion"


def test_outstanding_assertion_findings_reconstructs_only_vikunja_missing():
    state = {
        "fp_missing": {
            "first_seen": "x", "last_seen": "y", "last_alerted": "z",
            "source": "assertion", "assertion_kind": "artifact_missing",
            "artifact_kind": "vikunja_task", "artifact_id": "91",
            "agent": "main", "claim": "c",
        },
        "fp_cron": {  # cron drift -> not an assertion, excluded
            "first_seen": "x", "last_seen": "y", "last_alerted": "z",
            "source": "cron", "name": "mystery-cron",
        },
        "fp_unverifiable": {  # assertion but unverifiable_kind -> excluded
            "first_seen": "x", "last_seen": "y", "last_alerted": "z",
            "source": "assertion", "assertion_kind": "unverifiable_kind",
            "artifact_kind": "other", "artifact_id": "x1",
        },
    }
    findings = state_mod.outstanding_assertion_findings(state)
    assert len(findings) == 1
    assert findings[0].artifact_id == "91"
    assert findings[0].kind == "artifact_missing"
    assert findings[0].artifact_kind == "vikunja_task"


def test_outstanding_assertion_findings_empty_for_none_or_empty():
    assert state_mod.outstanding_assertion_findings(None) == []
    assert state_mod.outstanding_assertion_findings({}) == []


def test_load_state_preserves_source_and_assertion_identity(tmp_path: Path):
    path = tmp_path / "seen-findings.json"
    path.write_text(
        json.dumps(
            {
                "fp": {
                    "first_seen": "a", "last_seen": "b", "last_alerted": "c",
                    "source": "assertion", "assertion_kind": "artifact_missing",
                    "artifact_kind": "vikunja_task", "artifact_id": "91",
                    "agent": "main", "claim": "did",
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = state_mod.load_state(path)
    assert loaded["fp"]["source"] == "assertion"
    assert loaded["fp"]["artifact_id"] == "91"
    assert loaded["fp"]["claim"] == "did"


# --- F3: keep_due reverts last_alerted so a failed emit stays due ------------


def test_keep_due_first_observation_sets_always_due_sentinel():
    finding = _cron_finding()
    to_alert, _, new_state = state_mod.reconcile([(finding, BASELINE_HASH_A)], T0, state={})
    fp = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    assert new_state[fp]["last_alerted"] == state_mod._utc_iso(T0)
    # Emit failed -> keep_due with no prior state -> sentinel (long ago).
    state_mod.keep_due(new_state, fp, prior_state={})
    # Next scan (1 min later) must be DUE: reconcile re-alerts.
    to_alert2, _, _ = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], T0 + timedelta(minutes=1), state=new_state
    )
    assert to_alert2 == [finding]


def test_keep_due_restores_prior_last_alerted_when_present():
    finding = _cron_finding()
    fp = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    prior_alerted = state_mod._utc_iso(T0)
    prior_state = {
        fp: {
            "first_seen": prior_alerted, "last_seen": prior_alerted,
            "last_alerted": prior_alerted, "name": "mystery-cron", "source": "cron",
        }
    }
    # 24h later -> reconcile marks due and bumps last_alerted.
    later = T0 + timedelta(hours=24)
    _, _, new_state = state_mod.reconcile([(finding, BASELINE_HASH_A)], later, state=prior_state)
    assert new_state[fp]["last_alerted"] == state_mod._utc_iso(later)
    # Emit failed -> restore prior last_alerted (not the bumped one).
    state_mod.keep_due(new_state, fp, prior_state=prior_state)
    assert new_state[fp]["last_alerted"] == prior_alerted


def test_keep_due_missing_fingerprint_is_noop():
    state_mod.keep_due({}, "nope", prior_state={})  # must not raise


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
