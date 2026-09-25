"""D-10 calibration (WP04 T019): arm R's k, chosen ONCE from G's repeat-1 medians.

Deterministic — identical inputs give an identical record (the ledger authors the
timestamp when it writes the `calibration` row); written once and never recomputed:
repeats 2–3 of G must not move R's configuration.

Procedure (rubric A4 §2, research.md D-10):
- require all eight G repeat-1 cells `ok`; otherwise `CalibrationPopulationIncomplete`
  names the missing/terminal-error questions (the harness turns it into a `halt`
  event and a `blocked` bus post — never a silent default);
- for k = 1, 2, … compute R's assembled tokens per question via the supplied
  callable (records block + top-k events, availability-capped); pick the SMALLEST
  k whose median across the eight questions lies within the TWO-SIDED band
  [0.8, 1.2] × median(G repeat-1 assembled tokens);
- if the records block alone (k = 0) already exceeds 1.2× → `parity: unattainable`,
  k = 0; if no k within availability reaches 0.8× → k = max available,
  `parity: infeasible`; ties go to the smaller k (the smallest k is taken first).
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

__all__ = ["BAND", "Calibration", "CalibrationPopulationIncomplete", "calibrate", "ratio_for"]

BAND = (0.8, 1.2)
SCORED = "ok"


class CalibrationPopulationIncomplete(RuntimeError):
    """Not every G repeat-1 cell is `ok`; D-10's halt rule applies."""

    def __init__(self, missing: Sequence[str], terminal_error: Sequence[str]) -> None:
        self.missing = list(missing)
        self.terminal_error = list(terminal_error)
        super().__init__(f"G repeat-1 population incomplete: not yet scored {self.missing}; "
                         f"terminal error {self.terminal_error}")


@dataclass(frozen=True)
class Calibration:
    k: int
    parity: str                       # "ok" | "unattainable" | "infeasible"
    g_medians: dict[str, int]         # per question, G repeat-1 assembled tokens
    g_median: float                   # median of the eight
    r_tokens_at_k: dict[str, int]     # per question, R assembled tokens at k (availability-capped)
    r_median: float
    ratio: dict[str, float]           # per question r/g
    availability: dict[str, int]      # per question, events available at ask_time
    band: tuple[float, float]

    def as_record(self) -> dict[str, Any]:
        d = asdict(self)
        d["band"] = list(self.band)
        return d


def _g_repeat1(ledger: Any, questions: Sequence[str]) -> dict[str, int]:
    """Assembled tokens of every G repeat-1 `ok` row; raises when any is not scored."""
    from scripts.research.arms849.ledger import RunKey

    missing, terminal_error, out = [], [], {}
    rows = {(r["question"]): r for r in ledger.run_rows()
            if r["arm"] == "G" and r["repeat"] == 1 and r["outcome"] == SCORED}
    for q in questions:
        term = ledger.terminal(RunKey("G", q, 1))
        if term == SCORED and q in rows:
            out[q] = int(rows[q]["assembled_context_tokens"])
        elif term == "error":
            terminal_error.append(q)
        else:
            missing.append(q)
    if missing or terminal_error:
        raise CalibrationPopulationIncomplete(missing, terminal_error)
    return out


def calibrate(ledger: Any, availability: Mapping[str, int],
              assemble_r_tokens: Callable[[str, int], int],
              questions: Sequence[str] | None = None) -> Calibration:
    """See the module docstring. `assemble_r_tokens(question, k)` must return the exact token
    count of R's assembled text (records block + top-k events re-sorted) for that k, with k
    already capped at the question's availability by the caller-supplied cap here."""
    if questions is None:
        from scripts.research.arms849.questions import QUESTIONS
        questions = [q.id for q in QUESTIONS]
    questions = list(questions)
    g = _g_repeat1(ledger, questions)
    g_median = statistics.median(g[q] for q in questions)
    lo, hi = BAND[0] * g_median, BAND[1] * g_median
    caps = {q: int(availability[q]) for q in questions}
    max_k = max(caps.values()) if caps else 0

    def r_at(k: int) -> dict[str, int]:
        return {q: int(assemble_r_tokens(q, min(k, caps[q]))) for q in questions}

    def finish(k: int, parity: str, r: dict[str, int]) -> Calibration:
        r_median = statistics.median(r[q] for q in questions)
        return Calibration(
            k=k, parity=parity, g_medians=dict(g), g_median=float(g_median), r_tokens_at_k=r,
            r_median=float(r_median), ratio={q: (r[q] / g[q] if g[q] else float("inf")) for q in questions},
            availability=caps, band=BAND)

    r0 = r_at(0)
    if statistics.median(r0[q] for q in questions) > hi:
        return finish(0, "unattainable", r0)       # the records block alone overshoots the band
    for k in range(1, max_k + 1):
        r = r_at(k)
        med = statistics.median(r[q] for q in questions)
        if lo <= med <= hi:
            return finish(k, "ok", r)              # smallest k inside the two-sided band
        if med > hi:
            # The curve is monotone in k; crossing the band without landing in it means the
            # step from k-1 to k jumped over — take the closer side, recorded as ok only if inside.
            if k > 1:                                  # candidates start at k = 1; k = 0 is never "ok"
                prev = r_at(k - 1)
                prev_med = statistics.median(prev[q] for q in questions)
                if lo <= prev_med <= hi:
                    return finish(k - 1, "ok", prev)
            return finish(k, "unattainable", r)
    return finish(max_k, "infeasible", r_at(max_k))  # availability exhausted below 0.8×


def ratio_for(question: str, r_tokens: int | None, calibration: Calibration | None) -> float | str:
    """The per-row `r_g_ratio` (D-10): a positive number, or `unavailable:<reason>` — never null, never 0."""
    if calibration is None:
        return "unavailable: no calibration record"
    g = calibration.g_medians.get(question)
    if not g:
        return f"unavailable: no G repeat-1 median for {question}"
    if r_tokens is None or r_tokens <= 0:
        return f"unavailable: R assembled tokens not measured for {question}"
    return r_tokens / g
