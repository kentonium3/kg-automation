"""Tests for the #849 run harness — the phase-(a) properties, re-pointed to the arms849 modules (WP08).

The harness's job is not running 72 cells — it is stopping safely and resuming without
corrupting the result. So these test the stopping, not the running. Each test below is a
phase-(a) test kept by its property; the module each property now lives in is named.
The end-to-end fake-arm run is in test_arms849_integration.py.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
from datetime import datetime

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research import run_849_harness as h
from scripts.research.arms849 import preflight
from scripts.research.arms849.ledger import (
    Binding,
    LedgerBoundToAnotherConfig,
    open_ledger,
)
from scripts.research.arms849.questions import QUESTIONS
from tests.research.test_arms849_integration import (
    BLINDING_SEED,
    PRIMARY,
    ArmRefusal,
    FakeContextExceeded,
    FakeG,
    fake_arms,
    make_binding,
    make_runtime,
    open_fake,
    rows_of,
    runs,
)

CORPUS = h.DEFAULT_CORPUS

pytestmark = pytest.mark.skipif(
    not (CORPUS / "entities.json").exists(),
    reason="rendered corpus absent; run render_849_corpus first")


# --------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------


def test_the_plan_is_seventy_two_runs():
    assert len(h.plan()) == 72
    assert len(set(h.plan())) == 72, "a duplicated cell would be silently overwritten"
    assert len(h.plan("secondary")) == 24 and {k.arm for k in h.plan("secondary")} == {"D"}


def test_questions_run_in_ask_time_ascending_order_within_each_pass():
    """Protocol, not preference: D's cache hit rate is a property of this order,
    so a resume that reordered questions would change what cost measures."""
    expected = [q.id for q in QUESTIONS]
    stamps = [datetime.fromisoformat(q.ask_time) for q in QUESTIONS]
    assert stamps == sorted(stamps), "the manifest itself is out of order"

    for arm in h.ARMS:
        for repeat in range(1, 4):
            got = [k.question for k in h.plan() if k.arm == arm and k.repeat == repeat]
            assert got == expected, (arm, repeat, got)
    assert [k.arm for k in h.plan()[::24]] == ["G", "D", "R"], "arm-major G → D → R"


# --------------------------------------------------------------------------
# Resume (the ledger is the state)
# --------------------------------------------------------------------------


def test_resume_skips_completed_runs_and_finishes_the_matrix(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    for _ in range(2):
        with open_fake(ledger_path) as ledger:
            h.run_session(ledger, make_runtime(fake_arms()), limit=5)
    keys = [(r["arm"], r["question"], r["repeat"]) for r in runs(ledger_path)]
    assert len(keys) == 10 and len(set(keys)) == 10, "resume re-ran work already in the ledger"
    assert keys == [(k.arm, k.question, k.repeat) for k in h.plan()[:10]]


def test_a_completed_matrix_has_nothing_left_to_do(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    with open_fake(ledger_path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()))
    with open_fake(ledger_path) as ledger:
        report = h.run_session(ledger, make_runtime(fake_arms()))
        assert ledger.pending_keys(h.plan()) == []
    assert (report.completed, report.failed) == (0, 0)
    assert len(runs(ledger_path)) == 72


def test_every_ledger_line_is_complete_json(tmp_path):
    """An interrupted write would make the ledger unparseable, which loses the
    whole run rather than the cell in flight."""
    ledger_path = tmp_path / "ledger.jsonl"
    with open_fake(ledger_path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=4)
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        assert isinstance(json.loads(line), dict)


# --------------------------------------------------------------------------
# A ledger belongs to one corpus (now: one Binding — ledger.py, D-16)
# --------------------------------------------------------------------------


def _copy_corpus(dest: pathlib.Path) -> pathlib.Path:
    dest.mkdir()
    for p in CORPUS.iterdir():
        shutil.copy(p, dest / p.name)
    return dest


def test_a_ledger_refuses_to_resume_against_a_different_corpus(tmp_path):
    """The check that makes the pending freeze amendment safe: runs from two corpora
    averaged together are indistinguishable from runs from one."""
    ledger_path = tmp_path / "ledger.jsonl"
    with open_fake(ledger_path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=2)

    other = _copy_corpus(tmp_path / "corpus")
    with (other / "stream.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ref": "e99999", "at": "2026-01-01"}) + "\n")
    with pytest.raises(LedgerBoundToAnotherConfig):
        make_binding(corpus=other)

    # A binding that differs in any field is refused on resume, and nothing is appended.
    good = make_binding()
    foreign = Binding(**{**good.as_dict(), "run_env_commit": "another-export"})
    with pytest.raises(LedgerBoundToAnotherConfig, match="different configuration"):
        open_ledger(ledger_path, foreign, BLINDING_SEED, h.PRIMARY_PLAN)
    assert len(runs(ledger_path)) == 2, "the refused resume must not have appended"


def test_loader_links_are_part_of_the_binding(tmp_path):
    """The amendment added loader_links.jsonl — a corpus without it cannot be bound."""
    corpus = _copy_corpus(tmp_path / "corpus")
    assert make_binding(corpus=corpus).corpus["loader_links.jsonl"]
    (corpus / "loader_links.jsonl").unlink()
    with pytest.raises(LedgerBoundToAnotherConfig):
        make_binding(corpus=corpus)


# --------------------------------------------------------------------------
# Could-not-run and ran-and-failed are different outcomes
# --------------------------------------------------------------------------


def test_an_unregistered_arm_is_recorded_not_silently_skipped(tmp_path):
    """"Could not run" and "ran and scored zero" must never collapse."""
    ledger_path = tmp_path / "ledger.jsonl"
    with open_fake(ledger_path) as ledger:
        h.run_session(ledger, make_runtime({}), limit=3)
    assert [r["outcome"] for r in runs(ledger_path)] == ["not_implemented"] * 3


def test_an_arm_that_raises_is_recorded_and_the_run_continues(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    exploding = FakeG(fail=lambda q, ctx: ValueError("substrate unavailable"))
    with open_fake(ledger_path) as ledger:
        report = h.run_session(ledger, make_runtime(fake_arms(g=exploding)), limit=2)
    rs = runs(ledger_path)
    assert report.failed == 2 and report.stopped is None
    assert len(rs) == 6, "two keys × three attempts (FR-007)"
    assert all(r["outcome"] == "error" for r in rs)
    assert "substrate unavailable" in rs[0]["error"]


# --------------------------------------------------------------------------
# Amendment A1: loader_links is arm G's input only
# --------------------------------------------------------------------------


def test_only_arm_g_sees_loader_links():
    """The flat arms must not get the traversal the graph arm has to earn."""
    from scripts.research.load_849_corpus import replay
    ask = datetime.fromisoformat("2026-10-16T09:00:00-04:00")

    g = h.arm_view(h.RunKey("G", "B2", 1), replay(CORPUS, ask, verify=False))
    assert g.links, "arm G must receive the MENTIONS wiring"
    for arm in ("D", "R"):
        view = h.arm_view(h.RunKey(arm, "B2", 1), replay(CORPUS, ask, verify=False))
        assert view.links == [], f"arm {arm} must never see loader_links"


def test_arm_inputs_declares_links_for_g_only():
    from scripts.research.load_849_corpus import ARM_INPUTS
    assert "loader_links.jsonl" in ARM_INPUTS["G"]
    assert "loader_links.jsonl" not in ARM_INPUTS["D"]
    assert "loader_links.jsonl" not in ARM_INPUTS["R"]


# --------------------------------------------------------------------------
# Amendment A1 (d): the four gates precede any run (now: preflight + container gate)
# --------------------------------------------------------------------------


def test_the_four_gates_are_the_preflight_checkers_and_pass_on_the_current_corpus():
    names = preflight.checkers()
    assert sorted(n.rsplit("_", 1)[-1] for n in names) == ["freeze", "loader", "oracle", "seed"]
    outcomes = [preflight._run_checker(n) for n in names]
    assert all(o.passed for o in outcomes), [(o.name, o.tail) for o in outcomes if not o.passed]


def test_a_failing_gate_stops_the_run(tmp_path, monkeypatch):
    """A run against a corpus that fails a gate produces numbers that look exactly like numbers
    from a corpus that passed: the container phase refuses and no header is written."""
    from scripts.research.arms849.gates import GatesRefused

    def refuse(env, out):
        raise GatesRefused("container phase refused:\n  preflight_present_and_matching: "
                           "preflight gate check_849_loader did not pass")

    monkeypatch.setattr(h, "RUNS_DIR", tmp_path / "runs")
    with pytest.raises(GatesRefused, match="check_849_loader"):
        h.live_binding(tmp_path / "ledger.jsonl", CORPUS, PRIMARY, "2026-09-25T00:00:00+00:00",
                       skip_gates=False, container_phase=refuse)
    assert not (tmp_path / "ledger.jsonl").exists(), "no ledger on a failed gate"
    record = json.loads((tmp_path / "runs" / "gate-container.json").read_text(encoding="utf-8"))
    assert record["passed"] is False and record["failed"][0]["name"] == "preflight_present_and_matching"


# --------------------------------------------------------------------------
# Amendment A2: exceeds_model_context is an outcome, never a score
# --------------------------------------------------------------------------


def test_context_exceeded_is_recorded_not_errored_and_not_scored(tmp_path):
    """Six D cells are expected to land here: visible with the token count, distinct from an
    error, and absent from every average."""
    def d_arm(question, view, ctx):
        raise FakeContextExceeded(362_772, ctx.limit, ctx.limit_applied, {"layout": "events_entities_edges"})

    ledger_path = tmp_path / "ledger.jsonl"
    arms = {**fake_arms(), "D": h.ArmRegistration(refusal=ArmRefusal, answer=d_arm)}
    with open_fake(ledger_path) as ledger:
        report = h.run_session(ledger, make_runtime(arms), limit=26)   # 24 G cells, then two D
        header = ledger.header
    assert report.failed == 0, "exceeds_model_context must not count as a failure"
    d_rows = [r for r in runs(ledger_path) if r["arm"] == "D"]
    assert len(d_rows) == 2 and all(r["outcome"] == "exceeds_model_context" for r in d_rows)
    assert all(r["prompt_tokens"] == 362_772 and r["context_limit_applied"] == "trained" for r in d_rows)
    assert header.binding.model_context_tokens == 262_144


def test_exceeds_cells_are_never_averaged(tmp_path):
    """The could-not-check / verified-false collapse A2 forbids: a cell with no number must not
    read as zero (Ledger.summarise)."""
    ledger_path = tmp_path / "ledger.jsonl"
    with open_fake(ledger_path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()))
        s = ledger.summarise()
    assert s[("D", "C1")].mean_assembled_tokens == 20_000
    assert s[("D", "C1")].range_assembled_tokens == (20_000, 20_000)
    b2 = s[("D", "B2")]
    assert b2.n_scored == 0
    assert b2.mean_assembled_tokens is None, "an exceeds cell averaged in would read as 0"
    assert b2.counts["exceeds_model_context"] == 3


def test_summarise_would_fail_if_exceeds_cells_leaked_into_the_mean(tmp_path):
    """Guards the guard: a zero-token ok cell is what a leaked exceeds cell would look like — it
    is distinguishable by outcome, and it is."""
    def zero_d(question, view, ctx):
        from tests.research.test_arms849_integration import scored
        return scored("answer zero", 0, context_limit_applied=ctx.limit_applied)

    ledger_path = tmp_path / "ledger.jsonl"
    with open_fake(ledger_path) as ledger:
        h.run_session(ledger, make_runtime({**fake_arms(), "D": h.ArmRegistration(refusal=ArmRefusal, answer=zero_d)}), limit=32)
        s = ledger.summarise()
    assert s[("D", "B2")].mean_assembled_tokens == 0 and s[("D", "B2")].n_scored == 1


def test_status_line_is_one_line_the_operator_relays(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    with open_fake(ledger_path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=3)
        line = h.status_line(ledger)
    assert "\n" not in line and line.startswith("arms849 status: ledger.jsonl [primary] 3/72 terminal")
    assert [r.get("record") for r in rows_of(ledger_path)].count("header") == 1
