#!/usr/bin/env python3
"""Leak-detector for #849 seed files.

The #849 corpus is split into a SEED, which both arms see, and a HIDDEN ORACLE,
which neither does. The worksheet's governing rule is:

    Seeds assert primitives only. No conflict, drift or pattern is ever written
    as an edge; all of it must be inferable.

A seed that leaks one oracle fact does not fail loudly — it silently converts a
multi-hop inference into a field lookup and the run still produces numbers. That
is the worst failure mode available here, so this check exists to make the rule
mechanical rather than remembered.

Two classes of check:

1. **Vocabulary.** Verdict-shaped keys and values must not appear in seed DATA.
   Comments are exempt on purpose: a seed file SHOULD explain which leak it is
   avoiding, and a naive text scan cannot tell an assertion from a warning
   against that assertion. (Learned the hard way — the first version of this
   check failed on its own explanatory comment.)

2. **Structural absences.** Some arcs turn on something NOT being there. Those
   are asserted positively here so that adding the thing later fails a test
   instead of quietly weakening an arc.

Usage:
    python3 -m scripts.research.check_849_seed [PATH ...]

With no arguments, checks every *.yaml under docs/design/research/849-synthesis/seed/.
Exit 0 = clean, 1 = a leak was found.
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_DIR = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis" / "seed"

#: Tokens that are verdicts, not primitives. If one of these shows up in seed
#: DATA, an oracle fact has been written into the corpus.
FORBIDDEN_TOKENS = (
    "overdue",
    "unmaterialis",
    "near_miss",
    "is_near_miss",
    "near-miss:",
    "conflict:",
    "conflicts_with:",
    "is_conflict",
    "drift:",
    "is_drift",
    "travel_missing",
    "understated",
    "movable:",
    "fixed:",
    "point_of_no_return",
    "lapsed",
    "erosion",
    "should_have_been_caught",
    "correct_answer",
    "oracle",
)

#: Per-arc structural invariants: things that must be ABSENT.
#: (arc, description, predicate) — predicate returns True when the seed is OK.
def _no_inbound_edges_to(doc: dict, node_id: str) -> bool:
    return not [e for e in doc.get("edges", []) or [] if e.get("to") == node_id]


def _outcome_has_no_status(doc: dict, outcome_id: str) -> bool:
    for o in doc.get("outcomes", []) or []:
        if o.get("id") == outcome_id:
            return "status" not in o and "completed" not in o and "shipped" not in o
    return True  # outcome not in this file


def _tasks_have_no_outcome(doc: dict) -> bool:
    """Arc F: a standing practice anchors via EMBODIES, never an Outcome."""
    if doc.get("outcomes"):
        return False
    return not any("outcome" in (t or {}) for t in (doc.get("tasks") or []))


def _every_task_embodies_a_principle(doc: dict) -> bool:
    """The flip side: no Outcome is only correct if EMBODIES is present."""
    tasks = {t.get("id") for t in (doc.get("tasks") or [])}
    if not tasks:
        return True
    embodied = {
        e.get("from")
        for e in (doc.get("edges") or [])
        if e.get("type") == "EMBODIES"
    }
    return tasks <= embodied


def _no_rate_field_anywhere(doc: dict) -> bool:
    """Arc F's finding is the SLOPE; a seeded rate turns it into subtraction."""
    banned = {
        "target_rate", "expected_per_week", "goal_per_week", "streak",
        "target_check_ins", "expected_frequency", "threshold",
    }
    flat = yaml.safe_dump(doc).lower()
    return not any(b in flat for b in banned)


STRUCTURAL_CHECKS = {
    "A": [
        (
            "no commitment carries a fixed/movable verdict",
            lambda d: all(
                "movable" not in c and "fixed" not in c
                for c in (d.get("commitments") or [])
            ),
        ),
    ],
    "C": [
        (
            "OUT_LAUNCH must not assert completion — the launch-ended "
            "inference is the arc's third hop",
            lambda d: _outcome_has_no_status(d, "OUT_LAUNCH"),
        ),
        (
            "nothing may point at COM_DESIGN_REVIEW — the unmaterialised-"
            "commitment absence IS the finding",
            lambda d: _no_inbound_edges_to(d, "COM_DESIGN_REVIEW"),
        ),
        (
            "COM_DESIGN_REVIEW must be trigger-gated, never dated",
            lambda d: any(
                c.get("id") == "COM_DESIGN_REVIEW"
                and c.get("datetime") is None
                and c.get("trigger")
                for c in (d.get("commitments") or [])
            ),
        ),
    ],
    "B": [
        (
            "no checkpoint IDENTIFIERS or verdicts in the rendered view — "
            "CP1-CP4 and their targets are the ORACLE's derivation from the "
            "plan plus the conditioning rule. NOTE: the bare word "
            "'checkpoints' is ALLOWED, because Kent's conditioning rule says "
            "checkpoints exist — that is the primitive. What is forbidden is "
            "naming or evaluating them.",
            lambda d: not any(
                k in yaml.safe_dump(_rendered_view(d)).lower()
                for k in ("cp1", "cp2", "cp3", "cp4",
                          "checkpoint missed", "checkpoint failed",
                          "checkpoint hit", "50% point", "halfway checkpoint")
            ),
        ),
        (
            "the conditioning rule must be seeded as an episode — without it "
            "the 'point of no return' oracle point has no primitive behind it "
            "(#844 Threats §1)",
            lambda d: any(
                "halfway point" in (e.get("content") or "").lower()
                for e in (d.get("episodes") or [])
            ),
        ),
    ],
    "E": [
        (
            "the automation spec must NOT be seeded — it is the oracle's "
            "'what should be proposed' and seeding it answers E1 outright",
            lambda d: not any(
                k in yaml.safe_dump(_rendered_view(d)).lower()
                for k in ("calendly", "auto-file", "auto_file", "digest of just",
                          "30-day purge", "auto-purge")
            ),
        ),
        (
            "Interest must carry no status field — status as of a week is "
            "derived from add/drop episodes, which is what makes near-miss 7 "
            "bi-temporal rather than a lookup",
            lambda d: all(
                "status" not in (i or {}) for i in (d.get("interests") or [])
            ),
        ),
        (
            "no process vocabulary in the rendered view — the five "
            "sub-activities must be inferable from the action shape, not named",
            lambda d: not any(
                k in yaml.safe_dump(_rendered_view(d)).lower()
                for k in ("triage session", "sub-activit", "the same five")
            ),
        ),
    ],
    "F": [
        (
            "a standing practice must have NO Outcome — an Outcome requires a "
            "measure, and any measure seeds the target rate the oracle says "
            "must be inferred from the slope (Q1 ruling, Kent-ratified)",
            _tasks_have_no_outcome,
        ),
        (
            "every practice Task must carry an EMBODIES edge to its Principle "
            "— 'no Outcome' is only correct because EMBODIES is the anchor; "
            "without it the task floats",
            _every_task_embodies_a_principle,
        ),
        (
            "no target-rate field may appear anywhere in Arc F",
            _no_rate_field_anywhere,
        ),
    ],
}


#: Top-level keys whose contents are GENERATOR INPUT or CROSS-ARC REFERENCES —
#: consumed by the renderer to produce corpus events, never rendered verbatim.
#:
#: These legitimately contain oracle-adjacent structure. Arc B's generator input
#: marks which misses the oracle counts; Arc F's carries the phase bands. That
#: is correct: the renderer needs it to emit the right events, and the arms
#: never see it. But the exemption is only safe if it is DECLARED, so a seed
#: must list its non-rendered keys in `meta.non_rendered` and the renderer must
#: strip exactly those. An undeclared block containing verdict vocabulary is a
#: leak; a declared one is a contract.
DEFAULT_NON_RENDERED = frozenset()


def _non_rendered_keys(doc: dict) -> frozenset[str]:
    declared = (doc.get("meta") or {}).get("non_rendered") or []
    return frozenset(declared)


