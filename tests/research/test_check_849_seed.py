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


# --------------------------------------------------------------------------
# Arc F — the standing-practice invariants (Q1 ruling, Kent-ratified)
# --------------------------------------------------------------------------

ARC_F_OK = (
    "meta: {arc: F}\n"
    "tasks:\n"
    "  - {id: TASK_MEDITATION, recurrence_rule: 'FREQ=DAILY'}\n"
    "edges:\n"
    "  - {type: EMBODIES, from: TASK_MEDITATION, to: PRIN_SELF_INVESTMENT}\n"
)


def test_arc_f_clean_case_passes(tmp_path):
    assert check_file(_write(tmp_path, "arc-f.yaml", ARC_F_OK)) == []


def test_arc_f_rejects_an_outcome_for_a_standing_practice(tmp_path):
    """An Outcome requires a measure, and the measure IS the leaked answer."""
    text = ARC_F_OK + (
        "outcomes:\n"
        "  - {id: OUT_PRACTICE, target_date: 2026-12-31, measure: '>=5/week'}\n"
    )
    problems = check_file(_write(tmp_path, "arc-f.yaml", text))
    assert any("must have NO Outcome" in p for p in problems), problems


def test_arc_f_rejects_a_practice_task_with_no_embodies_anchor(tmp_path):
    """'No Outcome' is only correct because EMBODIES is the anchor."""
    text = (
        "meta: {arc: F}\n"
        "tasks:\n"
        "  - {id: TASK_MEDITATION, recurrence_rule: 'FREQ=DAILY'}\n"
        "edges: []\n"
    )
    problems = check_file(_write(tmp_path, "arc-f.yaml", text))
    assert any("EMBODIES" in p for p in problems), problems


@pytest.mark.parametrize(
    "field",
    ["target_rate", "expected_per_week", "streak", "expected_frequency", "threshold"],
)
def test_arc_f_rejects_any_seeded_rate(tmp_path, field):
    text = ARC_F_OK.replace(
        "recurrence_rule: 'FREQ=DAILY'",
        f"recurrence_rule: 'FREQ=DAILY', {field}: 5",
    )
    problems = check_file(_write(tmp_path, "arc-f.yaml", text))
    assert any("target-rate" in p or field in p for p in problems), (field, problems)


def test_the_committed_arc_f_seed_has_no_outcome_and_anchors_both_tasks():
    """Assert the real file, not a fixture — the invariant that matters."""
    import yaml as _yaml

    path = SEED_DIR / "arc-f.yaml"
    doc = _yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
    assert not doc.get("outcomes"), "Arc F must seed no Outcome"
    tasks = {t["id"] for t in doc["tasks"]}
    embodied = {e["from"] for e in doc["edges"] if e["type"] == "EMBODIES"}
    assert tasks and tasks == embodied, (tasks, embodied)


# --------------------------------------------------------------------------
# Rendered view vs generator input — the exemption must be DECLARED
# --------------------------------------------------------------------------


def test_undeclared_generator_input_is_rejected(tmp_path):
    """An undeclared block is emitted verbatim by the renderer, so it leaks."""
    text = (
        "meta: {arc: Z}\n"
        "generator_input:\n"
        "  weeks: [{wk: 1, counted: false}]\n"
    )
    problems = check_file(_write(tmp_path, "arc-z.yaml", text))
    assert any("not listed in meta.non_rendered" in p for p in problems), problems


def test_declared_generator_input_may_carry_oracle_adjacent_structure(tmp_path):
    """Declared is a contract: the renderer strips exactly this list.

    Uses a neutral arc so this exercises the declaration mechanism alone. It
    originally said `arc: B` for convenience and started failing the moment
    Arc B grew a structural requirement — a fixture borrowing a real arc's
    identity inherits that arc's rules.
    """
    text = (
        "meta: {arc: Z, non_rendered: [generator_input]}\n"
        "generator_input:\n"
        "  weeks: [{wk: 1, counted: false, point_of_no_return: true}]\n"
    )
    assert check_file(_write(tmp_path, "arc-z.yaml", text)) == []


