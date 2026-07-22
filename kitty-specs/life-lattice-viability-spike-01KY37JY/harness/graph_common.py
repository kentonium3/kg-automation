"""Factory for the spike's Graphiti instance.

FalkorDB (containerized, loopback:16379) + Claude LLM (entity extraction) + local FastEmbed
embedder + local cosine reranker. No OpenAI anywhere in the path.
"""
from __future__ import annotations

import os

from anthropic import NOT_GIVEN
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.anthropic_client import AnthropicClient
from graphiti_core.llm_client.config import LLMConfig

from embedder_local import FastEmbedEmbedder
from reranker_local import EmbeddingReranker

FALKOR_HOST = os.environ.get("FALKOR_HOST", "127.0.0.1")
FALKOR_PORT = int(os.environ.get("FALKOR_PORT", "16379"))

# Claude models (verified 200 on this key). Extraction uses sonnet; small ops use haiku.
EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", "claude-sonnet-5")
SMALL_MODEL = os.environ.get("SMALL_MODEL", "claude-haiku-4-5-20251001")


def build_graphiti() -> Graphiti:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY not set (source ~/.config/felix/anthropic-spike.env)")
    driver = FalkorDriver(host=FALKOR_HOST, port=FALKOR_PORT)
    llm = AnthropicClient(
        config=LLMConfig(
            api_key=key,
            model=EXTRACT_MODEL,
            small_model=SMALL_MODEL,
        )
    )
    # Newest Claude models deprecate `temperature`; graphiti passes it unconditionally, so set the
    # SDK NOT_GIVEN sentinel to omit it from requests. (Incidental spike finding.)
    llm.temperature = NOT_GIVEN
    return Graphiti(
        graph_driver=driver,
        llm_client=llm,
        embedder=FastEmbedEmbedder(),
        cross_encoder=EmbeddingReranker(),
    )
