"""The question manifest digests to the re-registered A4 constant (WP01 T003)."""

from __future__ import annotations

import hashlib
import pathlib
import sys
from datetime import datetime

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import questions as Q

RUBRIC = REPO_ROOT / "docs" / "design" / "research" / "849-rubric.md"


def test_manifest_digest_equals_the_registered_constant():
    ok, detail = Q.verify()
    assert ok, detail
    assert hashlib.sha256(Q.manifest_bytes()).hexdigest() == Q.MANIFEST_DIGEST


def test_a_one_character_change_in_any_text_is_refused(monkeypatch):
    q = Q.QUESTIONS[3]
    drifted = tuple(Q.Question(x.id, x.arc, x.ask_time, x.text + " ") if x is q else x for x in Q.QUESTIONS)
    monkeypatch.setattr(Q, "QUESTIONS", drifted)
    ok, _ = Q.verify()
    assert not ok


def test_eight_questions_in_ask_time_order():
    ids = [q.id for q in Q.QUESTIONS]
    assert ids == ["C1", "A", "F1", "B1", "E2", "E1", "F2", "B2"]
    stamps = [datetime.fromisoformat(q.ask_time) for q in Q.QUESTIONS]
    assert stamps == sorted(stamps)


@pytest.mark.skipif(not RUBRIC.exists(), reason="rubric not present")
def test_rows_match_the_rubric_table():
    rows = {}
    for line in RUBRIC.read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and "T" in line and "-04:00" in line and line.count("|") == 5:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells[0] in {"C1", "A", "F1", "B1", "E2", "E1", "F2", "B2"}:
                rows[cells[0]] = cells
    assert set(rows) == {q.id for q in Q.QUESTIONS}
    for q in Q.QUESTIONS:
        assert rows[q.id][1] == q.arc and rows[q.id][2] == q.ask_time and rows[q.id][3] == q.text


def test_by_id_and_ask_time():
    assert Q.by_id("B2").text == "Why did I miss sub-10?"
    assert Q.ask_time_dt("C1").isoformat() == "2026-04-28T09:06:00-04:00"
    with pytest.raises(KeyError):
        Q.by_id("Z9")
