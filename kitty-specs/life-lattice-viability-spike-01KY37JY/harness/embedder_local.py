"""Local FastEmbed EmbedderClient for the Life Lattice spike.

On-box embeddings (no OpenAI, no data leaving office2 for the vector half). This is the
spike's answer to R-06a: Anthropic has no embeddings API, so the embedder is a separate,
local choice. BAAI/bge-small-en-v1.5 is 384-dim, small, downloads ~130MB on first use.
"""
from __future__ import annotations

from functools import lru_cache

from fastembed import TextEmbedding
from graphiti_core.embedder.client import EmbedderClient

MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Synchronous batch embed → list of float vectors."""
    return [v.tolist() for v in _model().embed(list(texts))]


class FastEmbedEmbedder(EmbedderClient):
    """Graphiti EmbedderClient backed by FastEmbed (local ONNX)."""

    async def create(self, input_data):
        if isinstance(input_data, str):
            texts = [input_data]
        elif isinstance(input_data, list) and (not input_data or isinstance(input_data[0], str)):
            texts = list(input_data) or [""]
        else:
            # token-id inputs are not supported by this local embedder; stringify defensively
            texts = [str(input_data)]
        return embed_texts(texts)[0]

    async def create_batch(self, input_data_list):
        return embed_texts(list(input_data_list))
