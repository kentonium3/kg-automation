"""WP07 T030 — arm R against the real frozen corpus, the cached embedder and the cached tokenizer."""

from __future__ import annotations

import ast
import os
import pathlib
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import arm_r as R
from scripts.research.arms849 import questions as Q
from scripts.research.arms849 import serving as S
from scripts.research.arms849.embed import Embedder
from scripts.research.arms849.prompt import Prompt
from scripts.research.arms849.text import FrozenCorpusText, edge_key, entity_key
from scripts.research.load_849_corpus import DEFAULT_CORPUS, Loaded, replay

PKG = REPO_ROOT / "scripts" / "research" / "arms849"
CORPUS = pathlib.Path(os.environ.get("ARMS849_CORPUS", str(DEFAULT_CORPUS)))
CACHE = pathlib.Path(os.environ.get("ARMS849_CACHE", str(REPO_ROOT / "build" / "849-cache")))
needs_corpus = pytest.mark.skipif(not (CORPUS / "stream.jsonl").exists(), reason="rendered corpus absent")
needs_cache = pytest.mark.skipif(not (CACHE / "fastembed").is_dir() or not (CACHE / "qwen-tokenizer").exists(),
                                 reason="embedder / tokenizer cache absent")
SOURCE = (PKG / "arm_r.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# static rules
# ---------------------------------------------------------------------------


def test_no_second_embedder_definition_and_no_default_k():
    tree = ast.parse(SOURCE)
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert "Embedder" not in classes and "TextEmbedding" not in SOURCE
    assert "from scripts.research.arms849.embed import Embedder" in SOURCE
    # k is never defaulted: no function parameter named k carries a default, no `k = <int>` assignment
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = n.args.args + n.args.kwonlyargs
            named = [a.arg for a in params][-len(n.args.defaults):] if n.args.defaults else []
            assert "k" not in named, f"{n.name} defaults k"
            assert not any(a.arg == "k" and d is not None for a, d in zip(n.args.kwonlyargs, n.args.kw_defaults, strict=True))
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "k" for t in n.targets):
            assert not isinstance(n.value, ast.Constant), "a literal default k is a defect"
    for word in ("or" + "acle", "se" + "ed/", "trace" + "ability"):
        assert word not in SOURCE.lower()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def text() -> FrozenCorpusText:
    return FrozenCorpusText(CORPUS)


@pytest.fixture(scope="module")
def embedder() -> Embedder:
    return Embedder(CACHE / "fastembed")


@pytest.fixture(scope="module")
def tok() -> S.Tokenizer:
    return S.Tokenizer(CACHE / "qwen-tokenizer")


def narrowed(qid: str) -> Loaded:
    view = replay(CORPUS, Q.ask_time_dt(Q.by_id(qid)), verify=False)
    view.links = []
    return view


@pytest.fixture(scope="module")
def c1() -> Loaded:
    return narrowed("C1")


@pytest.fixture(scope="module")
def c1_index(c1, embedder, text) -> R.EventIndex:
    return R.EventIndex.build(c1, embedder, text)


class StubEmbedder:
    """Deterministic stand-in for tie-break and ordering tests; never used for a measurement."""

    def __init__(self, vec_for):
        self.vec_for = vec_for

    def embed(self, texts):
        return [self.vec_for(t) for t in texts]

    def embed_one(self, text):
        return self.vec_for(text)


# ---------------------------------------------------------------------------
# index, retrieval, assembly
# ---------------------------------------------------------------------------


@needs_corpus
def test_availability_cap_is_the_view_event_count(c1):
    assert R.availability_cap(c1) == 772 == len(c1.events)


@needs_corpus
@needs_cache
def test_same_view_same_k_twice_is_byte_identical_and_cache_or_rebuild_agree(c1, c1_index, embedder, text):
    q = Q.by_id("C1")
    a, plan_a = R.assemble(text, c1, c1_index, c1_index.retrieve(q.text, 12), 12)
    rebuilt = R.EventIndex.build(c1, embedder, text)
    b, plan_b = R.assemble(text, c1, rebuilt, rebuilt.retrieve(q.text, 12), 12)
    assert a.data == b.data and a.sha256 == b.sha256 == plan_a["assembled_context_sha256"] == plan_b["assembled_context_sha256"]
    assert plan_a["retrieved_refs_by_rank"] == plan_b["retrieved_refs_by_rank"]
    assert rebuilt.vectors == c1_index.vectors                       # deterministic embedder


