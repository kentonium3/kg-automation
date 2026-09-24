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

    h.run(ledger, CORPUS, limit=5)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 5

    h.run(ledger, CORPUS, limit=5)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 10, "resume re-ran work already in the ledger"
    keys = [(r["arm"], r["question"], r["repeat"]) for r in rows]
    assert len(set(keys)) == 10

    assert keys == [(k.arm, k.question, k.repeat) for k in h.plan()[:10]]


def test_a_completed_matrix_has_nothing_left_to_do(tmp_path, arms):
    ledger = tmp_path / "ledger.jsonl"
    h.run(ledger, CORPUS)
    completed, failed = h.run(ledger, CORPUS)
    assert (completed, failed) == (0, 0)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 72
    assert all(r["outcome"] == "ok" for r in rows)


def test_every_ledger_line_is_complete_json(tmp_path, arms):
    """An interrupted write would make the ledger unparseable, which loses the
    whole run rather than the cell in flight."""
    ledger = tmp_path / "ledger.jsonl"
    h.run(ledger, CORPUS, limit=4)
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
    h.run(ledger, CORPUS, limit=2)

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
    h.run(ledger, CORPUS, limit=3)
    _, rows = h.read_ledger(ledger)
    assert len(rows) == 3
    assert all(r["outcome"] == "not_implemented" for r in rows)


def test_an_arm_that_raises_is_recorded_and_the_run_continues(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"

    def exploding(question, ask_time, loaded):
        raise ValueError("substrate unavailable")

    monkeypatch.setitem(h.ARM_IMPLEMENTATIONS, "G", exploding)
    completed, failed = h.run(ledger, CORPUS, limit=2)
    assert failed == 2
    _, rows = h.read_ledger(ledger)
    assert all(r["outcome"] == "error" for r in rows)
    assert "substrate unavailable" in rows[0]["error"]
