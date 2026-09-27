"""Arm G (WP05 T022–T025): static rules, deterministic resolution, D-15 assembly, live graph.

The forbidden words are assembled from parts here, as in the isolation test.
"""

from __future__ import annotations

import ast
import asyncio
import os
import pathlib
import re
import sys
import urllib.request
from datetime import datetime

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# The research stack (graphiti_core, fastembed) lives in the runner image and the local venv, not in
# requirements.txt; CI has no graphiti_core, so skip this module there rather than fail collection
# (same shape as the corpus/cache skips). The real runs happen on office4.
pytest.importorskip("graphiti_core", reason="research stack (graphiti_core) not installed — e.g. CI")

from scripts.research.arms849 import arm_g as A
from scripts.research.arms849 import questions as Q
from scripts.research.arms849.text import FrozenCorpusText
from scripts.research.load_849_corpus import (
    DEFAULT_CORPUS,
    Loaded,
    replay,
)

PKG = REPO_ROOT / "scripts" / "research" / "arms849"
CORPUS = pathlib.Path(os.environ.get("ARMS849_CORPUS", str(DEFAULT_CORPUS)))
CACHE = pathlib.Path(os.environ.get("ARMS849_CACHE", str(REPO_ROOT / "build" / "849-cache")))
needs_corpus = pytest.mark.skipif(not (CORPUS / "stream.jsonl").exists(), reason="rendered corpus absent")
live = pytest.mark.skipif(os.environ.get("ARMS849_LIVE") != "1", reason="live graph tests need ARMS849_LIVE=1 and the WP02 stack")
_REAL_URLOPEN = urllib.request.urlopen   # captured before the conftest guard patches it


@pytest.fixture
def live_http(monkeypatch):
    """Live tests deliberately probe the local stack; lift the repo-wide no-live-HTTP guard."""
    monkeypatch.setattr(urllib.request, "urlopen", _REAL_URLOPEN)
FORBIDDEN = ("or" + "acle", "se" + "ed/", "trace" + "ability")
SOURCE = (PKG / "arm_g.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# static rules
# ---------------------------------------------------------------------------


def _calls(source: str):
    return [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)]


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def test_add_episode_is_never_called():
    """Graphiti's extraction entry point is never named as a call or attribute (typed saves only)."""
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Attribute):
            assert node.attr != "add_" + "episode"
        if isinstance(node, ast.Call):
            assert _call_name(node) != "add_" + "episode"
    assert "add_" + "episode" not in SOURCE                # not even in prose


def test_no_query_time_validity_filtering():
    """The graph is REPLAYED to ask_time; a search never filters by validity (Q3). Setting
    valid_at on a WRITE (EntityEdge(...)) is the bi-temporal field being honest, not a filter."""
    for node in _calls(SOURCE):
        if _call_name(node) in ("SearchFilters", "search_", "search"):
            for kw in node.keywords:
                assert kw.arg not in ("valid_at", "invalid_at", "expired_at", "created_at"), ast.dump(node)[:160]
    for m in re.finditer(r"SearchFilters\(([^)]*)\)", SOURCE):
        assert m.group(1).strip().startswith("node_labels="), m.group(0)


def test_no_bfs_in_any_search_config_and_group_ids_always_explicit():
    for cfg in (A.HYBRID_NODE_EDGE, A.TYPED_PULL):
        for sub in (cfg.node_config, cfg.edge_config, cfg.episode_config, cfg.community_config):
            if sub is not None:
                assert not any("breadth" in str(m) or "bfs" in str(m) for m in sub.search_methods), sub
    for node in _calls(SOURCE):
        if _call_name(node) in ("search_", "search"):
            kws = {kw.arg for kw in node.keywords}
            assert "group_ids" in kws and "bfs_origin_node_uuids" not in kws and "center_node_uuid" not in kws
            gid = next(kw.value for kw in node.keywords if kw.arg == "group_ids")
            assert isinstance(gid, ast.List) and len(gid.elts) == 1, ast.dump(gid)


def test_module_names_no_excluded_material():
    low = SOURCE.lower()
    assert all(w not in low for w in FORBIDDEN)


def test_group_id_regex_on_every_question_and_hyphen_refused():
    for q in Q.QUESTIONS:
        assert A.GROUP_RE.match(A.group_id_for(q.id))
    with pytest.raises(ValueError, match="hyphen"):
        A.group_id_for("A-1")
    with pytest.raises(ValueError):
        A.group_id_for("a")                       # lower case is not in the charset either


def test_link_targets_cover_both_loader_link_shapes():
    assert A.link_targets({"ref": "e1", "mentions": ["A", "B"]}) == ["A", "B"]
    assert A.link_targets({"ref": "e2", "commitment": "COM_X"}) == ["COM_X"]
    assert A.link_targets({"ref": "e3", "mentions": ["A"], "commitment": "COM_X"}) == ["A", "COM_X"]
    assert A.link_targets({"ref": "e4"}) == []


def test_hybrid_search_enables_only_nodes_and_edges():
    cfg = A.HYBRID_NODE_EDGE
    assert cfg.node_config is not None and cfg.edge_config is not None
    assert cfg.episode_config is None and cfg.community_config is None


def test_uuids_are_stable_across_rebuilds_and_distinct_across_groups():
    a1 = A.stable_uuid("arms_A", "node", "PER_MARCUS"); a2 = A.stable_uuid("arms_A", "node", "PER_MARCUS")
    assert a1 == a2 and len(a1) == 36
    assert A.stable_uuid("arms_B1", "node", "PER_MARCUS") != a1 and A.stable_uuid("arms_A", "episode", "PER_MARCUS") != a1


def test_description_ambiguity_is_keyed_by_the_matched_phrase():
    ents = [{"id": "COM_X", "kind": "Commitment", "description": "the design review for Fred"},
            {"id": "COM_Y", "kind": "Commitment", "description": "the design review for Priya"}]
    r = A.resolve_anchors("When is the design review?", _view(ents))
    assert set(r.anchors) == {"COM_X", "COM_Y"} and r.ambiguous == ("the design review",)


def test_typed_pull_is_a_complete_label_match_not_a_similarity_search():
    src = SOURCE[SOURCE.index("async def typed_pulls"):SOURCE.index("async def hybrid_search")]
    assert "MATCH (n:Entity" in src and "labels(n)" in src and "search_" not in src and "SearchFilters" not in src


def test_foreign_results_are_recorded_and_refused():
    """A retrieval result outside the group map is never a silent drop. WP02 sweep: the source-text check
    that stood here proved only that a line EXISTED; the behaviour is now proved by
    test_a_result_from_another_questions_graph_is_a_premise_violation_not_a_refusal and
    test_a_foreign_item_in_gs_own_graph_is_the_shared_arm_refusal, which drive a result through."""
    assert "foreign_items" in [f.name for f in __import__("dataclasses").fields(A.PlanRecord)]


def test_typed_labels_and_cap_are_the_ruled_values():
    assert A.TYPED_LABELS == ("Capacity", "Commitment", "Principle", "Interest") and A.CAP == 60


# ---------------------------------------------------------------------------
# resolution (no DB)
# ---------------------------------------------------------------------------


def _view(entities, events=(), edges=(), links=()) -> Loaded:
    return Loaded(ask_time=datetime.fromisoformat("2026-06-01T09:00:00-04:00"), events=list(events),
                  entities=list(entities), edges=list(edges), links=list(links))


PEOPLE = [
    {"id": "PER_MARCUS", "kind": "Person", "name": "Marcus Vale", "aliases": ["mvale@spec-kitty.example", "Marcus Vale", "@marcus"]},
    {"id": "PER_FRED", "kind": "Person", "name": "Fred Okafor", "aliases": ["fokafor@spec-kitty.example", "@fred"]},
    {"id": "PER_MARCUS2", "kind": "Person", "name": "Marcus Chen", "aliases": ["@mchen"]},
]
COMMITMENTS = [
    {"id": "COM_DESIGN_REVIEW", "kind": "Commitment", "description": "Design review for Fred once the launch is past"},
    {"id": "OUT_5K", "kind": "Outcome", "description": "Run the Riverside 5K under 30 minutes"},
]


def test_person_alias_and_handle_resolve():
    r = A.resolve_anchors("What did I promise Marcus Vale last week?", _view(PEOPLE))
    assert "PER_MARCUS" in r.anchors and r.paths["alias"] == ["PER_MARCUS"] and r.path == "anchored"
    r = A.resolve_anchors("did @fred ever get an answer?", _view(PEOPLE))
    assert r.anchors == ("PER_FRED",)


def test_ambiguous_first_name_keeps_every_candidate():
    r = A.resolve_anchors("Am I on track with Marcus?", _view(PEOPLE))
    assert set(r.anchors) == {"PER_MARCUS", "PER_MARCUS2"} and r.ambiguous


def test_commitment_and_outcome_descriptions_resolve_exact_and_by_fragment():
    r = A.resolve_anchors("Is the design review for Fred still owed?", _view(PEOPLE + COMMITMENTS))
    assert "COM_DESIGN_REVIEW" in r.paths["commitment_desc"] and "PER_FRED" in r.anchors
    r = A.resolve_anchors("Will I run the Riverside 5K on time?", _view(COMMITMENTS))
    assert r.paths["outcome_desc"] == ["OUT_5K"]
    r = A.resolve_anchors("Anything about the 5K?", _view(COMMITMENTS))     # < 3 common tokens
    assert r.paths["outcome_desc"] == []


def test_zero_anchors_is_search_only_and_deterministic():
    r1 = A.resolve_anchors("How am I spending my Sunday evenings?", _view(PEOPLE + COMMITMENTS))
    r2 = A.resolve_anchors("How am I spending my Sunday evenings?", _view(PEOPLE + COMMITMENTS))
    assert r1 == r2 and r1.anchors == () and r1.path == "search_only"


@needs_corpus
def test_every_registered_question_resolves_the_same_way_twice():
    view = replay(CORPUS, datetime.fromisoformat("2026-10-16T09:00:00-04:00"), verify=False)
    for q in Q.QUESTIONS:
        assert A.resolve_anchors(q.text, view) == A.resolve_anchors(q.text, view)


# ---------------------------------------------------------------------------
# assembly (D-15) with synthetic items over the real text
# ---------------------------------------------------------------------------


@needs_corpus
def test_assembly_priority_cap_dedup_and_frozen_layout():
    text = FrozenCorpusText(CORPUS)
    view = replay(CORPUS, datetime.fromisoformat("2026-05-01T09:00:00-04:00"), verify=False)
    refs = [str(e["ref"]) for e in view.events][:100]
    ents = [e["id"] for e in view.entities][:10]
    mk = lambda kind, key, score, origin, u=None: A.Item(kind, key, u or f"zz-{kind}:{key}", score, origin)
    pulls = [[mk("node", ents[0], 0.9, "pull:Capacity")], [mk("node", ents[1], 0.5, "pull:Commitment"), mk("node", ents[2], 0.7, "pull:Commitment")], [], []]
    hits = [mk("episode", r, 1.0 - i / 200, "search") for i, r in enumerate(refs[:70])] + [mk("node", ents[0], 0.99, "search")]  # duplicate uuid
    expansions = [[mk("episode", refs[85], 1.0, "expand:X"), mk("episode", refs[80], 1.0, "expand:X")]]  # caller order kept
    block, chosen = A.assemble(text, view, pulls, hits, expansions, cap=60)
    assert len(chosen) == 60 and len({c.uuid for c in chosen}) == 60
    assert [c.key for c in chosen[:3]] == [ents[0], ents[2], ents[1]]           # label order, then score desc
    assert not any(c.origin.startswith("expand") for c in chosen)             # the cap was reached before expansions
    # ties break by the STABLE KEY, never by uuid: re-label EVERY uuid (same mapping for all groups,
    # so de-dup still sees the duplicate) and the choice is unchanged
    rl = lambda it: A.Item(it.kind, it.key, "R" + it.uuid[::-1], it.score, it.origin)
    _, chosen2 = A.assemble(text, view, [[rl(i) for i in g] for g in pulls], [rl(i) for i in hits],
                            [[rl(i) for i in g] for g in expansions], cap=60)
    assert [c.key for c in chosen2] == [c.key for c in chosen]
    # expansions keep the caller's order when they do enter
    _, chosen3 = A.assemble(text, view, [[], [], [], []], [], expansions, cap=60)
    assert [c.key for c in chosen3] == [refs[85], refs[80]]
    # layout: events in view order then records; every line is a frozen line
    lines = block.data.split(b"\n")[:-1]
    n_events = sum(1 for c in chosen if c.kind == "episode")
    assert lines[:n_events] == [text.event_line(r) for r in block.event_refs]
    assert block.event_refs == tuple(r for r in refs if r in {c.key for c in chosen if c.kind == "episode"})
    assert lines[n_events:] == [text.record_line(k) for k in block.record_keys]
    # same inputs → same bytes
    block2, _ = A.assemble(text, view, pulls, hits, expansions, cap=60)
    assert block2.sha256 == block.sha256


# ---------------------------------------------------------------------------
# live: FalkorDB up (WP02 stack)
# ---------------------------------------------------------------------------