def test_declaring_a_block_does_not_exempt_the_rendered_part(tmp_path):
    """The exemption is scoped — a leak outside the declared block still fails."""
    text = (
        "meta: {arc: Z, non_rendered: [generator_input]}\n"
        "generator_input: {weeks: [{counted: false}]}\n"
        "episodes:\n"
        "  - {id: EP_X, content: 'x', point_of_no_return: '2026-08-09'}\n"
    )
    problems = check_file(_write(tmp_path, "arc-z.yaml", text))
    assert any("point_of_no_return" in p for p in problems), problems


def test_committed_seeds_declare_every_generator_block():
    """The real files must not rely on the author remembering."""
    import yaml as _yaml

    for path in sorted(SEED_DIR.glob("*.yaml")):
        doc = _yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        declared = set((doc.get("meta") or {}).get("non_rendered") or [])
        looks_generated = {
            k for k in doc
            if k.startswith("generator") or k.endswith("_input")
        }
        assert looks_generated <= declared, (path.name, looks_generated - declared)


# --------------------------------------------------------------------------
# Universal: a Decision must have a source episode
# --------------------------------------------------------------------------


def test_an_orphan_decision_is_rejected_in_any_arc(tmp_path):
    text = (
        "meta: {arc: F}\n"
        "decisions:\n"
        "  - {id: DEC_X, decided_at: '2026-05-12T21:14:00', rationale: 'because'}\n"
        "episodes: []\n"
    )
    problems = check_file(_write(tmp_path, "arc-f.yaml", text))
    assert any("has no source episode" in p for p in problems), problems


def test_a_decision_mentioned_by_an_episode_passes(tmp_path):
    text = (
        "meta: {arc: F}\n"
        "decisions:\n"
        "  - {id: DEC_X, decided_at: '2026-05-12T21:14:00', rationale: 'because'}\n"
        "episodes:\n"
        "  - {id: EP_X, content: 'note', mentions: [DEC_X]}\n"
    )
    assert check_file(_write(tmp_path, "arc-f.yaml", text)) == []


def test_committed_seeds_have_no_orphan_decisions():
    import yaml as _yaml

    for path in sorted(SEED_DIR.glob("*.yaml")):
        doc = _yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        decs = {d["id"] for d in (doc.get("decisions") or [])}
        mentioned = {m for e in (doc.get("episodes") or []) for m in (e.get("mentions") or [])}
        assert decs <= mentioned, (path.name, decs - mentioned)


# --------------------------------------------------------------------------
# Arc B and Arc E structural invariants
# --------------------------------------------------------------------------

ARC_B_OK = (
    "meta: {arc: B}\n"
    "episodes:\n"
    "  - {id: EP_RULE, content: 'If I am not hitting pace by the halfway point "
    "of the programme, there is no path to recovery.'}\n"
)


def test_arc_b_clean_case_passes(tmp_path):
    assert check_file(_write(tmp_path, "arc-b.yaml", ARC_B_OK)) == []


def test_arc_b_requires_the_conditioning_rule_to_be_seeded(tmp_path):
    """Without it, 'point of no return' has no primitive — #844 Threats §1."""
    text = "meta: {arc: B}\nepisodes:\n  - {id: EP_PLAN, content: 'the plan'}\n"
    problems = check_file(_write(tmp_path, "arc-b.yaml", text))
    assert any("no primitive behind it" in p for p in problems), problems


@pytest.mark.parametrize("leak", ["CP2", "checkpoint missed", "50% point"])
def test_arc_b_rejects_checkpoint_identifiers_and_verdicts(tmp_path, leak):
    text = ARC_B_OK + f"notes:\n  - '{leak} was the turning point'\n"
    problems = check_file(_write(tmp_path, "arc-b.yaml", text))
    assert any("checkpoint IDENTIFIERS" in p for p in problems), (leak, problems)


