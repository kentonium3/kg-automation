"""One embedder, one reranker, one tripwire (WP05 T021) — shared by arms G and R.

- :class:`Embedder` wraps FastEmbed ``BAAI/bge-small-en-v1.5`` from the local cache
  (``HF_HUB_OFFLINE=1``; refuses if the cache is absent — the run never fetches).
  Deterministic: the same text yields the same vector.
- :class:`GraphitiEmbedder` adapts it to graphiti-core's ``EmbedderClient``
  (``create`` / ``create_batch``).
- :class:`CosineReranker` fills Graphiti's ``CrossEncoderClient`` slot with the
  #974 cosine reranker: passages ranked by cosine similarity of their embedding
  to the query embedding. No learned cross-encoder, no external call.
- :class:`TripwireLLMClient` implements Graphiti's ``LLMClient`` and RAISES on
  every call, counting attempts; the arm records the count as ``llm_calls`` and
  a non-zero count fails the cell (D-2).

Recorded in the serving configuration as ``embedder`` and ``reranker`` (D-3).
"""

from __future__ import annotations

import math
import os
import pathlib
from collections.abc import Iterable, Sequence
from typing import Any

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient

__all__ = ["EMBEDDER_MODEL", "CosineReranker", "Embedder", "GraphitiEmbedder", "LLMCallAttempted",
           "TripwireLLMClient", "cosine"]

EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"


def _cache_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("ARMS849_CACHE", "build/849-cache"))


class Embedder:
    """FastEmbed from the local cache only; deterministic."""

    def __init__(self, cache_dir: pathlib.Path | None = None, model: str = EMBEDDER_MODEL) -> None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        self.cache_dir = pathlib.Path(cache_dir) if cache_dir else _cache_dir() / "fastembed"
        if not self.cache_dir.is_dir():
            raise RuntimeError(f"embedder cache absent at {self.cache_dir}; run substrate setup — the run never fetches")
        from fastembed import TextEmbedding

        self.model = model
        self._model = TextEmbedding(model, cache_dir=str(self.cache_dir))
        self.dimension = 384

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[float(x) for x in vec] for vec in self._model.embed(list(texts), batch_size=64)]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class GraphitiEmbedder(EmbedderClient):
    """graphiti-core's embedder interface over :class:`Embedder`."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder

    async def create(self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]) -> list[float]:
        if isinstance(input_data, str):
            return self.embedder.embed_one(input_data)
        items = list(input_data)  # type: ignore[arg-type]
        if items and isinstance(items[0], str):
            return self.embedder.embed_one(str(items[0]))
        raise TypeError("token-id inputs are not supported by the local embedder")

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return self.embedder.embed(input_data_list)


class CosineReranker(CrossEncoderClient):
    """#974's reranker: cosine similarity between the query and each passage embedding."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []
        q = self.embedder.embed_one(query)
        vecs = self.embedder.embed(passages)
        scored = [(p, cosine(q, v)) for p, v in zip(passages, vecs, strict=True)]
        # Deterministic: score desc, then the passage text asc.
        return sorted(scored, key=lambda t: (-t[1], t[0]))


class LLMCallAttempted(RuntimeError):
    """Graphiti tried to call an LLM. D-2: the arm never extracts; this is a failed cell."""

    def __init__(self, method: str, summary: str) -> None:
        self.method = method
        self.summary = summary
        super().__init__(f"TRIPWIRE: Graphiti attempted an LLM call via {method}: {summary}")


class TripwireLLMClient(LLMClient):
    """Every generation path raises and is counted; nothing is ever answered."""

    def __init__(self) -> None:
        super().__init__(config=None, cache=False)
        self.calls: list[str] = []

    @property
    def llm_calls(self) -> int:
        return len(self.calls)

    def _trip(self, method: str, messages: Any, response_model: Any) -> None:
        summary = f"{len(messages) if messages is not None else 0} messages, model={getattr(response_model, '__name__', response_model)}"
        self.calls.append(f"{method}: {summary}")
        raise LLMCallAttempted(method, summary)

    async def _generate_response(self, messages, response_model=None, max_tokens=16384, model_size=None):  # type: ignore[override]
        self._trip("_generate_response", messages, response_model)

    async def generate_response(self, messages, response_model=None, max_tokens=None, model_size=None,  # type: ignore[override]
                                group_id=None, prompt_name=None, *, attribute_extraction=False):
        self._trip("generate_response", messages, response_model)