def _rendered_view(doc: dict) -> dict:
    """The part of a seed the arms can eventually see."""
    skip = _non_rendered_keys(doc) | {"meta"}
    return {k: v for k, v in doc.items() if k not in skip}


def strip_comments(raw: str) -> str:
    """Remove whole-line comments so checks read DATA, not prose about it."""
    return re.sub(r"(?m)^\s*#.*$", "", raw)


def _orphan_decisions(doc: dict) -> list[str]:
    """Decisions with no source episode.

    Per §State vs history a Decision is EXTRACTED FROM an episode and stays
    linked to it via MENTIONS. A Decision that no episode mentions is a loader
    artefact rather than a record — it asserts that a trade-off was resolved
    while providing nothing that resolved it. Applies to every arc.
    """
    declared = {d.get("id") for d in (doc.get("decisions") or []) if isinstance(d, dict)}
    if not declared:
        return []
    mentioned = {
        m
        for e in (doc.get("episodes") or [])
        for m in (e.get("mentions") or [])
    }
    return sorted(declared - mentioned)


def check_file(path: pathlib.Path) -> list[str]:
    problems: list[str] = []
    raw = path.read_text(encoding="utf-8")

    try:
        doc = yaml.safe_load(strip_comments(raw))
    except yaml.YAMLError as exc:
        return [f"{path.name}: YAML does not parse: {exc}"]

    if not isinstance(doc, dict):
        return [f"{path.name}: expected a mapping at the top level"]

    # 1. vocabulary, over the RENDERED view only. Declared non-rendered blocks
    #    are exempt — see DEFAULT_NON_RENDERED.
    rendered = _rendered_view(doc)
    flat = yaml.safe_dump(rendered, default_flow_style=False).lower()
    for token in FORBIDDEN_TOKENS:
        if token in flat:
            problems.append(
                f"{path.name}: forbidden token {token!r} appears in RENDERED seed "
                f"data — that is an oracle fact, not a primitive"
            )

    # 1b. a block that looks like generator input must be DECLARED, or the
    #     renderer has no instruction to strip it and it leaks by default.
    declared = _non_rendered_keys(doc)
    for key in doc:
        if key in ("meta",) or key in declared:
            continue
        if key.startswith("generator") or key.endswith("_input"):
            problems.append(
                f"{path.name}: {key!r} looks like generator input but is not "
                f"listed in meta.non_rendered — the renderer would emit it "
                f"verbatim and leak whatever it contains"
            )

    # 2. universal: no orphan Decision nodes
    for orphan in _orphan_decisions(doc):
        problems.append(
            f"{path.name}: Decision {orphan!r} has no source episode — a "
            f"Decision is extracted FROM an episode and stays linked via "
            f"MENTIONS; an orphan asserts a resolved trade-off with nothing "
            f"that resolved it"
        )

    # 3. structural absences for this arc
    arc = (doc.get("meta") or {}).get("arc")
    for description, predicate in STRUCTURAL_CHECKS.get(arc, []):
        try:
            ok = predicate(doc)
        except Exception as exc:  # noqa: BLE001 - a broken check is a failure
            problems.append(f"{path.name}: check {description!r} raised {exc}")
            continue
        if not ok:
            problems.append(f"{path.name}: VIOLATED — {description}")

    return problems


def main(argv: list[str]) -> int:
    paths = [pathlib.Path(a) for a in argv[1:]] or sorted(SEED_DIR.glob("*.yaml"))
    if not paths:
        print(f"check_849_seed: no seed files found under {SEED_DIR}")
        return 0

    all_problems: list[str] = []
    for path in paths:
        all_problems.extend(check_file(path))

    if all_problems:
        print("check_849_seed: FAILED")
        for problem in all_problems:
            print(f"  {problem}")
        return 1

    names = ", ".join(p.name for p in paths)
    print(f"check_849_seed: OK ({len(paths)} file(s): {names})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
