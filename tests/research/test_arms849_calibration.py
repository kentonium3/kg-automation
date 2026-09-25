"""D-10 calibration (WP04 T019/T020): deterministic k, the two-sided band, the halt rule."""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import calibration as C

QUESTIONS = ["C1", "A", "F1", "B1", "E2", "E1", "F2", "B2"]


class FakeLedger:
    """Only what calibrate() reads: run_rows() and terminal()."""

    def __init__(self, g_tokens: dict[str, int], terminal: dict[str, str | None] | None = None) -> None:
        self._g = g_tokens
        self._terminal = terminal or {}

    def run_rows(self):
        return [{"arm": "G", "question": q, "repeat": 1, "outcome": "ok", "assembled_context_tokens": t}
                for q, t in self._g.items()]

    def terminal(self, key):
        if key.arm == "G" and key.repeat == 1:
            if key.question in self._terminal:
                return self._terminal[key.question]
            return "ok" if key.question in self._g else None
        return None


G = {q: 10_000 + i * 100 for i, q in enumerate(QUESTIONS)}         # median 10_350
AVAIL = {q: 50 for q in QUESTIONS}


def linear(records: int, per_event: int):
    """R tokens = records block + k events of `per_event` tokens each."""
    return lambda q, k: records + k * per_event


def test_smallest_k_inside_the_two_sided_band_is_chosen():
    cal = C.calibrate(FakeLedger(G), AVAIL, linear(2_000, 500), QUESTIONS)
    # 0.8 × 10_350 = 8_280 → k = 13 gives 8_500 (inside); k = 12 gives 8_000 (below)
    assert cal.k == 13 and cal.parity == "ok"
    assert 0.8 * cal.g_median <= cal.r_median <= 1.2 * cal.g_median
    assert set(cal.ratio) == set(QUESTIONS) and all(v > 0 for v in cal.ratio.values())


def test_same_inputs_twice_give_the_same_record():
    a = C.calibrate(FakeLedger(G), AVAIL, linear(2_000, 500), QUESTIONS).as_record()
    b = C.calibrate(FakeLedger(G), AVAIL, linear(2_000, 500), QUESTIONS).as_record()
    assert a == b and "ts" not in a and "record" not in a       # the ledger authors both


def test_records_block_alone_over_the_band_is_unattainable():
    cal = C.calibrate(FakeLedger(G), AVAIL, linear(20_000, 500), QUESTIONS)
    assert cal.k == 0 and cal.parity == "unattainable"


def test_availability_cap_below_the_band_is_infeasible():
    cal = C.calibrate(FakeLedger(G), {q: 3 for q in QUESTIONS}, linear(1_000, 500), QUESTIONS)
    assert cal.k == 3 and cal.parity == "infeasible" and cal.r_median < 0.8 * cal.g_median


def test_per_question_cap_applies_even_when_others_have_more():
    avail = {**AVAIL, "B2": 2}
    seen = {}
    def r(q, k):
        seen[q] = max(seen.get(q, 0), k)
        return 2_000 + k * 500
    C.calibrate(FakeLedger(G), avail, r, QUESTIONS)
    assert seen["B2"] == 2 and seen["C1"] > 2


def test_a_jump_over_the_band_takes_the_last_inside_point_or_is_unattainable():
    # step of 10_000 per event: k=1 → 12_000 (above 12_420? no: 12_000 ≤ 12_420 inside)
    cal = C.calibrate(FakeLedger(G), AVAIL, linear(2_000, 10_000), QUESTIONS)
    assert cal.k == 1 and cal.parity == "ok"
    # step of 11_000: k=1 → 13_000 > 12_420 and k=0 → 2_000 < 8_280 → nothing inside
    cal = C.calibrate(FakeLedger(G), AVAIL, linear(2_000, 11_000), QUESTIONS)
    assert cal.parity == "unattainable"


def test_population_incomplete_names_missing_and_terminal_error_questions():
    g = {q: t for q, t in G.items() if q not in ("E1", "B2")}
    with pytest.raises(C.CalibrationPopulationIncomplete) as ei:
        C.calibrate(FakeLedger(g, {"B2": "error"}), AVAIL, linear(2_000, 500), QUESTIONS)
    assert ei.value.missing == ["E1"] and ei.value.terminal_error == ["B2"]


def test_ratio_for_never_returns_null_or_zero():
    cal = C.calibrate(FakeLedger(G), AVAIL, linear(2_000, 500), QUESTIONS)
    assert isinstance(C.ratio_for("C1", 8_500, cal), float) and C.ratio_for("C1", 8_500, cal) > 0
    for r in (C.ratio_for("C1", None, cal), C.ratio_for("C1", 0, cal), C.ratio_for("ZZ", 10, cal), C.ratio_for("C1", 10, None)):
        assert isinstance(r, str) and r.startswith("unavailable:") and len(r) > len("unavailable:")
