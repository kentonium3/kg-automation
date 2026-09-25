"""Embedder, cosine reranker, tripwire (WP05 T021/T025)."""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import embed as E

CACHE = pathlib.Path(os.environ.get("ARMS849_CACHE", str(REPO_ROOT / "build" / "849-cache")))
needs_embedder = pytest.mark.skipif(not (CACHE / "fastembed").is_dir(), reason="FastEmbed cache absent (substrate setup)")


def test_tripwire_raises_and_counts_on_every_generation_path():
    t = E.TripwireLLMClient()
    with pytest.raises(E.LLMCallAttempted) as ei:
        asyncio.run(t.generate_response([]))
    assert ei.value.method == "generate_response" and t.llm_calls == 1
    with pytest.raises(E.LLMCallAttempted):
        asyncio.run(t._generate_response([]))
    assert t.llm_calls == 2 and all("messages" in c for c in t.calls)


def test_embedder_refuses_an_absent_cache(tmp_path):
    with pytest.raises(RuntimeError, match="never fetches"):
        E.Embedder(cache_dir=tmp_path / "absent")


def test_cosine_is_bounded_and_symmetric():
    assert E.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert E.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert E.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert E.cosine([1.0, 2.0], [2.0, 4.0]) == pytest.approx(E.cosine([2.0, 4.0], [1.0, 2.0]))


@needs_embedder
def test_embedder_is_deterministic_and_384_dim():
    emb = E.Embedder(cache_dir=CACHE / "fastembed")
    a, b = emb.embed_one("the quarterly report"), emb.embed_one("the quarterly report")
    assert a == b and len(a) == 384
    assert emb.embed([]) == []


@needs_embedder
def test_cosine_reranker_orders_by_similarity_and_is_deterministic():
    emb = E.Embedder(cache_dir=CACHE / "fastembed")
    rr = E.CosineReranker(emb)
    passages = ["invoice for the team plan", "5K race day pacing", "marathon training plan"]
    ranked = asyncio.run(rr.rank("running a 5K race", passages))
    assert next(p for p, _ in ranked) == "5K race day pacing"
    assert ranked == asyncio.run(rr.rank("running a 5K race", passages))
    assert all(ranked[i][1] >= ranked[i + 1][1] for i in range(len(ranked) - 1))
    assert asyncio.run(rr.rank("q", [])) == []


@needs_embedder
def test_graphiti_adapter_returns_vectors_for_str_and_batch():
    emb = E.Embedder(cache_dir=CACHE / "fastembed")
    ad = E.GraphitiEmbedder(emb)
    v = asyncio.run(ad.create("hello"))
    assert len(v) == 384 and v == emb.embed_one("hello")
    assert asyncio.run(ad.create_batch(["a", "b"])) == emb.embed(["a", "b"])
