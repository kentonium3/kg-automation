#!/usr/bin/env python3
"""The loader-side structural pass (owed since the freeze gate was written).

`check_849_freeze` says plainly what it cannot see:

    "a loader-side edge exists in neither seed nor stream and escaped every
     earlier check"

Everything before this checks the SEED or the RENDERED FILES. This checks the
graph the loader actually emits, at every ask_time a question is asked at,
which is the only view an arm ever has. Three things live only here:

* **Entity properties.** The renderer's default-deny allowlist covers the event
  stream. The entity path has none — `Corpus.entity()` is `{"kind": kind,
  **data}` — so a field added to a seed reaches every arm untouched.
* **The graph after replay.** A structural absence an arc depends on ("nothing
  points at COM_DESIGN_REVIEW") can hold in the rendered file and be false in
  the loaded graph, or vice versa, because replay removes nodes and edges.
* **Dangling edges.** An edge whose endpoint was withheld is worse than the
  leak it was meant to prevent: it names the hidden node and states its
  disposition while pointing at an id the arm cannot resolve.

Usage:
    python3 -m scripts.research.check_849_loader
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.check_849_seed import FORBIDDEN_TOKENS  # noqa: E402
from scripts.research.render_849_corpus import ENTITY_FIELDS  # noqa: E402
from scripts.research.load_849_corpus import (  # noqa: E402
    DEFAULT_CORPUS, UnfrozenCorpus, replay, verify_registration,
)

#: Every question's ask_time, in protocol order (rubric §2).
ASK_TIMES = [
    ("C1", "2026-04-28T09:06:00-04:00"),
    ("A",  "2026-06-09T09:15:00-04:00"),
    ("F1", "2026-08-10T09:00:00-04:00"),
    ("B1", "2026-08-17T09:00:00-04:00"),
    ("E2", "2026-09-04T17:00:00-04:00"),
    ("E1", "2026-09-21T09:00:00-04:00"),
    ("F2", "2026-09-25T09:00:00-04:00"),
    ("B2", "2026-10-16T09:00:00-04:00"),
]

#: The closed set of edge types. An unregistered type fails rather than loading,
#: because an arm querying a typed graph can only pull what the ontology names.
EDGE_TYPES = frozenset({
    "ADVANCES", "COMMITTED_TO", "CONTAINS", "DECIDED", "DELIVERS",
    "DUE_BY", "EMBODIES", "GATED_ON",
})


def check_entity_properties(corpus_dir: pathlib.Path) -> list[str]:
    """Default-deny over entity properties. The gap `arcs` walked through."""
    entities = json.loads((corpus_dir / "entities.json").read_text(encoding="utf-8"))
    problems = []
    for entity in entities:
        kind = entity.get("kind")
        allowed = ENTITY_FIELDS.get(kind)
        if allowed is None:
            problems.append(f"FAIL: unregistered entity kind {kind!r}")
            continue
        for key in entity:
            if key in ("id", "kind") or key in allowed:
                continue
            problems.append(
                f"FAIL: {entity.get('id', kind)} carries unregistered property "
                f"{key!r} = {entity[key]!r} — every arm sees it. Either register "
                f"it in ENTITY_FIELDS or strip it in the renderer.")
    return problems


def check_edge_types(corpus_dir: pathlib.Path) -> list[str]:
    entities = json.loads((corpus_dir / "entities.json").read_text(encoding="utf-8"))
    seen = {e["type"] for e in entities if e.get("kind") == "Edge"}
    return [f"FAIL: unregistered edge type {t!r}" for t in sorted(seen - EDGE_TYPES)]


def check_loader_links_exist(corpus_dir: pathlib.Path) -> list[str]:
    """Arm G's specified retrieval needs these; the corpus must carry them.

    Rubric §2 gives arm G "anchored history expansion (entity → its episodes
    via MENTIONS)" and seeds it "by structured writes (no LLM)". The loader is
    therefore not permitted to recover the links by extraction: if they are not
    in the corpus, arm G string-matches like the flat arms and the comparison
    the run exists to make measures nothing.
    """
    path = corpus_dir / "loader_links.jsonl"
    if not path.exists():
        return [
            "FAIL: loader_links.jsonl is absent. The renderer COLLECTS 22 links "
            "(Corpus.loader_links) and main() writes only stream.jsonl, "
            "entities.json and manifest.json — the graph wiring is built and "
            "dropped. Arm G's MENTIONS expansion has no data."
        ]
    links = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [] if links else ["FAIL: loader_links.jsonl is empty"]


def check_no_forbidden_vocabulary(loaded) -> list[str]:
    """Over the LOADED graph, not the rendered file."""
    blob = json.dumps(
        {"entities": loaded.entities, "edges": loaded.edges}, default=str).lower()
    return [f"FAIL: forbidden token {t!r} in the loaded graph"
            for t in FORBIDDEN_TOKENS if t in blob]


def check_no_dangling_edges(loaded) -> list[str]:
    ids = {e["id"] for e in loaded.entities if "id" in e}
    return [
        f"FAIL: dangling edge {e['from']}-{e['type']}->{e['to']} — an endpoint "
        f"is not in the loaded graph, which names the withheld node and states "
        f"its disposition while pointing at an unresolvable id"
        for e in loaded.edges if e["from"] not in ids or e["to"] not in ids
    ]


def check_no_future_material(loaded, ask_time: datetime) -> list[str]:
    """Nothing loaded may postdate the question."""
    from scripts.research.load_849_corpus import _cmp_key
    problems = []
    for entity in loaded.entities:
        if entity.get("kind") == "Decision":
            when = _cmp_key(entity.get("decided_at"), ask_time)
            if when and when > ask_time:
                problems.append(
                    f"FAIL: {entity['id']} decided {entity['decided_at']} is "
                    f"loaded at ask_time {ask_time.isoformat()}")
    for event in loaded.events:
        when = _cmp_key(event.get("at"), ask_time)
        if when and when > ask_time:
            problems.append(f"FAIL: event {event['ref']} at {event['at']} postdates ask_time")
    return problems


def check_structural_absences(loaded, label: str) -> list[str]:
    """The absences specific arcs turn on, asserted AFTER load."""
    problems = []
    ids = {e["id"] for e in loaded.entities if "id" in e}

    if "COM_DESIGN_REVIEW" in ids:
        inbound = [e for e in loaded.edges if e["to"] == "COM_DESIGN_REVIEW"]
        if inbound:
            problems.append(
                f"FAIL[{label}]: something points AT COM_DESIGN_REVIEW "
                f"({inbound}) — Arc C turns on nothing having scheduled it")

    for entity in loaded.entities:
        if entity.get("id") == "OUT_LAUNCH":
            for key in ("status", "completed", "completed_at", "shipped_at"):
                if key in entity:
                    problems.append(
                        f"FAIL[{label}]: OUT_LAUNCH carries {key!r} — Arc C "
                        f"requires the launch to carry no completion")

    # Arc F: standing practices carry EMBODIES and no Outcome (rubric line 192).
    for task in ("TASK_MEDITATION", "TASK_PERSONAL_INVESTMENT"):
        if task not in ids:
            continue
        if not [e for e in loaded.edges if e["from"] == task and e["type"] == "EMBODIES"]:
            problems.append(f"FAIL[{label}]: {task} has no EMBODIES edge")
        bad = [e for e in loaded.edges
               if task in (e["from"], e["to"])
               and any(o.get("id") in (e["from"], e["to"]) and o.get("kind") == "Outcome"
                       for o in loaded.entities)]
        if bad:
            problems.append(f"FAIL[{label}]: {task} is wired to an Outcome ({bad})")
    return problems


def main(argv: list[str]) -> int:
    corpus_dir = DEFAULT_CORPUS
    failures: list[str] = []

    try:
        verify_registration(corpus_dir)
        print(f"fingerprint gate: OK")
    except UnfrozenCorpus as exc:
        print(f"fingerprint gate: REFUSED\n{exc}")
        return 1

    print("\ncorpus-wide:")
    for problem in (check_entity_properties(corpus_dir)
                    + check_edge_types(corpus_dir)
                    + check_loader_links_exist(corpus_dir)):
        failures.append(problem)
        print(f"  {problem}")
    if not failures:
        print("  OK")

    print("\nper ask_time:")
    for label, stamp in ASK_TIMES:
        ask_time = datetime.fromisoformat(stamp)
        loaded = replay(corpus_dir, ask_time, verify=False)
        found = (check_no_forbidden_vocabulary(loaded)
                 + check_no_dangling_edges(loaded)
                 + check_no_future_material(loaded, ask_time)
                 + check_structural_absences(loaded, label))
        status = "OK" if not found else f"{len(found)} FAILURE(S)"
        print(f"  {label:3} {stamp}  events={len(loaded.events):5} "
              f"nodes={len(loaded.entities):3} edges={len(loaded.edges):3} "
              f"links={len(loaded.links):3}  {status}")
        for problem in found:
            failures.append(problem)
            print(f"      {problem}")

    if failures:
        print(f"\ncheck_849_loader: {len(failures)} FAILURE(S) — the loaded graph is "
              f"not fit for a run")
        return 1
    print("\ncheck_849_loader: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
