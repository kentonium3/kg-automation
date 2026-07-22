"""A/B reasoning runner (the Q2 experiment).

Two arms, identical fixed prompt + model, only the CONTEXT differs:
  A (graph)  : graphiti hybrid/temporal search retrieves relevant facts for each query.
  B (flat)   : the FULL seed rendered as flat text (complete info, unstructured).

Both derive from the same seed. Output is BLINDED (Arm-1/Arm-2 randomized per query) for Kent's
usefulness judgment; the reveal + captured contexts are written separately (research R-01b/c).

Note on validity controls: newest Claude models deprecate `temperature`, so determinism comes from
the model itself (we omit temperature) rather than temp=0. Contexts are captured verbatim.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from anthropic import AsyncAnthropic

from graph_common import build_graphiti
from seed_lattice import _episodes, _index, _load_seed  # reuse the exact ingested facts

OUT = Path(__file__).resolve().parent.parent / "results"
REASON_MODEL = "claude-opus-4-8"
BLIND_SEED = 20260721  # fixed for reproducible blinding (mapping stored in reveal file)

QUERIES = [
    ("upward",
     "Take the task 'Write and publish the Intentional LLC positioning page.' Why does it matter — "
     "what larger goal or purpose does it ultimately serve? Trace the chain from the task upward."),
    ("chronic_defer",
     "Across all the current work, is there something that has quietly become a risk — a task that "
     "keeps getting pushed back but actually matters a lot? Identify it and explain why it is a risk."),
    ("week_conflict",
     "Is there a scheduling conflict in the week of July 21–24, 2026? If so, what collides, why is it a "
     "conflict, and what should give?"),
    ("trade_off",
     "Where is there a genuine trade-off between two efforts that compete for the same limited time, "
     "and what principle should tip the decision?"),
]

PROMPT = (
    "You are helping someone reason about their priorities and commitments. Using ONLY the context "
    "below, answer the question as specifically as you can, citing the concrete facts you rely on. If "
    "the context does not support an answer, say so.\n\n=== CONTEXT ===\n{context}\n\n=== QUESTION ===\n{q}"
)


def _flat_dump() -> str:
    doc = _load_seed()
    idx = _index(doc)
    lines = [body for _, body, _ in _episodes(doc, idx)]
    return "\n".join(f"- {ln}" for ln in lines)


async def _graph_context(g, query: str) -> str:
    # Single clean group (wiped + re-seeded); unscoped search is the reliable path in this
    # graphiti+FalkorDB version (group-scoped search errors / returns empty).
    edges = await g.search(query, num_results=20)
    facts = []
    for e in edges:
        fact = getattr(e, "fact", None)
        if not fact:
            continue
        valid_at = getattr(e, "valid_at", None)
        stamp = f"  [valid_at: {valid_at.date()}]" if isinstance(valid_at, datetime) else ""
        facts.append(f"- {fact}{stamp}")
    return "\n".join(facts) if facts else "(no facts retrieved)"


async def _reason(client: AsyncAnthropic, context: str, q: str) -> str:
    msg = await client.messages.create(
        model=REASON_MODEL,
        max_tokens=900,
        messages=[{"role": "user", "content": PROMPT.format(context=context, q=q)}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    key = os.environ["ANTHROPIC_API_KEY"]
    client = AsyncAnthropic(api_key=key)
    g = build_graphiti()

    flat = _flat_dump()
    rng = random.Random(BLIND_SEED)

    blinded_md = ["# Life Lattice Spike — A/B reasoning (BLINDED)\n",
                  "For each question, two answers from two different context representations. "
                  "Judge which (if either) is more useful — you don't know which is which.\n"]
    reveal = {"reason_model": REASON_MODEL, "generated_note": "temperature omitted (deprecated)", "queries": {}}

    for qid, q in QUERIES:
        print(f"== {qid} ==")
        ctx_a = await _graph_context(g, q)          # graph arm
        ctx_b = flat                                 # flat arm
        print("  reasoning (graph arm) ...")
        ans_a = await _reason(client, ctx_a, q)
        print("  reasoning (flat arm) ...")
        ans_b = await _reason(client, ctx_b, q)

        # blind: randomize presentation order
        arms = [("graph", ctx_a, ans_a), ("flat", ctx_b, ans_b)]
        rng.shuffle(arms)
        blinded_md.append(f"\n## Question ({qid})\n\n> {q}\n")
        for i, (_kind, _ctx, ans) in enumerate(arms, 1):
            blinded_md.append(f"### Arm-{i}\n\n{ans}\n")
        reveal["queries"][qid] = {
            "question": q,
            "arm_1_is": arms[0][0], "arm_2_is": arms[1][0],
            "graph_context": ctx_a, "graph_answer": ans_a,
            "flat_answer": ans_b,
        }

    await g.close()
    (OUT / "ab_results_blinded.md").write_text("\n".join(blinded_md))
    (OUT / "ab_reveal.json").write_text(json.dumps(reveal, indent=2, default=str))
    (OUT / "flat_dump.txt").write_text(flat)
    print(f"\nWROTE {OUT/'ab_results_blinded.md'}  and  {OUT/'ab_reveal.json'}")
    print("AB OK")


if __name__ == "__main__":
    asyncio.run(main())
