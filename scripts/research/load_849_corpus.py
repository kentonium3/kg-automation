#!/usr/bin/env python3
"""Loader for the #849 frozen corpus — the substrate every arm is built from.

Three jobs, in this order, because the order is the point:

1. **Refuse an unfrozen corpus.** The fingerprint gate is the first thing this
   module does, not a later addition. A harness that will silently run on a
   corpus nobody registered produces numbers that look exactly like numbers
   from the corpus that was registered.

2. **Replay to `ask_time`** (rubric §2, "state as of, not filtered"). The
   difference is not stylistic. Filtering a final-state graph leaves every
   current-state attribute in place, so an arm asked a question in June reads
   an entity carrying what became true in September.

3. **Emit an arm-neutral view** the three arms specialise. Anything an arm may
   see is here; anything it must earn is not.

The replay rules below each exist because the corpus proved they were needed —
see `check_849_loader.py`, which asserts them against the real artifact.

Usage:
    python3 -m scripts.research.load_849_corpus --ask-time 2026-06-09T09:15:00-04:00
    python3 -m scripts.research.load_849_corpus --visibility     # the derived table
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO_ROOT / "build" / "849-corpus"

#: The registration (rubric §9). A run is valid only against THIS corpus.
#: Post-registration changes are dated amendments, so amending means editing
#: this block and the rubric together — never one of them.
REGISTRATION = {
    "commit": "b203907e",
    "registered": "2026-09-24T17:03Z",
    "files": {
        "stream.jsonl":
            "188b9bf1402645c5a015da01bd3241376a1914e25aacad8a529a84b10a290d4a",
        "entities.json":
            "c1962d4d7ceb623ccd909ffe82b62838494c5e193e441dd6568339ac863c27c5",
    },
}

#: Entity kinds that are DEFINITIONAL: they describe standing structure rather
#: than something that happened, so they carry no creation time and are visible
#: at every ask_time. A Decision is deliberately NOT here.
DEFINITIONAL_KINDS = frozenset({
    "Purpose", "Domain", "Capacity", "Outcome", "Objective", "Project",
    "Task", "Principle", "Commitment", "Person", "Interest",
})


class UnfrozenCorpus(RuntimeError):
    """Raised when the corpus on disk is not the registered one."""


# --------------------------------------------------------------------------
# 1. The fingerprint gate
# --------------------------------------------------------------------------


def fingerprint(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_registration(corpus_dir: pathlib.Path) -> dict[str, str]:
    """Refuse anything but the registered corpus, printing the mismatch.

    Returns the observed fingerprints so a caller can record them; raises
    UnfrozenCorpus otherwise. A missing file is a mismatch, not a separate
    kind of problem — a corpus with a file missing is not the frozen one.
    """
    observed, problems = {}, []
    for name, expected in REGISTRATION["files"].items():
        path = corpus_dir / name
        if not path.exists():
            problems.append(f"  {name}: MISSING (expected sha256 {expected})")
            continue
        got = fingerprint(path)
        observed[name] = got
        if got != expected:
            problems.append(f"  {name}:\n    expected {expected}\n    observed {got}")

    manifest_path = corpus_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("valid_for_run"):
            problems.append(
                f"  manifest.json: valid_for_run is false (scale="
                f"{manifest.get('scale')}) — a scaled corpus is for a fast loop, "
                f"never for a run")

    if problems:
        raise UnfrozenCorpus(
            f"corpus at {corpus_dir} is not the registered corpus "
            f"({REGISTRATION['commit']}, registered {REGISTRATION['registered']}):\n"
            + "\n".join(problems)
            + "\n\nIf the corpus was deliberately changed, the freeze needs a dated "
              "amendment in the rubric AND a new REGISTRATION here. Do not edit one "
              "of them alone."
        )
    return observed


# --------------------------------------------------------------------------
# 2. Replay
# --------------------------------------------------------------------------


def _ts(value) -> datetime | None:
    """Parse a corpus timestamp. Dates and datetimes both appear."""
    if value in (None, ""):
        return None
    return _parse(str(value))


@lru_cache(maxsize=None)
def _parse(text: str) -> datetime | None:
    """Memoised because replay parses every event's `at` and the harness
    replays 72 times: 5,750 events × 72 is ~414k parses of a few thousand
    distinct strings. Datetimes are immutable, so sharing them is safe."""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    return parsed


def _cmp_key(value, reference: datetime) -> datetime | None:
    """Compare naive and aware timestamps without crashing.

    The corpus mixes both — bare dates on old email, offset-aware datetimes on
    everything the arcs care about. Normalising to the reference's awareness is
    correct here because every timestamp is in one wall-clock frame.
    """
    parsed = _ts(value)
    if parsed is None:
        return None
    if (parsed.tzinfo is None) != (reference.tzinfo is None):
        parsed = (parsed.replace(tzinfo=reference.tzinfo)
                  if parsed.tzinfo is None else parsed.replace(tzinfo=None))
    return parsed


def _stat_key(corpus_dir: pathlib.Path) -> tuple:
    """Identify the corpus files by (size, mtime_ns) so the cache cannot serve
    stale content if a corpus is re-rendered inside one process."""
    key = []
    for name in ("stream.jsonl", "entities.json", "loader_links.jsonl"):
        path = corpus_dir / name
        st = path.stat() if path.exists() else None
        key.append((name, st.st_size, st.st_mtime_ns) if st else (name, None, None))
    return (str(corpus_dir), tuple(key))


@lru_cache(maxsize=4)
def _read_corpus_cached(_key: tuple, corpus_dir_str: str):
    corpus_dir = pathlib.Path(corpus_dir_str)
    rows = [json.loads(line) for line
            in (corpus_dir / "stream.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    entities = json.loads((corpus_dir / "entities.json").read_text(encoding="utf-8"))
    links_path = corpus_dir / "loader_links.jsonl"
    links = [json.loads(line) for line
             in links_path.read_text(encoding="utf-8").splitlines()
             if line.strip()] if links_path.exists() else []
    return rows, entities, links


def read_corpus(corpus_dir: pathlib.Path):
    """Parse the corpus once per process.

    The harness replays 72 times over an 828 KB stream; re-parsing it each time
    is the harness's dominant cost and buys nothing. Keyed on size+mtime so a
    re-render inside one process is picked up rather than served stale.

    Returns the cached lists — `replay` must not mutate them, and does not: it
    builds new lists by filtering.
    """
    return _read_corpus_cached(_stat_key(corpus_dir), str(corpus_dir))


@dataclass
class Loaded:
    """What an arm may see at one ask_time."""
    ask_time: datetime
    events: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    withheld: dict[str, list[str]] = field(default_factory=dict)

    @property
    def by_id(self) -> dict[str, dict]:
        return {e["id"]: e for e in self.entities if "id" in e}


def entity_visible_from(entity: dict, edges: list[dict]) -> datetime | None:
    """The time an entity starts existing, or None if it is definitional.

    A Decision exists when it was decided. Everything else in
    DEFINITIONAL_KINDS is standing structure that predates the corpus window.

    The one subtlety is a Commitment whose FIRST reference is dated —
    `COM_DESIGN_REVIEW` is spoken into existence by an edge made at
    2026-04-14. Treating it as visible earlier would show an arm a commitment
    that had not been made yet.

    That derivation is scoped to Commitment ON PURPOSE. A first version applied
    it to every definitional kind and made `PER_FRED` invisible until the
    commitment naming him was made — but a person is not created by someone
    scheduling a meeting with them, and no other kind here is either. A
    Commitment is the one kind whose existence IS an act with a date.
    """
    if entity.get("kind") == "Decision":
        return _ts(entity.get("decided_at"))
    if entity.get("kind") != "Commitment":
        return None
    dated = [_ts(e.get("made_at")) for e in edges
             if e.get("made_at") and entity.get("id") in (e.get("from"), e.get("to"))]
    undated = [e for e in edges
               if not e.get("made_at") and entity.get("id") in (e.get("from"), e.get("to"))]
    # Only constrain when EVERY reference is dated. One undated edge means the
    # commitment is standing structure that also acquired a dated link.
    if dated and not undated:
        return min(d for d in dated if d)
    return None


def edge_effective_time(edge: dict, entities: list[dict]) -> datetime | None:
    """When an edge starts existing.

    `made_at` when present. Otherwise, for a `DECIDED` edge, the `decided_at`
    of the Decision it leaves — because the edges out of a Decision carry no
    timestamp of their own, and without this they survive a filter that
    removed their own source node. That leaves a dangling edge whose `to` and
    `disposition` state the finding while pointing at an id the arm cannot
    resolve: the filter leaks in both directions at once.
    """
    if edge.get("made_at"):
        return _ts(edge["made_at"])
    source = next((e for e in entities if e.get("id") == edge.get("from")), None)
    if source is not None and source.get("kind") == "Decision":
        return _ts(source.get("decided_at"))
    return None


def replay(corpus_dir: pathlib.Path, ask_time: datetime,
           verify: bool = True) -> Loaded:
    """Build the view an arm may see at `ask_time`.

    Replays primitives forward rather than filtering a final state, per rubric
    §2. Records what it withheld, because a filter that silently removes
    nothing is indistinguishable from one that is not running.
    """
    if verify:
        verify_registration(corpus_dir)

    rows, all_entities, all_links = read_corpus(corpus_dir)

    nodes = [e for e in all_entities if e.get("kind") != "Edge"]
    edges = [e for e in all_entities if e.get("kind") == "Edge"]

    loaded = Loaded(ask_time=ask_time)

    loaded.events = [r for r in rows
                     if (t := _cmp_key(r.get("at"), ask_time)) is not None
                     and t <= ask_time]
    # By ref, not by `r not in loaded.events` — that was a linear scan over a
    # list of dicts for every row, so a single replay did ~25M dict comparisons
    # and took 290ms. The harness replays 72 times.
    kept = {r["ref"] for r in loaded.events}
    loaded.withheld["events"] = [r["ref"] for r in rows if r["ref"] not in kept]

    visible_ids = set()
    for node in nodes:
        start = entity_visible_from(node, edges)
        if start is None or _cmp_key(start, ask_time) <= ask_time:
            loaded.entities.append(node)
            visible_ids.add(node.get("id"))
        else:
            loaded.withheld.setdefault("entities", []).append(node.get("id"))

    for edge in edges:
        start = edge_effective_time(edge, nodes)
        in_time = start is None or _cmp_key(start, ask_time) <= ask_time
        connected = edge.get("from") in visible_ids and edge.get("to") in visible_ids
        if in_time and connected:
            loaded.edges.append(edge)
        else:
            loaded.withheld.setdefault("edges", []).append(
                f"{edge.get('from')}-{edge.get('type')}->{edge.get('to')}")

    kept_refs = {r["ref"] for r in loaded.events}
    loaded.links = [l for l in all_links if l.get("ref") in kept_refs]
    return loaded


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=pathlib.Path, default=DEFAULT_CORPUS)
    ap.add_argument("--ask-time")
    ap.add_argument("--visibility", action="store_true",
                    help="print the derived visibility table and exit")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the fingerprint gate (development only)")
    args = ap.parse_args(argv[1:])

    try:
        if not args.no_verify:
            verify_registration(args.corpus)
            print(f"fingerprint gate: OK — corpus is {REGISTRATION['commit']}")
    except UnfrozenCorpus as exc:
        print(f"fingerprint gate: REFUSED\n{exc}")
        return 1

    entities = json.loads((args.corpus / "entities.json").read_text(encoding="utf-8"))
    nodes = [e for e in entities if e.get("kind") != "Edge"]
    edges = [e for e in entities if e.get("kind") == "Edge"]

    if args.visibility:
        print("\nderived visibility (blank = definitional, visible at every ask_time):")
        for node in sorted(nodes, key=lambda n: (n.get("kind", ""), n.get("id", ""))):
            start = entity_visible_from(node, edges)
            if start:
                print(f"  {node['kind']:11} {node['id']:28} from {start.isoformat()}")
        for edge in edges:
            start = edge_effective_time(edge, nodes)
            if start:
                print(f"  {'Edge':11} {edge['from']}-{edge['type']}->{edge['to']} "
                      f"from {start.isoformat()}")
        return 0

    if not args.ask_time:
        ap.error("--ask-time is required unless --visibility is given")

    loaded = replay(args.corpus, datetime.fromisoformat(args.ask_time),
                    verify=not args.no_verify)
    print(f"\nreplayed to {args.ask_time}")
    print(f"  events   {len(loaded.events):5} of {len(loaded.events) + len(loaded.withheld.get('events', []))}")
    print(f"  entities {len(loaded.entities):5} of {len(nodes)}")
    print(f"  edges    {len(loaded.edges):5} of {len(edges)}")
    print(f"  links    {len(loaded.links):5}")
    for kind in ("entities", "edges"):
        if loaded.withheld.get(kind):
            print(f"  withheld {kind}: {', '.join(loaded.withheld[kind])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