@live
@needs_corpus
def test_live_build_search_assemble_and_replay_rule(live_http, falkor_endpoint):
    """One event loop for the whole scenario: the FalkorDB async client binds to the loop it
    first runs on (an asyncio.run per step fails with "Event loop is closed").

    WP02 sweep (FR-016): every read-back below goes to the question's OWN database
    (``driver.clone(database=<group>)``), where G now writes; the hybrid step must PRODUCE hits,
    not merely appear in the plan."""
    from graphiti_core.driver.falkordb_driver import FalkorDriver

    from scripts.research.arms849.embed import Embedder

    host, port = falkor_endpoint
    driver = FalkorDriver(host=host, port=port)          # outside any loop: no index build on the root database
    selected = _record_databases(driver)

    async def scenario() -> None:
        arm = A.GraphArm(driver, Embedder(cache_dir=CACHE / "fastembed"), FrozenCorpusText(CORPUS))
        qa = next(q for q in Q.QUESTIONS if q.id == "A")
        view = replay(CORPUS, datetime.fromisoformat(qa.ask_time), verify=False)
        stats = await arm.build_graph(qa, view)
        assert stats.group_id == "arms_A" and stats.nodes == len(view.entities) and stats.episodes == len(view.events)
        ids = {e["id"] for e in view.entities}
        assert stats.links == sum(1 for l in view.links for m in A.link_targets(l) if m in ids) and stats.links > 0
        assert stats.llm_calls == 0
        b1, p1 = await arm.plan_and_assemble(qa, view)
        b2, _ = await arm.plan_and_assemble(qa, view)
        assert b1.sha256 == b2.sha256 == p1.assembled_context_sha256 and p1.items_assembled <= 60 and p1.llm_calls == 0
        # rebuild → identical uuids → identical selection and sha (resume safety, D-15)
        stats2 = await arm.build_graph(qa, view)
        assert stats2.nodes == stats.nodes
        b3, _ = await arm.plan_and_assemble(qa, view)
        assert b3.sha256 == b1.sha256
        assert p1.plan_steps[0]["step"] == "typed_pull:Capacity"
        assert next(s["count"] for s in p1.plan_steps if s["step"] == "hybrid_search") >= 1   # PRODUCED, not ran
        # the typed pull is COMPLETE: every node of that label in the view, whatever the question says
        by_label = {e["kind"]: 0 for e in view.entities}
        for e in view.entities:
            by_label[e["kind"]] += 1
        for step in p1.plan_steps:
            if step["step"].startswith("typed_pull:"):
                label = step["step"].split(":", 1)[1]
                assert step["count"] == by_label.get(label, 0), (label, step, by_label)
        assert p1.foreign_items == 0
        assert p1.items_assembled > 0 and all(k in ("node", "edge", "episode") for k in p1.items_by_kind)
        # every MENTIONS edge carries its episode's time (Codex c2): compare saved created_at per edge
        db_a = driver.clone(database="arms_A")
        rows, _, _ = await db_a.execute_query(
            "MATCH (e:Episodic {group_id: $g})-[m:MENTIONS]->(n:Entity) RETURN e.name AS ref, m.created_at AS c, e.valid_at AS v",
            g="arms_A")
        assert rows and all(str(r["c"]) == str(r["v"]) for r in rows), rows[:3]
        # the replay rule made visible: DEC_F_RESTART absent for F1, present for B2
        qf1 = next(q for q in Q.QUESTIONS if q.id == "F1"); qb2 = next(q for q in Q.QUESTIONS if q.id == "B2")
        for q, present in ((qf1, False), (qb2, True)):
            v = replay(CORPUS, datetime.fromisoformat(q.ask_time), verify=False)
            await arm.build_graph(q, v)
            db_q = driver.clone(database=A.group_id_for(q.id))
            rows, _, _ = await db_q.execute_query("MATCH (n:Entity {name: $n, group_id: $g}) RETURN count(n) AS c", n="DEC_F_RESTART", g=A.group_id_for(q.id))
            assert (rows[0]["c"] > 0) is present, (q.id, rows)
            await arm.drop_graph(q)
        await arm.drop_graph(qa)
        rows, _, _ = await db_a.execute_query("MATCH (n {group_id: $g}) RETURN count(n) AS c", g="arms_A")
        assert rows[0]["c"] == 0
        await driver.close()

    asyncio.run(scenario())
    # no query of the scenario (the test's own read-backs included) touched the root database
    assert set(selected) == {"arms_A", "arms_F1", "arms_B2"}, collections.Counter(selected)


# ---------------------------------------------------------------------------
# WP02 (arms-preconditions-01M3FVRY): refusals, per-question database routing, the loop bridge
#
# The graph store below is a TRANSPORT-level fake: ``FalkorDriver(falkor_db=FakeFalkorDB())`` runs
# graphiti's real driver, node/edge saves, index build, search and decorator code, and the fake
# records the DATABASE every query was sent to. That is what FR-016 is about: which database a
# query reaches, not whether a step ran.
# ---------------------------------------------------------------------------

import collections
import contextlib
import hashlib
import json
import threading
import time
from types import SimpleNamespace

from graphiti_core.driver.falkordb_driver import FalkorDriver

from scripts.research.arms849 import errors as ERR
from scripts.research.arms849 import serving as S
from scripts.research.arms849.text import Block


class FakeResult:
    """What ``falkordb.asyncio`` returns: ``header`` as (type, name) pairs and ``result_set`` rows."""

    def __init__(self, header=(), rows=()) -> None:
        self.header = [[1, h] for h in header]
        self.result_set = [list(r) for r in rows]


class FakeFalkorDB:
    """The FalkorDB async client, faked at the transport. ``hang(db, cypher, params)`` injects a hang:
    ``"cancellable"`` sleeps until cancelled; ``"stubborn"`` swallows every cancellation until the
    test sets ``release`` (a cleanup that never acknowledges). ``respond(db, cypher, params)`` may
    return a :class:`FakeResult`; otherwise every query answers empty."""

    WRITE = re.compile(r"\b(MERGE|CREATE)\b")

    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []
        self.hang = lambda db, cypher, params: None
        self.respond = lambda db, cypher, params: None
        self.observe = lambda db, cypher, params: None
        self.release = threading.Event()
        self.in_flight = 0
        self.max_in_flight = 0
        self.threads: set[str] = set()
        self.graphs: set[str] = set()
        self.closed = False

    def select_graph(self, name: str) -> FakeGraph:
        return FakeGraph(self, name)

    async def list_graphs(self) -> list[str]:
        self.queries.append(("<server>", "GRAPH.LIST"))
        return sorted(self.graphs)

    async def aclose(self) -> None:
        self.closed = True

    def dbs(self) -> set[str]:
        return {db for db, _ in self.queries if db != "<server>"}


class FakeGraph:
    def __init__(self, store: FakeFalkorDB, name: str) -> None:
        self.store, self.name = store, name

    async def query(self, cypher: str, params=None) -> FakeResult:
        store = self.store
        store.queries.append((self.name, cypher))
        store.threads.add(threading.current_thread().name)
        store.in_flight += 1
        store.max_in_flight = max(store.max_in_flight, store.in_flight)
        try:
            store.observe(self.name, cypher, params or {})
            mode = store.hang(self.name, cypher, params or {})
            if mode == "cancellable":
                await asyncio.sleep(3600)
            elif mode == "brief":
                await asyncio.sleep(0.05)
            elif mode == "stubborn":
                while not store.release.is_set():
                    try:
                        await asyncio.sleep(0.01)
                    except asyncio.CancelledError:
                        continue                                   # never acknowledges
            if FakeFalkorDB.WRITE.search(cypher):
                store.graphs.add(self.name)
            return store.respond(self.name, cypher, params or {}) or FakeResult()
        finally:
            store.in_flight -= 1


class FakeEmbedder:
    """Deterministic 384-d vectors from sha256; no cache, no model."""

    model = "fake-embedder"

    def embed(self, texts):
        return [[(b - 128) / 128 for b in (hashlib.sha256(t.encode("utf-8")).digest() * 12)[:384]] for t in texts]

    def embed_one(self, text):
        return self.embed([text])[0]


TINY_EVENTS = [
    {"ref": "ev1", "at": "2026-04-01T09:00:00-04:00", "channel": "email", "text": "Fred asked about the design review"},
    {"ref": "ev2", "at": "2026-04-02T09:00:00-04:00", "channel": "chat", "text": "Marcus moved the Friday 1:1"},
]
TINY_ENTITIES = [
    {"id": "PER_FRED", "kind": "Person", "name": "Fred Okafor", "aliases": ["@fred"]},
    {"id": "PER_MARCUS", "kind": "Person", "name": "Marcus Vale", "aliases": ["@marcus"]},
    {"id": "COM_REVIEW", "kind": "Commitment", "description": "design review for Fred"},
]
TINY_EDGES = [{"from": "PER_FRED", "to": "COM_REVIEW", "type": "OWED", "kind": "Edge"}]
QC1 = SimpleNamespace(id="C1", text="Fred just sent this. What is he referring to, and what do I owe him?")
QA = SimpleNamespace(id="A", text="Marcus just moved our Friday 1:1 to Thursday. Is that a problem?")


@pytest.fixture
def tiny(tmp_path):
    """A frozen corpus of two events and three entities, and its replayed view (links are G's input)."""
    (tmp_path / "stream.jsonl").write_text("".join(json.dumps(e) + "\n" for e in TINY_EVENTS), encoding="utf-8")
    (tmp_path / "entities.json").write_text(json.dumps(TINY_ENTITIES + TINY_EDGES), encoding="utf-8")
    text = FrozenCorpusText(tmp_path)
    view = Loaded(ask_time=datetime.fromisoformat("2026-04-28T09:06:00-04:00"), events=list(TINY_EVENTS),
                  entities=list(TINY_ENTITIES), edges=[dict(e) for e in TINY_EDGES],
                  links=[{"ref": "ev1", "mentions": ["PER_FRED"]}, {"ref": "ev2", "mentions": ["PER_MARCUS"]}])
    return text, view


@pytest.fixture
def store():
    s = FakeFalkorDB()
    yield s
    s.release.set()                                   # let an abandoned stubborn hang finish


@pytest.fixture
def clones(monkeypatch):
    """Every ``FalkorDriver.clone`` call, by database — the decorator's clones included."""
    seen: list[str] = []
    real = FalkorDriver.clone

    def counting(self, database):
        seen.append(database)
        return real(self, database)

    monkeypatch.setattr(FalkorDriver, "clone", counting)
    return seen


@pytest.fixture
def bridges():
    made: list = []
    yield made
    for b in made:
        b.close()


def make_bridge(store, text, bridges, embedder=None):
    b = A.make_bridge(embedder or FakeEmbedder(), text, driver=FalkorDriver(falkor_db=store))
    bridges.append(b)
    return b


def pending(bridge) -> list:
    """Tasks on the bridge's loop other than this probe: the quiescence measure."""
    async def probe():
        me = asyncio.current_task()
        return [t for t in asyncio.all_tasks() if t is not me and not t.done()]
    return asyncio.run_coroutine_threadsafe(probe(), bridge._loop).result(5)


# -- FR-016: one per-question database for every G operation -------------------------------------


def test_every_g_operation_reads_and_writes_one_per_question_database(tiny, store, clones):
    """FR-016 (research D-2b). The defect: writes went to ``default_db`` through the root driver while
    ``Graphiti.search_``'s ``@handle_multiple_group_ids`` cloned to ``arms_<Q>``, so hybrid search read
    an EMPTY graph. Here every query of every operation — index build, node/edge/episode writes, typed
    pulls, hybrid search, anchored expansion, drop — is recorded with its database, over the async
    GraphArm API that existed before the fix. Each question gets exactly ONE clone."""
    text, view = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)

    async def scenario():
        for q in (QC1, QA):
            await arm.build_graph(q, view)
            for _ in range(3):                                            # three repeats
                await arm.plan_and_assemble(q, view)
        await arm.drop_graph(QC1)
    asyncio.run(scenario())

    by_db = collections.defaultdict(list)
    for db, cypher in store.queries:
        by_db[db].append(cypher)
    assert set(by_db) == {"arms_C1", "arms_A"}, {db: len(c) for db, c in by_db.items()}
    for db in ("arms_C1", "arms_A"):
        qs = by_db[db]
        writes = [c for c in qs if "MERGE" in c]
        searches = [c for c in qs if "db.idx.fulltext.query" in c]
        assert writes and searches, (db, len(writes), len(searches))     # hybrid search read where the writes went
        assert any("labels(n)" in c for c in qs)
        assert any("MENTIONS" in c and "MERGE" not in c for c in qs)             # the expansion READ, not the write
        assert any("CREATE INDEX" in c for c in qs)                       # the index build too
    assert any("DETACH DELETE" in c for c in by_db["arms_C1"])
    assert collections.Counter(clones) == {"arms_C1": 1, "arms_A": 1}


