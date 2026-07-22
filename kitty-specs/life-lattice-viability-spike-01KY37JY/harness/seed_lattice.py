"""Load the manufactured seed chain into Graphiti as episodes.

Design: we feed FACTS as episodes and let Graphiti extract the temporal graph (faithful to the
#692 stack). Structural facts use reference_time = now; the chronic-defer reschedules are emitted
as FOUR separate episodes at their historical observed_at times, so Graphiti's bi-temporal model
must capture the rescheduling history (the make-or-break temporal case).

Guardrails (seed-quality checklist / hidden-oracle rule):
  * every Task traces upward to exactly one Purpose
  * >=1 hard and >=1 soft Principle
  * NO CONFLICTS_WITH / TRADES_OFF edges in the seed (conflicts must be inferred; oracle is hidden)
  * the chronic-defer task has exactly 4 defer events
This module NEVER reads oracle.yaml.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from graphiti_core.nodes import EpisodeType

from graph_common import build_graphiti

DATA = Path(__file__).resolve().parent.parent / "data"
SEED = DATA / "seed_chain.yaml"
GROUP = "lattice-spike"
NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)


def _load_seed() -> dict:
    doc = yaml.safe_load(SEED.read_text())
    # Hidden-oracle rule: the seed must not assert conflicts/trade-offs as edges.
    raw = SEED.read_text()
    for banned in ("CONFLICTS_WITH", "TRADES_OFF"):
        assert f"{banned}:" not in raw and f"- {banned}" not in raw, f"seed asserts {banned} (forbidden)"
    return doc


def _index(doc: dict) -> dict[str, dict]:
    idx = {}
    for p in doc.get("purposes", []):
        idx[p["id"]] = {**p, "type": "purpose"}
    for n in doc.get("nodes", []):
        idx[n["id"]] = n
    return idx


def _label(idx: dict, nid: str) -> str:
    return idx.get(nid, {}).get("label", nid)


def _validate(doc: dict, idx: dict) -> None:
    # every task -> purpose (walk `serves` up to a purpose)
    def resolves_to_purpose(nid: str) -> bool:
        seen = set()
        cur = nid
        while cur and cur not in seen:
            seen.add(cur)
            node = idx.get(cur, {})
            if node.get("type") == "purpose":
                return True
            cur = node.get("serves")
        return False

    tasks = [n for n in doc["nodes"] if n.get("type") == "task"]
    for t in tasks:
        assert resolves_to_purpose(t["id"]), f"task {t['id']} does not trace up to a Purpose"
    strict = {p["strictness"] for p in doc["principles"]}
    assert "hard" in strict and "soft" in strict, "need >=1 hard and >=1 soft principle"
    # chronic-defer has 4 events
    cd = next(n for n in doc["nodes"] if n["id"] == "TASK_POSITIONING")
    assert len(cd["defer_history"]) == 4, "chronic-defer task must have 4 defer events"
    print(f"  seed-quality OK: {len(tasks)} tasks trace to a Purpose; hard+soft principles present; 4 defer events")


def _episodes(doc: dict, idx: dict) -> list[tuple[str, str, datetime]]:
    eps: list[tuple[str, str, datetime]] = []

    cap = doc["constraints"][0]
    eps.append(("capacity", f"Available focused deep-work capacity is about {cap['hours_per_week']} hours per week. This is a hard limit on how much work can happen in any one week.", NOW))

    for c in doc["constraints"][1:]:
        eps.append((c["id"], f"{c['statement']}", NOW))

    for pr in doc["principles"]:
        eps.append((pr["id"], f"Principle ({pr['strictness']}): {pr['statement']}", NOW))

    for p in doc["purposes"]:
        eps.append((p["id"], f"Purpose: {p['label']}.", NOW))

    for n in doc["nodes"]:
        t = n["type"]
        serves = _label(idx, n["serves"]) if n.get("serves") else None
        parts = [f"{t.capitalize()}: '{n['label']}'."]
        if serves:
            parts.append(f"It serves / is part of '{serves}'.")
        if "own_priority" in n:
            parts.append(f"Its own stated priority is {n['own_priority']}.")
        if "estimate_hours" in n:
            parts.append(f"It takes about {n['estimate_hours']} hours.")
        if "estimate_hours_this_month" in n:
            parts.append(f"It needs about {n['estimate_hours_this_month']} hours of work this month.")
        if n.get("current_planned_date"):
            parts.append(f"It is currently planned for {n['current_planned_date']}.")
        if n.get("deadline_ref"):
            parts.append("It has a fixed calendar deadline.")
        if n.get("governed_by"):
            parts.append("It is governed by principle(s): " + ", ".join(n["governed_by"]) + ".")
        eps.append((n["id"], " ".join(parts), NOW))

    # Chronic-defer: 4 reschedule episodes at their historical observed_at times.
    cd = next(n for n in doc["nodes"] if n["id"] == "TASK_POSITIONING")
    label = cd["label"]
    for i, ev in enumerate(cd["defer_history"], 1):
        obs = datetime.fromisoformat(ev["observed_at"]).replace(tzinfo=timezone.utc)
        if ev["previous_planned_date"] is None:
            body = f"The task '{label}' was first scheduled for {ev['new_planned_date']}."
        else:
            body = (f"The task '{label}' was rescheduled again: pushed from {ev['previous_planned_date']} "
                    f"to {ev['new_planned_date']}. This is deferral number {i}.")
        eps.append((f"defer_{i}", body, obs))

    return eps


async def main() -> None:
    doc = _load_seed()
    idx = _index(doc)
    _validate(doc, idx)
    eps = _episodes(doc, idx)
    print(f"  built {len(eps)} episodes; ingesting (LLM extraction) ...")

    g = build_graphiti()
    await g.build_indices_and_constraints()
    # chronological order so bi-temporal edges land correctly
    for name, body, ref in sorted(eps, key=lambda e: e[2]):
        await g.add_episode(name=name, episode_body=body, source_description="seed",
                            reference_time=ref, source=EpisodeType.text)
        print(f"    + {name} @ {ref.date()}")

    print("\n  retrievability check — chronic-defer history:")
    res = await g.search("How many times has the Intentional LLC positioning page been deferred or rescheduled?")
    for r in res[:6]:
        print("    -", getattr(r, "fact", r))
    await g.close()
    print("SEED OK")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
