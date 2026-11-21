"""Tests for scripts.common.vikunja_rule (WP01, #1111)."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.common import vikunja_rule as vr
from scripts.common.et_datetime import parse_vikunja_instant
from tests.common.vikunja_v2_factory import make_task, strip_rule

DAILY = {"freq": "daily", "interval": 1}


# --------------------------------------------------------------------------- purity


def test_module_is_pure_no_client_or_io_imports() -> None:
    tree = ast.parse(Path(vr.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"scripts.common.vikunja_client", "urllib.request", "socket", "http.client"}
    assert not imported & forbidden


# --------------------------------------------------------------------------- normalise


def test_normalise_lowercases_and_sorts_and_drops_read_only() -> None:
    raw = {"freq": "WEEKLY", "interval": 2, "by_day": ["WE", "mo"], "wkst": "SU", "read_only": True}
    assert vr.normalise(raw) == {"freq": "weekly", "interval": 2, "by_day": ["mo", "we"], "wkst": "su"}


# Server d7e202228 omits the default WKST (mo) in responses and compares "" equal
# to "mo" (pkg/models/task_repeat.go:60, 444-446, 524-526).
@pytest.mark.parametrize("wkst", [None, "", "mo", "MO", " Mo"])
def test_normalise_default_wkst_is_canonical(wkst: Any) -> None:
    raw: dict[str, Any] = {"freq": "weekly", "interval": 2, "by_day": ["mo"]}
    if wkst is not None:
        raw["wkst"] = wkst.strip()
    assert vr.normalise(raw) == {"freq": "weekly", "interval": 2, "by_day": ["mo"]}


def test_explicit_monday_wkst_text_matches_server_response() -> None:
    parsed = vr.rrule_text_to_parts("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;WKST=MO")
    server_response = {"freq": "weekly", "interval": 2, "by_day": ["mo"]}
    assert vr.same_rule(parsed, server_response)


@pytest.mark.parametrize("wkst", ["su", "tu", "SA"])
def test_non_default_wkst_stays_distinct(wkst: str) -> None:
    base = {"freq": "weekly", "interval": 2, "by_day": ["mo"]}
    assert not vr.same_rule({**base, "wkst": wkst}, base)
    assert not vr.same_rule({**base, "wkst": wkst}, {**base, "wkst": "mo"})


@pytest.mark.parametrize("empty", [None, {}, {"interval": 1}, {"freq": ""}])
def test_normalise_no_rule_is_none(empty: Any) -> None:
    assert vr.normalise(empty) is None


@pytest.mark.parametrize("interval", [None, 0])
def test_normalise_interval_defaults_to_one(interval: Any) -> None:
    raw: dict[str, Any] = {"freq": "daily"}
    if interval is not None:
        raw["interval"] = interval
    assert vr.normalise(raw) == {"freq": "daily", "interval": 1}


def test_normalise_drops_zero_and_empty_parts() -> None:
    raw = {"freq": "daily", "interval": 1, "count": 0, "until": "", "by_month_day": [], "wkst": None}
    assert vr.normalise(raw) == DAILY


def test_normalise_until_to_utc_z() -> None:
    raw = {"freq": "daily", "interval": 1, "until": "2026-12-31T18:59:59-05:00"}
    assert vr.normalise(raw)["until"] == "2026-12-31T23:59:59Z"  # type: ignore[index]


def test_normalise_unparseable_until_kept_not_dropped() -> None:
    a = vr.normalise({"freq": "daily", "until": "garbage"})
    assert a is not None and a["until"] == "garbage"
    assert not vr.same_rule({"freq": "daily", "until": "garbage"}, DAILY)


# --------------------------------------------------------------------------- same_rule / has_rule


def test_same_rule_true_pairs() -> None:
    assert vr.same_rule({"freq": "weekly", "interval": 1, "by_day": ["mo", "we"]},
                        {"freq": "WEEKLY", "by_day": ["WE", "MO"], "read_only": False})
    assert vr.same_rule(None, {})


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ({"freq": "weekly", "by_day": ["mo"]}, {"freq": "weekly", "by_day": ["tu"]}),
        ({"freq": "monthly", "by_month_day": [1]}, {"freq": "monthly", "by_month_day": [15]}),
        ({"freq": "weekly", "by_day": ["2tu"]}, {"freq": "weekly", "by_day": ["tu"]}),
        ({"freq": "daily", "interval": 1}, {"freq": "daily", "interval": 2}),
        ({"freq": "daily"}, None),
    ],
)
def test_same_rule_false_pairs(a: Any, b: Any) -> None:
    assert not vr.same_rule(a, b)


def test_has_rule() -> None:
    assert vr.has_rule(make_task())
    assert not vr.has_rule(strip_rule(make_task()))
    assert not vr.has_rule({"repeat": {}})
    assert not vr.has_rule({})


# --------------------------------------------------------------------------- rule_equal_except_count


def test_rule_equal_except_count() -> None:
    two = {"freq": "daily", "interval": 1, "count": 2}
    assert vr.rule_equal_except_count(two, {**two, "count": 1})
    assert not vr.rule_equal_except_count(two, two)
    assert not vr.rule_equal_except_count(two, {"freq": "weekly", "interval": 1, "count": 1})
    assert not vr.rule_equal_except_count(two, {**two, "count": 0})  # count 0 == no count
    assert not vr.rule_equal_except_count(DAILY, DAILY)


# --------------------------------------------------------------------------- text <-> parts


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("FREQ=DAILY;INTERVAL=1", {"freq": "daily", "interval": 1}),
        ("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=6",
         {"freq": "weekly", "interval": 2, "by_day": ["mo", "we"], "count": 6}),
        ("FREQ=MONTHLY;BYMONTHDAY=1,15", {"freq": "monthly", "by_month_day": [1, 15]}),
        ("FREQ=DAILY;COUNT=3", {"freq": "daily", "count": 3}),
        ("FREQ=DAILY;UNTIL=20261231T235959Z", {"freq": "daily", "until": "2026-12-31T23:59:59Z"}),
        ("RRULE:FREQ=WEEKLY;BYDAY=2TU;WKST=SU", {"freq": "weekly", "by_day": ["2tu"], "wkst": "su"}),
    ],
)
def test_text_to_parts_and_round_trip(text: str, parts: dict[str, Any]) -> None:
    parsed = vr.rrule_text_to_parts(text)
    assert parsed == parts
    again = vr.rrule_text_to_parts(vr.parts_to_rrule_text(parsed))
    assert vr.normalise(again) == vr.normalise(parsed)


def test_parts_to_text_deterministic_order_uppercase() -> None:
    parts = {"wkst": "su", "count": 6, "by_day": ["we", "mo"], "interval": 2, "freq": "weekly",
             "until": "2026-12-31T23:59:59Z", "read_only": True}
    assert vr.parts_to_rrule_text(parts) == (
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=6;UNTIL=20261231T235959Z;WKST=SU"
    )


def test_parts_to_text_omits_default_wkst() -> None:
    assert vr.parts_to_rrule_text({"freq": "weekly", "wkst": "mo"}) == "FREQ=WEEKLY;INTERVAL=1"


def test_parts_to_text_rejects_non_rule() -> None:
    with pytest.raises(ValueError):
        vr.parts_to_rrule_text({})


@pytest.mark.parametrize(
    "bad",
    [
        "INTERVAL=1",
        "FREQ=DAILY;FOO=1",
        "FREQ=DAILY;COUNT",
        "FREQ=DAILY;COUNT=x",
        "FREQ=DAILY;UNTIL=20261231",  # date-only: no instant
        "FREQ=DAILY;UNTIL=20261231T235959",  # floating: no zone
        "FREQ=DAILY;UNTIL=2026-12-31T23:59:59Z",
    ],
)
def test_text_to_parts_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        vr.rrule_text_to_parts(bad)


# --------------------------------------------------------------------------- exhaustion_expected

UNTIL_RULE = {"freq": "daily", "interval": 1, "until": "2026-11-20T23:59:59Z"}


def _until_task(**kw: Any) -> dict[str, Any]:
    return make_task(repeat=UNTIL_RULE, **kw)


def _preview_returning(result: Any, calls: list[dict[str, Any]] | None = None):
    def preview(**kwargs: Any) -> Any:
        if calls is not None:
            calls.append(kwargs)
        return result
    return preview


def test_exhaustion_no_rule() -> None:
    assert vr.exhaustion_expected(strip_rule(make_task()), preview=None) == "no"


def test_exhaustion_count_one_is_yes_without_preview() -> None:
    task = make_task(repeat={"freq": "daily", "interval": 1, "count": 1})
    assert vr.exhaustion_expected(task, preview=None) == "yes"


def test_exhaustion_count_two_is_no() -> None:
    task = make_task(repeat={"freq": "daily", "interval": 1, "count": 2})
    assert vr.exhaustion_expected(task, preview=None) == "no"


def test_exhaustion_no_count_no_until_is_no() -> None:
    assert vr.exhaustion_expected(make_task(), preview=None) == "no"


@pytest.mark.parametrize("reason", ["until_passed", "count_exhausted"])
def test_exhaustion_until_preview_explicit_reason_yes(reason: str) -> None:
    calls: list[dict[str, Any]] = []
    task = _until_task()
    result = vr.exhaustion_expected(
        task, preview=_preview_returning({"occurrences": [], "reason": reason}, calls)
    )
    assert result == "yes"
    assert calls == [{
        "repeat": vr.normalise(UNTIL_RULE),
        "due_date": task["due_date"],
        "repeats_from_current_date": False,
        "count": 1,
    }]


def test_exhaustion_until_preview_occurrence_is_no() -> None:
    preview = _preview_returning({"occurrences": ["2026-11-21T04:59:59Z"]})
    assert vr.exhaustion_expected(_until_task(), preview=preview) == "no"


@pytest.mark.parametrize(
    "result",
    [
        {"occurrences": [], "reason": "anchor_beyond_horizon"},
        {"occurrences": [], "reason": "no_occurrence"},
        {"occurrences": []},
        {"occurrences": ["2026-11-21T04:59:59Z"], "reason": "anchor_beyond_horizon"},
        None,
    ],
)
def test_exhaustion_until_preview_other_is_unknown(result: Any) -> None:
    assert vr.exhaustion_expected(_until_task(), preview=_preview_returning(result)) == "unknown"


def test_exhaustion_until_from_current_flag_is_unknown() -> None:
    calls: list[dict[str, Any]] = []
    task = _until_task(repeats_from_current_date=True)
    preview = _preview_returning({"occurrences": [], "reason": "until_passed"}, calls)
    assert vr.exhaustion_expected(task, preview=preview) == "unknown"
    assert calls == []


def test_exhaustion_until_no_preview_is_unknown() -> None:
    assert vr.exhaustion_expected(_until_task(), preview=None) == "unknown"


def test_exhaustion_until_preview_raises_is_unknown() -> None:
    class FakeVikunjaError(Exception):
        pass

    def preview(**_: Any) -> Any:
        raise FakeVikunjaError("401")

    assert vr.exhaustion_expected(_until_task(), preview=preview) == "unknown"


# --------------------------------------------------------------------------- completion_outcome

LATER = "2026-11-21T04:59:59Z"


def test_outcome_advanced_same_rule() -> None:
    before = make_task()
    after = make_task(due_date=LATER, repeat={"freq": "DAILY", "interval": 1, "read_only": False})
    assert vr.completion_outcome(before, after, exhaustion="no") == "advanced"


def test_outcome_advanced_count_two_to_one() -> None:
    before = make_task(repeat={"freq": "daily", "interval": 1, "count": 2})
    after = make_task(repeat={"freq": "daily", "interval": 1, "count": 1}, due_date=LATER)
    assert vr.completion_outcome(before, after, exhaustion="no") == "advanced"


def test_outcome_series_ended_count_one_rule_cleared() -> None:
    before = make_task(repeat={"freq": "daily", "interval": 1, "count": 1})
    after = strip_rule(make_task(done=True))
    assert vr.completion_outcome(before, after, exhaustion="yes") == "series_ended"


def test_outcome_count_one_done_but_rule_still_present_is_unexpected() -> None:
    rule = {"freq": "daily", "interval": 1, "count": 1}
    before = make_task(repeat=rule)
    after = make_task(repeat=rule, done=True)
    assert vr.completion_outcome(before, after, exhaustion="yes") == "unexpected"


def test_outcome_series_ended_until_rule_kept() -> None:
    before = _until_task()
    after = _until_task(done=True)
    assert vr.completion_outcome(before, after, exhaustion="yes") == "series_ended"


def test_outcome_until_rule_stripped_is_unexpected() -> None:
    before = _until_task()
    after = strip_rule(_until_task(done=True))
    assert vr.completion_outcome(before, after, exhaustion="yes") == "unexpected"


def test_outcome_until_rule_replaced_is_unexpected() -> None:
    before = _until_task()
    after = make_task(repeat={"freq": "yearly", "interval": 1}, done=True)
    assert vr.completion_outcome(before, after, exhaustion="yes") == "unexpected"


def test_outcome_until_rule_kept_in_other_casing_is_series_ended() -> None:
    before = _until_task()
    after = _until_task(done=True)
    after["repeat"] = {"freq": "DAILY", "interval": 1, "until": "2026-11-20T18:59:59-05:00",
                       "read_only": True}
    assert vr.completion_outcome(before, after, exhaustion="yes") == "series_ended"


@pytest.mark.parametrize("exhaustion", ["unknown", "no"])
def test_outcome_done_without_established_exhaustion_is_unexpected(exhaustion: str) -> None:
    before = _until_task()
    after = _until_task(done=True)
    assert vr.completion_outcome(before, after, exhaustion=exhaustion) == "unexpected"


def test_outcome_not_done_no_due_change_is_unexpected() -> None:
    before = make_task()
    assert vr.completion_outcome(before, make_task(), exhaustion="no") == "unexpected"


def test_outcome_rule_changed_beyond_count_is_unexpected() -> None:
    before = make_task()
    after = make_task(repeat={"freq": "weekly", "interval": 1}, due_date=LATER)
    assert vr.completion_outcome(before, after, exhaustion="no") == "unexpected"


def test_outcome_rule_stripped_on_advance_is_unexpected() -> None:
    before = make_task()
    after = strip_rule(make_task(due_date=LATER))
    assert vr.completion_outcome(before, after, exhaustion="no") == "unexpected"


def test_outcome_non_repeating_before_is_unexpected() -> None:
    before = strip_rule(make_task())
    after = strip_rule(make_task(due_date=LATER))
    assert vr.completion_outcome(before, after, exhaustion="no") == "unexpected"


# --------------------------------------------------------------------------- recurrence_drift
# The shared drift helper (WP08, rule of three over set_due_dates, migrate_tasks
# and escalation.record_completion) and its absolute-reminder predictor.

_PARITY = json.loads(
    (Path(__file__).parent / "fixtures" / "reminder_move_parity.json").read_text(
        encoding="utf-8"
    )
)
_UNSET = "0001-01-01T00:00:00Z"
_WEEKLY = {"freq": "weekly", "interval": 1, "by_day": ["we"]}


def _at(value: str) -> datetime:
    parsed = parse_vikunja_instant(value)
    assert parsed is not None
    return parsed


def _abs(value: str) -> dict[str, Any]:
    return {"reminder": value, "relative_to": "", "relative_period": 0}


def _rel(value: str, period: int = -3600, anchor: str = "due_date") -> dict[str, Any]:
    return {"reminder": value, "relative_to": anchor, "relative_period": period}


@pytest.mark.parametrize("case", _PARITY["cases"], ids=lambda c: c["name"])
def test_moved_absolute_reminder_matches_server_engine(case: dict[str, Any]) -> None:
    """Parity with the server's own engine output (fixture provenance in the file)."""
    rule = vr.rrule_text_to_parts(case["rule"])
    old_due, new_due = _at(case["due"]), _at(case["new_due"])
    got = [
        vr.moved_absolute_reminder(_at(r), old_due, new_due, rule)
        for r in case["reminders"]
    ]
    assert got == [_at(m) for m in case["moved"]]