def test_indices_are_built_once_per_database_not_once_per_arm(tiny, store):
    """`_indices_built` was one global flag: the first question's index build on one database stood in
    for every other database. Now each per-question database gets its own build, once."""
    text, view = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)

    async def scenario():
        await arm.build_graph(QC1, view)
        await arm.build_graph(QA, view)
        await arm.build_graph(QC1, view)                                   # idempotent rebuild
    asyncio.run(scenario())
    index_queries = collections.Counter(db for db, c in store.queries if c.lstrip().startswith("CREATE INDEX"))
    assert set(index_queries) == {"arms_C1", "arms_A"} and index_queries["arms_C1"] == index_queries["arms_A"] > 0
    # index-READY before first use: on each database every index query precedes its first other query
    for db in ("arms_C1", "arms_A"):
        kinds = [_is_index_query(c) for d, c in store.queries if d == db]
        first_use = kinds.index(False)
        assert all(kinds[:first_use]) and not any(kinds[first_use:]), (db, kinds[:first_use + 3])


def _is_index_query(cypher: str) -> bool:
    c = cypher.lstrip()
    return c.startswith(("CREATE INDEX", "CREATE FULLTEXT INDEX")) or "db.idx.fulltext.create" in c


# -- FR-002: G's refusals and premise violations ---------------------------------------------------


def _typed_pull_row(uuid: str, group: str):
    def respond(db, cypher, params):
        if "labels(n)" in cypher and params.get("label") == "Commitment":
            return FakeResult(("uuid", "name", "group_id"), [(uuid, "X", group)])
        return None
    return respond


def test_a_graph_not_built_is_the_shared_arm_refusal(tiny, store):
    text, view = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    with pytest.raises(ERR.ArmRefusal, match="not built"):
        asyncio.run(arm.plan_and_assemble(QC1, view))


def test_a_result_from_another_questions_graph_is_a_premise_violation_not_a_refusal(tiny, store):
    """Retrieval crossing the per-question graph boundary halts the run (FR-002; contracts/arm-registration
    item 5): ``PremiseViolated('cross_group_leak')``, which is NOT an ``ArmRefusal``."""
    text, view = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    store.respond = _typed_pull_row(A.stable_uuid("arms_A", "node", "COM_REVIEW"), "arms_A")

    async def scenario():
        await arm.build_graph(QC1, view)
        await arm.plan_and_assemble(QC1, view)
    with pytest.raises(ERR.PremiseViolated) as info:
        asyncio.run(scenario())
    assert info.value.reason == "cross_group_leak" and not isinstance(info.value, ERR.ArmRefusal)


def test_a_foreign_item_in_gs_own_graph_is_the_shared_arm_refusal(tiny, store):
    """An item carrying THIS question's group that G did not write from this view (a stale map, a graph
    not built from this view) is a configuration defect: terminal for the cell (FR-002)."""
    text, view = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    store.respond = _typed_pull_row("00000000-0000-5000-8000-000000000000", "arms_C1")

    async def scenario():
        await arm.build_graph(QC1, view)
        await arm.plan_and_assemble(QC1, view)
    with pytest.raises(ERR.ArmRefusal, match="foreign"):
        asyncio.run(scenario())


def test_the_tripwire_firing_is_a_premise_violation(tiny, store):
    """The no-LLM tripwire firing halts the run: a plan that counted an LLM call is refused as a
    PremiseViolated before anything is served (the tripwire's own exception class: test_arms849_embed)."""
    text, _ = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    facade = FakeFacade()
    block = text.render_block(["ev1"], [])
    plan = _plan(llm_calls=1)
    with pytest.raises(ERR.PremiseViolated) as info:
        arm.respond(block, plan, QC1, ctx_for(facade))
    assert info.value.reason == "tripwire" and facade.sent == [] and facade.counted == []


# -- respond: served exactly as D and R, on the attempt thread -------------------------------------

IDENT = S.ServingIdentity("gguf", "sha256:img", "emb", "tok", "a" * 64)


class FakePrompt:
    def render(self, block: Block, question_text: str) -> bytes:
        return block.data + question_text.encode("utf-8")


class FakeFacade:
    """``ctx.serving``: serialize/count as D and R use them; ``complete`` records the thread it ran on.
    ``before_send`` (when set) goes through the REAL ``serving.complete`` with the network refused."""

    def __init__(self, before_send=None) -> None:
        self.sent: list[dict] = []
        self.counted: list[int] = []
        self.threads: list[str] = []
        self.before_send = before_send

    def serialize(self, request: bytes, seed: int) -> dict:
        return {"prompt": request.decode("utf-8"), "seed": seed, "cache_prompt": True}

    def count_tokens(self, body: dict) -> int:
        self.counted.append(id(body))
        return len(body["prompt"].split())

    def count_text(self, data: bytes) -> int:
        return len(data.split())

    def complete(self, body: dict):
        self.threads.append(threading.current_thread().name)
        if self.before_send is not None:
            tok = SimpleNamespace(count=lambda s: len(s.split()))
            return S.complete(body, tok, 10**9, "http://127.0.0.1:1", before_send=self.before_send)
        self.sent.append(body)
        n = len(body["prompt"].split())
        return S.map_timings({"content": "ans", "stop_type": "eos",
                              "timings": {"prompt_n": n, "cache_n": 0, "prompt_ms": 10.0,
                                          "predicted_n": 5, "predicted_ms": 50.0}}, n)


def ctx_for(facade, config=None, limit=None, limit_applied=None, deadline=None, cancelled=None):
    cfg = config or S.ServingConfiguration.primary(IDENT)
    name, lim = cfg.limit_applied()
    return SimpleNamespace(prompt=FakePrompt(), seed=1001, config=cfg, serving=facade,
                           limit=lim if limit is None else limit,
                           limit_applied=name if limit_applied is None else limit_applied,
                           deadline=deadline, cancelled=cancelled or threading.Event())


def _plan(llm_calls: int = 0) -> A.PlanRecord:
    return A.PlanRecord(anchors_resolved=[], foreign_items=0, anchor_resolution_paths={}, ambiguous_mentions=[],
                        path="search_only", plan_steps=[], items_assembled=1, items_by_kind={"episode": 1},
                        llm_calls=llm_calls, group_id="arms_C1", assembled_context_sha256="x")


def test_an_incoherent_or_unconfigured_context_limit_is_refused_before_counting(tiny, store):
    """G's limit check is D's and R's (one shared check reading ONLY ctx.config): an incoherent pair,
    a pair that is not the configuration's, and a ctx whose configuration rides only on the facade."""
    text, _ = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    block = text.render_block(["ev1"], [])
    for kwargs in ({"limit": 0}, {"limit_applied": "configured"}, {"limit": S.TRAINED_CONTEXT - 1},
                   {"config": S.ServingConfiguration.secondary_yarn(IDENT), "limit": S.TRAINED_CONTEXT,
                    "limit_applied": "trained"}):
        facade = FakeFacade()
        with pytest.raises(ERR.ArmRefusal, match="configuration|incoherent"):
            arm.respond(block, _plan(), QC1, ctx_for(facade, **kwargs))
        assert facade.counted == [] and facade.sent == [], kwargs
    facade = FakeFacade()
    facade.config = S.ServingConfiguration.primary(IDENT)
    ctx = ctx_for(facade)
    del ctx.config                                                         # the removed fallback path
    with pytest.raises(ERR.ArmRefusal, match="ctx.config"):
        arm.respond(block, _plan(), QC1, ctx)
    assert facade.counted == [] and facade.sent == []


def test_g_is_served_exactly_as_d_and_r_and_never_refuses_cache_prompt(tiny, store):
    """C-008: same prompt, same serving; ``cache_prompt: true`` is what G sends, never a refusal."""
    text, _ = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    facade = FakeFacade()
    block = text.render_block(["ev1"], [])
    row = arm.respond(block, _plan(), QC1, ctx_for(facade))
    assert facade.sent[0]["cache_prompt"] is True and facade.counted == [id(facade.sent[0])]
    assert row["assembled_context_sha256"] == block.sha256 and row["prompt_tokens"] == len(facade.sent[0]["prompt"].split())
    import inspect

    assert "cache_prompt" not in inspect.getsource(A.GraphArm.respond).split('"""')[2]   # the code, not the docstring


@pytest.mark.parametrize("exc", [ERR.CeilingBreached(58.0, 57.5), ERR.CeilingUnreadable("GTT sysfs unreadable")],
                         ids=["breach", "unreadable"])
def test_the_ceiling_guard_reaches_the_caller_unaltered_through_g(tiny, store, bridges, monkeypatch, exc):
    """FR-008 (serving side): ``before_send`` raising inside the REAL ``serving.complete`` reaches the
    caller of ``Bridge.answer`` as the SAME object, and nothing is sent."""
    import urllib.request

    def never(*a, **k):
        raise AssertionError("a byte was sent past the ceiling guard")
    monkeypatch.setattr(urllib.request, "urlopen", never)

    def guard():
        raise exc
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    with pytest.raises(type(exc)) as info:
        bridge.answer(QC1, view, ctx_for(FakeFacade(before_send=guard)))
    assert info.value is exc


# -- the bridge (research D-2; NFR-003) --------------------------------------------------------------


def test_retrieval_runs_on_the_bridge_loop_and_serving_on_the_attempt_thread(tiny, store, bridges, clones):
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    stats = bridge.build_graph(QC1, view)
    assert stats.group_id == "arms_C1" and stats.nodes == 3 and stats.episodes == 2 and stats.links == 2
    facade = FakeFacade()
    rows = [bridge.answer(QC1, view, ctx_for(facade)) for _ in range(3)]
    assert len({r["assembled_context_sha256"] for r in rows}) == 1
    assert store.threads == {A.LOOP_THREAD_NAME}                            # every query on the ONE loop
    assert facade.threads == [threading.current_thread().name] * 3          # serving on the caller's thread
    assert collections.Counter(clones) == {"arms_C1": 1}
    assert pending(bridge) == []


def test_the_production_grace_is_ten_seconds():
    assert ERR.G_CANCEL_GRACE_S == 10


def test_gcancellation_unacknowledged_escapes_every_ordinary_handler():
    assert issubclass(ERR.GCancellationUnacknowledged, BaseException)
    assert not issubclass(ERR.GCancellationUnacknowledged, Exception)
    try:
        try:
            raise ERR.GCancellationUnacknowledged(10.0)
        except Exception:                                                  # noqa: BLE001 — the point
            pytest.fail("an ordinary handler absorbed GCancellationUnacknowledged")
    except ERR.GCancellationUnacknowledged as exc:
        assert exc.grace_s == 10.0


@pytest.mark.parametrize("how", ["deadline", "cancelled"])
def test_an_acknowledged_cancellation_leaves_no_bridge_task_behind(tiny, store, bridges, how):
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    store.hang = lambda db, cypher, params: "cancellable" if "labels(n)" in cypher else None
    cancelled = threading.Event()
    deadline = time.monotonic() + 0.2 if how == "deadline" else None
    if how == "cancelled":
        threading.Timer(0.2, cancelled.set).start()
    t0 = time.monotonic()
    with pytest.raises(TimeoutError, match="acknowledged"):
        bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=deadline, cancelled=cancelled))
    assert time.monotonic() - t0 < 5
    assert pending(bridge) == [] and store.in_flight == 0
    store.hang = lambda db, cypher, params: None                                    # the bridge is still usable
    assert bridge.answer(QC1, view, ctx_for(FakeFacade()))["text"] == "ans"


def test_an_unacknowledged_cancellation_raises_and_the_bridge_issues_nothing_more(tiny, store, bridges, monkeypatch):
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.3)
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    store.hang = lambda db, cypher, params: "stubborn" if "labels(n)" in cypher else None
    t0 = time.monotonic()
    with pytest.raises(ERR.GCancellationUnacknowledged) as info:
        bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.1))
    assert info.value.grace_s == 0.3 and 0.35 <= time.monotonic() - t0 < 5
    n = len(store.queries)
    for call in (lambda: bridge.build_graph(QA, view), lambda: bridge.drop_graph(QC1), lambda: bridge.list_graphs(),
                 lambda: bridge.answer(QC1, view, ctx_for(FakeFacade()))):
        with pytest.raises(ERR.GCancellationUnacknowledged):
            call()
    assert bridge.close() is False
    assert len(store.queries) == n and store.closed is False                # no further query, no cleanup query