@needs_corpus
@needs_cache
def test_retrieved_refs_are_resorted_into_view_order_while_rank_order_is_recorded(c1, c1_index, text):
    q = Q.by_id("C1")
    by_rank = c1_index.retrieve(q.text, 20)
    assert len(by_rank) == 20 and len(set(by_rank)) == 20
    block, plan = R.assemble(text, c1, c1_index, by_rank, 20)
    assert plan["retrieved_refs_by_rank"] == by_rank
    assert list(block.event_refs) == sorted(by_rank, key=c1_index.position)
    assert list(block.event_refs) != by_rank, "rank order and ask-time order differ for this question"
    assert plan["assembled_order"] == "ask_time" and plan["k"] == 20 and plan["availability_capped"] is False
    positions = [c1_index.position(r) for r in block.event_refs]
    assert positions == sorted(positions)
    # R's events are a subsequence of D's dump (the whole view in view order)
    full = [str(e["ref"]) for e in c1.events]
    it = iter(full)
    assert all(any(r == x for x in it) for r in block.event_refs)


@needs_corpus
@needs_cache
def test_records_section_is_byte_identical_to_d_s(c1, c1_index, text):
    """The structured half R inserts is the SAME bytes D inserts for that question — what makes the
    R:G ratio meaningful (WP07 reviewer guidance)."""
    q = Q.by_id("C1")
    block, plan = R.assemble(text, c1, c1_index, c1_index.retrieve(q.text, 5), 5)
    d_full = text.render_full_view(c1).data
    d_events = text.render_block((str(e["ref"]) for e in c1.events), ()).data
    d_records = d_full[len(d_events):]
    r_events = text.render_block(block.event_refs, ()).data
    assert block.data[len(r_events):] == d_records
    assert plan["entities_in_records"] == len(c1.entities) and plan["edges_in_records"] == len(c1.edges)
    assert R.records_keys(c1) == tuple(entity_key(e) for e in c1.entities) + tuple(edge_key(e) for e in c1.edges)


@needs_corpus
@needs_cache
def test_availability_capped_on_c1_when_k_exceeds_the_events(c1, c1_index, text):
    q = Q.by_id("C1")
    by_rank = c1_index.retrieve(q.text, 800)
    assert len(by_rank) == 772
    block, plan = R.assemble(text, c1, c1_index, by_rank, 800)
    assert plan["availability_capped"] is True and plan["events_available"] == 772
    assert set(block.event_refs) == {str(e["ref"]) for e in c1.events}
    assert list(block.event_refs) == [str(e["ref"]) for e in c1.events]     # ask-time order = the full run
    _, plan0 = R.assemble(text, c1, c1_index, c1_index.retrieve(q.text, 772), 772)
    assert plan0["availability_capped"] is False


@needs_corpus
@needs_cache
def test_r_tokens_for_is_exact_and_monotone_in_k(c1, c1_index, text, tok):
    q = Q.by_id("C1")
    prev = -1
    for k in (0, 1, 2, 4, 8, 16, 64, 256, 772, 900):
        n = R.r_tokens_for(q, c1, k, tok, text, c1_index)
        block, _ = R.assemble(text, c1, c1_index, c1_index.retrieve(q.text, k), k)
        assert n == tok.count(block.data), k                        # exact: the bytes the assembly inserts
        assert n >= prev, (k, n, prev)
        prev = n
    assert R.r_tokens_for(q, c1, 0, tok, text, c1_index) == tok.count(text.render_block((), R.records_keys(c1)).data)
    assert R.r_tokens_for(q, c1, 772, tok, text, c1_index) == R.r_tokens_for(q, c1, 900, tok, text, c1_index)


def test_ties_break_by_ref_ascending_and_k_zero_retrieves_nothing():
    refs = ("e9", "e1", "e5")
    index = R.EventIndex(refs, [[1.0, 0.0]] * 3, StubEmbedder(lambda t: [1.0, 0.0]))
    assert index.retrieve("q", 2) == ["e1", "e5"]                   # equal cosine → ref ascending
    assert index.retrieve("q", 0) == []
    with pytest.raises(ValueError):
        index.retrieve("q", -1)
    scored = R.EventIndex(refs, [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], StubEmbedder(lambda t: [0.0, 1.0]))
    assert scored.retrieve("q", 3) == ["e1", "e5", "e9"]            # by cosine desc


