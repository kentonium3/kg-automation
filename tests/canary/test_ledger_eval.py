"""Unit tests for scripts.canary.ledger.

Offline, deterministic, no filesystem, no network. Every test constructs its
own ledger and document inline (contract Test Strategy). ``now`` is always
injected, never ``datetime.now()`` (matches ``tests/canary/test_probes.py``).

Covers T012 (membership / type identity, both collision directions),
T013 (absence + unmeasured), T014 (totality against hostile input), and T016
(first-run suppression, both directions). T015 (the evaluator itself) is
exercised throughout rather than as a section of its own.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from scripts.canary.ledger import (
    FreshnessObligation,
    LedgerResult,
    evaluate,
)

NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def _ledger(**adjudicated: dict) -> dict:
    return {"adjudicated": adjudicated}


# --------------------------------------------------------------------------- #
# T012 — membership semantics, all four collision directions + ordinary cases
# --------------------------------------------------------------------------- #

# (value, good_values, expected_match) — the four dangerous collisions plus
# the three ordinary cases the contract lists alongside them.
_MEMBERSHIP_CASES = [
    pytest.param(1, [True, None], False, id="int-1-vs-bool-good-set"),
    pytest.param(0, [False], False, id="int-0-vs-bool-false-good-set"),
    pytest.param(False, [0, 3], False, id="bool-false-vs-int-good-set"),
    pytest.param(True, [1], False, id="bool-true-vs-int-good-set"),
    pytest.param(0, [0, 3], True, id="ordinary-int-match"),
    pytest.param(True, [True, None], True, id="ordinary-bool-match"),
    pytest.param(None, [True, None], True, id="ordinary-null-match"),
]


@pytest.mark.parametrize("value,good_values,expected_match", _MEMBERSHIP_CASES)
def test_good_values_membership_type_identity(value, good_values, expected_match):
    ledger = _ledger(k={"good_values": good_values})
    result = evaluate({"k": value}, ledger, now=NOW)
    if expected_match:
        assert result.outcome == "ok"
    else:
        assert result.outcome == "unhealthy"
        assert "k" in result.evidence


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("false", id="string"),
        pytest.param(3.5, id="float"),
        pytest.param([0, 3], id="list"),
    ],
)
def test_value_outside_good_set_unhealthy_regardless_of_type(value):
    ledger = _ledger(k={"good_values": [0, 3]})
    result = evaluate({"k": value}, ledger, now=NOW)
    assert result.outcome == "unhealthy"
    assert "k" in result.evidence
    assert repr(value) in result.evidence


# --------------------------------------------------------------------------- #
# T013 — absence, and the unmeasured case
# --------------------------------------------------------------------------- #

_ABSENT_PREDICATES = [
    pytest.param({"good_values": [True, None]}, id="good_values-with-null-in-set"),
    pytest.param({"minimum": 2}, id="minimum"),
    pytest.param({"freshness": True, "anchor": True}, id="freshness"),
]


@pytest.mark.parametrize("predicate", _ABSENT_PREDICATES)
def test_absent_adjudicated_key_is_unhealthy_for_every_predicate_form(predicate):
    ledger = _ledger(k=predicate)
    result = evaluate({}, ledger, now=NOW)
    assert result.outcome == "unhealthy"
    assert "k" in result.evidence
    assert "not emitted" in result.evidence


def test_present_null_with_unmeasured_is_unknown_yields_unknown():
    ledger = _ledger(k={"minimum": 2, "unmeasured_is_unknown": True})
    result = evaluate({"k": None}, ledger, now=NOW)
    assert result.outcome == "unknown"
    assert "k" in result.evidence


def test_present_null_without_unmeasured_flag_is_unhealthy():
    ledger = _ledger(k={"minimum": 2})
    result = evaluate({"k": None}, ledger, now=NOW)
    assert result.outcome == "unhealthy"
    assert "k" in result.evidence


@pytest.mark.parametrize(
    "predicate,value",
    [
        pytest.param({"good_values": [1, 2, 3]}, 99, id="good_values"),
        pytest.param({"minimum": 100}, 1, id="minimum"),
        pytest.param({"minimum": 100, "unmeasured_is_unknown": True}, None, id="minimum-null-unknown"),
    ],
)
def test_diagnostic_only_keys_never_influence_verdict(predicate, value):
    # A key that would fail its predicate has NO effect when it lives only in
    # diagnostic_only -- evaluate() never even looks there, since it iterates
    # `adjudicated` exclusively. Ledger below adjudicates nothing, so the
    # document must read healthy no matter what a `diagnostic_only`-shaped key
    # carries.
    ledger = {
        "adjudicated": {},
        "diagnostic_only": {"d": {"reason": "not health-bearing"}},
    }
    document = {"d": value}
    result = evaluate(document, ledger, now=NOW)
    assert result.outcome == "ok"


# --------------------------------------------------------------------------- #
# T014 — totality: hostile inputs never raise
# --------------------------------------------------------------------------- #

_GOOD_LEDGER = _ledger(
    k={"good_values": [0, 3]},
    m={"minimum": 2},
    f={"freshness": True, "anchor": True},
)

# Raw values (not pytest.param) so the combinatorial test below can iterate
# them directly; ids are attached separately for the individual parametrize.
_HOSTILE_DOCUMENTS_RAW: list[tuple[str, object]] = [
    ("document-none", None),
    ("document-string", "not-a-dict"),
    ("document-list", ["not", "a", "dict"]),
    ("document-int", 42),
    ("nested-scalar-slot", {"k": {"nested": "structure"}, "m": 5, "f": "x"}),
    ("list-in-scalar-slot", {"k": [1, 2, 3], "m": 5, "f": "x"}),
    ("minimum-vs-string", {"k": 0, "m": "not-a-number", "f": "x"}),
    ("freshness-non-string-value", {"k": 0, "m": 2, "f": 12345}),
    ("freshness-non-string-nested", {"k": 0, "m": 2, "f": {"nested": True}}),
    ("very-long-string", {"k": "x" * 100_000, "m": 2, "f": "x"}),
    ("unicode-string", {"k": "éè\U0001f600" * 100, "m": 2, "f": "x"}),
]


@pytest.mark.parametrize(
    "document", [pytest.param(v, id=i) for i, v in _HOSTILE_DOCUMENTS_RAW]
)
def test_hostile_documents_never_raise_and_are_decided(document):
    result = evaluate(document, _GOOD_LEDGER, now=NOW)
    assert isinstance(result, LedgerResult)
    assert result.outcome in ("ok", "unhealthy", "unknown")
    assert result.evidence


_HOSTILE_LEDGERS_RAW: list[tuple[str, object]] = [
    ("predicate-no-fields", {"adjudicated": {"k": {}}}),
    ("predicate-two-fields", {"adjudicated": {"k": {"good_values": [1], "minimum": 5}}}),
    ("predicate-not-a-dict", {"adjudicated": {"k": "not-a-dict"}}),
    ("predicate-none", {"adjudicated": {"k": None}}),
    ("good_values-not-a-list", {"adjudicated": {"k": {"good_values": "not-a-list"}}}),
    ("good_values-empty", {"adjudicated": {"k": {"good_values": []}}}),
    (
        "good_values-unhashable-candidates",
        {"adjudicated": {"k": {"good_values": [[1, 2], {"a": 1}, {"b": [1, 2]}]}}},
    ),
    ("minimum-not-a-number", {"adjudicated": {"k": {"minimum": "five"}}}),
    ("minimum-is-bool", {"adjudicated": {"k": {"minimum": True}}}),
    (
        "suppress_until_utc-not-a-string",
        {"adjudicated": {"k": {"minimum": 2, "suppress_until_utc": 12345}}},
    ),
    (
        "suppress_until_utc-unparseable",
        {"adjudicated": {"k": {"minimum": 2, "suppress_until_utc": "not-a-date"}}},
    ),
    (
        "max_age_seconds-not-a-number",
        {"adjudicated": {"k": {"freshness": True, "max_age_seconds": "soon"}}},
    ),
    ("adjudicated-not-a-dict", {"adjudicated": "not-a-dict"}),
    ("adjudicated-none", {"adjudicated": None}),
    ("ledger-not-a-dict", "not-a-dict"),
    ("ledger-no-adjudicated-key", {}),
]


@pytest.mark.parametrize(
    "ledger", [pytest.param(v, id=i) for i, v in _HOSTILE_LEDGERS_RAW]
)
def test_hostile_ledgers_never_raise_and_are_decided(ledger):
    document = {"k": 0}
    result = evaluate(document, ledger, now=NOW)
    assert isinstance(result, LedgerResult)
    assert result.outcome in ("ok", "unhealthy", "unknown")


def test_hostile_ledger_and_hostile_document_combined_never_raises():
    for _, ledger in _HOSTILE_LEDGERS_RAW:
        for _, document in _HOSTILE_DOCUMENTS_RAW:
            result = evaluate(document, ledger, now=NOW)
            assert isinstance(result, LedgerResult)
            assert result.outcome in ("ok", "unhealthy", "unknown")


# --------------------------------------------------------------------------- #
# T016 — first-run suppression (suppress_until_utc), both directions
# --------------------------------------------------------------------------- #

def test_suppress_until_utc_in_future_predicate_not_evaluated():
    future = (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    ledger = _ledger(k={"minimum": 2, "suppress_until_utc": future})
    # value=1 would fail the floor outright -- but the exemption is still
    # active, so the predicate must not even be evaluated.
    result = evaluate({"k": 1}, ledger, now=NOW)
    assert result.outcome == "ok"


def test_suppress_until_utc_in_past_evaluated_normally_and_still_catches_the_wipe_case():
    past = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    ledger = _ledger(k={"minimum": 2, "suppress_until_utc": past})
    # An established repository reporting 1 AFTER its exemption has expired
    # is exactly the wipe case this rule exists to catch -- must still alert.
    result = evaluate({"k": 1}, ledger, now=NOW)
    assert result.outcome == "unhealthy"
    assert "k" in result.evidence


def test_suppress_until_utc_exactly_at_now_is_evaluated_normally():
    # `now < suppress_until` is strict, so an instant equal to `now` is no
    # longer suppressed.
    at_now = NOW.isoformat().replace("+00:00", "Z")
    ledger = _ledger(k={"minimum": 2, "suppress_until_utc": at_now})
    result = evaluate({"k": 1}, ledger, now=NOW)
    assert result.outcome == "unhealthy"


def test_suppress_until_utc_does_not_override_absence():
    # Absence is unconditional (P4) -- an active exemption does not rescue a
    # key the producer stopped emitting altogether.
    future = (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    ledger = _ledger(k={"minimum": 2, "suppress_until_utc": future})
    result = evaluate({}, ledger, now=NOW)
    assert result.outcome == "unhealthy"
    assert "not emitted" in result.evidence


# Review cycle 1 defect: a malformed suppress_until_utc is NOT a valid,
# deliberate exemption, so it must fall through to the ordinary `minimum`
# verdict -- never decide `unknown` on its own. `unknown` is not neutral (a
# first-seen unknown is recorded WITHOUT alerting), so treating a typo'd
# modifier as "unknown" would silently switch off a live health rule. Cover
# both a failing and a passing `minimum` for each malformed shape, to prove
# the modifier is genuinely IGNORED rather than inverted into either an
# always-pass or an always-unknown escape hatch.
@pytest.mark.parametrize(
    "malformed_suppress_until_utc",
    [
        pytest.param("not-a-date", id="non-timestamp-string"),
        pytest.param(123, id="non-string-int"),
        pytest.param(None, id="explicit-null"),
    ],
)
def test_malformed_suppress_until_utc_with_failing_minimum_is_unhealthy_not_unknown(
    malformed_suppress_until_utc,
):
    ledger = _ledger(k={"minimum": 2, "suppress_until_utc": malformed_suppress_until_utc})
    result = evaluate({"k": 1}, ledger, now=NOW)
    assert result.outcome == "unhealthy"
    assert "k" in result.evidence


@pytest.mark.parametrize(
    "malformed_suppress_until_utc",
    [
        pytest.param("not-a-date", id="non-timestamp-string"),
        pytest.param(123, id="non-string-int"),
        pytest.param(None, id="explicit-null"),
    ],
)
def test_malformed_suppress_until_utc_with_passing_minimum_is_ok(malformed_suppress_until_utc):
    ledger = _ledger(k={"minimum": 2, "suppress_until_utc": malformed_suppress_until_utc})
    result = evaluate({"k": 5}, ledger, now=NOW)
    assert result.outcome == "ok"


def test_absent_suppress_until_utc_key_still_evaluates_minimum_normally():
    # No suppress_until_utc field at all -- baseline for the malformed cases
    # above: absence of the modifier itself must behave identically to a
    # malformed value of it (both mean "no suppression").
    ledger = _ledger(k={"minimum": 2})
    assert evaluate({"k": 1}, ledger, now=NOW).outcome == "unhealthy"
    assert evaluate({"k": 5}, ledger, now=NOW).outcome == "ok"


# --------------------------------------------------------------------------- #
# T015 — the evaluator itself: ordinary healthy path, evidence contents,
# freshness deferral, and outcome/type shape
# --------------------------------------------------------------------------- #

def test_all_adjudicated_keys_satisfied_is_ok():
    ledger = _ledger(
        a={"good_values": [0, 3]},
        b={"minimum": 2},
        c={"freshness": True, "anchor": True, "max_age_seconds": 100},
    )
    document = {"a": 0, "b": 5, "c": "2026-08-30T11:59:00Z"}
    result = evaluate(document, ledger, now=NOW)
    assert result.outcome == "ok"


def test_freshness_predicate_is_deferred_not_resolved():
    ledger = _ledger(
        ts={"freshness": True, "anchor": True, "max_age_seconds": 100},
        other={"freshness": True, "max_age_seconds": 500},
    )
    document = {"ts": "not-even-a-timestamp", "other": "also-not-one"}
    result = evaluate(document, ledger, now=NOW)
    # A freshness key's raw value is never parsed here -- only presence is
    # enforced -- so an unparseable value does not itself decide the verdict.
    assert result.outcome == "ok"
    assert len(result.freshness_pending) == 2
    by_key = {o.key: o for o in result.freshness_pending}
    assert by_key["ts"].anchor is True
    assert by_key["ts"].max_age_seconds == 100
    assert by_key["ts"].value == "not-even-a-timestamp"
    assert by_key["other"].anchor is False
    assert by_key["other"].max_age_seconds == 500


def test_first_failure_in_declaration_order_wins():
    # `a` fails first in declared order; `b` would also fail, but evidence
    # must name `a`.
    ledger = _ledger(a={"good_values": [0]}, b={"minimum": 100})
    document = {"a": 1, "b": 1}
    result = evaluate(document, ledger, now=NOW)
    assert result.outcome == "unhealthy"
    assert "a" in result.evidence
    assert "b" not in result.evidence


def test_no_adjudicated_keys_declared_is_ok():
    ledger = {"adjudicated": {}}
    result = evaluate({"whatever": "value"}, ledger, now=NOW)
    assert result.outcome == "ok"


def test_ledger_result_is_frozen_and_evidence_is_non_empty_on_every_outcome():
    ledger = _ledger(k={"good_values": [0]})
    for document, expected_outcome in (
        ({"k": 0}, "ok"),
        ({"k": 1}, "unhealthy"),
        ({}, "unhealthy"),
        ("not-a-dict", "unknown"),
    ):
        result = evaluate(document, ledger, now=NOW)
        assert result.outcome == expected_outcome
        assert result.evidence
        with pytest.raises(FrozenInstanceError):
            result.outcome = "ok"  # type: ignore[misc]  # frozen dataclass


def test_freshness_obligation_is_frozen():
    obligation = FreshnessObligation(key="k", value="v", anchor=True, max_age_seconds=100)
    with pytest.raises(FrozenInstanceError):
        obligation.key = "other"  # type: ignore[misc]