@pytest.mark.parametrize("mode,acknowledged", [("cancellable", True), ("stubborn", False)])
def test_cancellation_during_a_clones_index_build(tiny, store, bridges, clones, monkeypatch, mode, acknowledged):
    """The clone's detached ``_init_task`` is a task the bridge started: an acknowledgement counts only
    once it is done. A cancelled index build is never reused — the next build clones afresh."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.3)
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    store.hang = lambda db, cypher, params: mode if cypher.lstrip().startswith("CREATE INDEX") else None
    expected = TimeoutError if acknowledged else ERR.GCancellationUnacknowledged
    with pytest.raises(expected):
        bridge.build_graph(QC1, view, deadline=time.monotonic() + 0.2)
    assert not any("MERGE" in c for _, c in store.queries)                  # nothing written before indices
    if not acknowledged:
        return
    assert pending(bridge) == []
    store.hang = lambda db, cypher, params: None
    stats = bridge.build_graph(QC1, view)
    assert stats.nodes == 3 and collections.Counter(clones) == {"arms_C1": 2}
    assert pending(bridge) == []


def test_rebuild_and_drop_across_two_databases(tiny, store, bridges, clones):
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    assert bridge.list_graphs() == []
    bridge.build_graph(QC1, view)
    bridge.build_graph(QA, view)
    assert bridge.list_graphs() == ["arms_A", "arms_C1"]
    mark = len(store.queries)
    bridge.drop_graph(QC1)
    dropped = store.queries[mark:]
    assert [db for db, _ in dropped] == ["arms_C1"] and "DETACH DELETE" in dropped[0][1]
    mark = len(store.queries)
    bridge.build_graph(QC1, view)                                            # rebuild: same database, same clone
    assert {db for db, _ in store.queries[mark:]} == {"arms_C1"}
    bridge.answer(QA, view, ctx_for(FakeFacade()))
    assert collections.Counter(clones) == {"arms_C1": 1, "arms_A": 1} and pending(bridge) == []


@pytest.mark.parametrize("mode,acknowledged", [("cancellable", True), ("stubborn", False)])
def test_a_detached_task_started_during_the_work_is_part_of_the_acknowledgement(tiny, store, bridges, monkeypatch,
                                                                                mode, acknowledged):
    """Quiescence covers EVERY task the bridge's work started, not only the awaited chain: a task the
    transport detaches (as ``FalkorDriver`` detaches ``_init_task`` on every clone) must be done before
    the acknowledgement — after a normal return and after a cancellation. One that ignores its
    cancellation withholds the acknowledgement."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.3)
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    detached: list = []

    async def lingering():
        if mode == "stubborn":
            while not store.release.is_set():
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    continue
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await asyncio.sleep(0.2)          # a SLOW unwind: still running when a premature acknowledgement fires
            raise

    def spawn(db, cypher, params):
        if params.get("label") == A.TYPED_LABELS[0]:
            detached.append(asyncio.get_running_loop().create_task(lingering()))
    store.observe = spawn
    if acknowledged:
        assert bridge.answer(QC1, view, ctx_for(FakeFacade()))["text"] == "ans"          # a normal return
        assert detached and all(t.done() for t in detached) and pending(bridge) == []
        store.hang = lambda db, cypher, params: "cancellable" if "labels(n)" in cypher else None
        with pytest.raises(TimeoutError, match="acknowledged"):
            bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.1))
        assert len(detached) == 2 and all(t.done() for t in detached)       # at the moment the bridge returned
        assert pending(bridge) == []
    else:
        # even after a normal return the acknowledgement is withheld, so the attempt's deadline expires
        with pytest.raises(ERR.GCancellationUnacknowledged):
            bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.3))


def test_a_finalised_abandoned_bridge_never_touches_another_bridges_loop(tiny, monkeypatch):
    """An abandoned bridge's pending coroutine is finalised by the garbage collector wherever GC happens
    to run — here, on ANOTHER bridge's loop thread mid-query. Its cleanup must not quiesce (cancel) that
    other loop's work, and must not claim an acknowledgement."""
    import gc

    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.2)
    text, view = tiny
    s1 = FakeFalkorDB()
    b1 = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=s1))
    b1.build_graph(QC1, view)
    s1.hang = lambda db, cypher, params: "stubborn" if "labels(n)" in cypher else None
    with pytest.raises(ERR.GCancellationUnacknowledged):
        b1.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.05))
    assert b1.close() is False
    b1._thread.join(2)
    import weakref

    abandoned = weakref.ref(b1._loop)
    del b1
    s2 = FakeFalkorDB()
    b2 = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=s2))
    try:
        b2.build_graph(QC1, view)
        collected: list[int] = []
        unraisable: list = []
        monkeypatch.setattr(sys, "unraisablehook", unraisable.append)
        first = lambda params: params.get("label") == A.TYPED_LABELS[0]
        # GC as a plain loop CALLBACK (no current task) while b2's retrieval is suspended mid-query:
        # a finaliser that quiesced "the running loop" would cancel b2's work right there.
        s2.hang = lambda db, cypher, params: "brief" if first(params) else None
        s2.observe = lambda db, cypher, params: (asyncio.get_running_loop().call_soon(
            lambda: collected.append(gc.collect())) if first(params) else None)
        assert b2.answer(QC1, view, ctx_for(FakeFacade()))["text"] == "ans"
        assert collected and abandoned() is None                     # the abandoned loop WAS finalised mid-query
        # ... quietly: its coroutine awaited nothing while being closed ("coroutine ignored GeneratorExit")
        assert not [u for u in unraisable if "_guarded" in repr(u.object)], [(u.exc_value, u.object) for u in unraisable]
        assert pending(b2) == []
    finally:
        b2.close()
        s1.release.set()


def test_a_coroutine_closed_while_suspended_quiesces_nothing_and_acknowledges_nothing(tiny, store, bridges,
                                                                                    monkeypatch):
    """The finalisation half of the test above, pinned directly: ``GeneratorExit`` (a coroutine being
    closed, not cancelled) touches no loop and sets no acknowledgement."""
    text, _ = tiny
    bridge = make_bridge(store, text, bridges)
    touched: list[int] = []

    async def fake_quiesce():
        touched.append(1)
    monkeypatch.setattr(bridge, "_quiesce", fake_quiesce)

    class Suspend:
        def __await__(self):
            yield

    async def make():
        await Suspend()
    ack = threading.Event()
    coro = bridge._guarded(make, ack, {})
    coro.send(None)                                                         # suspended inside make()
    coro.close()
    assert touched == [] and not ack.is_set()


def test_close_shuts_the_loop_down_after_its_own_quiescence(tiny, store):
    text, view = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=store))
    bridge.build_graph(QC1, view)
    assert bridge.close() is True
    assert store.closed and not bridge._thread.is_alive()
    with pytest.raises(RuntimeError, match="closed"):
        bridge.build_graph(QC1, view)


def test_no_attempt_starts_before_the_previous_termination_is_acknowledged(tiny, store, bridges):
    """NFR-003 at the arm level: 100 consecutive attempts with injected timeouts and cancellations
    against the fake store. At the first query of every attempt, no other bridge task is pending, and
    never more than one query is in flight."""
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    overlaps: list[int] = []
    inject = [False]

    def first_query_of_an_attempt(db, cypher, params):
        return "labels(n)" in cypher and params.get("label") == A.TYPED_LABELS[0]

    def observe(db, cypher, params):
        if first_query_of_an_attempt(db, cypher, params):
            me = asyncio.current_task()
            overlaps.append(sum(1 for t in asyncio.all_tasks() if t is not me and not t.done()))

    store.observe = observe
    store.hang = lambda db, cypher, params: "cancellable" if inject[0] and first_query_of_an_attempt(db, cypher, params) else None
    outcomes: collections.Counter = collections.Counter()
    for i in range(100):
        inject[0] = i % 3 != 2
        cancelled = threading.Event()
        deadline = time.monotonic() + 0.02 if i % 3 == 0 else None
        if i % 3 == 1:
            threading.Timer(0.02, cancelled.set).start()
        try:
            bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=deadline, cancelled=cancelled))
            outcomes["ok"] += 1
        except TimeoutError:
            outcomes["cancelled"] += 1
    assert outcomes == {"cancelled": 67, "ok": 33}, outcomes
    assert len(overlaps) == 100 and set(overlaps) == {0}, collections.Counter(overlaps)
    assert store.max_in_flight == 1 and pending(bridge) == []


# -- WP02 review cycle 1 (Codex): lifecycle and boundary regressions ------------------------------


@pytest.mark.parametrize("row_group,expected,reason", [
    ("arms_A", ERR.PremiseViolated, "cross_group_leak"),
    ("arms_C1", ERR.ArmRefusal, None),
], ids=["leak", "foreign"])
def test_a_terminal_exception_raised_during_the_grace_wait_reaches_the_caller(tiny, store, bridges, monkeypatch,
                                                                               row_group, expected, reason):
    """Review c1 finding 1: the deadline passes while the transport is stalled; the stall clears INSIDE the
    grace wait and the retrieval then detects a terminal condition. The caller gets THAT exception — the
    same class the uncancelled path raises — never a retryable TimeoutError."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 2.0)
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    store.hang = lambda db, cypher, params: "stubborn" if "labels(n)" in cypher else None
    store.respond = _typed_pull_row("00000000-0000-5000-8000-0000000000aa", row_group)
    threading.Timer(0.15, store.release.set).start()
    with pytest.raises(expected) as info:
        bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.05))
    if reason:
        assert info.value.reason == reason
    assert pending(bridge) == []


def test_an_ordinary_failure_during_the_grace_wait_stays_a_retryable_timeout(tiny, store, bridges, monkeypatch):
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 2.0)
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    store.hang = lambda db, cypher, params: "stubborn" if "labels(n)" in cypher else None

    def boom(db, cypher, params):
        if store.release.is_set() and "labels(n)" in cypher:
            raise ConnectionError("socket reset while unwinding")
    real_query = FakeGraph.query

    async def failing(self, cypher, params=None):
        out = await real_query(self, cypher, params)
        boom(self.name, cypher, params or {})
        return out
    monkeypatch.setattr(FakeGraph, "query", failing)
    threading.Timer(0.15, store.release.set).start()
    with pytest.raises(TimeoutError, match="acknowledged") as info:
        bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.05))
    assert isinstance(info.value.__cause__, ConnectionError)


def test_after_an_unacknowledged_cancellation_nothing_more_reaches_the_transport(tiny, store, bridges, monkeypatch):
    """Review c1 finding 2: once GCancellationUnacknowledged is raised, clearing the stall must not let the
    abandoned work issue a single further query: the loop is stopped BEFORE the signal is raised."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.2)
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    store.hang = lambda db, cypher, params: "stubborn" if "labels(n)" in cypher else None
    with pytest.raises(ERR.GCancellationUnacknowledged):
        bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.05))
    assert not bridge._thread.is_alive()                                       # stopped before the signal
    n = len(store.queries)
    store.release.set()                                                        # the stall clears
    time.sleep(0.3)
    assert len(store.queries) == n, store.queries[n:]


def test_quiescence_drains_tasks_spawned_during_cleanup(tiny, store, bridges):
    """Review c1 finding 3: a task that, while being cancelled, spawns ANOTHER task — the acknowledgement
    waits for the descendant too, after a normal return and after a cancellation."""
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    spawned: list = []

    async def child():
        await asyncio.sleep(3600)

    async def parent():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            spawned.append(asyncio.get_running_loop().create_task(child()))
            raise

    def spawn(db, cypher, params):
        if params.get("label") == A.TYPED_LABELS[0]:
            spawned.append(asyncio.get_running_loop().create_task(parent()))
    store.observe = spawn
    assert bridge.answer(QC1, view, ctx_for(FakeFacade()))["text"] == "ans"
    assert len(spawned) == 2 and all(t.done() for t in spawned), spawned
    assert pending(bridge) == []
    store.hang = lambda db, cypher, params: "cancellable" if "labels(n)" in cypher else None
    with pytest.raises(TimeoutError, match="acknowledged"):
        bridge.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.1))
    assert len(spawned) == 4 and all(t.done() for t in spawned), spawned
    assert pending(bridge) == []


def test_close_during_an_active_operation_has_one_cancellation_owner(tiny, store):
    """Review c1 finding 4: close() while an operation is in flight stops new submissions, cancels the active
    one through ITS OWN acknowledgement path, and only then shuts down — no competing quiescence passes
    (which cancelled each other recursively), nothing left pending."""
    text, view = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=store))
    bridge.build_graph(QC1, view)
    store.hang = lambda db, cypher, params: "cancellable" if "labels(n)" in cypher else None
    outcome: dict = {}

    def run():
        try:
            bridge.answer(QC1, view, ctx_for(FakeFacade()))                  # no deadline, no cancel flag
        except BaseException as exc:                                          # noqa: BLE001 — recorded
            outcome["exc"] = exc
    loop_errors: list = []
    bridge._loop.set_exception_handler(lambda loop, context: loop_errors.append(context))
    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.2)
    assert store.in_flight == 1
    t0 = time.monotonic()
    assert bridge.close() is True
    worker.join(5)
    assert not worker.is_alive() and time.monotonic() - t0 < 5
    assert isinstance(outcome.get("exc"), TimeoutError) and "closing" in str(outcome["exc"]), outcome
    assert store.closed and not bridge._thread.is_alive() and loop_errors == []
    assert not [t for t in asyncio.all_tasks(bridge._loop) if not t.done()]
    with pytest.raises(RuntimeError, match="closed"):
        bridge.list_graphs()


def test_a_uuid_g_wrote_for_another_question_is_a_leak_even_under_this_group(tiny, store):
    """The other half of the boundary: a result reported under THIS group whose uuid G wrote for ANOTHER
    question's graph is a leak (PremiseViolated), not a foreign item (ArmRefusal)."""
    text, view = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    store.respond = _typed_pull_row(A.stable_uuid("arms_A", "node", "COM_REVIEW"), "arms_C1")

    async def scenario():
        await arm.build_graph(QA, view)
        await arm.build_graph(QC1, view)
        await arm.plan_and_assemble(QC1, view)
    with pytest.raises(ERR.PremiseViolated) as info:
        asyncio.run(scenario())
    assert info.value.reason == "cross_group_leak"