def test_arc_b_allows_the_bare_word_checkpoints(tmp_path):
    """Kent's rule SAYS checkpoints exist — that sentence is the primitive.

    The first version of this check banned the word outright and rejected the
    very episode it exists to require. Precision matters more than breadth.
    """
    text = (
        "meta: {arc: B}\n"
        "episodes:\n"
        "  - {id: EP_RULE, content: 'There are mid-programme checkpoints that "
        "say whether I am on track. If I am not hitting pace by the halfway "
        "point of the programme, there is no path to recovery.'}\n"
    )
    assert check_file(_write(tmp_path, "arc-b.yaml", text)) == []


ARC_E_OK = "meta: {arc: E}\ninterests:\n  - {id: INT_X, topic: 'graphs'}\n"


def test_arc_e_clean_case_passes(tmp_path):
    assert check_file(_write(tmp_path, "arc-e.yaml", ARC_E_OK)) == []


def test_arc_e_rejects_a_seeded_interest_status(tmp_path):
    """Status as of a week must be derived from add/drop episodes."""
    text = "meta: {arc: E}\ninterests:\n  - {id: INT_X, topic: 'x', status: active}\n"
    problems = check_file(_write(tmp_path, "arc-e.yaml", text))
    assert any("no status field" in p for p in problems), problems


@pytest.mark.parametrize("leak", ["Calendly", "auto-purge", "digest of just"])
def test_arc_e_rejects_the_automation_spec(tmp_path, leak):
    """Kent's automation spec is the oracle's answer to E1."""
    text = ARC_E_OK + f"notes:\n  - 'send a {leak} reply'\n"
    problems = check_file(_write(tmp_path, "arc-e.yaml", text))
    assert any("automation spec" in p for p in problems), (leak, problems)


@pytest.mark.parametrize("leak", ["triage session", "the same five"])
def test_arc_e_rejects_process_vocabulary(tmp_path, leak):
    text = ARC_E_OK + f"events:\n  - {{title: '{leak}'}}\n"
    problems = check_file(_write(tmp_path, "arc-e.yaml", text))
    assert any("process vocabulary" in p for p in problems), (leak, problems)


# --------------------------------------------------------------------------
# Oracle artifacts must not be confused with seeds
# --------------------------------------------------------------------------

ORACLE_DIR = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis" / "oracle"


def test_an_oracle_artifact_outside_the_seed_dir_is_skipped(tmp_path):
    """It legitimately contains every forbidden token — it IS the answer key."""
    text = (
        "meta: {arc: B, never_load: true}\n"
        "B1: {must_identify: ['the point of no return is the halfway point']}\n"
    )
    assert check_file(_write(tmp_path, "arc-b-oracle.yaml", text)) == []


def test_an_oracle_artifact_inside_the_seed_dir_is_rejected(tmp_path, monkeypatch):
    """An oracle file in seed/ is one glob away from being loaded into an arm."""
    import scripts.research.check_849_seed as mod

    monkeypatch.setattr(mod, "SEED_DIR", tmp_path)
    text = "meta: {arc: B, never_load: true}\nB1: {must_identify: ['x']}\n"
    problems = mod.check_file(_write(tmp_path, "arc-b-oracle.yaml", text))
    assert any("lives in the SEED directory" in p for p in problems), problems


def test_no_committed_seed_file_declares_never_load():
    import yaml as _yaml

    for path in sorted(SEED_DIR.glob("*.yaml")):
        doc = _yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        assert not (doc.get("meta") or {}).get("never_load"), path.name


def test_oracle_artifacts_live_outside_the_seed_directory():
    if not ORACLE_DIR.exists():
        pytest.skip("no oracle artifacts yet")
    assert ORACLE_DIR.resolve() != SEED_DIR.resolve()
    for path in ORACLE_DIR.glob("*.yaml"):
        assert check_file(path) == [], path.name
