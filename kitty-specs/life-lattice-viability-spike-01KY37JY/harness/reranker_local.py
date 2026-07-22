"""Local embedding-cosine reranker for the spike.

Graphiti defaults to OpenAIRerankerClient when cross_encoder is None; the BGE reranker needs
heavy sentence-transformers/torch. This reranks by cosine similarity of local FastEmbed
embeddings — no OpenAI, no torch. Reranking quality is not the Q2 crux (the reasoning is), but
this keeps retrieval fully local and honest.
"""
from __future__ import annotations

import math

from graphiti_core.cross_encoder.client import CrossEncoderClient

from embedder_local import embed_texts


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingReranker(CrossEncoderClient):
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []
        vecs = embed_texts([query] + list(passages))
        q, ps = vecs[0], vecs[1:]
        scored = [(p, _cosine(q, v)) for p, v in zip(passages, ps)]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored
