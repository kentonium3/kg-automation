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

    async def scenario() -> None:
        driver = FalkorDriver(host=host, port=port)
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
        # nothing of these questions was ever written to the root driver's database
        rows, _, _ = await driver.execute_query("MATCH (n) WHERE n.group_id IN $gs RETURN count(n) AS c",
                                                gs=["arms_A", "arms_F1", "arms_B2"])
        assert rows[0]["c"] == 0, rows
        await arm.drop_graph(qa)
        rows, _, _ = await db_a.execute_query("MATCH (n {group_id: $g}) RETURN count(n) AS c", g="arms_A")
        assert rows[0]["c"] == 0
        await driver.close()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# WP02 (arms-preconditions-01M3FVRY): refusals, per-question database routing, the loop bridge
#
# The graph store below is a TRANSPORT-level fake: ``FalkorDriver(falkor_db=FakeFalkorDB())`` runs
# graphiti's real driver, node/edge saves, index build, search and decorator code, and the fake
# records the DATABASE every query was sent to. That is what FR-016 is about: which database a
# query reaches, not whether a step ran.
# ---------------------------------------------------------------------------

import collections
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


def make_bridge(store, text, bridges):
    b = A.make_bridge(FakeEmbedder(), text, driver=FalkorDriver(falkor_db=store))
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
        assert any("labels(n)" in c for c in qs) and any("MENTIONS" in c for c in qs)
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
    coro = bridge._guarded(make, ack)
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

    async def scenario() -> None:
        driver = FalkorDriver(host=host, port=port)
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
