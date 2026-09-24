"""Tests for the #849 seed leak-detector.

The detector exists because a leaked oracle fact does not fail loudly — it
silently turns a multi-hop inference into a field lookup and the run still
produces numbers. So these tests assert it DISCRIMINATES: each one injects a
specific leak into a real seed and requires the checker to reject it.

A checker that only ever passes is worth nothing here, which is the whole
point of the injection tests below.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_DIR = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis" / "seed"
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.check_849_seed import (  # noqa: E402
    check_file,
    strip_comments,
)


def _write(tmp_path: pathlib.Path, name: str, text: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The real seeds must be clean
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "seed", sorted(SEED_DIR.glob("*.yaml")), ids=lambda p: p.name
)
def test_committed_seeds_are_clean(seed):
    assert check_file(seed) == []


def test_there_is_at_least_one_seed_to_check():
    """Guards the vacuous case: an empty glob would make the test above pass."""
    assert list(SEED_DIR.glob("*.yaml")), "no seed files found — is the path right?"


# --------------------------------------------------------------------------
# Comments must be exempt — the detector's own first bug
# --------------------------------------------------------------------------


def test_a_comment_warning_against_a_leak_is_not_itself_a_leak(tmp_path):
    """The first version of this checker failed on its own explanatory comment.

    A seed SHOULD document which leak it is avoiding, and a text scan cannot
    tell an assertion from a warning against that assertion.
    """
    text = (
        "# Do NOT write `status: shipped` here — it would gut the arc.\n"
        "meta: {arc: C}\n"
        "outcomes:\n"
        "  - {id: OUT_LAUNCH, target_date: 2026-04-23}\n"
        "commitments:\n"
        "  - {id: COM_DESIGN_REVIEW, datetime: null, trigger: 'after launch'}\n"
        "edges: []\n"
    )
    assert check_file(_write(tmp_path, "arc-c.yaml", text)) == []


def test_strip_comments_removes_only_whole_line_comments():
    raw = "# gone\nkey: value  # kept-inline\n"
    out = strip_comments(raw)
    assert "gone" not in out
    assert "kept-inline" in out


# --------------------------------------------------------------------------
# Leak injections — each must be rejected
# --------------------------------------------------------------------------


def test_asserting_launch_completion_is_rejected(tmp_path):
    """Arc C's third hop is inferring the launch ended from an unrelated thread."""
    text = (
        "meta: {arc: C}\n"
        "outcomes:\n"
        "  - {id: OUT_LAUNCH, target_date: 2026-04-23, status: shipped}\n"
        "commitments:\n"
        "  - {id: COM_DESIGN_REVIEW, datetime: null, trigger: 'after launch'}\n"
        "edges: []\n"
    )
    problems = check_file(_write(tmp_path, "arc-c.yaml", text))
    assert any("must not assert completion" in p for p in problems), problems


def test_materialising_the_dropped_commitment_is_rejected(tmp_path):
    """The unmaterialised-commitment absence IS Arc C's finding."""
    text = (
        "meta: {arc: C}\n"
        "outcomes:\n"
        "  - {id: OUT_LAUNCH, target_date: 2026-04-23}\n"
        "commitments:\n"
        "  - {id: COM_DESIGN_REVIEW, datetime: null, trigger: 'after launch'}\n"
        "edges:\n"
        "  - {type: DUE_BY, from: TASK_REVIEW, to: COM_DESIGN_REVIEW}\n"
    )
    problems = check_file(_write(tmp_path, "arc-c.yaml", text))
    assert any("nothing may point at" in p for p in problems), problems


def test_dating_the_trigger_gated_commitment_is_rejected(tmp_path):
    """Arc C's first hard property is that nothing can go overdue."""
    text = (
        "meta: {arc: C}\n"
        "outcomes:\n"
        "  - {id: OUT_LAUNCH, target_date: 2026-04-23}\n"
        "commitments:\n"
        "  - {id: COM_DESIGN_REVIEW, datetime: '2026-05-01T10:00:00', trigger: null}\n"
        "edges: []\n"
    )
    problems = check_file(_write(tmp_path, "arc-c.yaml", text))
    assert any("trigger-gated, never dated" in p for p in problems), problems


def test_a_fixed_or_movable_verdict_is_rejected(tmp_path):
    """Arc A must make the arm reason from facts to 'fixed', not read it off."""
    text = (
        "meta: {arc: A}\n"
        "commitments:\n"
        "  - {id: COM_PT_THU, datetime: '2026-06-11T14:30:00', fixed: true}\n"
        "edges: []\n"
    )
    problems = check_file(_write(tmp_path, "arc-a.yaml", text))
    assert any("fixed/movable verdict" in p for p in problems), problems


@pytest.mark.parametrize(
    "token, snippet",
    [
        ("travel_missing", "travel_missing: true"),
        ("overdue", "overdue: true"),
        ("point_of_no_return", "point_of_no_return: '2026-08-09'"),
        ("near_miss", "near_miss: true"),
        ("should_have_been_caught", "should_have_been_caught: '2026-08-02'"),
    ],
)
def test_verdict_vocabulary_is_rejected_wherever_it_appears(tmp_path, token, snippet):
    text = f"meta: {{arc: B}}\nitems:\n  - {{id: X, {snippet}}}\n"
    problems = check_file(_write(tmp_path, "arc-b.yaml", text))
    assert any(token in p for p in problems), (token, problems)


# --------------------------------------------------------------------------
# Failure modes of the checker itself
# --------------------------------------------------------------------------


def test_unparseable_yaml_is_reported_not_swallowed(tmp_path):
    problems = check_file(_write(tmp_path, "bad.yaml", "key: [unclosed\n"))
    assert any("does not parse" in p for p in problems), problems


def test_a_non_mapping_top_level_is_reported(tmp_path):
    problems = check_file(_write(tmp_path, "list.yaml", "- a\n- b\n"))
    assert any("expected a mapping" in p for p in problems), problems


def test_an_unknown_arc_gets_vocabulary_checks_but_no_structural_ones(tmp_path):
    """A new arc must not silently skip checking; vocabulary still applies."""
    clean = _write(tmp_path, "arc-z.yaml", "meta: {arc: Z}\nitems: []\n")
    assert check_file(clean) == []

    leaky = _write(tmp_path, "arc-z2.yaml", "meta: {arc: Z}\nitems:\n  - {overdue: true}\n")
    assert any("overdue" in p for p in check_file(leaky))