def test_a_known_uuid_reported_under_another_questions_group_is_a_leak(tiny, store):
    """Review c1 finding 5: the result's reported group is checked BEFORE the uuid map — a uuid G wrote for
    THIS question, returned carrying another question's group, has crossed the boundary."""
    text, view = tiny
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    store.respond = _typed_pull_row(A.stable_uuid("arms_C1", "node", "COM_REVIEW"), "arms_A")

    async def scenario():
        await arm.build_graph(QC1, view)
        await arm.plan_and_assemble(QC1, view)
    with pytest.raises(ERR.PremiseViolated) as info:
        asyncio.run(scenario())
    assert info.value.reason == "cross_group_leak"


# -- WP02 review cycle 2 (Codex): structural invariants A (transport gate), B (acknowledgement on every
#    completion path), C (append-only uuid ownership) -------------------------------------------------


class BlockingEmbedder(FakeEmbedder):
    """Blocks SYNCHRONOUSLY — on the loop thread, where graphiti calls it — once ``armed`` is set, until
    ``unblock`` is set: work no cancellation can interrupt."""

    def __init__(self) -> None:
        self.armed = threading.Event()
        self.unblock = threading.Event()
        self.blocked = threading.Event()

    def embed(self, texts):
        if self.armed.is_set() and not self.unblock.is_set():
            self.blocked.set()
            self.unblock.wait(30)
        return super().embed(texts)


def test_a_poisoned_bridge_sends_nothing_even_when_blocked_synchronous_work_resumes(tiny, store, bridges, monkeypatch):
    """Invariant A (review c2 finding 2): the embedder blocks synchronously on the loop thread, so neither
    cancellation nor a loop stop can take effect. The fatal signal is raised anyway; when the block clears,
    the resumed build reaches the transport — and the gate refuses every query."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.3)
    text, view = tiny
    emb = BlockingEmbedder()
    bridge = make_bridge(store, text, bridges, emb)
    emb.armed.set()
    with pytest.raises(ERR.GCancellationUnacknowledged):
        bridge.build_graph(QC1, view, deadline=time.monotonic() + 0.1)
    assert emb.blocked.is_set() and bridge._thread.is_alive()                  # the loop is stuck in sync code
    n = len(store.queries)
    emb.unblock.set()                                                           # the block clears
    bridge._thread.join(5)
    time.sleep(0.2)
    assert len(store.queries) == n, store.queries[n:]
    for call in (lambda: bridge.list_graphs(), lambda: bridge.drop_graph(QC1)):
        with pytest.raises(ERR.GCancellationUnacknowledged):
            call()
    assert len(store.queries) == n


def test_close_during_a_blocked_synchronous_call_sends_nothing_afterwards(tiny, store, monkeypatch):
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.3)
    text, view = tiny
    emb = BlockingEmbedder()
    bridge = A.make_bridge(emb, text, driver=FalkorDriver(falkor_db=store))
    emb.armed.set()
    outcome: dict = {}

    def run():
        try:
            bridge.build_graph(QC1, view)                                     # no deadline, no cancel flag
        except BaseException as exc:                                           # noqa: BLE001 — recorded
            outcome["exc"] = exc
    worker = threading.Thread(target=run)
    worker.start()
    assert emb.blocked.wait(5)
    t0 = time.monotonic()
    assert bridge.close() is False                                              # not acknowledged: not clean
    assert time.monotonic() - t0 < 5
    worker.join(5)
    assert isinstance(outcome.get("exc"), ERR.GCancellationUnacknowledged), outcome
    n = len(store.queries)
    emb.unblock.set()
    bridge._thread.join(5)
    time.sleep(0.2)
    assert len(store.queries) == n and store.closed is False, store.queries[n:]


def test_a_task_that_refuses_to_finish_on_the_success_path_is_never_a_success(tiny, store, bridges, monkeypatch):
    """Invariant B (review c2 finding 1): the work RETURNS, but a task it started refuses to finish. With a
    deadline far LONGER than the drain grace, the drain overruns: that is an unacknowledged termination —
    the bridge poisons and raises, it never returns the answer, and nothing further is sent."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.3)
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)

    async def refuses():
        while not store.release.is_set():
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                continue

    def spawn(db, cypher, params):
        if params.get("label") == A.TYPED_LABELS[0]:
            asyncio.get_running_loop().create_task(refuses())
    store.observe = spawn
    facade = FakeFacade()
    t0 = time.monotonic()
    with pytest.raises(ERR.GCancellationUnacknowledged):
        bridge.answer(QC1, view, ctx_for(facade, deadline=time.monotonic() + 30))
    assert time.monotonic() - t0 < 5 and facade.sent == []
    n = len(store.queries)
    with pytest.raises(ERR.GCancellationUnacknowledged):
        bridge.list_graphs()
    store.release.set()
    time.sleep(0.2)
    assert len(store.queries) == n


def _classify(text, view, report_uuid: str, report_group: str, lifecycle: str):
    """Build A and C1, apply ``lifecycle`` to A, then have retrieval for C1 report ``report_uuid`` under
    ``report_group``: the resulting classification as (exception class, reason)."""
    store = FakeFalkorDB()
    arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
    store.respond = _typed_pull_row(report_uuid, report_group)

    async def scenario():
        await arm.build_graph(QA, view)
        await arm.build_graph(QC1, view)
        if lifecycle in ("drop", "drop_and_rebuild"):
            await arm.drop_graph(QA)
        if lifecycle == "drop_and_rebuild":
            await arm.build_graph(QA, view)
        await arm.plan_and_assemble(QC1, view)
    try:
        asyncio.run(scenario())
    except (ERR.PremiseViolated, ERR.ArmRefusal) as exc:
        return type(exc), getattr(exc, "reason", None)
    return None, None


@pytest.mark.parametrize("report_group", ["arms_C1", "arms_A"], ids=["labelled-C1", "labelled-A"])
def test_dropping_a_graph_never_changes_how_a_later_report_is_classified(tiny, report_group):
    """Invariant C as a DIFFERENTIAL (review c2 finding 3): the same report — A's uuid, labelled C1 or A,
    returned by C1's retrieval — is classified identically whether or not A was dropped (or dropped and
    rebuilt) in between, and that classification is a cross-group leak."""
    text, view = tiny
    a_uuid = A.stable_uuid("arms_A", "node", "COM_REVIEW")
    got = {lc: _classify(text, view, a_uuid, report_group, lc) for lc in ("none", "drop", "drop_and_rebuild")}
    assert len(set(got.values())) == 1, got
    assert got["none"] == (ERR.PremiseViolated, "cross_group_leak"), got


def test_the_gate_checks_when_a_query_starts_not_when_it_was_created(tiny, store, bridges):
    """Invariant A, timing: a query coroutine created BEFORE the gate shut and awaited after it is refused
    when it starts — a suspended step of abandoned work cannot carry a query past the fatal signal."""
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    graph = bridge.arm._databases["arms_C1"].client.select_graph("arms_C1")
    pending_query = graph.query("RETURN 1")
    bridge._shut.set()
    n = len(store.queries)

    async def go():
        await pending_query
    with pytest.raises(A.TransportPoisoned):
        asyncio.run(go())
    assert len(store.queries) == n


_NETWORK_PACKAGES = ("falkordb", "redis")
_NOT_STATE_PACKAGES = ("asyncio", "threading", "concurrent", "_thread", "logging", "selectors", "socket", "weakref")


def _cell_filled(cell) -> bool:
    try:
        _ = cell.cell_contents
    except ValueError:
        return False
    return True


def _transport_reachable(root):
    """Walk every object reachable from ``root`` (attributes, slots, containers, bound methods). Returns
    (objects behind a TransportGate, paths to network objects reached WITHOUT one). A network object is
    anything from the client packages (falkordb, redis) — derived from what is there, not from a list of
    today's entry points."""
    import types as _types

    seen: set[int] = set()
    stack = [(root, "bridge")]
    gated, raw = [], []
    while stack:
        obj, path = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, getattr(A, "TransportGate", ())):
            gated.append(object.__getattribute__(obj, "_target"))
            continue
        top = (type(obj).__module__ or "").split(".")[0]
        if top in _NETWORK_PACKAGES:
            raw.append(f"{path} ({type(obj).__module__}.{type(obj).__qualname__})")
            continue
        if isinstance(obj, _types.FunctionType):
            # A function RETAINS what its closure cells, defaults and __wrapped__ hold (review c3 minor: a
            # closure keeping a raw client passed the earlier walk). Its globals are the module, not state.
            stack.extend((c.cell_contents, f"{path}.<closure {i}>") for i, c in enumerate(obj.__closure__ or ())
                         if _cell_filled(c))
            stack.extend((d, f"{path}.<default {i}>") for i, d in enumerate(obj.__defaults__ or ()))
            stack.extend((d, f"{path}.<kwdefault {k}>") for k, d in (obj.__kwdefaults__ or {}).items())
            if hasattr(obj, "__wrapped__"):
                stack.append((obj.__wrapped__, f"{path}.__wrapped__"))
            continue
        if top in _NOT_STATE_PACKAGES or isinstance(obj, (type, _types.ModuleType, _types.BuiltinFunctionType,
                                                           str, bytes, int, float, bool, type(None),
                                                           _types.CodeType)):
            continue
        if isinstance(obj, _types.MethodType):
            stack.append((obj.__self__, f"{path}.__self__"))
            continue
        if isinstance(obj, dict):
            stack.extend((v, f"{path}[{k!r}]") for k, v in obj.items())
            stack.extend((k, f"{path}<key>") for k in obj)
            continue
        if isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend((v, f"{path}[{i}]") for i, v in enumerate(obj))
            continue
        attrs = dict(getattr(obj, "__dict__", {}) or {})
        for klass in type(obj).__mro__:
            for slot in getattr(klass, "__slots__", ()) or ():
                if isinstance(slot, str) and hasattr(obj, slot):
                    attrs.setdefault(slot, getattr(obj, slot))
        stack.extend((v, f"{path}.{k}") for k, v in attrs.items())
    return gated, raw


def test_no_network_object_is_reachable_from_the_bridge_except_through_the_gate(tiny, monkeypatch):
    """Invariant A, DERIVED at test time (fails on ADDITION): with the REAL falkordb client (its query
    methods replaced at the class, so nothing leaves the process), the bridge builds two questions and
    answers. Then every object reachable from the bridge is walked, and any falkordb/redis object reached
    NOT through a TransportGate fails the test. A new driver attribute, a clone that opens its own
    connection, a Graphiti that keeps a raw client — anything that can reach the network ungated — shows
    up here without this test naming it."""
    from falkordb.asyncio import FalkorDB as RealFalkorDB
    from falkordb.asyncio.graph import AsyncGraph

    sent: list[str] = []

    async def fake_query(self, q, params=None, timeout=None):
        sent.append(self.name)
        return FakeResult()
    monkeypatch.setattr(AsyncGraph, "query", fake_query)
    monkeypatch.setattr(AsyncGraph, "ro_query", fake_query)

    async def fake_list(self):
        return []
    monkeypatch.setattr(RealFalkorDB, "list_graphs", fake_list)
    # The client's constructor probes the server synchronously (INFO, for cluster mode) — at construction,
    # before any gate can exist; it is the one connection a bridge makes outside the gate (WP02 notes).
    import falkordb.asyncio.falkordb as _falkor_module
    monkeypatch.setattr(_falkor_module, "Is_Cluster", lambda conn: False)
    text, view = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=1)
    try:
        bridge.build_graph(QC1, view)
        bridge.build_graph(QA, view)
        bridge.answer(QC1, view, ctx_for(FakeFacade()))
        bridge.list_graphs()
        gated, raw = _transport_reachable(bridge)
        assert raw == [], raw
        assert any(isinstance(t, RealFalkorDB) for t in gated), gated
        assert set(sent) == {"arms_C1", "arms_A"}                              # the walk saw a live transport
    finally:
        bridge.close()


def _returns_and_raises(fn):
    tree = ast.parse(__import__("textwrap").dedent(__import__("inspect").getsource(fn)))
    return [n for n in ast.walk(tree) if isinstance(n, (ast.Return, ast.Raise))], tree


