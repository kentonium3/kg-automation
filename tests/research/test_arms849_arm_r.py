"""WP07 T030 — arm R against the real frozen corpus, the cached embedder and the cached tokenizer."""

from __future__ import annotations

import ast
import json
import os
import pathlib
import shutil
import statistics
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

    def __init__(self, vec_for, model="stub-model"):
        self.vec_for = vec_for
        self.model = model

    def embed(self, texts):
        return [self.vec_for(t) for t in texts]

    def embed_one(self, text):
        return self.vec_for(text)


class CountingEmbedder:
    """Wraps an embedder and records every batch and every single embedding it is asked for."""

    def __init__(self, inner):
        self.inner, self.model, self.batches, self.singles = inner, inner.model, [], []

    def embed(self, texts):
        self.batches.append(len(texts))
        return self.inner.embed(texts)

    def embed_one(self, text):
        self.singles.append(text)
        return self.inner.embed_one(text)


def stub_index(view: Loaded, text: FrozenCorpusText, vec=None, model="stub-model") -> R.EventIndex:
    """An index over the view's real refs with stub vectors and a TRUE digest for (text, view, model)."""
    stub = StubEmbedder(vec or (lambda t: [1.0]), model)
    refs = tuple(str(e["ref"]) for e in view.events)
    return R.EventIndex(refs, [stub.embed_one(r) for r in refs], stub, R.EventIndex.digest_for(text, view, model))


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
    assert rebuilt.view_digest == c1_index.view_digest == R.EventIndex.digest_for(text, c1, embedder.model)


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
    index = R.EventIndex(refs, [[1.0, 0.0]] * 3, StubEmbedder(lambda t: [1.0, 0.0]), "digest-of-nothing")
    assert index.retrieve("q", 2) == ["e1", "e5"]                   # equal cosine → ref ascending
    assert index.retrieve("q", 0) == []
    with pytest.raises(ValueError):
        index.retrieve("q", -1)
    scored = R.EventIndex(refs, [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], StubEmbedder(lambda t: [0.0, 1.0]), "digest-of-nothing")
    assert scored.retrieve("q", 3) == ["e1", "e5", "e9"]            # by cosine desc


def test_ranking_is_computed_once_per_question_and_sliced_per_k():
    """N-1: calibration's k = 1..max_k sweep must not re-embed the question or re-sort per k."""
    refs = ("e9", "e1", "e5", "e7")
    counting = CountingEmbedder(StubEmbedder(lambda t: [1.0, 0.0] if t == "q" else [0.0, 1.0]))
    index = R.EventIndex(refs, [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5], [0.9, 0.1]], counting, "digest-of-nothing")
    top1, top3, top9 = index.retrieve("q", 1), index.retrieve("q", 3), index.retrieve("q", 9)
    assert counting.singles == ["q"], "one embedding of the question serves every k"
    assert top3[:1] == top1 and top9[:3] == top3 and len(top9) == 4
    assert top9 == ["e9", "e7", "e5", "e1"]
    assert index.retrieve("other", 2) == ["e1", "e5"] and counting.singles == ["q", "other"]
    assert index.retrieve("q", 2) == top3[:2] and counting.singles == ["q", "other"]
    assert index.retrieve("q", 0) == [] and counting.singles == ["q", "other"]


@needs_corpus
def test_index_for_another_view_and_links_are_refused(c1, text):
    other = narrowed("A")
    idx = stub_index(other, text)
    with pytest.raises(R.ArmRefusal, match="different view"):
        R.assemble(text, c1, idx, [], 0)
    raw = replay(CORPUS, Q.ask_time_dt(Q.by_id("B2")), verify=False)
    assert raw.links
    with pytest.raises(R.ArmRefusal, match="loader links"):
        R.EventIndex.build(raw, StubEmbedder(lambda t: [1.0]), text)
    with pytest.raises(R.ArmRefusal, match="no links attribute"):
        R._refuse_links(SimpleNamespace(events=[]))
    c1_idx = stub_index(c1, text)
    with pytest.raises(R.ArmRefusal, match="distinct"):
        R.assemble(text, c1, c1_idx, ["e05570", "e05570"], 2)


@needs_corpus
def test_a_truncated_or_padded_retrieved_list_is_refused(c1, text):
    """R-5: the retrieved list must be EXACTLY min(k, available) long — a truncated list is not a k-assembly."""
    idx = stub_index(c1, text)
    by_rank = idx.retrieve(Q.by_id("C1").text, 5)
    assert len(by_rank) == 5
    block, _ = R.assemble(text, c1, idx, by_rank, 5)
    assert len(block.event_refs) == 5
    with pytest.raises(R.ArmRefusal, match="exactly 5"):
        R.assemble(text, c1, idx, by_rank[:3], 5)
    with pytest.raises(R.ArmRefusal, match="exactly 5"):
        R.assemble(text, c1, idx, idx.retrieve(Q.by_id("C1").text, 6), 5)
    with pytest.raises(R.ArmRefusal, match="exactly 772"):
        R.assemble(text, c1, idx, by_rank, 800)                     # availability-capped k still needs all 772
    with pytest.raises(R.ArmRefusal, match="exactly 0"):
        R.assemble(text, c1, idx, by_rank[:1], 0)


@needs_corpus
def test_index_identity_is_the_frozen_bytes_and_the_model_not_the_refs(c1, text, tmp_path):
    """R-2: an index built over a corpus copy with the SAME refs but different frozen bytes is refused by
    assemble() and replaced by bind()/index_for(); another ask_time (another ref set) is rebuilt, not reused."""
    altered_dir = tmp_path / "altered-corpus"
    shutil.copytree(CORPUS, altered_dir)
    lines = (altered_dir / "stream.jsonl").read_bytes().split(b"\n")
    hits = 0
    for i, line in enumerate(lines):
        if line and json.loads(line)["ref"] == "e05570":              # in C1's view (at 2024-09-11)
            row = json.loads(line)
            row["text"] = row.get("text", "") + " [altered copy]"
            lines[i] = json.dumps(row, ensure_ascii=False).encode("utf-8")
            hits += 1
    assert hits == 1
    (altered_dir / "stream.jsonl").write_bytes(b"\n".join(lines))
    altered = FrozenCorpusText(altered_dir)
    assert altered.event_line("e05570") != text.event_line("e05570")

    stub = StubEmbedder(lambda t: [1.0])
    from_altered = R.EventIndex.build(c1, stub, altered)
    genuine = R.EventIndex.build(c1, stub, text)
    assert from_altered.refs == genuine.refs, "same refs, different bytes — refs alone cannot tell them apart"
    assert from_altered.view_digest != genuine.view_digest
    assert genuine.serves(text, c1) and not from_altered.serves(text, c1)
    with pytest.raises(R.ArmRefusal, match="different view"):
        R.assemble(text, c1, from_altered, [], 0)
    R.assemble(text, c1, genuine, [], 0)                              # the genuine one is accepted
    # the same bytes embedded by another model are another index too (the digest carries the model);
    # assemble() has no embedder to compare against — the cross-model check is index_for's, below
    other_model = stub_index(c1, text, model="another-model")
    assert other_model.refs == genuine.refs and other_model.view_digest != genuine.view_digest
    assert other_model.serves(text, c1) and other_model.model == "another-model"

    # index_for / bind: a cached index that does not serve the view is REPLACED under the same key
    cache = {"C1": from_altered}
    got = R.index_for("C1", c1, stub, text, cache)
    assert got is not from_altered and got is cache["C1"] and got.serves(text, c1) and set(cache) == {"C1"}
    assert R.index_for("C1", c1, stub, text, cache) is got            # and then reused, not rebuilt
    # a cached index built with another embedder model is replaced as well
    cache = {"C1": other_model}
    assert R.index_for("C1", c1, stub, text, cache) is not other_model and cache["C1"].model == stub.model
    # another ask_time is another ref set: rebuilt, not reused
    a_view = narrowed("A")
    cache = {"A": genuine}
    got_a = R.index_for("A", a_view, stub, text, cache)
    assert got_a is not genuine and got_a.refs != genuine.refs and got_a.serves(text, a_view)
    assert cache["A"] is got_a


@needs_corpus
def test_empty_view_sections_are_refused_like_arm_d(c1, text):
    """R-3: zero events, zero entities or zero edges is a configuration defect — the same refusal
    shape arm D's render_dump uses — at the index and at the assembly."""
    stub = StubEmbedder(lambda t: [1.0])
    eventless = Loaded(ask_time=c1.ask_time, entities=c1.entities, edges=c1.edges)
    recordless = Loaded(ask_time=c1.ask_time, events=c1.events, edges=c1.edges)
    edgeless = Loaded(ask_time=c1.ask_time, events=c1.events, entities=c1.entities)
    for view, noun in ((eventless, "events"), (recordless, "entities"), (edgeless, "edges")):
        with pytest.raises(R.ArmRefusal, match=rf"empty view: .*\b0 {noun}"):
            R.EventIndex.build(view, stub, text)
        idx = stub_index(view, text)                                # an index over whatever is there
        with pytest.raises(R.ArmRefusal, match=rf"empty view: .*\b0 {noun}"):
            R.assemble(text, view, idx, [], 0)
    with pytest.raises(R.ArmRefusal, match="empty view"):
        R.EventIndex.build(Loaded(ask_time=c1.ask_time), stub, text)


# ---------------------------------------------------------------------------
# the calibration adapter (T029): availability + assemble_r_tokens over the SAME index cache
# ---------------------------------------------------------------------------


class FakeLedger:
    """Only what calibrate() reads: run_rows() and terminal() — as tests/research/test_arms849_calibration.py."""

    def __init__(self, g_tokens: dict[str, int]) -> None:
        self._g = g_tokens

    def run_rows(self):
        return [{"arm": "G", "question": q, "repeat": 1, "outcome": "ok", "assembled_context_tokens": t}
                for q, t in self._g.items()]

    def terminal(self, key):
        if key.arm == "G" and key.repeat == 1:
            return "ok" if key.question in self._g else None
        return None


@pytest.fixture(scope="module")
def adapter(text, tok, embedder):
    """calibration_inputs over C1 and A with a counting embedder into a fresh cache, built ONCE."""
    counting = CountingEmbedder(embedder)
    views = {"C1": narrowed("C1"), "A": narrowed("A")}
    cache: dict[str, R.EventIndex] = {}
    availability, assemble_r_tokens = R.calibration_inputs(text, tok, counting, views, cache)
    return SimpleNamespace(counting=counting, views=views, cache=cache, availability=availability,
                           assemble_r_tokens=assemble_r_tokens)


