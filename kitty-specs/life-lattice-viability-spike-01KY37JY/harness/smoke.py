"""Connectivity smoke test: build Graphiti (FalkorDB + Claude + local embedder/reranker),
ingest two episodes (LLM extraction), and run a hybrid search. Validates the whole stack
before the real loader/A-B."""
import asyncio
from datetime import datetime, timezone

from graphiti_core.nodes import EpisodeType

from graph_common import build_graphiti


async def main():
    g = build_graphiti()
    print("building indices/constraints ...")
    await g.build_indices_and_constraints()
    now = datetime.now(timezone.utc)
    print("ingesting episode 1 (LLM extraction) ...")
    await g.add_episode(
        name="e1",
        episode_body="Kent runs a consulting practice named Intentional LLC to keep his client pipeline full.",
        source_description="smoke",
        reference_time=now,
        source=EpisodeType.text,
    )
    print("ingesting episode 2 ...")
    await g.add_episode(
        name="e2",
        episode_body="The PointerHealth Q3 deliverable is due Friday 2026-07-24 and is a committed client deadline.",
        source_description="smoke",
        reference_time=now,
        source=EpisodeType.text,
    )
    print("=== search: 'What is due for a client and why does it matter?' ===")
    res = await g.search("What is due for a client and why does it matter?")
    for r in res[:8]:
        print("  -", getattr(r, "fact", r))
    await g.close()
    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