def test_every_exit_of_every_operation_passes_the_acknowledgement_check():
    """Invariant B, SECONDARY guard from the source (the proof is behavioural: the frame-level tests
    below inject a KeyboardInterrupt and a raising helper). (1) Work reaches the loop only in
    ``Bridge._run``; (2) after the submit, ``_run`` is ONE try whose ``finally`` poisons unless a verdict was
    delivered, and every return/raise comes after that try; (3) ``_conclude`` raises nothing itself and
    returns only after the ``if not acknowledged: self._poison(...)`` gate; (4) ``_poison`` marks first, and
    marking shuts the gate first."""
    import inspect as _inspect

    def body(fn):
        return ast.parse(__import__("textwrap").dedent(_inspect.getsource(fn))).body[0]

    src = ast.parse(__import__("textwrap").dedent(_inspect.getsource(A.Bridge)))
    submitters = {f.name for f in ast.walk(src) if isinstance(f, ast.FunctionDef)
                  for c in ast.walk(f) if isinstance(c, ast.Call) and _call_name(c) == "run_coroutine_threadsafe"}
    assert submitters == {"_run"}, submitters
    run = body(A.Bridge._run)
    submit_line = next(c.lineno for c in ast.walk(run) if isinstance(c, ast.Call)
                       and _call_name(c) == "run_coroutine_threadsafe")
    tries = [st for st in run.body if isinstance(st, ast.Try) and st.lineno > submit_line]
    assert len(tries) == 1, [ast.unparse(t)[:60] for t in tries]
    guard = tries[0]
    assert "if not concluded" in ast.unparse(guard.finalbody[0]) and "_mark_poisoned" in ast.unparse(guard.finalbody[0])
    assert ast.unparse(guard.body[-1]) == "concluded = True"
    for node in ast.walk(run):
        if isinstance(node, (ast.Return, ast.Raise)) and node.lineno > submit_line:
            assert node.lineno > guard.end_lineno, ast.unparse(node)
    exits, _ = _returns_and_raises(A.Bridge._wait)
    assert not [n for n in exits if isinstance(n, ast.Raise)]
    conclude = body(A.Bridge._conclude)
    gate = next(st for st in conclude.body if isinstance(st, ast.If) and ast.unparse(st.test) == "not acknowledged")
    assert any(isinstance(c, ast.Call) and _call_name(c) == "_poison" for c in ast.walk(gate))
    assert not [n for n in ast.walk(conclude) if isinstance(n, ast.Raise)]
    for node in ast.walk(conclude):
        if isinstance(node, ast.Return):
            assert node.lineno > gate.end_lineno, ast.unparse(node)

    def statements(fn):
        return [st for st in body(fn).body if not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant))]
    assert ast.unparse(statements(A.Bridge._poison)[0]) == "self._mark_poisoned(grace)"
    assert ast.unparse(statements(A.Bridge._mark_poisoned)[0]) == "self._shut.set()"


def _instance(cls):
    for args in (("probe",), ("cross_group_leak", "probe"), (58.0, 57.5)):
        try:
            return cls(*args)
        except (TypeError, ValueError):
            continue
    raise AssertionError(f"cannot construct {cls}")


#: Outcomes DERIVED from the code at collection time: a new TERMINAL_EXCEPTIONS member is covered with no edit here.
_OUTCOMES = ["ok", RuntimeError, *A.TERMINAL_EXCEPTIONS]


@pytest.mark.parametrize("ending", ["finishes", "past_deadline"])
@pytest.mark.parametrize("outcome", _OUTCOMES, ids=lambda o: o if isinstance(o, str) else o.__name__)
def test_no_outcome_is_accepted_while_a_bridge_task_remains(tiny, monkeypatch, outcome, ending):
    """Invariant B, behavioural, over outcomes DERIVED from the code (``TERMINAL_EXCEPTIONS``, plus a
    return and an ordinary exception), each ending normally AND past its deadline: the work leaves behind
    a task that refuses to finish, with a deadline far longer than the drain grace in the normal case.
    Every one fails the path — poison, then GCancellationUnacknowledged — and nothing further reaches the
    transport."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.2)
    text, _ = tiny
    store = FakeFalkorDB()
    bridge = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=store))

    async def refuses():
        while not store.release.is_set():
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                continue

    async def work():
        asyncio.get_running_loop().create_task(refuses())
        await asyncio.sleep(0)                                           # let it start (and so refuse)
        await bridge.arm.list_graphs()                                   # one real transport call
        if ending == "past_deadline":
            await asyncio.sleep(0.3)
        if outcome != "ok":
            raise _instance(outcome)
        return "result"
    try:
        deadline = time.monotonic() + (0.1 if ending == "past_deadline" else 30)
        with pytest.raises(ERR.GCancellationUnacknowledged):
            bridge._submit(work, deadline, None, f"probe {outcome} {ending}")
        n = len(store.queries)
        store.release.set()
        time.sleep(0.05)
        with pytest.raises(ERR.GCancellationUnacknowledged):
            bridge.list_graphs()
        assert len(store.queries) == n
    finally:
        store.release.set()
        bridge.close()


def test_the_gate_blocks_only_the_poisoned_bridge(tiny, monkeypatch):
    """The permitted side of invariant A: a never-poisoned bridge — here a FRESH one in the same process
    after another was poisoned — sends its queries normally, and its close() performs the normal
    teardown (the connection is closed through the gate) and is clean."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.2)
    text, view = tiny
    s1 = FakeFalkorDB()
    b1 = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=s1))
    b1.build_graph(QC1, view)
    s1.hang = lambda db, cypher, params: "stubborn" if "labels(n)" in cypher else None
    with pytest.raises(ERR.GCancellationUnacknowledged):
        b1.answer(QC1, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 0.05))
    s2 = FakeFalkorDB()
    b2 = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=s2))
    try:
        stats = b2.build_graph(QC1, view)
        assert stats.nodes == 3
        row = b2.answer(QC1, view, ctx_for(FakeFacade()))
        assert row["text"] == "ans" and "arms_C1" in b2.list_graphs()
        assert len(s2.queries) > 20 and s2.dbs() == {"arms_C1"}
        b2.drop_graph(QC1)
        assert any("DETACH DELETE" in c for _, c in s2.queries)
    finally:
        assert b2.close() is True
        assert s2.closed                                                       # the normal teardown ran
        s1.release.set()
        b1.close()


def test_every_transport_entry_point_goes_through_the_one_gate(tiny, store, bridges):
    """Invariant A, coverage. The installed FalkorDriver reaches FalkorDB ONLY through ``self.client``
    (``_get_graph`` → ``select_graph`` → ``graph.query``; ``close`` → ``aclose``/``connection``), and every
    clone shares its parent's client. So: (1) the root and every clone the bridge made — and the driver
    each per-question Graphiti holds — carry the gate as ``client``; (2) the installed ``clone`` still
    passes ``falkor_db=self.client`` and nothing else constructs a client (fails if an upgrade opens a
    new connection); (3) once poisoned, the gate refuses EVERY public method of the real ``FalkorDB`` and
    ``AsyncGraph`` classes, enumerated from the installed package, before the target sees it."""
    import inspect as _inspect

    from falkordb.asyncio import FalkorDB as RealFalkorDB
    from falkordb.asyncio.graph import AsyncGraph
    from graphiti_core.driver import falkordb_driver as FD

    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    bridge.build_graph(QA, view)
    bridge.answer(QC1, view, ctx_for(FakeFacade()))
    gate = bridge.arm.driver.client
    assert isinstance(gate, A.TransportGate)
    drivers = [bridge.arm.driver, *bridge.arm._databases.values(),
               *(g.clients.driver for g in bridge.arm._graphiti.values())]
    assert len(drivers) == 5 and all(d.client is gate for d in drivers)
    # (2) the installed driver's own entry points
    tree = ast.parse(_inspect.getsource(FD))
    client_builds = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == "FalkorDB"]
    assert len(client_builds) == 1                                              # __init__, only when none is passed
    clone = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "clone")
    for call in (n for n in ast.walk(clone) if isinstance(n, ast.Call) and _call_name(n) == "FalkorDriver"):
        kw = {k.arg: ast.unparse(k.value) for k in call.keywords}
        assert kw.get("falkor_db") == "self.client", ast.unparse(call)
    # (3) every public method of the real client and graph classes, refused once poisoned
    calls: list[str] = []

    class Target:
        def __getattr__(self, name):
            def record(*a, **k):
                calls.append(name)
            return record
    for cls in (RealFalkorDB, AsyncGraph):
        names = [n for n, _ in _inspect.getmembers(cls, callable) if not n.startswith("_")]
        assert len(names) >= 5, (cls, names)
        shut = threading.Event()
        probe = A.TransportGate(Target(), shut)
        getattr(probe, names[0])()                                              # open: passes
        assert calls == [names[0]]
        calls.clear()
        shut.set()
        for name in names:
            with pytest.raises(A.TransportPoisoned):
                getattr(probe, name)()
        assert calls == [], calls


# -- WP02 review cycle 3 → cycle 4 (design correction): the gate at the SOCKET, the exit by FRAME,
#    ownership reserved BEFORE each write. The tests speak real RESP to an in-process server and count the
#    bytes and connections it receives: that is the physical layer the invariant is about.
# ---------------------------------------------------------------------------------------------------