@needs_corpus
def test_index_for_another_view_and_links_are_refused(c1, text):
    other = narrowed("A")
    idx = R.EventIndex(tuple(str(e["ref"]) for e in other.events), [[1.0]] * len(other.events), StubEmbedder(lambda t: [1.0]))
    with pytest.raises(R.ArmRefusal, match="different view"):
        R.assemble(text, c1, idx, [], 0)
    raw = replay(CORPUS, Q.ask_time_dt(Q.by_id("B2")), verify=False)
    assert raw.links
    with pytest.raises(R.ArmRefusal, match="loader links"):
        R.EventIndex.build(raw, StubEmbedder(lambda t: [1.0]), text)
    with pytest.raises(R.ArmRefusal, match="no links attribute"):
        R._refuse_links(SimpleNamespace(events=[]))
    c1_idx = R.EventIndex(tuple(str(e["ref"]) for e in c1.events), [[1.0]] * len(c1.events), StubEmbedder(lambda t: [1.0]))
    with pytest.raises(R.ArmRefusal, match="distinct"):
        R.assemble(text, c1, c1_idx, ["e05570", "e05570"], 2)


# ---------------------------------------------------------------------------
# the arm end to end (fake serving facade, real tokenizer)
# ---------------------------------------------------------------------------


class Facade:
    def __init__(self, tok, config):
        self.tok, self.config, self.sent, self.counted = tok, config, [], []

    def serialize(self, request, seed):
        return S.serialize(request, self.config, seed, self.tok)

    def count_tokens(self, body):
        self.counted.append(id(body))
        return self.tok.count(body["prompt"])

    def count_text(self, data):
        return self.tok.count(data)

    def complete(self, body):
        self.sent.append(body)
        client = self.tok.count(body["prompt"])
        return S.map_timings({"content": "ans", "stop_type": "eos",
                              "timings": {"prompt_n": client, "cache_n": 0, "prompt_ms": 100.0,
                                          "predicted_n": 10, "predicted_ms": 500.0}}, client)


def ctx_for(tok, embedder, calibration):
    cfg = S.ServingConfiguration.primary(S.ServingIdentity("gguf", "sha256:img", "emb", "tok", tok.chat_template_sha256()))
    name, limit = cfg.limit_applied()
    return SimpleNamespace(prompt=Prompt(), seed=1001, limit=limit, limit_applied=name, serving=Facade(tok, cfg),
                           embedder=embedder, calibration=calibration)


@needs_corpus
@needs_cache
def test_arm_r_refuses_without_a_calibration_record_and_runs_with_one(c1, c1_index, text, tok, embedder):
    q = Q.by_id("C1")
    with pytest.raises(R.ArmRefusal, match="calibration record"):
        R.arm_r(q, c1, ctx_for(tok, embedder, None), text, c1_index)
    with pytest.raises(R.ArmRefusal, match="usable k"):
        R.arm_r(q, c1, ctx_for(tok, embedder, SimpleNamespace(k=None)), text, c1_index)
    ctx = ctx_for(tok, embedder, SimpleNamespace(k=12))
    row = R.arm_r(q, c1, ctx, text, c1_index)
    assert ctx.serving.counted == [id(ctx.serving.sent[0])]
    block, plan = R.assemble(text, c1, c1_index, c1_index.retrieve(q.text, 12), 12)
    assert row["assembled_context_sha256"] == block.sha256 and row["plan"]["k"] == 12
    assert row["assembled_context_tokens"] == tok.count(block.data) < row["prompt_tokens"]
    assert row["plan"]["retrieved_refs_by_rank"] == plan["retrieved_refs_by_rank"]
    assert "r_g_ratio" not in row                                   # the harness's field (arm-interface)
    assert row["context_limit_applied"] == "trained" and row["cache_state"] == "cold"
    # the same cell again (a repeat) assembles byte-identical context — NFR-005
    row2 = R.arm_r(q, c1, ctx, text, c1_index)
    assert row2["assembled_context_sha256"] == row["assembled_context_sha256"]
    # dict-shaped calibration (the ledger record) works too
    row3 = R.arm_r(q, c1, ctx_for(tok, embedder, {"record": "calibration", "k": 12}), text, c1_index)
    assert row3["assembled_context_sha256"] == row["assembled_context_sha256"]


@needs_corpus
@needs_cache
def test_bind_caches_the_index_per_question_and_matches_a_rebuild(c1, text, tok, embedder):
    cache: dict[str, R.EventIndex] = {}
    arm = R.bind(text, cache)
    ctx = ctx_for(tok, embedder, SimpleNamespace(k=3))
    q = Q.by_id("C1")
    row = arm(q, c1, ctx)
    assert set(cache) == {"C1"}
    again = arm(q, c1, ctx)
    assert again["assembled_context_sha256"] == row["assembled_context_sha256"]
    fresh_index = R.EventIndex.build(c1, embedder, text)
    block, _ = R.assemble(text, c1, fresh_index, fresh_index.retrieve(q.text, 3), 3)
    assert block.sha256 == row["assembled_context_sha256"]