def test_parity_fixture_covers_the_arbiter_cases() -> None:
    """Named-time clamping, DST gap and overlap, and a reorder are all present."""
    names = {c["name"] for c in _PARITY["cases"]}
    assert {"named_time_gap_clamp", "daily_gap_forward", "daily_overlap_earlier"} <= names
    clamp = next(c for c in _PARITY["cases"] if c["name"] == "named_time_gap_clamp")
    assert clamp["moved"] == [clamp["new_due"]]  # clamped onto the new due date
    reorder = next(c for c in _PARITY["cases"] if c["name"] == "daily_gap_forward")
    assert sorted(reorder["reminders"]) == reorder["reminders"]
    assert sorted(reorder["moved"]) != reorder["moved"]  # the move flips their order


def _advanced_pair(case_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    case = next(c for c in _PARITY["cases"] if c["name"] == case_name)
    rule = vr.rrule_text_to_parts(case["rule"])
    before = make_task(
        repeat=rule, due_date=case["due"], reminders=[_abs(r) for r in case["reminders"]]
    )
    # The read path returns reminders sorted by instant, not in input order.
    after = make_task(
        repeat=rule,
        due_date=case["new_due"],
        reminders=[_abs(m) for m in sorted(case["moved"])],
    )
    return before, after


def test_drift_accepts_server_moved_reordered_reminders_on_advance() -> None:
    before, after = _advanced_pair("daily_gap_forward")
    assert vr.recurrence_drift(before, after, compare_rule=False, advanced=True) == []
    # The same move is damage when the write was not an advance.
    assert vr.recurrence_drift(before, after, compare_rule=False) == ["reminders"]


def test_drift_rejects_a_naive_shift_where_the_server_clamps() -> None:
    before, after = _advanced_pair("named_time_gap_clamp")
    assert vr.recurrence_drift(before, after, compare_rule=False, advanced=True) == []
    naive = {**after, "reminders": [_abs("2027-03-14T07:30:00Z")]}
    assert vr.recurrence_drift(before, naive, compare_rule=False, advanced=True) == [
        "reminders"
    ]


def test_drift_none_when_everything_survives() -> None:
    before = make_task(
        repeat=_WEEKLY,
        repeats_from_current_date=True,
        reminders=[_rel("2026-11-20T03:59:59Z"), _abs("2026-11-19T12:00:00Z")],
    )
    assert vr.recurrence_drift(before, json.loads(json.dumps(before))) == []


def test_drift_names_each_corruption_in_order() -> None:
    base = make_task(
        repeat=_WEEKLY,
        repeats_from_current_date=True,
        reminders=[_rel("2026-11-20T03:59:59Z"), _abs("2026-11-19T12:00:00Z")],
    )
    assert vr.recurrence_drift(base, {**base, "repeat": None}) == ["repeat"]
    assert vr.recurrence_drift(base, {**base, "repeat": None}, compare_rule=False) == []
    assert vr.recurrence_drift(base, {**base, "repeats_from_current_date": False}) == [
        "repeats_from_current_date"
    ]
    assert vr.recurrence_drift(base, {**base, "reminders": []}) == ["reminders"]
    assert vr.recurrence_drift(base, {**base, "reminders": None}) == ["reminders"]
    moved = [base["reminders"][0], _abs("2026-11-19T13:00:00Z")]
    assert vr.recurrence_drift(base, {**base, "reminders": moved}) == ["reminders"]
    re_period = [_rel("2026-11-20T03:59:59Z", period=-7200), base["reminders"][1]]
    assert vr.recurrence_drift(base, {**base, "reminders": re_period}) == ["reminders"]
    everything = {**base, "repeat": None, "repeats_from_current_date": False, "reminders": []}
    assert vr.recurrence_drift(base, everything) == [
        "repeat",
        "repeats_from_current_date",
        "reminders",
    ]


def test_drift_ignores_a_recomputed_relative_trigger() -> None:
    before = make_task(reminders=[_rel("2027-03-14T00:00:00Z", period=-86400)],
                       due_date="2027-03-15T00:00:00Z")
    after = {**before, "reminders": [_rel("2027-03-14T01:00:00Z", period=-86400)]}
    assert vr.recurrence_drift(before, after) == []


@pytest.mark.parametrize("anchor", ["due_date", "start_date", "end_date"])
def test_drift_flags_sentinel_trigger_beside_a_set_base_date(anchor: str) -> None:
    """The server derives the trigger from anchor + period on every save
    (d7e202228 tasks.go:2575-2590): a set base date with a sentinel trigger
    is not a state it produces."""
    task = make_task(**{anchor: "2026-11-21T14:00:00Z"})
    good = {**task, "reminders": [_rel("2026-11-21T13:00:00Z", anchor=anchor)]}
    broken = {**task, "reminders": [_rel(_UNSET, anchor=anchor)]}
    assert vr.recurrence_drift(good, good) == []
    assert vr.recurrence_drift(good, broken) == ["reminders"]
    missing = {**task, "reminders": [{"relative_to": anchor, "relative_period": -3600}]}
    assert vr.recurrence_drift(good, missing) == ["reminders"]


def test_drift_accepts_sentinel_trigger_when_the_base_date_is_unset() -> None:
    task = make_task(start_date=_UNSET)
    unset = {**task, "reminders": [_rel(_UNSET, anchor="start_date")]}
    assert vr.recurrence_drift(unset, unset) == []


def test_drift_treats_malformed_reminders_as_values_not_crashes() -> None:
    before = make_task(reminders=["garbage"])
    assert vr.recurrence_drift(before, before) == []
    assert vr.recurrence_drift(before, {**before, "reminders": []}) == ["reminders"]


# --------------------------------------------------------------------------- BYDAY ordinals


@pytest.mark.parametrize(
    ("text", "served"),
    [
        ("FREQ=MONTHLY;BYDAY=+1MO", ["1mo"]),
        ("FREQ=MONTHLY;BYDAY=1MO", ["1mo"]),
        ("FREQ=MONTHLY;BYDAY=-1FR", ["-1fr"]),
        ("FREQ=MONTHLY;BYDAY=+1MO,-1FR", ["-1fr", "1mo"]),
        ("FREQ=YEARLY;BYDAY=+01MO", ["1mo"]),
        ("FREQ=WEEKLY;BYDAY=MO,WE", ["we", "mo"]),
    ],
)
def test_same_rule_accepts_the_servers_by_day_spelling(text: str, served: list[str]) -> None:
    """d7e202228 serves structured by_day as fmt.Sprintf("%d%s") (task_repeat.go:556-562):
    no "+", lowercase. Rule text keeps "+1MO". Both are one rule."""
    freq = vr.rrule_text_to_parts(text)["freq"]
    assert vr.same_rule(vr.rrule_text_to_parts(text), {"freq": freq, "by_day": served})


@pytest.mark.parametrize(
    ("a", "b"),
    [(["1mo"], ["2mo"]), (["-1fr"], ["1fr"]), (["mo"], ["1mo"]), (["1mo"], ["1tu"])],
)
def test_same_rule_keeps_different_ordinals_apart(a: list[str], b: list[str]) -> None:
    assert not vr.same_rule({"freq": "monthly", "by_day": a}, {"freq": "monthly", "by_day": b})


def test_parts_to_text_round_trips_ordinals() -> None:
    parts = {"freq": "monthly", "interval": 1, "by_day": ["-1fr", "1mo"]}
    text = vr.parts_to_rrule_text(parts)
    assert text == "FREQ=MONTHLY;INTERVAL=1;BYDAY=-1FR,1MO"
    assert vr.same_rule(vr.rrule_text_to_parts(text), parts)
