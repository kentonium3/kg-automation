"""Unit tests for scripts.canary.dedup (WP04 T016 / T021).

Deterministic: ``now`` is always injected, never ``datetime.now()``. The headline
test proves the F7 / INV-F guarantee — the ``failed → healthy → failed`` sequence
emits all three transitions (keyed by ``component_id`` with ``last_outcome``, not
by ``(component_id, outcome)``).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.canary import dedup

T0 = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# decide() — transitions always emit.
# --------------------------------------------------------------------------- #
def test_first_observation_of_bad_outcome_emits():
    state: dict[str, dict[str, str]] = {}
    should_emit, is_recovery, entry = dedup.decide("svc", "failed", T0, state)
    assert should_emit is True
    assert is_recovery is False
    assert entry["last_outcome"] == "failed"


def test_transition_between_bad_outcomes_always_emits():
    # failed -> stale is a transition; emit regardless of window.
    state = {"svc": {"last_outcome": "failed", "last_emitted_utc": T0.isoformat()}}
    should_emit, is_recovery, entry = dedup.decide(
        "svc", "stale", T0 + timedelta(minutes=1), state
    )
    assert should_emit is True
    assert is_recovery is False
    assert entry["last_outcome"] == "stale"


def test_transition_to_healthy_is_recovery_info():
    state = {"svc": {"last_outcome": "failed", "last_emitted_utc": T0.isoformat()}}
    should_emit, is_recovery, entry = dedup.decide(
        "svc", "healthy", T0 + timedelta(minutes=1), state
    )
    assert should_emit is True
    assert is_recovery is True
    assert entry["last_outcome"] == "healthy"


def test_first_seen_healthy_is_not_a_recovery():
    # No prior outcome -> a healthy first observation must NOT emit a recovery.
    state: dict[str, dict[str, str]] = {}
    should_emit, is_recovery, entry = dedup.decide("svc", "healthy", T0, state)
    assert should_emit is False
    assert is_recovery is False
    assert entry["last_outcome"] == "healthy"


# --------------------------------------------------------------------------- #
# decide() — unchanged-bad within/after window.
# --------------------------------------------------------------------------- #
def test_unchanged_bad_within_window_suppresses():
    state = {"svc": {"last_outcome": "failed", "last_emitted_utc": T0.isoformat()}}
    should_emit, is_recovery, entry = dedup.decide(
        "svc", "failed", T0 + timedelta(hours=1), state
    )
    assert should_emit is False
    assert is_recovery is False
    # The prior emit time is carried forward (window not reset).
    assert entry["last_emitted_utc"] == T0.isoformat()


def test_unchanged_bad_window_elapsed_reemits():
    state = {"svc": {"last_outcome": "failed", "last_emitted_utc": T0.isoformat()}}
    later = T0 + timedelta(hours=6, minutes=1)
    should_emit, is_recovery, entry = dedup.decide("svc", "failed", later, state)
    assert should_emit is True
    assert is_recovery is False
    assert entry["last_emitted_utc"] == later.isoformat()


def test_custom_window_boundary_is_respected():
    state = {"svc": {"last_outcome": "failed", "last_emitted_utc": T0.isoformat()}}
    # 30-minute window; at exactly 30 minutes it is due (>=).
    should_emit, _, _ = dedup.decide(
        "svc", "failed", T0 + timedelta(minutes=30), state, window=timedelta(minutes=30)
    )
    assert should_emit is True


def test_unchanged_healthy_no_emit_no_churn():
    state = {"svc": {"last_outcome": "healthy", "last_emitted_utc": T0.isoformat()}}
    should_emit, is_recovery, entry = dedup.decide(
        "svc", "healthy", T0 + timedelta(hours=100), state
    )
    assert should_emit is False
    assert is_recovery is False
    assert entry["last_outcome"] == "healthy"


# --------------------------------------------------------------------------- #
# Headline: failed -> healthy -> failed emits all three (INV-F / F7).
# --------------------------------------------------------------------------- #
def test_failed_healthy_failed_emits_three_times():
    """The re-failure after a recovery must NOT be swallowed (F7).

    A ``(component_id, outcome)`` key would suppress the second ``failed`` because
    it had emitted a ``failed`` before. Keying by ``component_id`` with
    ``last_outcome`` makes each transition emit.
    """
    state: dict[str, dict[str, str]] = {}
    emits: list[tuple[str, bool]] = []

    for outcome, t in [
        ("failed", T0),
        ("healthy", T0 + timedelta(minutes=5)),
        # The re-failure lands well WITHIN the 6h window measured from the first
        # failure — a (id,outcome) design would suppress it. It must still emit.
        ("failed", T0 + timedelta(minutes=10)),
    ]:
        should_emit, is_recovery, entry = dedup.decide("svc", outcome, t, state)
        if should_emit:
            emits.append((outcome, is_recovery))
        state["svc"] = entry

    assert emits == [("failed", False), ("healthy", True), ("failed", False)]


# --------------------------------------------------------------------------- #
# State I/O — fail-safe + atomic + round-trip.
# --------------------------------------------------------------------------- #
def test_load_state_missing_file_is_empty(tmp_path):
    assert dedup.load_state(tmp_path / "nope.json") == {}


def test_load_state_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "dedup.json"
    p.write_text("{ not json", encoding="utf-8")
    assert dedup.load_state(p) == {}


def test_load_state_non_object_is_empty(tmp_path):
    p = tmp_path / "dedup.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert dedup.load_state(p) == {}


def test_save_then_load_round_trips(tmp_path):
    p = tmp_path / "state" / "dedup.json"
    state = {"svc": {"last_outcome": "failed", "last_emitted_utc": T0.isoformat()}}
    dedup.save_state(state, p)
    assert dedup.load_state(p) == state
    # Atomic write leaves no stray temp files behind.
    assert [q.name for q in p.parent.iterdir()] == ["dedup.json"]


def test_load_state_drops_malformed_entries(tmp_path):
    p = tmp_path / "dedup.json"
    p.write_text(
        '{"good": {"last_outcome": "failed", "last_emitted_utc": "x"}, '
        '"bad": {"last_outcome": 5}}',
        encoding="utf-8",
    )
    loaded = dedup.load_state(p)
    assert "good" in loaded
    assert "bad" not in loaded


def test_decide_never_calls_datetime_now(monkeypatch):
    # A guard: if decide() reached for wall-clock time, this would blow up.
    # Proxy the real datetime for everything (fromisoformat etc.) but make .now
    # raise, so only a stray datetime.now() call fails.
    import scripts.canary.dedup as dedup_mod

    real_datetime = dedup_mod.datetime

    class _NoNow:
        def __getattr__(self, name):
            if name == "now":
                raise AssertionError("decide must not call datetime.now()")
            return getattr(real_datetime, name)

    monkeypatch.setattr(dedup_mod, "datetime", _NoNow())
    state = {"svc": {"last_outcome": "failed", "last_emitted_utc": T0.isoformat()}}
    # Should complete purely off the injected `now`.
    dedup.decide("svc", "failed", T0 + timedelta(hours=7), state)
