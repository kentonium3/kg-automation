"""Tests for scripts.trust.state (WP04, #683).

Covers the seen-findings cadence (first-seen alert, 24h re-alert,
drift_resolved on disappearance), baseline-hash-versioned fingerprints,
atomic (temp+rename) writes, and fail-safe load of a missing/corrupt state
file. All time is injected via `now` — never a real clock.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.trust import state as state_mod
from scripts.trust.alert_render import render_drift_resolved
from scripts.trust.assertion_verifier import AssertionFinding
from scripts.trust.cron_baseline import ApprovedCron
from scripts.trust.cron_drift_detector import CronDriftFinding, detect_cron_drift
from scripts.trust.unit_drift_detector import UnitDriftFinding

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


def _unit_finding(name="felix-canary.service") -> UnitDriftFinding:
    return UnitDriftFinding(
        kind="content_drift", name=name, repo_source=f"scripts/office2/{name}"
    )


def test_fingerprint_unit_stable_and_distinct_from_other_sources():
    fp1 = state_mod.fingerprint_finding(_unit_finding(), "")
    fp2 = state_mod.fingerprint_finding(_unit_finding(), "")
    assert fp1 == fp2  # identity = (unit, kind, name); stable across ticks
    assert fp1 != state_mod.fingerprint_finding(_cron_finding(), "")
    assert fp1 != state_mod.fingerprint_finding(_unit_finding("felix-trust-scan.service"), "")


def test_unit_finding_name_and_source():
    finding = _unit_finding("felix-trust-scan.service")
    assert state_mod._finding_name(finding) == "felix-trust-scan.service"
    assert state_mod._finding_source(finding) == "unit-drift"


def test_reconcile_unit_finding_first_observation_alerts():
    finding = _unit_finding()
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, "")], datetime(2026, 1, 1, tzinfo=timezone.utc), {}
    )
    assert to_alert == [finding]
    assert resolved == []
    fp = state_mod.fingerprint_finding(finding, "")
    assert new_state[fp]["source"] == "unit-drift"
    assert new_state[fp]["name"] == "felix-canary.service"


def test_reconcile_unit_finding_resolves_when_drift_clears():
    """A redeployed unit (drift gone → finding absent next tick) produces a
    unit-drift resolution event and drops from state."""
    finding = _unit_finding()
    _, _, state1 = state_mod.reconcile(
        [(finding, "")], datetime(2026, 1, 1, tzinfo=timezone.utc), {}
    )
    to_alert, resolved, state2 = state_mod.reconcile(
        [], datetime(2026, 1, 2, tzinfo=timezone.utc), state1
    )
    assert to_alert == []
    assert len(resolved) == 1
    assert resolved[0].source == "unit-drift"
    assert resolved[0].name == "felix-canary.service"
    assert state_mod.fingerprint_finding(finding, "") not in state2


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


# --- #1124: null-agent (plugin-managed) cron findings ------------------------

# Pinned pre-fix fingerprint of _cron_finding() under BASELINE_HASH_A, computed
# on the unfixed code (2026-11-23). Existing str-agent fingerprints MUST stay
# byte-identical, or every persisted finding would spuriously re-alert.
PINNED_STR_AGENT_FINGERPRINT = (
    "3f90cd2da8a504e0479ce69b3264cb3cf6375d7ffebed21ff440258c1b9f3704"
)


def _null_agent_finding(name="Memory Dreaming Promotion") -> CronDriftFinding:
    return CronDriftFinding(
        kind="unapproved_present",
        name=name,
        agent_id=None,
    )


def test_fingerprint_null_agent_returns_hex_digest():
    fp = state_mod.fingerprint_finding(_null_agent_finding(), BASELINE_HASH_A)
    assert isinstance(fp, str)
    assert len(fp) == 64
    int(fp, 16)  # hex


def test_fingerprint_null_agent_distinct_from_empty_and_real_agents():
    fp_none = state_mod.fingerprint_finding(_null_agent_finding("c"), BASELINE_HASH_A)
    for agent in ("", "None", "none", "<none>", "main"):
        other = CronDriftFinding(kind="unapproved_present", name="c", agent_id=agent)
        assert fp_none != state_mod.fingerprint_finding(other, BASELINE_HASH_A), agent


def test_fingerprint_str_agent_byte_identical_to_pre_fix_value():
    fp = state_mod.fingerprint_finding(_cron_finding(), BASELINE_HASH_A)
    assert fp == PINNED_STR_AGENT_FINGERPRINT


def test_fingerprint_ignores_declaration_key():
    """declaration_key is forensic only — NOT part of the fingerprint identity."""
    a = _cron_finding()
    b = CronDriftFinding(
        kind=a.kind, name=a.name, agent_id=a.agent_id, declaration_key="plugin:x"
    )
    assert state_mod.fingerprint_finding(b, BASELINE_HASH_A) == PINNED_STR_AGENT_FINGERPRINT


def test_reconcile_null_agent_finding_alerts_and_persists_str_name(tmp_path: Path):
    finding = _null_agent_finding()
    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], T0, {}
    )

    assert to_alert == [finding]
    assert resolved == []
    assert len(new_state) == 1
    entry = next(iter(new_state.values()))
    assert entry["name"] == "Memory Dreaming Promotion"
    assert all(isinstance(v, str) for v in entry.values())

    # Round-trips through save/load and does not re-alert before 24h.
    path = tmp_path / "seen.json"
    state_mod.save_state(new_state, path)
    loaded = state_mod.load_state(path)
    to_alert2, _, _ = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], T0 + timedelta(minutes=15), loaded
    )
    assert to_alert2 == []


# --- #1128: injective fingerprint encoding -----------------------------------


def test_fingerprint_pipe_collision_pair_is_distinct():
    """The filed pair: legacy '|'.join made both canonical strings identical."""
    a = CronDriftFinding(kind="unapproved_present", name="a|x", agent_id="y")
    b = CronDriftFinding(kind="unapproved_present", name="a", agent_id="x|y")
    assert state_mod.fingerprint_finding(a, BASELINE_HASH_A) != state_mod.fingerprint_finding(
        b, BASELINE_HASH_A
    )


def test_fingerprint_pipe_field_uses_v2_json_encoding():
    finding = CronDriftFinding(kind="unapproved_present", name="a|x", agent_id="y")
    expected_canonical = "v2:" + json.dumps(
        ["cron", "unapproved_present", "a|x", "y", BASELINE_HASH_A]
    )
    assert state_mod.fingerprint_finding(finding, BASELINE_HASH_A) == hashlib.sha256(
        expected_canonical.encode("utf-8")
    ).hexdigest()


def test_fingerprint_pipe_in_assertion_field_is_distinct():
    a = AssertionFinding(
        kind="artifact_missing", agent="m|a", artifact_kind="k", artifact_id="1", claim="c"
    )
    b = AssertionFinding(
        kind="artifact_missing", agent="m", artifact_kind="a|k", artifact_id="1", claim="c"
    )
    assert state_mod.fingerprint_finding(a, "h") != state_mod.fingerprint_finding(b, "h")


def test_fingerprint_v2_lone_surrogate_does_not_raise():
    finding = CronDriftFinding(kind="unapproved_present", name="a|\ud800", agent_id="y")
    fp = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    assert len(fp) == 64


def test_canonical_helper_documents_and_keeps_legacy_encoding():
    assert state_mod._canonical(("cron", "k", "n", "a", "h")) == "cron|k|n|a|h"
    assert state_mod._canonical(("cron", "k", "n|x", "a", "h")).startswith("v2:[")


def test_fingerprint_unencodable_pipe_free_part_routes_to_v2():
    """A lone surrogate with no pipe cannot be UTF-8 encoded on the legacy
    path; it must route to v2 (ASCII-escaped) instead of raising."""
    finding = CronDriftFinding(kind="unapproved_present", name="a\ud800", agent_id="y")
    expected_canonical = "v2:" + json.dumps(
        ["cron", "unapproved_present", "a\ud800", "y", BASELINE_HASH_A]
    )
    assert state_mod.fingerprint_finding(finding, BASELINE_HASH_A) == hashlib.sha256(
        expected_canonical.encode("utf-8")
    ).hexdigest()


# --- #1126: duplicate_present identity is 5-field -----------------------------


def _dup_finding(cron_id, name="inbox-5pm", agent_id="felix-admin-capture"):
    return CronDriftFinding(
        kind="duplicate_present",
        name=name,
        agent_id=agent_id,
        cron_id=cron_id,
        primary_cron_id="primary",
    )


def test_duplicate_present_fingerprint_is_five_field_identity():
    expected = hashlib.sha256(
        "cron|duplicate_present|inbox-5pm|felix-admin-capture|dup-1|h".encode("utf-8")
    ).hexdigest()
    assert state_mod.fingerprint_finding(_dup_finding("dup-1"), "h") == expected


def test_duplicate_present_distinct_cron_ids_distinct_fingerprints():
    assert state_mod.fingerprint_finding(_dup_finding("d1"), "h") != state_mod.fingerprint_finding(
        _dup_finding("d2"), "h"
    )


def test_duplicate_present_id_less_uses_sentinel_and_null_agent_sentinel():
    expected = hashlib.sha256(
        "cron|duplicate_present|n|\x00none|\x00noid|h".encode("utf-8")
    ).hexdigest()
    assert (
        state_mod.fingerprint_finding(_dup_finding(None, name="n", agent_id=None), "h") == expected
    )
    # An id-less copy never collides with a real id.
    for real in ("", "noid", "\x00none"):
        assert state_mod.fingerprint_finding(_dup_finding(None), "h") != state_mod.fingerprint_finding(
            _dup_finding(real), "h"
        ), real


def test_duplicate_present_resolution_name_names_the_copy():
    assert state_mod._finding_name(_dup_finding("d1")) == "inbox-5pm (duplicate d1)"
    assert state_mod._finding_name(_dup_finding(None)) == "inbox-5pm (duplicate no-id)"


def test_enabled_state_and_primary_fields_not_fingerprinted():
    base = CronDriftFinding(kind="enabled_mismatch", name="n", agent_id="a")
    rich = CronDriftFinding(
        kind="enabled_mismatch",
        name="n",
        agent_id="a",
        cron_id="c",
        enabled_state="malformed",
        enabled_raw="'yes'",
        primary_cron_id="p",
    )
    assert state_mod.fingerprint_finding(base, "h") == state_mod.fingerprint_finding(rich, "h")


# --- #1126 duplicate lifecycle through reconcile (pre-merge review) ----------

_INBOX_BASELINE = [
    ApprovedCron(
        name="inbox-5pm",
        agent_id="felix-admin-capture",
        schedule_expr="0 17 * * *",
        tz="America/New_York",
        purpose="p",
        approved_by="kent",
        approved_at="2026-07-10",
    )
]


def _inbox_job(id_, created, enabled=True):
    return {
        "id": id_,
        "name": "inbox-5pm",
        "agentId": "felix-admin-capture",
        "enabled": enabled,
        "createdAtMs": created,
        "schedule": {"kind": "cron", "expr": "0 17 * * *", "tz": "America/New_York"},
    }


def _tick(live, now, state):
    findings = detect_cron_drift(live, _INBOX_BASELINE)
    return findings, *state_mod.reconcile([(f, BASELINE_HASH_A) for f in findings], now, state)


def test_two_tick_disabling_primary_does_not_churn_duplicate_identity():
    """Tick 1: approved copies A (older) and B, both enabled. Tick 2: A is
    disabled. B's duplicate_present fingerprint must not change (no new
    alert, no resolve); A gets enabled_mismatch."""
    _, to_alert1, resolved1, state1 = _tick(
        [_inbox_job("A", 1000), _inbox_job("B", 2000)], T0, {}
    )
    assert [(f.kind, f.cron_id) for f in to_alert1] == [("duplicate_present", "B")]
    assert resolved1 == []
    (dup_fp,) = state1

    findings2, to_alert2, resolved2, state2 = _tick(
        [_inbox_job("A", 1000, enabled=False), _inbox_job("B", 2000)],
        T0 + timedelta(minutes=15),
        state1,
    )

    dup2 = [f for f in findings2 if f.kind == "duplicate_present"]
    assert [(f.cron_id, f.primary_cron_id) for f in dup2] == [("B", "A")]
    assert state_mod.fingerprint_finding(dup2[0], BASELINE_HASH_A) == dup_fp
    assert resolved2 == []
    assert [(f.kind, f.cron_id) for f in to_alert2] == [("enabled_mismatch", "A")]
    assert dup_fp in state2
    assert state2[dup_fp]["first_seen"] == state1[dup_fp]["first_seen"]


def test_duplicate_lifecycle_removed_copy_resolves_with_named_copy():
    _, _, _, state1 = _tick([_inbox_job("A", 1000), _inbox_job("B", 2000)], T0, {})

    _, to_alert2, resolved2, state2 = _tick(
        [_inbox_job("A", 1000)], T0 + timedelta(minutes=15), state1
    )

    assert to_alert2 == []
    assert state2 == {}
    (event,) = resolved2
    assert event.name == "inbox-5pm (duplicate B)"
    assert event.source == "cron"
    alert = render_drift_resolved(
        event.name, event.first_seen, event.cleared_at, source=event.source
    )
    assert alert.title.startswith("Cron drift cleared:")
    assert alert.title == "Cron drift cleared: inbox-5pm (duplicate B)"


# --- #1129: a sub-scan that did not complete never resolves its findings ------


def _seen_entry(source: str | None, name: str, **extra: str) -> dict[str, str]:
    entry = {
        "first_seen": state_mod._utc_iso(T0),
        "last_seen": state_mod._utc_iso(T0),
        "last_alerted": state_mod._utc_iso(T0),
        "name": name,
        **extra,
    }
    if source is not None:
        entry["source"] = source
    return entry


def _three_source_state() -> dict[str, dict[str, str]]:
    """One outstanding entry per source, none of them in the current findings."""
    return {
        "fp-cron": _seen_entry("cron", "rogue-cron"),
        "fp-unit": _seen_entry("unit-drift", "felix-canary.service"),
        "fp-assert": _seen_entry(
            "assertion",
            "vikunja_task:91",
            assertion_kind="artifact_missing",
            artifact_kind="vikunja_task",
            artifact_id="91",
            agent="main",
            claim="c",
        ),
    }


def test_source_constants_keep_their_persisted_values():
    # The tags are persisted in seen-state: renaming a value would orphan it.
    assert state_mod.SOURCE_CRON == "cron"
    assert state_mod.SOURCE_ASSERTION == "assertion"
    assert state_mod.SOURCE_UNIT == "unit-drift"
    assert state_mod.ALL_SOURCES == frozenset({"cron", "assertion", "unit-drift"})


def test_finding_source_covers_exactly_all_sources():
    """One instance of each finding class maps onto ALL_SOURCES, no more, no less."""
    findings = [_cron_finding(), _assertion_finding(), _unit_finding()]
    assert {state_mod._finding_source(f) for f in findings} == state_mod.ALL_SOURCES


@pytest.mark.parametrize(
    "completed, resolved_fp",
    [
        (frozenset({"cron"}), "fp-cron"),
        (frozenset({"unit-drift"}), "fp-unit"),
        (frozenset({"assertion"}), "fp-assert"),
    ],
)
def test_reconcile_absent_entry_of_uncompleted_source_is_carried(completed, resolved_fp):
    seeded = _three_source_state()
    now = T0 + timedelta(hours=1)

    to_alert, resolved, new_state = state_mod.reconcile(
        [], now, seeded, completed_sources=completed
    )

    assert to_alert == []
    # Only the completed source resolves.
    assert [e.fingerprint for e in resolved] == [resolved_fp]
    assert resolved_fp not in new_state
    # Every other entry is carried forward identical: no last_seen refresh.
    carried = set(seeded) - {resolved_fp}
    assert set(new_state) == carried
    for fp in carried:
        assert new_state[fp] == seeded[fp]


def test_reconcile_carried_entry_is_a_copy_not_an_alias():
    seeded = _three_source_state()
    _, _, new_state = state_mod.reconcile([], T0, seeded, completed_sources=frozenset())
    new_state["fp-cron"]["last_alerted"] = "mutated"
    assert seeded["fp-cron"]["last_alerted"] == state_mod._utc_iso(T0)


def test_reconcile_no_completed_sources_carries_everything_and_resolves_nothing():
    seeded = _three_source_state()
    to_alert, resolved, new_state = state_mod.reconcile(
        [], T0 + timedelta(hours=1), seeded, completed_sources=frozenset()
    )
    assert to_alert == []
    assert resolved == []
    assert new_state == seeded


def test_reconcile_present_entry_of_uncompleted_source_is_updated_as_today():
    """A partial result is still real evidence of presence."""
    finding = _cron_finding()
    fp = state_mod.fingerprint_finding(finding, BASELINE_HASH_A)
    seeded = {fp: _seen_entry("cron", "mystery-cron")}
    now = T0 + timedelta(hours=1)

    to_alert, resolved, new_state = state_mod.reconcile(
        [(finding, BASELINE_HASH_A)], now, seeded, completed_sources=frozenset()
    )

    assert to_alert == []  # not due (<24h)
    assert resolved == []
    assert new_state[fp]["last_seen"] == state_mod._utc_iso(now)


def test_reconcile_completed_sources_none_is_todays_behaviour():
    seeded = _three_source_state()
    _, resolved_none, state_none = state_mod.reconcile([], T0, seeded)
    _, resolved_all, state_all = state_mod.reconcile(
        [], T0, seeded, completed_sources=state_mod.ALL_SOURCES
    )
    assert {e.fingerprint for e in resolved_none} == set(seeded)
    assert state_none == {}
    assert resolved_none == resolved_all
    assert state_none == state_all


@pytest.mark.parametrize("source", [None, "bogus-source"], ids=["missing", "unknown"])
def test_reconcile_missing_or_unknown_source_is_treated_as_cron(source):
    seeded = {"fp-odd": _seen_entry(source, "odd")}

    # Cron did not complete -> carried, even though the tag is not "cron".
    _, resolved, new_state = state_mod.reconcile(
        [], T0, seeded, completed_sources=frozenset({"assertion", "unit-drift"})
    )
    assert resolved == []
    assert new_state == seeded

    # Cron completed -> resolved, and the event routes as a cron resolution.
    _, resolved, new_state = state_mod.reconcile(
        [], T0, seeded, completed_sources=frozenset({"cron"})
    )
    assert new_state == {}
    (event,) = resolved
    assert event.source == "cron"


@pytest.mark.parametrize(
    "completed",
    [frozenset({"cron", "unit"}), frozenset({"bogus"})],
    ids=["identity-tag-not-source-tag", "unknown"],
)
def test_reconcile_rejects_completed_sources_outside_all_sources(completed):
    with pytest.raises(ValueError):
        state_mod.reconcile([], T0, _three_source_state(), completed_sources=completed)