@needs_corpus
@needs_cache
def test_calibration_inputs_are_calibrate_s_two_inputs_over_the_cache_the_cells_read(adapter, text, tok):
    """R-1: (availability: {qid: int}, assemble_r_tokens(qid, k) -> int); each index built ONCE into the
    cache bind() reads, so calibration and the R cells embed once and identically."""
    assert adapter.availability == {"C1": 772, "A": 2184}
    assert all(type(v) is int for v in adapter.availability.values())
    assert set(adapter.cache) == {"C1", "A"} and adapter.counting.batches == [772, 2184]
    c1_idx, a_idx = adapter.cache["C1"], adapter.cache["A"]
    assert c1_idx.serves(text, adapter.views["C1"]) and a_idx.serves(text, adapter.views["A"])
    # the callable is r_tokens_for over THAT index: exact, availability-capped, monotone
    before = list(adapter.counting.singles)
    n0, n1, n3 = (adapter.assemble_r_tokens("C1", k) for k in (0, 1, 3))
    assert n0 == R.r_tokens_for(Q.by_id("C1"), adapter.views["C1"], 0, tok, text, c1_idx)
    assert n3 == R.r_tokens_for(Q.by_id("C1"), adapter.views["C1"], 3, tok, text, c1_idx)
    assert n0 < n1 < n3 and type(n3) is int
    assert adapter.assemble_r_tokens("C1", 772) == adapter.assemble_r_tokens("C1", 800)
    assert adapter.assemble_r_tokens("A", 2) == R.r_tokens_for(Q.by_id("A"), adapter.views["A"], 2, tok, text, a_idx)
    assert adapter.counting.singles[len(before):] == [Q.by_id("C1").text, Q.by_id("A").text]   # one embedding per question
    with pytest.raises(R.ArmRefusal, match="no view in this adapter"):
        adapter.assemble_r_tokens("B2", 1)
    # the SAME index object serves the cell (identity): bind over the same cache neither rebuilds nor re-embeds
    arm = R.bind(text, adapter.cache)
    ctx = ctx_for(tok, adapter.counting, {"record": "calibration", "k": 3})
    row = arm(Q.by_id("C1"), adapter.views["C1"], ctx)
    assert adapter.cache["C1"] is c1_idx and adapter.counting.batches == [772, 2184]
    assert adapter.counting.singles[len(before):] == [Q.by_id("C1").text, Q.by_id("A").text]
    block, _ = R.assemble(text, adapter.views["C1"], c1_idx, c1_idx.retrieve(Q.by_id("C1").text, 3), 3)
    assert row["assembled_context_sha256"] == block.sha256 and row["assembled_context_tokens"] == n3
    # calling the adapter again over the same cache reuses every index (no second embedding)
    availability2, fn2 = R.calibration_inputs(text, tok, adapter.counting, adapter.views, adapter.cache)
    assert availability2 == adapter.availability and adapter.cache["C1"] is c1_idx and adapter.cache["A"] is a_idx
    assert adapter.counting.batches == [772, 2184] and fn2("C1", 3) == n3


@needs_corpus
@needs_cache
def test_the_real_calibrate_runs_over_the_adapter(adapter, text, tok):
    """R-1, end to end: calibrate(ledger, *calibration_inputs(...)) on the real corpus for two questions.
    The fake G medians are chosen from the adapter's own k=2 / k=3 counts so the smallest in-band k is 3."""
    C = pytest.importorskip("scripts.research.arms849.calibration",
                            reason="arms849.calibration (WP04) is not on this lane yet")
    qs = ["C1", "A"]
    r2 = statistics.median(adapter.assemble_r_tokens(q, 2) for q in qs)
    r3 = statistics.median(adapter.assemble_r_tokens(q, 3) for q in qs)
    g = int((r2 + r3) / 1.6)                                          # 0.8·g sits between r2 and r3
    cal = C.calibrate(FakeLedger({q: g for q in qs}), adapter.availability, adapter.assemble_r_tokens, qs)
    assert cal.k == 3 and cal.parity == "ok"
    assert cal.availability == adapter.availability == {"C1": 772, "A": 2184}
    for q in qs:
        assert cal.r_tokens_at_k[q] == adapter.assemble_r_tokens(q, 3) == R.r_tokens_for(
            Q.by_id(q), adapter.views[q], 3, tok, text, adapter.cache[q])
    assert cal.as_record() == C.calibrate(FakeLedger({q: g for q in qs}), adapter.availability,
                                          adapter.assemble_r_tokens, qs).as_record()


# ---------------------------------------------------------------------------
# the arm end to end (fake serving facade, real tokenizer)
# ---------------------------------------------------------------------------


class Facade:
    def __init__(self, tok, config):
        self.tok, self.config, self.sent, self.counted = tok, config, [], []
        self._serialize_with = config                      # what serialize() uses even when .config is unset

    def serialize(self, request, seed):
        return S.serialize(request, self._serialize_with, seed, self.tok)

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


def identity_for(tok) -> S.ServingIdentity:
    return S.ServingIdentity("gguf", "sha256:img", "emb", "tok", tok.chat_template_sha256())