class FakeRedisServer:
    """A RESP2 server on 127.0.0.1:<ephemeral> in its own thread and loop, counting what it RECEIVES:
    ``accepted`` connections and ``received`` bytes (per connection). It answers FalkorDB enough for
    graphiti: every GRAPH.QUERY/RO_QUERY gets a statistics-only reply; GRAPH.LIST lists the graphs
    queried; INFO says standalone. Control sets (graph names): ``hold`` delays the reply until
    ``release``; ``stale`` answers once with ``version mismatch`` (the client then refreshes its
    schema with three procedure calls); ``drop`` holds, then closes the socket without a reply."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.accepted = 0
        self.received: dict[int, int] = {}
        self.commands: list[tuple[int, list[str]]] = []
        self.hold: set[str] = set()
        self.stale: set[str] = set()
        self.drop: set[str] = set()
        self.graphs: set[str] = set()
        self.release = threading.Event()
        self._loop = asyncio.new_event_loop()
        ready = threading.Event()

        async def start():
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
            self.port = self._server.sockets[0].getsockname()[1]
            ready.set()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="fake-redis")
        self._thread.start()
        asyncio.run_coroutine_threadsafe(start(), self._loop)
        assert ready.wait(5)

    def totals(self) -> tuple[int, int]:
        with self.lock:
            return self.accepted, sum(self.received.values())

    def stop(self) -> None:
        self.release.set()
        self._loop.call_soon_threadsafe(self._server.close)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)

    async def _line(self, reader, cid):
        line = await reader.readline()
        with self.lock:
            self.received[cid] += len(line)
        return line

    async def _handle(self, reader, writer):
        with self.lock:
            self.accepted += 1
            cid = self.accepted
            self.received[cid] = 0
        try:
            while True:
                line = await self._line(reader, cid)
                if not line:
                    return
                if not line.startswith(b"*"):
                    args = line.decode().split()
                else:
                    args = []
                    for _ in range(int(line[1:])):
                        size = int((await self._line(reader, cid))[1:])
                        data = await reader.readexactly(size + 2)
                        with self.lock:
                            self.received[cid] += len(data)
                        args.append(data[:-2].decode("utf-8", "replace"))
                with self.lock:
                    self.commands.append((cid, args))
                cmd, key = args[0].upper(), (args[1] if len(args) > 1 else "")
                if key in self.hold or key in self.drop:
                    while not self.release.is_set():
                        await asyncio.sleep(0.01)
                if key in self.drop:
                    writer.close()
                    return
                writer.write(self._reply(cmd, key))
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            return

    def _reply(self, cmd: str, key: str) -> bytes:
        def bulk(s: str) -> bytes:
            b = s.encode()
            return b"$%d\r\n%s\r\n" % (len(b), b)
        if cmd in ("GRAPH.QUERY", "GRAPH.RO_QUERY"):
            self.graphs.add(key)
            if key in self.stale:
                self.stale.discard(key)
                return b"*2\r\n-version mismatch\r\n:7\r\n"
            return b"*1\r\n*1\r\n" + bulk("Query internal execution time: 0.100000 milliseconds")
        if cmd == "GRAPH.LIST":
            names = sorted(self.graphs)
            return b"*%d\r\n" % len(names) + b"".join(bulk(n) for n in names)
        if cmd == "INFO":
            return bulk("# Server\r\nredis_version:7.2.4\r\nredis_mode:standalone\r\n")
        if cmd == "PING":
            return b"+PONG\r\n"
        if cmd == "HELLO":                                                  # a RESP3 client: answer as RESP3 would
            return b"%1\r\n+proto\r\n:3\r\n"
        return b"+OK\r\n"


@pytest.fixture
def resp_server():
    server = FakeRedisServer()
    yield server
    server.stop()


def _gated_client(port):
    """The production client stack at the socket: ONE SocketGate, one pool minting GatedConnections that
    all hold it, and the FalkorDB client over that pool (what make_bridge builds)."""
    import redis.asyncio as redis_async
    from falkordb.asyncio import FalkorDB as RealFalkorDB

    gate = A.SocketGate()
    pool = redis_async.ConnectionPool(connection_class=A.GatedConnection, transport_gate=gate, host="127.0.0.1",
                                      port=port, decode_responses=True, protocol=2)
    return gate, pool, RealFalkorDB(connection_pool=pool)


def test_poison_during_one_connection_stops_every_connection_of_the_pool(resp_server):
    """Acceptance A.1/A.2: ≥ 2 REAL, DISTINCT connections of one pool. The poison is set THROUGH the first
    connection's own gate reference while it waits on a held reply; the OTHER connection, a command on the
    client, and a freshly minted connection then write ZERO bytes and open ZERO sockets — the poison is
    pool-scoped, shared by every connection the pool mints, and connect is gated too."""
    gate, pool, client = _gated_client(resp_server.port)
    resp_server.hold = {"slow"}

    async def scenario():
        c1 = await pool.get_connection()
        c2 = await pool.get_connection()
        assert c1 is not c2 and c1._transport_gate is c2._transport_gate is gate
        await c1.send_command("GRAPH.QUERY", "slow", "RETURN 1")          # in flight on the first connection
        await asyncio.sleep(0.05)
        c1._transport_gate.shut.set()                                       # poisoned via the first connection
        mark = resp_server.totals()
        for attempt in (lambda: c2.send_command("PING"), lambda: client.execute_command("PING"),
                        lambda: client.select_graph("g").query("RETURN 1"), lambda: pool.get_connection(),
                        lambda: c2.connect()):
            with pytest.raises(A.TransportPoisoned):
                await attempt()
        resp_server.release.set()
        await asyncio.sleep(0.1)
        assert resp_server.totals() == mark, (mark, resp_server.totals())
    asyncio.run(scenario())
    assert len(resp_server.received) >= 2


def test_a_schema_refresh_and_a_retry_after_poison_send_nothing(resp_server):
    """Review c3 finding A, reproduced at the socket: a query sent BEFORE the poison whose reply arrives
    AFTER it (``version mismatch``) makes the client refresh its schema with three procedure calls; a
    command whose connection DROPS after the poison makes redis-py retry, reconnecting. Neither sends a
    byte nor opens a socket. The control run shows the refresh does issue three calls when not poisoned."""
    _, _, client = _gated_client(resp_server.port)

    async def control():
        resp_server.stale = {"s0"}
        with contextlib.suppress(Exception):                               # the mismatch itself
            await client.select_graph("s0").query("RETURN 1")
    asyncio.run(control())
    refresh = [a for _, a in resp_server.commands if a[:2] == ["GRAPH.RO_QUERY", "s0"]]
    assert len(refresh) == 3, resp_server.commands[-6:]                    # DB.LABELS / RELATIONSHIPTYPES / PROPERTYKEYS

    gate2, _, client2 = _gated_client(resp_server.port)
    resp_server.stale, resp_server.hold, resp_server.drop = {"s1"}, {"s1"}, {"d1"}
    resp_server.release.clear()

    async def scenario():
        refresh_q = asyncio.ensure_future(client2.select_graph("s1").query("RETURN 1"))
        retry_q = asyncio.ensure_future(client2.execute_command("GRAPH.QUERY", "d1", "RETURN 1"))
        await asyncio.sleep(0.1)
        gate2.shut.set()
        mark = resp_server.totals()
        resp_server.release.set()
        for q in (refresh_q, retry_q):
            with pytest.raises(Exception):                                  # noqa: B017 — any failure; bytes are the proof
                await q
        await asyncio.sleep(0.1)
        return mark
    mark = asyncio.run(scenario())
    assert resp_server.totals() == mark, (mark, resp_server.totals())


def _poison_with_a_refusing_task(bridge, server, sent_after: list):
    """Poison ``bridge`` for real, the way Codex's c3 probe did. The work warms THREE pooled connections,
    then holds two of them on held replies (two distinct connections in flight), leaving one connected and
    idle. A detached task then blocks the loop thread SYNCHRONOUSLY until the server releases, so neither
    the cancellation nor the loop stop can land. When it resumes it holds the RAW client — everything
    beneath any object-level wrapper — and tries a command (which the idle connection would carry at
    once), a graph query and a listing."""
    raw = object.__getattribute__(bridge.arm.driver.client, "_target") \
        if isinstance(bridge.arm.driver.client, A.TransportGate) else bridge.arm.driver.client
    server.hold = {"slow1", "slow2"}

    def held_in_flight() -> int:
        with server.lock:
            return sum(1 for _, a in server.commands if len(a) > 1 and a[1] in ("slow1", "slow2"))

    async def refuses():
        while held_in_flight() < 2:                                         # refuses cancellation from the start,
            try:                                                            # so a slow machine cannot turn the
                await asyncio.sleep(0.01)                                   # poison into an acknowledged timeout
            except asyncio.CancelledError:
                continue
        server.release.wait(30)                                             # the loop thread is frozen here
        for attempt in (lambda: raw.execute_command("PING"), lambda: raw.select_graph("x").query("RETURN 1"),
                        lambda: raw.list_graphs()):
            try:
                await attempt()
                sent_after.append("sent")
            except BaseException as exc:                                    # noqa: BLE001 — recorded
                sent_after.append(type(exc).__name__)

    async def work():
        await asyncio.gather(*(raw.execute_command("PING") for _ in range(3)))
        asyncio.get_running_loop().create_task(refuses())
        await asyncio.gather(raw.select_graph("slow1").query("RETURN 1"), raw.select_graph("slow2").query("RETURN 1"))
    with pytest.raises(ERR.GCancellationUnacknowledged):
        bridge._submit(work, time.monotonic() + 0.3, None, "poison probe")


def test_a_poisoned_bridge_writes_no_byte_on_any_pooled_connection(tiny, resp_server, monkeypatch):
    """Acceptance A.2 through the bridge (make_bridge's own pool, the real client): two connections in
    flight, a poison, then abandoned work that holds the raw client tries three commands: ZERO bytes,
    ZERO new sockets."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.2)
    text, view = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    try:
        bridge.build_graph(QC1, view)
        before = len(resp_server.received)
        sent_after: list[str] = []
        _poison_with_a_refusing_task(bridge, resp_server, sent_after)
        assert len(resp_server.received) >= before and len(resp_server.received) >= 3   # sync probe + ≥ 2 async
        mark = resp_server.totals()
        resp_server.release.set()
        deadline = time.monotonic() + 5
        while len(sent_after) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.1)
        assert resp_server.totals() == mark, (mark, resp_server.totals(), sent_after)
        assert "sent" not in sent_after, sent_after
    finally:
        t0 = time.monotonic()
        assert bridge.close() is False                                      # poisoned: never a clean close
        assert time.monotonic() - t0 < 5                                    # bounded teardown after poison


def test_poisoning_one_bridge_leaves_another_in_the_same_process_working(tiny, resp_server, monkeypatch):
    """Acceptance A.3 (the permitted side, same process, same server). Bridge A is poisoned. Bridge B is then
    built and starts working — minting its own connections — and ONLY THEN, with B open and busy, A's
    abandoned work resumes: A sends ZERO bytes (a poison state shared through the class, last written by
    B's open gate, would let A through here), while B builds, answers, lists, drops, sends bytes and closes
    cleanly (a process-global poison would stop B)."""
    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.2)
    text, view = tiny
    a = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    a.build_graph(QC1, view)
    a_sent: list[str] = []
    _poison_with_a_refusing_task(a, resp_server, a_sent)
    resp_server.hold = set()
    b = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    try:
        before_b = resp_server.totals()
        stats = b.build_graph(QC1, view, deadline=time.monotonic() + 60)   # B mints its connections, gate open
        assert stats.nodes == 3 and resp_server.totals()[1] > before_b[1]
        mark = resp_server.totals()
        resp_server.release.set()                                           # A's abandoned work resumes NOW
        deadline = time.monotonic() + 5
        while len(a_sent) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.1)
        assert resp_server.totals() == mark and "sent" not in a_sent, (mark, resp_server.totals(), a_sent)
        assert b.answer(QC1, view, ctx_for(FakeFacade()))["text"] == "ans"
        assert "arms_C1" in b.list_graphs()
        b.drop_graph(QC1)
        assert resp_server.totals()[1] > mark[1]                            # B still sends
    finally:
        resp_server.release.set()
        assert b.close() is True                                            # normal teardown of a clean bridge
        t0 = time.monotonic()
        assert a.close() is False and time.monotonic() - t0 < 5


def _on_bridge_loop(bridge, coro_fn):
    return asyncio.run_coroutine_threadsafe(coro_fn(), bridge._loop).result(5)


def test_make_bridge_client_decodes_responses_to_str(tiny, resp_server):
    """The pool-arguments landmine (design lead, bus 100641/101357): with ``connection_pool=`` supplied,
    redis-py ignores the CLIENT's arguments silently, so FalkorDB's own ``decode_responses=True`` is inert
    and the POOL must carry it. Pinned by behaviour: a value round-tripped through make_bridge's client
    comes back as ``str``, not ``bytes``."""
    text, _ = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    try:
        raw = object.__getattribute__(bridge.arm.driver.client, "_target")
        resp_server.graphs = {"arms_Z9"}
        listed = _on_bridge_loop(bridge, lambda: raw.execute_command("GRAPH.LIST"))
        assert listed == ["arms_Z9"] and all(type(x) is str for x in listed), listed
        assert _on_bridge_loop(bridge, raw.list_graphs) == ["arms_Z9"]
    finally:
        bridge.close()


def test_make_bridge_client_speaks_resp2_as_negotiated(tiny, resp_server):
    """The protocol IN EFFECT, observed rather than requested: make_bridge's connections negotiate RESP2 —
    the server sees no ``HELLO`` from them (RESP3 would open with ``HELLO 3``) and the live connection's
    parser is the RESP2 parser — which is what FalkorDB(host, port) would have used and what its result
    parsing expects. redis-py's own default is RESP3, so an inert client-level ``protocol=2`` fails here."""
    text, _ = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    try:
        raw = object.__getattribute__(bridge.arm.driver.client, "_target")
        seen = len(resp_server.commands)

        async def probe():
            await raw.list_graphs()
            pool = raw.connection.connection_pool
            conn = await pool.get_connection()
            try:
                return type(conn._parser).__name__
            finally:
                await pool.release(conn)
        parser = _on_bridge_loop(bridge, probe)
        hellos = [a for _, a in resp_server.commands[seen:] if a and a[0].upper() == "HELLO"]
        assert hellos == [] and "RESP2" in parser, (hellos, parser)
    finally:
        bridge.close()


def test_make_bridge_connections_behave_like_falkordbs_own_client(tiny, resp_server, monkeypatch):
    """The pool-arguments landmine, closed as a DIFFERENTIAL: every scalar setting of a live connection from
    make_bridge's pool equals that of the connection FalkorDB(host, port)'s OWN client mints — the attribute
    list is derived from the connection object at test time, not written here. (Found this way: redis-py's
    pool defaults are a 5 s read and connect timeout and keepalive on; FalkorDB's client has none.)"""
    import falkordb.asyncio.falkordb as falkor_module

    text, _ = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    try:
        raw = object.__getattribute__(bridge.arm.driver.client, "_target")
        ours = raw.connection.connection_pool.make_connection()
        monkeypatch.setattr(falkor_module, "Is_Cluster", lambda conn: False)
        stock = falkor_module.FalkorDB(host="127.0.0.1", port=resp_server.port).connection.connection_pool.make_connection()
        names = set(getattr(stock, "__dict__", {})) | {n for k in type(stock).__mro__
                                                       for n in getattr(k, "__slots__", ()) if isinstance(n, str)}
        compared, differ = [], []
        for name in sorted(names):
            try:
                theirs, mine = getattr(stock, name), getattr(ours, name)
            except AttributeError:
                continue
            if isinstance(theirs, (int, float, str, bool, type(None))):
                compared.append(name)
                if theirs != mine:
                    differ.append((name, theirs, mine))
        assert differ == [] and {"socket_timeout", "socket_connect_timeout", "protocol"} <= set(compared), differ
        assert ours.encoder.decode_responses is stock.encoder.decode_responses is True
        assert type(ours.retry._backoff) is type(stock.retry._backoff) and ours.retry._retries == stock.retry._retries
    finally:
        bridge.close()


def test_a_reply_slower_than_redis_default_timeout_still_arrives(tiny, resp_server):
    """The timeout IN EFFECT, by behaviour: a reply held 6 s — longer than redis-py's 5 s pool default —
    still arrives through make_bridge's client (as through FalkorDB's own client, which sets no timeout).
    The bridge's deadline, not a socket timeout, bounds G's work."""
    text, _ = tiny
    bridge = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    try:
        raw = object.__getattribute__(bridge.arm.driver.client, "_target")
        resp_server.hold = {"slow6"}
        threading.Timer(6.0, resp_server.release.set).start()
        t0 = time.monotonic()
        result = asyncio.run_coroutine_threadsafe(raw.select_graph("slow6").query("RETURN 1"), bridge._loop).result(20)
        assert result is not None and time.monotonic() - t0 >= 5.9
    finally:
        resp_server.release.set()
        bridge.close()


#: The ungated footprint of FalkorDB's constructor, EXACTLY (design lead, bus 20260927T085156195841Zf6c8b07323):
#: ONE synchronous connection carrying its redis-py handshake and the Is_Cluster INFO. Measured with the
#: installed falkordb + redis-py 8.1.0. A library upgrade that changes it must fail here and be re-reviewed.
EXPECTED_SYNC_CONNECTIONS_AT_CONSTRUCTION = 1
EXPECTED_SYNC_COMMANDS_AT_CONSTRUCTION = (("CLIENT", "SETINFO", "LIB-NAME"), ("CLIENT", "SETINFO", "LIB-VER"),
                                          ("INFO", "server"))


