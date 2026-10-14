"""Verdicts of the canary's real tick declaration (FR-011, #1063).

``felix-canary``'s tick signal used to be judged by the legacy
``tick-signal-file`` conventions, which read four "ticked but did nothing" or
"ticked but not successfully" shapes as healthy (reproduced 2026-10-14,
Codex post-plan finding 1):

* ``status`` missing;
* ``status`` ``partial`` (a deny-list never names it);
* ``completed_at_utc`` unusable while another candidate timestamp is fresh
  (the first *parseable* candidate wins);
* ``components_evaluated: 0``.

felix-health-check (#1063) uses this declaration as its dead-man's switch on
the canary, so each of those would have read a dark canary as alive. The
declaration now carries a ``key_ledger`` that makes liveness affirmative.

These tests run the shipped declaration from the real inventory through the
canary's own evaluator. A test copy of the declaration would prove nothing
about what ships.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.canary import health, registry

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"

# Captured verbatim from office2 /data/services/felix-canary/state/last-tick.json
# on 2026-10-14 (charter: fixtures mirror real inputs).
REAL_TICK: dict = {
    "completed_at_utc": "2026-10-14T18:44:16.390963+00:00",
    "components_evaluated": 32,
    "coverage_gaps": 0,
    "duration_ms": 4966,
    "emitted": 0,
    "errors": [],
    "status": "success",
    "suppressed_dedup": 1,
    "suppressed_status": 4,
}
TICK_AT = datetime(2026, 10, 14, 18, 44, 16, 390963, tzinfo=timezone.utc)
FRESH_NOW = TICK_AT + timedelta(minutes=5)


def _refuse(*_a, **_k):
    raise RuntimeError("the tick declaration must be judged from the file alone")


def _target() -> registry.CanaryTarget:
    targets, _gaps = registry.load_targets(registry.load_inventory(INVENTORY))
    matches = [t for t in targets if t.component_id == "felix-canary"]
    assert len(matches) == 1, "felix-canary must appear exactly once in the inventory"
    return matches[0]


def _verdict(doc: dict, now: datetime = FRESH_NOW) -> health.HealthResult:
    return health.evaluate(
        _target(), now, http_get=_refuse, run_cmd=_refuse, read_state=lambda _p: doc
    )


def _tick(**changes) -> dict:
    doc = copy.deepcopy(REAL_TICK)
    for key, value in changes.items():
        if value is _DROP:
            doc.pop(key)
        else:
            doc[key] = value
    return doc


_DROP = object()


def test_real_tick_is_healthy():
    """Positive control: the same fixture every negative case is derived from."""
    result = _verdict(_tick())
    assert result.outcome == "healthy", result.evidence


def test_declaration_carries_a_ledger():
    """The four cases below are only rejected because of this ledger."""
    ledger = (_target().health_check or {}).get("key_ledger")
    assert isinstance(ledger, dict), "felix-canary must declare a key_ledger (FR-011)"


@pytest.mark.parametrize(
    "case, doc",
    [
        ("status missing", _tick(status=_DROP)),
        ("status partial", _tick(status="partial")),
        ("status error", _tick(status="error")),
        ("status null", _tick(status=None)),
        (
            "broken anchor with a fresh fallback timestamp",
            _tick(completed_at_utc="garbage", timestamp_utc=FRESH_NOW.isoformat()),
        ),
        ("anchor missing with a fresh fallback timestamp",
         _tick(completed_at_utc=_DROP, timestamp_utc=FRESH_NOW.isoformat())),
        ("zero components evaluated", _tick(components_evaluated=0)),
        ("components_evaluated missing", _tick(components_evaluated=_DROP)),
    ],
)
def test_do_nothing_or_unsuccessful_tick_is_not_alive(case, doc):
    # Pinned to "failed", not merely "not healthy": a silent downgrade to
    # "unknown" would stop the canary paging on a first sighting.
    result = _verdict(doc)
    assert result.outcome == "failed", f"{case}: {result.outcome} ({result.evidence})"


def test_broken_anchor_evidence_names_the_anchor():
    result = _verdict(_tick(completed_at_utc="garbage", timestamp_utc=FRESH_NOW.isoformat()))
    assert "completed_at_utc" in result.evidence


def test_seventeen_day_old_tick_is_stale():
    """The 2026-09-27 -> 10-14 shape: a canary that stopped ticking."""
    result = _verdict(_tick(), now=TICK_AT + timedelta(days=17))
    assert result.outcome == "stale", result.evidence


def test_future_dated_tick_is_stale():
    result = _verdict(_tick(completed_at_utc=(FRESH_NOW + timedelta(hours=1)).isoformat()))
    assert result.outcome == "stale", result.evidence


def test_fixture_matches_the_captured_document():
    """Guard against the fixture drifting into an invented shape."""
    assert set(REAL_TICK) == {
        "completed_at_utc", "components_evaluated", "coverage_gaps", "duration_ms",
        "emitted", "errors", "status", "suppressed_dedup", "suppressed_status",
    }
