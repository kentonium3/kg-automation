"""Blinded grading export (WP08 T034; contracts/grading-view.md; data-model.md § GradingView; FR-014, NFR-006).

The exporter is the one place an arm identity could reach the grader, so it is written to be
read with that single question in mind. From a COMPLETE ledger it writes three files into
three distinct directories under ``out_root``:

* ``views/<name>-grading.json`` — per question: ``question_text``, ``ask_time`` and, per
  blinded id, ``{"text", "truncated"}`` for every ``ok`` cell (up to nine), entries ordered by
  id. Nothing else: no arm, repeat, timing, token count, plan, seed, outcome or ledger path.
* ``admin/<name>-admin.json`` — the non-scored cells with arm/question/repeat/token counts, for
  the run's reader; never merged into the view ("a classification under a stable label would
  identify D").
* ``seals/<name>-seal.json`` — ``{blinded_id: {arm, question, repeat}}``, the blinding seed and
  the sha256 of the persisted header line; opened only after scores are in.

Blinded id per scored cell (contracts/grading-view.md, verbatim): "`q<Q>-<6 hex>` from
`Random(f"{seed}:{question}:{arm}:{repeat}")`; the id encodes neither arm nor repeat; entries are
ordered by id within a question." Six hex digits are the first 24 random bits of that generator.
Two cells of one question drawing the same id is refused, never resolved silently.

Refusals (:class:`ExportRefused`, nothing written): an incomplete ledger (a planned key not yet
terminal, or any ``not_implemented``), a seed that is not the header's blinding seed, a ledger
whose gates were skipped (development only — :data:`SKIP_GATES_SHA`), two outputs resolving into
one directory, or an existing output with different content.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
from dataclasses import dataclass
from typing import Any

from scripts.research.arms849 import questions as questions_mod
from scripts.research.arms849.ledger import (
    SCORED_OUTCOME,
    Binding,
    Ledger,
    RunKey,
    plan_keys,
)

__all__ = [
    "OUTPUT_DIRS",
    "SKIP_GATES_SHA",
    "ExportPaths",
    "ExportRefused",
    "binds_skip_gates",
    "blinded_id",
    "export",
    "is_complete",
    "seal_map",
]

#: The three output directories, one per output (contracts/grading-view.md: "the exporter never
#: writes two into one").
OUTPUT_DIRS = {"view": "views", "admin": "admin", "seal": "seals"}

#: The gate sha a ``--skip-gates`` ledger binds in place of all three gate records. A constant so
#: a development ledger is recognisable forever: sha256 of the bytes
#: ``b"arms849: gates skipped (development only)"``. The exporter refuses such a ledger.
SKIP_GATES_SHA = hashlib.sha256(b"arms849: gates skipped (development only)").hexdigest()


def binds_skip_gates(binding: Binding) -> bool:
    """A development ledger: its binding carries :data:`SKIP_GATES_SHA` in ANY of the three gate
    fields. The one predicate — the exporter and the harness both call it, so the two can never
    disagree on which ledgers are development (design lead, bus 20260926T005839019738Z48adbc3a83)."""
    return SKIP_GATES_SHA in (binding.preflight_sha, binding.gate_host_sha, binding.gate_container_sha)

#: The only keys a view entry may carry (contracts/grading-view.md "Nothing else").
VIEW_ENTRY_KEYS = ("text", "truncated")
VIEW_QUESTION_KEYS = ("question_text", "ask_time", "entries")


class ExportRefused(RuntimeError):
    """The ledger cannot be exported (incomplete, development-only, or an output collision)."""


@dataclass(frozen=True)
class ExportPaths:
    view: pathlib.Path
    admin: pathlib.Path
    seal: pathlib.Path


def blinded_id(seed: int, question: str, arm: str, repeat: int) -> str:
    """``q<Q>-<6 hex>`` drawn from ``Random(f"{seed}:{question}:{arm}:{repeat}")`` — the string seed
    is hashed by :mod:`random` deterministically (sha512 of the str), independent of PYTHONHASHSEED."""
    rng = random.Random(f"{seed}:{question}:{arm}:{repeat}")
    return f"q{question}-{rng.getrandbits(24):06x}"


def _planned_keys(ledger: Ledger) -> list[RunKey]:
    plan = ledger.header.plan
    if plan == len(plan_keys()):
        return plan_keys()
    if plan == len(plan_keys(arms=("D",))):
        return plan_keys(arms=("D",))
    raise ExportRefused(f"header plan {plan} is neither the primary (72) nor the secondary (24) plan")


def is_complete(ledger: Ledger) -> tuple[bool, str]:
    """Every planned key terminal and none ``not_implemented`` (contracts/grading-view.md; SC-001)."""
    keys = _planned_keys(ledger)
    pending = [k for k in keys if ledger.terminal(k) is None]
    unbuilt = [k for k in keys if ledger.terminal(k) == "not_implemented"]
    if pending or unbuilt:
        return False, (f"{len(pending)} of {len(keys)} planned cells not terminal, "
                       f"{len(unbuilt)} not_implemented")
    return True, f"{len(keys)} cells terminal, zero not_implemented"


def seal_map(ledger: Ledger, seed: int) -> dict[str, dict[str, Any]]:
    """``{blinded_id: {arm, question, repeat}}`` over every ``ok`` row; refuses an id collision."""
    out: dict[str, dict[str, Any]] = {}
    for row in ledger.grading_rows():
        bid = blinded_id(seed, row["question"], row["arm"], row["repeat"])
        if bid in out:
            raise ExportRefused(f"blinded id collision within question {row['question']}; choose another seed")
        out[bid] = {"arm": row["arm"], "question": row["question"], "repeat": row["repeat"]}
    return dict(sorted(out.items()))


def _view(ledger: Ledger, seed: int) -> dict[str, Any]:
    by_question: dict[str, dict[str, dict[str, Any]]] = {}
    for row in ledger.grading_rows():
        bid = blinded_id(seed, row["question"], row["arm"], row["repeat"])
        # Built from exactly two fields; nothing else of the row is read into the view.
        by_question.setdefault(row["question"], {})[bid] = {"text": row["text"], "truncated": row["truncated"]}
    view: dict[str, Any] = {"questions": {}}
    for q in questions_mod.QUESTIONS:              # manifest (ask_time) order
        entries = by_question.get(q.id, {})
        view["questions"][q.id] = {"question_text": q.text, "ask_time": q.ask_time,
                                   "entries": dict(sorted(entries.items()))}
    return view


def _admin(ledger: Ledger, name: str) -> dict[str, Any]:
    cells = []
    runs = ledger.run_rows()
    for key in _planned_keys(ledger):
        outcome = ledger.terminal(key)
        if outcome == SCORED_OUTCOME:
            continue
        key_rows = [r for r in runs if (r["arm"], r["question"], r["repeat"]) == (key.arm, key.question, key.repeat)]
        last = key_rows[-1] if key_rows else {}
        cells.append({
            **key.as_dict(), "outcome": outcome, "attempts": ledger.attempts_for(key),
            "prompt_tokens": last.get("prompt_tokens"), "context_limit_applied": last.get("context_limit_applied"),
            "error": last.get("error"),
        })
    return {"ledger": name, "non_scored": cells}


def _header_sha(ledger: Ledger) -> str:
    """sha256 of the header line exactly as persisted (line 1 of the file)."""
    with ledger.path.open("rb") as fh:
        first = fh.readline().rstrip(b"\n")
    return hashlib.sha256(first).hexdigest()


def _dirs(out_root: pathlib.Path) -> ExportPaths:
    root = pathlib.Path(out_root)
    made = {}
    for role, sub in OUTPUT_DIRS.items():
        d = root / sub
        d.mkdir(parents=True, exist_ok=True)
        made[role] = d.resolve()
    if len(set(made.values())) != len(made):
        raise ExportRefused(f"output directories are not distinct ({made}); the exporter never writes two "
                            f"outputs into one directory")
    return ExportPaths(**made)


def _write(path: pathlib.Path, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == data:
            return
        raise ExportRefused(f"{path} exists with different content; refusing to overwrite")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def export(ledger: Ledger, seed: int, out_root: pathlib.Path) -> ExportPaths:
    """Write the view, the admin report and the seal for a complete ledger (see module docstring)."""
    header = ledger.header
    if type(seed) is not int or seed != header.blinding_seed:
        raise ExportRefused("seed is not this ledger's blinding seed; ids would not reproduce from the seal")
    binding = header.binding
    if binds_skip_gates(binding):
        raise ExportRefused("this ledger was written with --skip-gates (development only); it is never graded")
    ok, detail = is_complete(ledger)
    if not ok:
        raise ExportRefused(f"ledger incomplete: {detail}")
    name = ledger.path.stem
    mapping = seal_map(ledger, seed)
    seal = {"seed": seed, "header_sha256": _header_sha(ledger), "map": mapping}
    view = _view(ledger, seed)
    n_entries = sum(len(q["entries"]) for q in view["questions"].values())
    if n_entries != len(ledger.grading_rows()) or n_entries != len(mapping):
        raise ExportRefused(f"view carries {n_entries} entries for {len(ledger.grading_rows())} ok rows")
    paths = _dirs(out_root)
    out = ExportPaths(view=paths.view / f"{name}-grading.json", admin=paths.admin / f"{name}-admin.json",
                      seal=paths.seal / f"{name}-seal.json")
    _write(out.view, view)
    _write(out.admin, _admin(ledger, name))
    _write(out.seal, seal)
    return out
