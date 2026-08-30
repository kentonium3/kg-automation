"""Ledger-aware freshness binding and the future-skew guard (WP04, T017/T018).

Two properties that only exist once ``health_check.key_ledger`` is wired into
``_probe_freshness``:

* T017 — a ledger declaring ``freshness``/``anchor: true`` on a key makes THAT
  key the staleness anchor, resolved specifically, never a fall-through to
  :data:`TIMESTAMP_KEYS`'s ordered candidate list. Without the binding, the
  candidate-list order (not the ledger) would silently decide the anchor.
* T018 — a resolved freshness timestamp more than 5 minutes in the future
  (:data:`~scripts.canary.probes._FUTURE_SKEW_TOLERANCE`, strict ``>``) is not
  fresh. Without this guard ``age = now - ts`` is negative for a future-dated
  timestamp, never exceeds any budget, and a skewed clock pins the component
  fresh forever.

Both properties are exercised through the REAL ``run_probe`` dispatcher — a
hand-rolled judge would not exercise the actual wiring these tests exist to
pin.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.canary.probes import run_probe

NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def judge(tmp_path):
    ptr = tmp_path / "pointer.json"

    def _judge(payload: dict, *, key_ledger: dict | None = None, max_age_seconds=100800):
        ptr.write_text(json.dumps(payload))
        hc = {
            "method": "state-file",
            "state_path": str(ptr),
            "max_age_seconds": max_age_seconds,
        }
        if key_ledger is not None:
            hc["key_ledger"] = key_ledger
        return run_probe(
            hc, NOW, http_get=None, run_cmd=None,
            read_state=lambda p: json.loads(Path(p).read_text()),
        )

    _judge.now = NOW
    return _judge


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# T017 — the declared freshness key is the anchor, not TIMESTAMP_KEYS order
# --------------------------------------------------------------------------- #

# Minimal ledger declaring only the anchor key — deliberately narrow so this
# test exercises exactly the binding mechanism, not the full adjudication
# surface (that is T023's job, against the real restic-backup ledger).
ANCHOR_LEDGER = {
    "reconciliation_harness": "tests/fake/does-not-need-to-exist-for-this-test.py",
    "adjudicated": {
        "snapshot_timestamp_utc": {"freshness": True, "anchor": True},
    },
    "diagnostic_only": {},
}


def _mixed_document(now):
    # completed_at_utc precedes snapshot_timestamp_utc in TIMESTAMP_KEYS, so
    # the ordered-candidate-list path resolves completed_at_utc (fresh) and
    # never looks at snapshot_timestamp_utc (stale) at all.
    return {
        "completed_at_utc": iso(now),  # fresh
        "snapshot_timestamp_utc": iso(now - timedelta(days=3)),  # stale
    }


def test_ledger_anchor_binds_to_declared_key_not_list_order(judge):
    """With the ledger attached, the declared anchor (snapshot_timestamp_utc)
    is judged — reads stale, even though completed_at_utc is both present and
    fresh and sorts first in TIMESTAMP_KEYS."""
    r = judge(_mixed_document(judge.now), key_ledger=ANCHOR_LEDGER,
              max_age_seconds=3600)
    assert r.evaluable
    assert r.stale, f"declared anchor must be judged, not the list-order key: {r.evidence}"


def test_without_ledger_same_document_resolves_via_timestamp_keys_order(judge):
    """Same document, no ledger: the pre-existing TIMESTAMP_KEYS behaviour is
    unchanged — completed_at_utc wins because it sorts first, so the document
    reads fresh even though snapshot_timestamp_utc (unused) is stale."""
    r = judge(_mixed_document(judge.now), key_ledger=None, max_age_seconds=3600)
    assert r.evaluable and r.ok
    assert not r.stale, (
        "a ledger-free component must still resolve via TIMESTAMP_KEYS order "
        f"exactly as before: {r.evidence}"
    )
    assert "completed_at_utc" in r.evidence


def test_ledger_anchor_evidence_names_the_judged_key(judge):
    """The evidence must name the key actually judged (the anchor), not a
    TIMESTAMP_KEYS candidate that was never consulted."""
    r = judge(_mixed_document(judge.now), key_ledger=ANCHOR_LEDGER,
              max_age_seconds=3600)
    assert "snapshot_timestamp_utc" in r.evidence
    assert "completed_at_utc" not in r.evidence


def test_ledger_anchor_fresh_when_within_bound(judge):
    """Sanity check on the healthy side: the anchor being fresh reads fresh,
    even with an unrelated fresh non-anchor key elsewhere in the document."""
    payload = {
        "completed_at_utc": iso(judge.now - timedelta(days=30)),  # would be
                                                                    # stale if
                                                                    # consulted
        "snapshot_timestamp_utc": iso(judge.now),  # fresh
    }
    r = judge(payload, key_ledger=ANCHOR_LEDGER, max_age_seconds=3600)
    assert r.evaluable and r.ok and not r.stale
    assert "snapshot_timestamp_utc" in r.evidence


# --------------------------------------------------------------------------- #
# T018 — the future-dating boundary (5 minutes, strict `>`)
# --------------------------------------------------------------------------- #

def test_one_second_inside_skew_tolerance_is_fresh(judge):
    """T − 1s in the future: skew (299s) is NOT > the 300s tolerance → fresh.

    The boundary sits so that skew == tolerance is still fresh — only
    STRICTLY greater than 300s counts as future-dated (matching the sibling
    guard's strict `>` in scripts/deploy/lib/snapshot.py).
    """
    future_ts = judge.now + timedelta(minutes=5) - timedelta(seconds=1)
    payload = {"completed_at_utc": iso(future_ts)}
    r = judge(payload, max_age_seconds=100800)
    assert r.evaluable and r.ok
    assert not r.stale, f"1s inside tolerance must read fresh: {r.evidence}"


def test_one_second_past_skew_tolerance_is_not_fresh(judge):
    """T + 1s in the future: skew (301s) IS > the 300s tolerance → not fresh."""
    future_ts = judge.now + timedelta(minutes=5) + timedelta(seconds=1)
    payload = {"completed_at_utc": iso(future_ts)}
    r = judge(payload, max_age_seconds=100800)
    assert r.evaluable
    assert r.stale, f"1s past tolerance must not read fresh: {r.evidence}"
    assert "future-dated" in r.evidence


def test_future_skew_guard_applies_without_a_ledger(judge):
    """The guard is not ledger-scoped (T022 point 3) — a ledger-free
    component with a wildly future timestamp must not be pinned fresh
    forever."""
    far_future = judge.now + timedelta(days=10)
    payload = {"completed_at_utc": iso(far_future)}
    r = judge(payload, key_ledger=None, max_age_seconds=100800)
    assert r.evaluable and r.stale


def test_future_skew_guard_applies_to_ledger_anchor(judge):
    """The guard also applies through the ledger anchor-resolution path."""
    far_future = judge.now + timedelta(days=10)
    payload = {
        "completed_at_utc": iso(judge.now),
        "snapshot_timestamp_utc": iso(far_future),
    }
    r = judge(payload, key_ledger=ANCHOR_LEDGER, max_age_seconds=100800)
    assert r.evaluable and r.stale
    assert "snapshot_timestamp_utc" in r.evidence


def test_naive_timestamp_becomes_unknown_not_a_crash(judge):
    """A naive ISO value (no UTC offset) parses to a naive datetime;
    comparing it against the aware `now` raises TypeError inside the probe,
    which `run_probe`'s dispatcher catches and maps to `unknown` (evaluable
    False) — never a raised exception out of run_probe, and never silently
    treated as fresh. This is pre-existing behaviour for the bound
    comparison; the guard must not widen or narrow that surface."""
    payload = {"completed_at_utc": "2026-07-11T11:59:00"}  # no trailing Z/offset
    r = judge(payload, max_age_seconds=100800)
    assert not r.evaluable, (
        "a naive timestamp must be handled deliberately (mapped to unknown "
        f"upstream), not crash run_probe or read healthy: {r}"
    )


def test_naive_timestamp_via_ledger_anchor_also_becomes_unknown(judge):
    """Same TypeError-to-unknown behaviour through the ledger anchor path."""
    payload = {
        "completed_at_utc": iso(judge.now),
        "snapshot_timestamp_utc": "2026-07-08T11:59:00",  # naive
    }
    r = judge(payload, key_ledger=ANCHOR_LEDGER, max_age_seconds=100800)
    assert not r.evaluable


def test_normal_recent_past_timestamp_is_unaffected_by_the_guard(judge):
    """A normal recent-past timestamp must read exactly as before — the
    guard only fires on future-dated values."""
    recent = judge.now - timedelta(minutes=15)
    payload = {"completed_at_utc": iso(recent)}
    r = judge(payload, max_age_seconds=2100)
    assert r.evaluable and r.ok and not r.stale
