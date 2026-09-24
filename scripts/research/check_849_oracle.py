#!/usr/bin/env python3
"""Contract checker for #849 hidden-oracle artifacts (rubric §3.1).

The oracle is the answer key. Two things can go wrong with it, and neither
fails loudly on its own:

1. **An oracle point with no traceability.** That is the #844 Threats §1
   defect — a point the arm is scored on with no primitive in the corpus that
   makes it inferable. Three have been found by hand during this synthesis
   (Arc A's "paid, hard to reschedule"; Arc B's halfway-point rule; Arc F's
   email-first mornings), which is the argument for checking it mechanically
   rather than by review. The rubric is explicit: the freeze check FAILS on an
   oracle point whose `traceability` is empty.

2. **An oracle file reaching an arm.** Every one of these contains the answers
   verbatim. The harness must assert `oracle/` is absent from every arm's input
   path before a run; this checker asserts the files are at least shaped so
   that assertion is possible — they declare themselves.

Usage:
    python3 -m scripts.research.check_849_oracle [PATH ...]

Exit 0 = conforms, 1 = does not.
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SYNTH = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis"
ORACLE_DIR = SYNTH / "oracle"
SEED_DIR = SYNTH / "seed"

#: Files in oracle/ that are appendices rather than per-question artifacts.
#: They carry supporting classification and are exempt from the question
#: contract, but not from living outside the seed directory.
APPENDIX_SUFFIX = "-appendix.yaml"

REQUIRED_POINT_KEYS = {"id", "statement", "required_values", "traceability"}
REQUIRED_TOP_KEYS = {"question", "ask_time", "question_text", "must_identify"}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def strip_comments(raw: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", raw)


def _seed_ids() -> set[str]:
    """Every id declared anywhere in the seed files.

    Used to catch a traceability entry that names something which does not
    exist — a typo there is indistinguishable from a real reference by eye,
    and it silently turns a checked point into an unchecked one.
    """
    ids: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), str):
                ids.add(node["id"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in SEED_DIR.glob("*.yaml"):
        try:
            doc = yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue
        walk(doc)
        # Rendered-event ids the arc's generator is contracted to emit. The
        # rubric allows traceability to name "seed ids OR rendered-event ids";
        # declaring them in the seed makes the second kind checkable before the
        # renderer exists, and binds the renderer to produce them.
        if isinstance(doc, dict):
            ids.update((doc.get("meta") or {}).get("emits") or [])
    return ids


def check_file(path: pathlib.Path, known_ids: set[str] | None = None) -> list[str]:
    problems: list[str] = []
    name = path.name

    if path.resolve().parent == SEED_DIR.resolve():
        return [f"{name}: an oracle artifact must not live in the seed directory"]

    try:
        doc = yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        return [f"{name}: YAML does not parse: {exc}"]

    if not isinstance(doc, dict):
        return [f"{name}: expected a mapping at the top level"]

    if name.endswith(APPENDIX_SUFFIX):
        return problems  # appendices carry no question contract

    missing = REQUIRED_TOP_KEYS - set(doc)
    if missing:
        problems.append(f"{name}: missing required key(s): {sorted(missing)}")
        return problems

    if not _ISO_DATE.match(str(doc["ask_time"])):
        problems.append(
            f"{name}: ask_time must be an ISO instant — it is the time cut, and "
            f"an ambiguous one silently changes what every arm can see"
        )

    points = doc.get("must_identify") or []
    if not points:
        problems.append(f"{name}: must_identify is empty — nothing would be scored")

    seen_ids: set[str] = set()
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            problems.append(f"{name}: must_identify[{index}] is not a mapping")
            continue

        pid = point.get("id", f"<index {index}>")
        absent = REQUIRED_POINT_KEYS - set(point)
        if absent:
            problems.append(f"{name}: point {pid} missing key(s): {sorted(absent)}")
            continue

        if pid in seen_ids:
            problems.append(f"{name}: duplicate oracle point id {pid!r}")
        seen_ids.add(pid)

        # THE RULE THIS FILE EXISTS FOR.
        if not point["traceability"]:
            problems.append(
                f"{name}: point {pid} has EMPTY traceability — it would score an "
                f"arm on something no primitive makes inferable (#844 Threats §1). "
                f"The fix belongs in the SEED, never here."
            )
            continue

        if known_ids is not None:
            unknown = [t for t in point["traceability"] if t not in known_ids]
            if unknown:
                problems.append(
                    f"{name}: point {pid} traceability names id(s) not found in any "
                    f"seed: {unknown} — a typo here silently turns a checked point "
                    f"into an unchecked one"
                )

    return problems


def main(argv: list[str]) -> int:
    paths = [pathlib.Path(a) for a in argv[1:]] or sorted(ORACLE_DIR.glob("*.yaml"))
    if not paths:
        print(f"check_849_oracle: no oracle files under {ORACLE_DIR}")
        return 0

    known = _seed_ids()
    problems: list[str] = []
    for path in paths:
        problems.extend(check_file(path, known))

    if problems:
        print("check_849_oracle: FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1

    names = ", ".join(p.name for p in paths)
    print(f"check_849_oracle: OK ({len(paths)} file(s): {names})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