def ctx_for(tok, embedder, calibration, config=None, limit=None, limit_applied=None, on_ctx=False):
    """A ctx over a Facade carrying the configuration (``ctx.serving.config``); ``on_ctx=True`` puts it on
    ``ctx.config`` (the contract name) and hands the facade out without one."""
    cfg = config or S.ServingConfiguration.primary(identity_for(tok))
    name, lim = cfg.limit_applied()
    facade = Facade(tok, cfg)
    if on_ctx:
        facade.config = None
    return SimpleNamespace(prompt=Prompt(), seed=1001, limit=lim if limit is None else limit,
                           limit_applied=name if limit_applied is None else limit_applied, serving=facade,
                           embedder=embedder, calibration=calibration, **({"config": cfg} if on_ctx else {}))


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
    # the contract's ctx.config path, with a facade that carries no configuration of its own
    row4 = R.arm_r(q, c1, ctx_for(tok, embedder, {"k": 12}, on_ctx=True), text, c1_index)
    assert row4["assembled_context_sha256"] == row["assembled_context_sha256"]


@needs_corpus
@needs_cache
def test_a_calibration_record_without_k_or_of_another_kind_is_refused(c1, c1_index, text, tok, embedder):
    """R-4 / Codex MINOR: a record with no k at all, or a dict that is not a calibration record, is a
    configuration defect (ArmRefusal, terminal) — never an AttributeError into the retry ladder."""
    q = Q.by_id("C1")
    for calibration, why in ((SimpleNamespace(), "no k at all"), ({}, "no k at all"),
                             ({"record": "calibration"}, "no k at all"),
                             ({"record": "run", "k": 3}, "not a calibration record"),
                             ({"record": "header", "k": 3}, "not a calibration record"),
                             (SimpleNamespace(k=True), "usable k"), ({"k": "3"}, "usable k"), ({"k": -1}, "usable k")):
        ctx = ctx_for(tok, embedder, calibration)
        with pytest.raises(R.ArmRefusal, match=why):
            R.arm_r(q, c1, ctx, text, c1_index)
        assert ctx.serving.counted == [] and ctx.serving.sent == [], calibration


@needs_corpus
@needs_cache
def test_incoherent_and_disagreeing_ctx_limits_are_refused_before_counting(c1, c1_index, text, tok, embedder):
    """R-6: arm D's _configuration / _check_limit shape — an incoherent pair, a well-formed pair that is not
    the configuration's, or a ctx with no configuration at all is refused before anything is counted."""
    q = Q.by_id("C1")
    cal = {"record": "calibration", "k": 3}
    for name, limit in (("configured", S.PRIMARY_N_CTX), ("trained", "262144"), ("trained", 0), ("banana", 1)):
        ctx = ctx_for(tok, embedder, cal, limit=limit, limit_applied=name)
        with pytest.raises(R.ArmRefusal, match="incoherent context limit"):
            R.arm_r(q, c1, ctx, text, c1_index)
        assert ctx.serving.counted == [] and ctx.serving.sent == [], (name, limit)
    primary = S.ServingConfiguration.primary(identity_for(tok))
    secondary = S.ServingConfiguration.secondary_yarn(identity_for(tok))
    permitted_secondary = secondary.limits().permitted
    probes = [(primary, "trained", 1), (primary, "trained", S.TRAINED_CONTEXT - 1), (primary, "trained", S.TRAINED_CONTEXT + 1),
              (primary, "permitted", permitted_secondary),           # the secondary's pair under the primary
              (primary, "permitted", primary.limits().permitted),   # the right value for the wrong ledger
              (secondary, "trained", S.TRAINED_CONTEXT),            # the primary's pair under the secondary
              (secondary, "permitted", permitted_secondary + 1)]
    for config, name, limit in probes:
        for on_ctx in (False, True):
            ctx = ctx_for(tok, embedder, cal, config=config, limit=limit, limit_applied=name, on_ctx=on_ctx)
            with pytest.raises(R.ArmRefusal, match="configuration") as info:
                R.arm_r(q, c1, ctx, text, c1_index)
            assert not isinstance(info.value, S.ContextExceeded)
            assert ctx.serving.counted == [] and ctx.serving.sent == [], (name, limit, on_ctx)
    # no configuration anywhere: neither ctx.config nor ctx.serving.config
    ctx = ctx_for(tok, embedder, cal)
    ctx.serving.config = None
    with pytest.raises(R.ArmRefusal, match="ServingConfiguration"):
        R.arm_r(q, c1, ctx, text, c1_index)
    assert ctx.serving.counted == [] and ctx.serving.sent == []
    # the secondary's own pair under the secondary is coherent and runs
    ctx = ctx_for(tok, embedder, cal, config=secondary)
    assert R.arm_r(q, c1, ctx, text, c1_index)["context_limit_applied"] == "permitted"