def test_the_only_synchronous_redis_socket_is_the_constructors_probe(tiny, resp_server, monkeypatch):
    """The accepted residual (design lead, option a; recorded in the mission's contracts/), pinned so it
    cannot grow in EITHER direction. AT construction the synchronous footprint is EXACTLY the expected one
    connection and its three commands (handshake + Is_Cluster INFO) — nothing asynchronous is sent yet. AFTER
    construction, across build, answer, list, drop, a poison and close, NO synchronous redis connection is
    opened and no synchronous command is sent."""
    import redis.connection as sync_connection

    monkeypatch.setattr(ERR, "G_CANCEL_GRACE_S", 0.2)
    text, view = tiny
    counted: list[tuple[str, ...]] = []
    real_connect = sync_connection.AbstractConnection.connect
    real_send = sync_connection.AbstractConnection.send_packed_command

    def connect(self, *a, **k):
        counted.append(("connect",))
        return real_connect(self, *a, **k)

    def send(self, command, *a, **k):
        counted.append(("send",))
        return real_send(self, command, *a, **k)
    monkeypatch.setattr(sync_connection.AbstractConnection, "connect", connect)
    monkeypatch.setattr(sync_connection.AbstractConnection, "send_packed_command", send)
    seen_before = len(resp_server.commands)
    bridge = A.make_bridge(FakeEmbedder(), text, host="127.0.0.1", port=resp_server.port)
    at_construction = list(counted)
    server_side = [tuple(a[:len(e)]) for (_, a), e in zip(resp_server.commands[seen_before:],
                                                           EXPECTED_SYNC_COMMANDS_AT_CONSTRUCTION)]
    assert at_construction.count(("connect",)) == EXPECTED_SYNC_CONNECTIONS_AT_CONSTRUCTION, at_construction
    assert at_construction.count(("send",)) == len(EXPECTED_SYNC_COMMANDS_AT_CONSTRUCTION), at_construction
    assert len(resp_server.commands) - seen_before == len(EXPECTED_SYNC_COMMANDS_AT_CONSTRUCTION)
    assert tuple(server_side) == EXPECTED_SYNC_COMMANDS_AT_CONSTRUCTION, resp_server.commands[seen_before:]
    counted.clear()
    try:
        bridge.build_graph(QC1, view)
        bridge.answer(QC1, view, ctx_for(FakeFacade()))
        bridge.list_graphs()
        bridge.drop_graph(QC1)
        _poison_with_a_refusing_task(bridge, resp_server, [])
    finally:
        resp_server.release.set()
        bridge.close()
    assert counted == [], counted


# -- B by frame -------------------------------------------------------------------------------------


def test_a_caller_interrupt_during_the_wait_poisons_before_it_propagates(tiny, store, bridges, monkeypatch):
    """Review c3 finding B (Codex's probe): a KeyboardInterrupt raised on the caller's thread DURING the wait
    propagates as itself — and the bridge is poisoned with the gate shut, so the abandoned operation's
    later listing reaches nothing."""
    text, _ = tiny
    bridge = make_bridge(store, text, bridges)
    started, release, done = threading.Event(), threading.Event(), threading.Event()
    outcome: list[str] = []

    async def work():
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        try:
            await bridge.arm.list_graphs()
            outcome.append("sent")
        except BaseException as exc:                                        # noqa: BLE001 — recorded
            outcome.append(type(exc).__name__)
        done.set()
    real_wait = A.concurrent.futures.wait
    interrupt = KeyboardInterrupt("caller interrupted during wait")

    def interrupted(*a, **k):
        assert started.wait(2)
        raise interrupt
    monkeypatch.setattr(A.concurrent.futures, "wait", interrupted)
    with pytest.raises(KeyboardInterrupt) as info:
        bridge._submit(work, None, None, "interrupt probe")
    monkeypatch.setattr(A.concurrent.futures, "wait", real_wait)
    assert info.value is interrupt
    assert bridge._shut.is_set() and bridge._poisoned is not None
    n = len(store.queries)
    release.set()
    done.wait(2)
    assert len(store.queries) == n and "sent" not in outcome, (store.queries[n:], outcome)
    with pytest.raises(ERR.GCancellationUnacknowledged):
        bridge.list_graphs()


def test_an_exception_from_any_helper_on_the_exit_path_poisons(tiny, store, bridges, monkeypatch):
    """Review c3 minor (the AST test passed an added raising helper): whatever raises between submit and
    the verdict — here ``_wait`` itself — poisons the bridge; the exception propagates as itself."""
    text, view = tiny
    bridge = make_bridge(store, text, bridges)
    bridge.build_graph(QC1, view)
    boom = RuntimeError("a helper on the exit path raised")

    def raising(*a, **k):
        raise boom
    monkeypatch.setattr(bridge, "_wait", raising)
    with pytest.raises(RuntimeError) as info:
        bridge.answer(QC1, view, ctx_for(FakeFacade()))
    assert info.value is boom and bridge._shut.is_set() and bridge._poisoned is not None


def test_a_fatal_signal_raised_by_the_work_itself_propagates_and_poisons(tiny, store, bridges):
    """Codex c3 probe B_FATAL_ON_CANCEL: work that raises a non-Exception BaseException while being
    cancelled must not be turned into a retryable TimeoutError: the same object propagates, poisoned."""
    text, _ = tiny
    bridge = make_bridge(store, text, bridges)
    fatal = ERR.GCancellationUnacknowledged(10)

    async def fatal_work():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise fatal from None
    with pytest.raises(ERR.GCancellationUnacknowledged) as info:
        bridge._submit(fatal_work, time.monotonic() + 0.05, None, "fatal probe")
    assert info.value is fatal and bridge._shut.is_set() and bridge._poisoned is not None


# -- C reserved before each write ------------------------------------------------------------------


class FailingEmbedder(FakeEmbedder):
    """Fails the Nth embedding: a build that has already SAVED earlier nodes stops half-way."""

    def __init__(self, fail_at: int) -> None:
        self.calls, self.fail_at = 0, fail_at

    def embed(self, texts):
        self.calls += len(texts)
        if self.calls >= self.fail_at:
            raise RuntimeError("embedding failed mid-build")
        return super().embed(texts)


@pytest.mark.parametrize("report_group", ["arms_C1", "arms_A"], ids=["labelled-C1", "labelled-A"])
def test_a_partial_build_never_changes_how_a_later_report_is_classified(tiny, report_group):
    """Review c3 finding C, as a differential: A is built fully, or only PARTIALLY (the second embedding
    fails after the first node was saved), or partially and then dropped, or its FIRST save is sent and
    then lost (an uncertain outcome). C1's retrieval then reports A's
    FIRST node (the one that was written) — the classification is the same in every lifecycle, and it is a
    cross-group leak. Ownership is reserved before each write, including one whose outcome is uncertain."""
    text, view = tiny
    first = A.stable_uuid("arms_A", "node", TINY_ENTITIES[0]["id"])
    got = {}
    for lifecycle in ("full", "partial", "partial_and_drop", "save_uncertain"):
        store = FakeFalkorDB()
        arm = A.GraphArm(FalkorDriver(falkor_db=store), FakeEmbedder(), text)
        store.respond = _typed_pull_row(first, report_group)

        async def scenario(lifecycle=lifecycle, arm=arm, store=store):
            if lifecycle == "full":
                await arm.build_graph(QA, view)
            elif lifecycle == "save_uncertain":
                # the FIRST node's save reaches the server and then fails: its outcome is uncertain
                def sent_then_lost(db, cypher, params):
                    if db == "arms_A" and "MERGE" in cypher and "Entity" in cypher:
                        store.observe = lambda *a: None
                        raise ConnectionError("connection lost after the write was sent")
                store.observe = sent_then_lost
                with pytest.raises(ConnectionError):
                    await arm.build_graph(QA, view)
            else:
                arm.embedder = FailingEmbedder(fail_at=2)
                with pytest.raises(RuntimeError, match="mid-build"):
                    await arm.build_graph(QA, view)
                arm.embedder = FakeEmbedder()
                if lifecycle == "partial_and_drop":
                    await arm.drop_graph(QA)
            await arm.build_graph(QC1, view)
            await arm.plan_and_assemble(QC1, view)
        try:
            asyncio.run(scenario())
            got[lifecycle] = (None, None)
        except (ERR.PremiseViolated, ERR.ArmRefusal) as exc:
            got[lifecycle] = (type(exc), getattr(exc, "reason", None))
    assert len(set(got.values())) == 1 and got["full"] == (ERR.PremiseViolated, "cross_group_leak"), got


# -- live FR-016 (sandbox FalkorDB; ARMS849_LIVE=1) ---------------------------------------------------


@pytest.fixture
def falkor_endpoint():
    """A live FalkorDB: ``ARMS849_FALKOR_HOST``/``ARMS849_FALKOR_PORT`` name a throwaway sandbox
    (nothing else is started); otherwise the WP02 compose stack is brought up and down."""
    port = os.environ.get("ARMS849_FALKOR_PORT")
    if port:
        yield os.environ.get("ARMS849_FALKOR_HOST", "127.0.0.1"), int(port)
        return
    from scripts.research.arms849 import substrate as SUB

    SUB.up(yarn=False)
    try:
        yield "127.0.0.1", SUB.FALKOR_PORT
    finally:
        SUB.down()


@live
@needs_corpus
def test_live_hybrid_search_returns_an_item_the_question_names(live_http, falkor_endpoint):
    """FR-016 (REQUIRED by WP05's pre-merge checker). On a real FalkorDB, the hybrid step RETURNS at
    least one hit for question A, and among the hits is an entity the question names — resolved from
    the question text against the FROZEN CORPUS view (``resolve_anchors``), never from any answer key.
    Before the fix the hybrid search read an empty ``arms_A`` while the graph sat in ``default_db``."""
    from scripts.research.arms849.embed import Embedder

    host, port = falkor_endpoint
    driver = FalkorDriver(host=host, port=port)          # outside any loop: no index build on the root database
    selected = _record_databases(driver)

    async def scenario() -> None:
        arm = A.GraphArm(driver, Embedder(cache_dir=CACHE / "fastembed"), FrozenCorpusText(CORPUS))
        qa = Q.by_id("A")
        view = replay(CORPUS, Q.ask_time_dt(qa), verify=False)
        expected = set(A.resolve_anchors(qa.text, view).anchors)
        assert expected, "question A names no corpus entity; the expected item cannot be identified"
        try:
            await arm.build_graph(qa, view)
            hits = await arm.hybrid_search(qa.text, A.group_id_for(qa.id))
            assert len(hits) >= 1, "hybrid search returned nothing"
            found = {h.key for h in hits if h.kind == "node"} & expected
            assert found, (sorted(expected), [(h.kind, h.key) for h in hits[:10]])
            _, plan = await arm.plan_and_assemble(qa, view)
            assert next(s["count"] for s in plan.plan_steps if s["step"] == "hybrid_search") >= 1
        finally:
            await arm.drop_graph(qa)
            await driver.close()

    asyncio.run(scenario())
    # every query of the scenario, at the transport: only the question's database, never the root's
    assert selected and set(selected) == {"arms_A"}, collections.Counter(selected)


def _record_databases(driver) -> list[str]:
    """Record the database of EVERY query a FalkorDriver and all its clones send: they share one client, and
    each query selects its graph through ``client.select_graph`` (installed falkordb_driver ``_get_graph``)."""
    seen: list[str] = []
    real = driver.client.select_graph

    def select(name):
        seen.append(name)
        return real(name)
    driver.client.select_graph = select
    return seen


@live
@needs_corpus
def test_live_bridge_builds_retrieves_lists_drops_and_closes(live_http, falkor_endpoint):
    """The production path on a real FalkorDB: the bridge's loop thread, the real async client, and
    quiescence after every operation (no task the bridge started survives an operation), then a
    clean close. Serving is faked; the retrieval half and the graph listing are real."""
    from scripts.research.arms849.embed import Embedder

    host, port = falkor_endpoint
    qa = Q.by_id("A")
    view = replay(CORPUS, Q.ask_time_dt(qa), verify=False)
    bridge = A.make_bridge(Embedder(cache_dir=CACHE / "fastembed"), FrozenCorpusText(CORPUS), host=host, port=port)
    try:
        stats = bridge.build_graph(qa, view, deadline=time.monotonic() + 600)
        assert stats.group_id == "arms_A" and stats.nodes == len(view.entities) and pending(bridge) == []
        assert "arms_A" in bridge.list_graphs()
        facade = FakeFacade()
        row = bridge.answer(qa, view, ctx_for(facade, deadline=time.monotonic() + 600))
        hybrid = next(s["count"] for s in row["plan"]["plan_steps"] if s["step"] == "hybrid_search")
        assert hybrid >= 1 and row["plan"]["foreign_items"] == 0 and pending(bridge) == []
        assert facade.threads == [threading.current_thread().name]
        # a deadline that has already passed: acknowledged, and the bridge stays usable
        with pytest.raises(TimeoutError, match="acknowledged"):
            bridge.answer(qa, view, ctx_for(FakeFacade(), deadline=time.monotonic()))
        assert pending(bridge) == []
        again = bridge.answer(qa, view, ctx_for(FakeFacade(), deadline=time.monotonic() + 600))
        assert again["assembled_context_sha256"] == row["assembled_context_sha256"]
        bridge.drop_graph(qa, deadline=time.monotonic() + 600)
    finally:
        assert bridge.close() is True
