"""Tests for the #849 freeze gate (rubric §9).

This is the last check before a run and the only one that looks at what the
arms actually consume. Its two severities are load-bearing and are tested
separately: a FAIL is unambiguously a leak, while an ADJUDICATE is usually
correct — the oracle describes what the corpus must contain, so overlap is
expected and judging it by hand is the rubric's rule.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.check_849_freeze import (  # noqa: E402
    adjudicate_oracle_statements,
    check_no_forbidden_vocabulary,
    check_no_non_rendered_keys,
    check_no_seed_comments,
    check_no_wrong_answer_phrases,
    load_oracles,
    run,
    seed_comment_lines,
)
from scripts.research.probe_849_recoverability import PROBES  # noqa: E402
from scripts.research.render_849_corpus import render  # noqa: E402


@pytest.fixture(scope="module")
def full():
    return render(scale=1)[0]


def test_the_corpus_is_frozen_clean(full):
    failures, _, _ = run(scale=1)
    assert failures == [], failures


# --------------------------------------------------------------------------
# Each check must be able to fail
# --------------------------------------------------------------------------


def test_a_leaked_seed_comment_is_caught():
    name, body = seed_comment_lines()[0]
    assert check_no_seed_comments(f"...{body}...")


def test_forbidden_vocabulary_is_caught():
    assert check_no_forbidden_vocabulary('{"note": "point_of_no_return"}')


def test_a_leaked_non_rendered_key_is_caught():
    assert check_no_non_rendered_keys('{"generator_input": 1}')


def test_a_verbatim_wrong_answer_is_caught():
    oracles = load_oracles()
    phrase = next(
        p for d in oracles for p in (d.get("wrong_answers") or []) if len(p) > 20
    )
    assert check_no_wrong_answer_phrases(f"x {phrase} y", oracles)


def test_seed_comments_are_actually_collected():
    """Guards the vacuous case — an empty list makes the leak check pass."""
    lines = seed_comment_lines()
    assert len(lines) > 50, len(lines)
    assert any("footprint" in body.lower() for _, body in lines)


# --------------------------------------------------------------------------
# The severity split
# --------------------------------------------------------------------------


def test_oracle_statement_overlap_adjudicates_rather_than_fails(full):
    """The oracle describes what the corpus contains, so overlap is expected.

    Failing on it would make the gate unpassable by construction.
    """
    failures, adjudications, _ = run(scale=1)
    assert failures == []
    assert adjudications, "expected at least one fragment to adjudicate"
    assert all(n.startswith("ADJUDICATE:") for n in adjudications)


# --------------------------------------------------------------------------
# The recoverability probes — the point of the whole gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("arc", sorted(PROBES))
def test_every_arc_probe_recovers_its_structure(full, arc):
    """Each claim checked by a script rather than by an author's conviction.

    This is the mechanism that distinguishes "the corpus is too thin" from
    "the arm is not good enough". Probes live in ONE module — mine covered E
    and F and were dropped when the design lead's covered all five.
    """
    from scripts.research.check_849_freeze import _as_rows

    rows, ents = _as_rows(full)
    ok, detail = PROBES[arc](rows, ents)
    assert ok, detail


@pytest.mark.parametrize("arc", sorted(PROBES))
def test_a_probe_fails_when_the_signal_is_absent(arc):
    """A probe that cannot fail proves nothing."""
    ok, _ = PROBES[arc]([], [])
    assert not ok


def test_the_gate_fails_when_a_probe_fails(monkeypatch):
    """The gate must surface a probe failure, not merely report it.

    Patched on the imported name in the gate module, because the gate now
    imports the probes from their single home rather than defining its own.
    """
    import scripts.research.check_849_freeze as mod

    monkeypatch.setitem(mod._RECOVERY_PROBES, "Z", lambda rows, ents: (False, "forced"))
    try:
        failures, _, _ = mod.run(scale=20)
    finally:
        mod._RECOVERY_PROBES.pop("Z", None)
    assert any("recoverability probe [arc Z]" in f for f in failures), failures


# --------------------------------------------------------------------------
# The inverse check: a required value must be PRESENT, not merely not-leaked
# --------------------------------------------------------------------------


def test_every_required_value_appears_in_the_corpus(full):
    """A missing required value makes a point unhittable — the grader demands
    a literal the arm had no way to see. Just as fatal as a leak, and silent."""
    from scripts.research.check_849_freeze import (
        check_required_values_present, corpus_text, load_oracles)

    assert check_required_values_present(corpus_text(full), load_oracles()) == []


def test_the_required_value_check_can_fail():
    from scripts.research.check_849_freeze import check_required_values_present

    fake = [{"_file": "X.yaml", "must_identify": [
        {"id": "X-1", "required_values": ["a-value-not-in-the-corpus"]}]}]
    assert check_required_values_present("nothing here", fake)


# --------------------------------------------------------------------------
# The stream allowlist — default deny
# --------------------------------------------------------------------------


def test_no_internal_bookkeeping_field_reaches_the_stream(full):
    """Four of five blocking freeze findings were this one shape."""
    from scripts.research.render_849_corpus import STREAM_FIELDS

    seen = {k for e in full.events for k in e}
    assert seen <= STREAM_FIELDS, seen - STREAM_FIELDS


@pytest.mark.parametrize(
    "field",
    ["emit", "week", "over_travel_block_min", "travel_before_min",
     "label_in_corpus", "kind", "decision", "duration_min"],
)
def test_specific_leaked_fields_are_gone(full, field):
    assert not any(field in e for e in full.events), field


def test_semantic_ids_do_not_reach_the_stream(full):
    """EP_C_PROMISE tells an arm the episode IS the promise."""
    import json as _json

    text = _json.dumps(full.events, default=str)
    # Every id prefix the ontology uses, not a sample of them. The first
    # version listed six and omitted PER_, which is how five E2 emails shipped
    # with `sender: PER_CLIENT` through a check written to prevent exactly that
    # (freeze finding L11). A partial denylist is the too-narrow failure again.
    for prefix in ("EP_", "GEN_", "COM_", "DEC_", "PRIN_", "INT_", "PER_",
                   "TASK_", "OUT_", "DOM_", "PUR_", "OBJ_", "PRJ_", "CAP_"):
        assert prefix not in text, prefix


def test_loader_wiring_is_held_apart_from_the_stream(full):
    """`mentions` is how G wires episodes to entities; putting it in the dump
    would hand D and R the traversal G has to earn."""
    assert full.loader_links, "no loader links captured"
    assert not any("mentions" in e for e in full.events)


def test_stripped_fields_are_reported_not_silently_dropped(full):
    """A stripped field is either new vocabulary or a prevented leak.

    Either way somebody should look, so the renderer records them.
    """
    assert full.stripped_fields
    assert "emit" in full.stripped_fields