@needs_corpus
@needs_cache
def test_bind_caches_the_index_per_question_and_matches_a_rebuild(c1, text, tok, embedder):
    cache: dict[str, R.EventIndex] = {}
    arm = R.bind(text, cache)
    ctx = ctx_for(tok, embedder, SimpleNamespace(k=3))
    q = Q.by_id("C1")
    row = arm(q, c1, ctx)
    assert set(cache) == {"C1"}
    first = cache["C1"]
    again = arm(q, c1, ctx)
    assert again["assembled_context_sha256"] == row["assembled_context_sha256"] and cache["C1"] is first
    fresh_index = R.EventIndex.build(c1, embedder, text)
    block, _ = R.assemble(text, c1, fresh_index, fresh_index.retrieve(q.text, 3), 3)
    assert block.sha256 == row["assembled_context_sha256"]


# ---------------------------------------------------------------------------
# the context gate and the last line (contracts/arm-interface.md exception classes; arm D's shape)
# ---------------------------------------------------------------------------


@needs_corpus
@needs_cache
def test_the_gate_refusal_carries_the_plan_and_the_count_and_sends_nothing(c1, c1_index, text, tok, embedder):
    """The arm's own ContextExceeded (a serving.ContextExceeded subclass) carries prompt_tokens, the limit,
    its name and the plan, so the harness's exceeds_model_context row is complete and I4-truthful. No
    registered question exceeds the trained limit under R's small k on the real corpus, so the question
    text is padded (as arm D's window test does) until the exact request does."""
    q = Q.by_id("C1")
    padded = SimpleNamespace(id="C1", text=q.text + " x" * 262_144)
    ctx = ctx_for(tok, embedder, {"record": "calibration", "k": 3})
    with pytest.raises(R.ContextExceeded) as info:
        R.arm_r(padded, c1, ctx, text, c1_index)
    exc = info.value
    assert isinstance(exc, S.ContextExceeded) and ctx.serving.sent == [] and len(ctx.serving.counted) == 1
    block, plan = R.assemble(text, c1, c1_index, c1_index.retrieve(padded.text, 3), 3)
    counted = tok.count(ctx.serving.serialize(Prompt().render(block, padded.text), 1001)["prompt"])
    assert exc.prompt_tokens == counted > S.TRAINED_CONTEXT == exc.limit and exc.limit_applied == "trained"
    assert isinstance(exc.plan, R.PlanRecord) and exc.plan.prompt_tokens == counted
    assert exc.plan.k == 3 and exc.plan.retrieved_refs_by_rank == plan["retrieved_refs_by_rank"]
    assert exc.plan.assembled_context_sha256 == block.sha256 and exc.plan.assembled_context_tokens == tok.count(block.data)
    assert exc.plan.context_limit_applied == "trained"
    assert f"{counted} tokens" in str(exc) and "exceeds_model_context" in str(exc) and "not sent" in str(exc)


