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
    probe_arc_e_sessions,
    probe_arc_f_slope,
    run,
    seed_comment_lines,
)
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


def test_the_session_shape_is_deterministically_recoverable(full):
    """E1-4's claim, checked by a script rather than by an author's conviction.

    This is the mechanism that distinguishes "the corpus is too thin" from
    "the arm is not good enough", and it is the answer to whether a repeated
    action shape is enough signal.
    """
    ok, detail = probe_arc_e_sessions(full)
    assert ok, detail
    assert "13" in detail


def test_the_practice_decline_is_recoverable_as_a_slope(full):
    ok, detail = probe_arc_f_slope(full)
    assert ok, detail


def test_a_probe_fails_when_the_signal_is_absent():
    """A probe that cannot fail proves nothing."""

    class Empty:
        events: list = []
        entities: list = []

    ok_e, _ = probe_arc_e_sessions(Empty())
    ok_f, _ = probe_arc_f_slope(Empty())
    assert not ok_e and not ok_f


def test_the_gate_fails_when_a_probe_fails(monkeypatch):
    import scripts.research.check_849_freeze as mod

    monkeypatch.setitem(mod.PROBES, "synthetic", lambda c: (False, "forced"))
    failures, _, _ = mod.run(scale=20)
    assert any("recoverability probe [synthetic]" in f for f in failures), failures
