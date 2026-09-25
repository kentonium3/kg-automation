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
    mk = lambda kind, key, score, origin, u=None: A.Item(kind, key, u or f"{kind}:{key}", score, origin)
    pulls = [[mk("node", ents[0], 0.9, "pull:Capacity")], [mk("node", ents[1], 0.5, "pull:Commitment"), mk("node", ents[2], 0.7, "pull:Commitment")], [], []]
    hits = [mk("episode", r, 1.0 - i / 200, "search") for i, r in enumerate(refs[:70])] + [mk("node", ents[0], 0.99, "search")]  # duplicate uuid
    expansions = [[mk("episode", refs[80], 1.0, "expand:X")]]
    block, chosen = A.assemble(text, view, pulls, hits, expansions, cap=60)
    assert len(chosen) == 60 and len({c.uuid for c in chosen}) == 60
    assert [c.key for c in chosen[:3]] == [ents[0], ents[2], ents[1]]           # label order, then score desc
    assert not any(c.origin.startswith("expand") for c in chosen)             # the cap was reached before expansions
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
def test_live_build_search_assemble_and_replay_rule(live_http):
    """One event loop for the whole scenario: the FalkorDB async client binds to the loop it
    first runs on (an asyncio.run per step fails with "Event loop is closed")."""
    from graphiti_core.driver.falkordb_driver import FalkorDriver

    from scripts.research.arms849 import substrate as SUB
    from scripts.research.arms849.embed import Embedder

    async def scenario() -> None:
        driver = FalkorDriver(host="127.0.0.1", port=SUB.FALKOR_PORT)
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
        assert p1.plan_steps[0]["step"] == "typed_pull:Capacity" and any(s["step"] == "hybrid_search" for s in p1.plan_steps)
        assert p1.items_assembled > 0 and all(k in ("node", "edge", "episode") for k in p1.items_by_kind)
        # the replay rule made visible: DEC_F_RESTART absent for F1, present for B2
        qf1 = next(q for q in Q.QUESTIONS if q.id == "F1"); qb2 = next(q for q in Q.QUESTIONS if q.id == "B2")
        for q, present in ((qf1, False), (qb2, True)):
            v = replay(CORPUS, datetime.fromisoformat(q.ask_time), verify=False)
            await arm.build_graph(q, v)
            rows, _, _ = await driver.execute_query("MATCH (n:Entity {name: $n, group_id: $g}) RETURN count(n) AS c", n="DEC_F_RESTART", g=A.group_id_for(q.id))
            assert (rows[0]["c"] > 0) is present, (q.id, rows)
            await arm.drop_graph(q)
        await arm.drop_graph(qa)
        rows, _, _ = await driver.execute_query("MATCH (n {group_id: $g}) RETURN count(n) AS c", g="arms_A")
        assert rows[0]["c"] == 0
        await driver.close()

    SUB.up(yarn=False)
    try:
        asyncio.run(scenario())
    finally:
        SUB.down()