@needs_corpus
@needs_cache
def test_a_bare_last_line_refusal_from_complete_is_terminal_and_names_the_true_limit(c1, c1_index, text, tok, embedder):
    """serving.complete's own guard raises the BASE exception with only a message. The gate said the request
    fits the ledger's limit, so a refusal here is a configuration defect (ArmRefusal, terminal), never an
    exceeds_model_context row, and the message names the permitted limit read from the configuration —
    260,096, not an invented 'permitted limit 262144' (arm D, Codex c4)."""
    q = Q.by_id("C1")
    cal = {"record": "calibration", "k": 3}
    ctx = ctx_for(tok, embedder, cal)
    facade, config = ctx.serving, ctx.serving.config

    def refuse(body):
        facade.sent.append(body)
        raise S.ContextExceeded("prompt is N tokens; permitted limit M — not sent")

    facade.complete = refuse
    with pytest.raises(R.ArmRefusal) as info:
        R.arm_r(q, c1, ctx, text, c1_index)
    exc = info.value
    assert isinstance(exc.__cause__, S.ContextExceeded) and not isinstance(exc, S.ContextExceeded)
    permitted = config.limits().permitted
    assert permitted == S.PRIMARY_N_CTX - S.MAX_TOKENS == 260_096
    assert f"permitted limit {permitted}" in str(exc) and f"trained limit {S.TRAINED_CONTEXT}" in str(exc)
    assert "permitted limit 262144" not in str(exc)
    assert "exceeds_model_context" in str(exc) and str(tok.count(facade.sent[0]["prompt"])) in str(exc)
    assert len(facade.sent) == 1 and facade.counted == [id(facade.sent[0])]

    # The arm's OWN exception raised from inside complete propagates as the identical object.
    ctx2 = ctx_for(tok, embedder, cal)
    block, _ = R.assemble(text, c1, c1_index, c1_index.retrieve(q.text, 3), 3)
    own = R.ContextExceeded(1, 2, "trained", R.PlanRecord(3, [], "ask_time", 1, 1, False, 1, block.sha256, 1, "trained", 1))

    def raise_own(body):
        raise own

    ctx2.serving.complete = raise_own
    with pytest.raises(R.ContextExceeded) as info2:
        R.arm_r(q, c1, ctx2, text, c1_index)
    assert info2.value is own and info2.value.__cause__ is None


@needs_corpus
@needs_cache
def test_a_request_in_the_window_below_the_trained_limit_is_a_configuration_error(c1, c1_index, text, tok, embedder, monkeypatch):
    """With the REAL last line (serving.complete, which refuses before any network call): C1 at k = 3 plus
    a padded question counts inside the window (permitted 260,096 < count ≤ trained 262,144). The gate admits
    it under the primary; complete refuses it at the permitted limit. Not exceeds_model_context (I4 cannot
    hold) and the message names the true limit. The corpus + records under R's k cannot reach the window,
    so the question is padded, as arm D's test does."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    q = Q.by_id("C1")
    ctx = ctx_for(tok, embedder, {"record": "calibration", "k": 3})
    config = ctx.serving.config
    lim = config.limits()
    ctx.serving.complete = lambda body: S.complete(body, tok, lim.permitted)   # the real last line
    block, _ = R.assemble(text, c1, c1_index, c1_index.retrieve(q.text, 3), 3)
    base = tok.count(ctx.serving.serialize(Prompt().render(block, q.text), 1001)["prompt"])
    padded = SimpleNamespace(id="C1", text=q.text + " x" * (lim.permitted - base + 1_000))
    with pytest.raises(R.ArmRefusal) as info:
        R.arm_r(padded, c1, ctx, text, c1_index)
    block_p, _ = R.assemble(text, c1, c1_index, c1_index.retrieve(padded.text, 3), 3)
    counted = tok.count(ctx.serving.serialize(Prompt().render(block_p, padded.text), 1001)["prompt"])
    assert lim.permitted < counted <= lim.trained, f"the probe must land in the window: {counted}"
    exc = info.value
    assert isinstance(exc.__cause__, S.ContextExceeded) and not isinstance(exc, S.ContextExceeded)
    assert f"permitted limit {lim.permitted}" in str(exc) and f"{counted} tokens" in str(exc)
    assert "permitted limit 262144" not in str(exc) and "permitted limit 262144" not in str(exc.__cause__)
    assert f"permitted limit {lim.permitted}" in str(exc.__cause__)      # serving's own message agrees
    assert len(ctx.serving.counted) == 1                                 # the gate counted once
