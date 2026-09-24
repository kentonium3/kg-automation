"""Tests for the #849 run harness.

The harness's job is not running 72 cells — it is stopping safely and resuming
without corrupting the result. So these test the stopping, not the running.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research import run_849_harness as h  # noqa: E402
from scripts.research.check_849_loader import ASK_TIMES  # noqa: E402

CORPUS = h.DEFAULT_CORPUS

pytestmark = pytest.mark.skipif(
    not (CORPUS / "entities.json").exists(),
    reason="rendered corpus absent; run render_849_corpus first")


@pytest.fixture
def arms(monkeypatch):
    """Register three trivial arms so the matrix can actually execute."""
    def make(label):
        def arm(question, ask_time, loaded):
            return h.Answer(text=f"{label}:{question}",
                            assembled_context_tokens=len(loaded.events))
        return arm
    monkeypatch.setitem(h.ARM_IMPLEMENTATIONS, "G", make("G"))
    monkeypatch.setitem(h.ARM_IMPLEMENTATIONS, "D", make("D"))
    monkeypatch.setitem(h.ARM_IMPLEMENTATIONS, "R", make("R"))


# --------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------


def test_the_plan_is_seventy_two_runs():
    assert len(h.plan()) == 72
    assert len(set(h.plan())) == 72, "a duplicated cell would be silently overwritten"


def test_questions_run_in_ask_time_ascending_order_within_each_pass():
    """Protocol, not preference: D's cache hit rate is a property of this order,
    so a resume that reordered questions would change what cost measures."""
    expected = [label for label, _ in ASK_TIMES]
    stamps = [datetime.fromisoformat(s) for _, s in ASK_TIMES]
    assert stamps == sorted(stamps), "ASK_TIMES itself is out of order"

    for arm in h.ARMS:
        for repeat in range(1, h.REPEATS + 1):
            got = [k.question for k in h.plan()
                   if k.arm == arm and k.repeat == repeat]
            assert got == expected, (arm, repeat, got)


# --------------------------------------------------------------------------
# Resume
# --------------------------------------------------------------------------


def test_resume_skips_completed_runs_and_finishes_the_matrix(tmp_path, arms):
    ledger = tmp_path / "ledger.jsonl"

    h.run(ledger, CORPUS, limit=5, gates=False)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 5

    h.run(ledger, CORPUS, limit=5, gates=False)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 10, "resume re-ran work already in the ledger"
    keys = [(r["arm"], r["question"], r["repeat"]) for r in rows]
    assert len(set(keys)) == 10

    assert keys == [(k.arm, k.question, k.repeat) for k in h.plan()[:10]]


def test_a_completed_matrix_has_nothing_left_to_do(tmp_path, arms):
    ledger = tmp_path / "ledger.jsonl"
    h.run(ledger, CORPUS, gates=False)
    completed, failed = h.run(ledger, CORPUS, gates=False)
    assert (completed, failed) == (0, 0)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 72
    assert all(r["outcome"] == "ok" for r in rows)


def test_every_ledger_line_is_complete_json(tmp_path, arms):
    """An interrupted write would make the ledger unparseable, which loses the
    whole run rather than the cell in flight."""
    ledger = tmp_path / "ledger.jsonl"
    h.run(ledger, CORPUS, limit=4, gates=False)
    for line in ledger.read_text(encoding="utf-8").splitlines():
        assert json.loads(line)


# --------------------------------------------------------------------------
# A ledger belongs to one corpus
# --------------------------------------------------------------------------


def test_a_ledger_refuses_to_resume_against_a_different_corpus(tmp_path, arms):
    """The check that makes the pending freeze amendment safe.

    Runs from two corpora averaged together are indistinguishable from runs
    from one, and #849 has an amendment pending that changes the fingerprints.
    """
    ledger = tmp_path / "ledger.jsonl"
    h.run(ledger, CORPUS, limit=2, gates=False)

    other = tmp_path / "corpus"
    other.mkdir()
    for name in ("stream.jsonl", "entities.json", "manifest.json"):
        (other / name).write_bytes((CORPUS / name).read_bytes())
    with (other / "stream.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ref": "e99999", "at": "2026-01-01"}) + "\n")

    with pytest.raises(h.LedgerBoundToAnotherCorpus) as exc:
        h.open_ledger(ledger, other)
    assert "two corpora" in str(exc.value)

    _, rows = h.read_ledger(ledger)
    assert len(rows) == 2, "the refused resume must not have appended"


def test_adding_loader_links_changes_the_binding(tmp_path, arms):
    """The amendment adds loader_links.jsonl — that alone must rebind."""
    corpus_a = tmp_path / "a"
    corpus_a.mkdir()
    for name in ("stream.jsonl", "entities.json", "manifest.json"):
        (corpus_a / name).write_bytes((CORPUS / name).read_bytes())
    before = h.corpus_fingerprints(corpus_a)

    (corpus_a / "loader_links.jsonl").write_text(
        json.dumps({"ref": "e00009", "mentions": ["PER_MARCUS"]}) + "\n",
        encoding="utf-8")
    after = h.corpus_fingerprints(corpus_a)

    assert "loader_links.jsonl" not in before
    assert "loader_links.jsonl" in after
    assert before != after


# --------------------------------------------------------------------------
# Could-not-run and ran-and-failed are different outcomes
# --------------------------------------------------------------------------


def test_an_unregistered_arm_is_recorded_not_silently_skipped(tmp_path):
    """"Could not run" and "ran and scored zero" must never collapse."""
    ledger = tmp_path / "ledger.jsonl"
    h.ARM_IMPLEMENTATIONS.clear()
    h.run(ledger, CORPUS, limit=3, gates=False)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 3
    assert all(r["outcome"] == "not_implemented" for r in rows)


def test_an_arm_that_raises_is_recorded_and_the_run_continues(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"

    def exploding(question, ask_time, loaded):
        raise ValueError("substrate unavailable")

    monkeypatch.setitem(h.ARM_IMPLEMENTATIONS, "G", exploding)
    completed, failed = h.run(ledger, CORPUS, limit=2, gates=False)
    assert failed == 2
    _, rows = h.read_ledger(ledger)
    assert all(r["outcome"] == "error" for r in rows)
    assert "substrate unavailable" in rows[0]["error"]


# --------------------------------------------------------------------------
# Amendment A1: loader_links is arm G's input only
# --------------------------------------------------------------------------


def test_only_arm_g_sees_loader_links():
    """The flat arms must not get the traversal the graph arm has to earn.

    D and R are handed a view with no links rather than trusted not to look —
    an assertion that depends on an arm's good behaviour is not an assertion.
    """
    from datetime import datetime as _dt
    from scripts.research.load_849_corpus import replay as _replay
    ask = _dt.fromisoformat("2026-10-16T09:00:00-04:00")

    g = h.arm_view(h.RunKey("G", "B2", 1), _replay(CORPUS, ask, verify=False))
    assert g.links, "arm G must receive the MENTIONS wiring"

    for arm in ("D", "R"):
        view = h.arm_view(h.RunKey(arm, "B2", 1), _replay(CORPUS, ask, verify=False))
        assert view.links == [], f"arm {arm} must never see loader_links"


def test_arm_inputs_declares_links_for_g_only():
    from scripts.research.load_849_corpus import ARM_INPUTS
    assert "loader_links.jsonl" in ARM_INPUTS["G"]
    assert "loader_links.jsonl" not in ARM_INPUTS["D"]
    assert "loader_links.jsonl" not in ARM_INPUTS["R"]


# --------------------------------------------------------------------------
# Amendment A1 (d): the four gates precede any run
# --------------------------------------------------------------------------


def test_all_four_gates_pass_on_the_current_corpus():
    assert h.verify_gates() == []


def test_a_failing_gate_stops_the_run(tmp_path, monkeypatch, arms):
    """A run against a corpus that fails a gate produces numbers that look
    exactly like numbers from a corpus that passed."""
    import scripts.research.check_849_loader as loader_check
    monkeypatch.setattr(loader_check, "main", lambda argv: 1)

    with pytest.raises(h.GateFailed) as exc:
        h.run(tmp_path / "ledger.jsonl", CORPUS, limit=1, gates=True)
    assert "check_849_loader" in str(exc.value)
    assert not (tmp_path / "ledger.jsonl").exists(), "no ledger on a failed gate"


# --------------------------------------------------------------------------
# Amendment A2: exceeds_model_context is an outcome, never a score
# --------------------------------------------------------------------------


def test_context_exceeded_is_recorded_not_errored_and_not_scored(tmp_path, monkeypatch):
    """Six D cells are expected to land here. They must be visible in the
    ledger with the token count, distinct from an error, and absent from
    every average."""
    def d_arm(question, ask_time, loaded):
        raise h.ContextExceeded(prompt_tokens=362_772)

    def ok_arm(question, ask_time, loaded):
        return h.Answer(text="x", assembled_context_tokens=1000)

    monkeypatch.setitem(h.ARM_IMPLEMENTATIONS, "D", d_arm)
    monkeypatch.setitem(h.ARM_IMPLEMENTATIONS, "G", ok_arm)
    ledger = tmp_path / "ledger.jsonl"
    # 24 G cells (all ok), then the first D cells.
    completed, failed = h.run(ledger, CORPUS, limit=26, gates=False)
    assert failed == 0, "exceeds_model_context must not count as a failure"
    header, rows = h.read_ledger(ledger)
    d_rows = [r for r in rows if r["arm"] == "D"]
    assert d_rows and all(r["outcome"] == "exceeds_model_context" for r in d_rows)
    assert all(r["prompt_tokens"] == 362_772 for r in d_rows)
    assert all(r["model_context_tokens"] == h.MODEL_CONTEXT_TOKENS for r in d_rows)
    assert header["model_context_tokens"] == h.MODEL_CONTEXT_TOKENS


def test_exceeds_cells_are_never_averaged():
    """The could-not-check / verified-false collapse A2 forbids: a cell with
    no number must not read as zero."""
    rows = [
        {"arm": "D", "question": "C1", "repeat": 1, "outcome": "ok", "assembled_context_tokens": 50_000},
        {"arm": "D", "question": "C1", "repeat": 2, "outcome": "ok", "assembled_context_tokens": 52_000},
        {"arm": "D", "question": "B2", "repeat": 1, "outcome": "exceeds_model_context", "prompt_tokens": 362_772},
        {"arm": "D", "question": "B2", "repeat": 2, "outcome": "exceeds_model_context", "prompt_tokens": 362_772},
        {"arm": "D", "question": "B2", "repeat": 3, "outcome": "error", "error": "boom"},
    ]
    s = h.summarise(rows)
    assert s[("D", "C1")]["mean_context_tokens"] == 51_000
    assert s[("D", "C1")]["range_context_tokens"] == (50_000, 52_000)
    b2 = s[("D", "B2")]
    assert b2["n_scored"] == 0
    assert b2["mean_context_tokens"] is None, "an exceeds cell averaged in would read as 0"
    assert b2["exceeds_model_context"] == 2
    assert b2["error"] == 1


def test_summarise_would_fail_if_exceeds_cells_leaked_into_the_mean():
    """Guards the guard: prove the test above discriminates."""
    rows = [
        {"arm": "D", "question": "B2", "repeat": 1, "outcome": "ok", "assembled_context_tokens": 0},
    ]
    assert h.summarise(rows)[("D", "B2")]["mean_context_tokens"] == 0, \
        "a zero-token ok cell is what a leaked exceeds cell would look like — it must be distinguishable by outcome, and it is"
