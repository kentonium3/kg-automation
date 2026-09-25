"""Arm G — the graph arm under test (WP05 T022–T024), built exactly as ruled.

Graphiti's DATA MODEL and HYBRID RETRIEVAL, none of its extraction (research.md
D-1, D-2, D-3, D-15; rubric §2 G row with the A3 query plan):

- **Writes** are typed direct saves — ``EntityNode`` / ``EntityEdge`` /
  ``EpisodicNode`` / ``EpisodicEdge`` ``.save(driver)`` — never Graphiti's extraction entry point.
  One graph per question, ``group_id = arms_<Q>`` (``^arms_[A-Z0-9]+$``; a hyphen
  zeroes BM25 on FalkorDB — #976 RQ-6a), built once from the replayed view and
  dropped after the third repeat. Episode content IS the frozen stream line (D-7).
- **The tripwire** LLM client raises on any call; the plan records ``llm_calls``
  and the harness fails the cell when it is not 0.
- **Retrieval** (A3): anchors resolved FROM THE QUESTION TEXT by deterministic
  matching against the loaded entities (never a per-question list) → one typed
  pull per label (``SearchFilters(node_labels=[label])``, one label at a time —
  RQ-6e) → node+edge hybrid search on the question text → anchored history
  expansion via ``EpisodicNode.get_by_entity_node_uuid`` (the MENTIONS wiring) →
  assembly under the 60-item cap. ``group_ids=[…]`` is always explicit (RQ-6b).
  **No BFS**: no search method expands from a hit to its neighbours.
- **Assembly** (D-15) decides WHICH items enter, in priority order (typed pulls
  by label order, hybrid hits, expansions per anchor), pulls and hits sorted by
  ``(score desc, stable key asc)``, expansions by event time DESC then ref ASC,
  de-duplicated by uuid, cut at 60. The bytes then
  follow ``FrozenCorpusText.render_block``'s layout — selected events in view
  order, then selected records in view order — so G's prompt has the same shape
  as D's and R's (rubric §2 layout protocol) and every inserted line is a frozen
  corpus line.

``EntityNode.name`` is reserved by Graphiti, so a node is named by the entity's
``id``; an entity's own ``name`` attribute is stored as ``display_name``.

The FalkorDB async client binds to the event loop it first runs on: a caller runs
the whole per-question sequence (build → assemble × 3 → drop) inside ONE loop
(one ``asyncio.run`` for the harness session), never one ``asyncio.run`` per step.
"""

from __future__ import annotations

import re
import time
import uuid as _uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.search.search_config import (
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
    SearchConfig,
    SearchResults,
)
from graphiti_core.tracer import NoOpTracer

from scripts.research.arms849.embed import (
    CosineReranker,
    Embedder,
    GraphitiEmbedder,
    TripwireLLMClient,
)
from scripts.research.arms849.text import Block, FrozenCorpusText, edge_key, entity_key
from scripts.research.load_849_corpus import Loaded, edge_effective_time

__all__ = ["CAP", "GROUP_RE", "TYPED_LABELS", "GraphArm", "GraphStats", "Item", "PlanRecord", "Resolution",
           "assemble", "group_id_for", "link_targets", "normalise", "resolve_anchors"]

GROUP_RE = re.compile(r"^arms_[A-Z0-9]+$")
TYPED_LABELS = ("Capacity", "Commitment", "Principle", "Interest")
CAP = 60
MIN_PHRASE_TOKENS = 3


#: Stable identity for every graph object: uuid5 over (group, kind, corpus key), so a rebuild —
#: and therefore a resume — reproduces the same uuids and D-15's (score desc, uuid asc) tie-break
#: selects the same items (Codex WP05 c1).
UUID_NS = _uuid.UUID("9b1c0a8e-7f14-5c3d-9e2a-849849849849")


def stable_uuid(group: str, kind: str, key: str) -> str:
    return str(_uuid.uuid5(UUID_NS, f"{group}\0{kind}\0{key}"))


def group_id_for(question_id: str) -> str:
    gid = f"arms_{question_id}"
    if not GROUP_RE.match(gid):
        raise ValueError(f"group id {gid!r} is not ^arms_[A-Z0-9]+$ (a hyphen zeroes BM25 on FalkorDB, RQ-6a)")
    return gid


def link_targets(link: Mapping[str, Any]) -> list[str]:
    """A loader link names its entities as a `mentions` list and/or a single `commitment`
    (two record shapes in loader_links.jsonl); the MENTIONS wiring covers both."""
    targets = [str(m) for m in link.get("mentions", []) or []]
    if link.get("commitment"):
        targets.append(str(link["commitment"]))
    return targets


def _ts(value: Any, fallback: datetime) -> datetime:
    if not value:
        return fallback
    s = str(value)
    dt = datetime.fromisoformat(s) if "T" in s or ":" in s else datetime.fromisoformat(s + "T00:00:00")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphStats:
    group_id: str
    nodes: int
    edges: int
    episodes: int
    links: int
    build_seconds: float
    llm_calls: int


@dataclass(frozen=True)
class Resolution:
    anchors: tuple[str, ...]                       # entity ids, sorted
    paths: dict[str, list[str]]                    # alias / commitment_desc / outcome_desc → ids
    ambiguous: tuple[str, ...]                     # mentions with more than one candidate
    path: str                                      # "anchored" | "search_only"


@dataclass(frozen=True)
class Item:
    kind: str                                      # node | edge | episode
    key: str                                       # entity id | edge key | event ref
    uuid: str
    score: float
    origin: str                                    # pull:<Label> | search | expand:<anchor id>


@dataclass
class PlanRecord:
    anchors_resolved: list[str]
    foreign_items: int
    anchor_resolution_paths: dict[str, list[str]]
    ambiguous_mentions: list[str]
    path: str
    plan_steps: list[dict[str, Any]]
    items_assembled: int
    items_by_kind: dict[str, int]
    llm_calls: int
    group_id: str
    assembled_context_sha256: str
    cap: int = CAP

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# anchor resolution (pure)
# ---------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s@']+", re.UNICODE)


def normalise(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", text.casefold()).split())


def _phrase_in(needle: str, haystack: str) -> bool:
    """Whole-token phrase containment on normalised text."""
    return f" {needle} " in f" {haystack} " if needle else False


def _longest_common_phrase(a_tokens: Sequence[str], b_tokens: Sequence[str]) -> int:
    """Length of the longest common contiguous token run."""
    best = 0
    prev = [0] * (len(b_tokens) + 1)
    for i in range(1, len(a_tokens) + 1):
        cur = [0] * (len(b_tokens) + 1)
        for j in range(1, len(b_tokens) + 1):
            if a_tokens[i - 1] == b_tokens[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def _longest_common_phrase_text(a_tokens: Sequence[str], b_tokens: Sequence[str]) -> str:
    """The longest common contiguous token run itself (first occurrence on ties)."""
    best, end = 0, 0
    prev = [0] * (len(b_tokens) + 1)
    for i in range(1, len(a_tokens) + 1):
        cur = [0] * (len(b_tokens) + 1)
        for j in range(1, len(b_tokens) + 1):
            if a_tokens[i - 1] == b_tokens[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, end = cur[j], i
        prev = cur
    return " ".join(a_tokens[end - best:end])


def resolve_anchors(question_text: str, view: Loaded) -> Resolution:
    """A3's three resolution paths, deterministic, from the question text only."""
    q_norm = normalise(question_text)
    q_tokens = q_norm.split()
    raw_tokens = set(re.findall(r"@\w+|\w[\w.'-]*", question_text.casefold()))
    paths: dict[str, list[str]] = {"alias": [], "commitment_desc": [], "outcome_desc": []}
    mention_hits: dict[str, set[str]] = {}

    # Persons: full names and aliases first; a bare first name resolves only when no full
    # name/alias hit already consumed it ("Marcus Vale" names one person; "Marcus" alone may
    # name several — those are the ambiguous mentions, kept ALL, sorted).
    persons = [e for e in view.entities if e.get("kind") == "Person"]
    first_names_consumed: set[str] = set()
    for entity in persons:
        eid = str(entity.get("id"))
        candidates = [str(entity.get("name") or "")] + [str(a) for a in entity.get("aliases", [])]
        for cand in candidates:
            c_norm = normalise(cand)
            if c_norm and (_phrase_in(c_norm, q_norm) or cand.casefold() in raw_tokens):
                paths["alias"].append(eid)
                mention_hits.setdefault(c_norm, set()).add(eid)
                if " " in c_norm:
                    first_names_consumed.add(c_norm.split()[0])
    for entity in persons:
        eid = str(entity.get("id"))
        if eid in paths["alias"]:
            continue
        full = normalise(str(entity.get("name") or ""))
        first = full.split()[0] if " " in full else ""
        if len(first) > 2 and first not in first_names_consumed and _phrase_in(first, q_norm):
            paths["alias"].append(eid)
            mention_hits.setdefault(first, set()).add(eid)
    for entity in view.entities:
        kind, eid = entity.get("kind"), str(entity.get("id"))
        if kind == "Person":
            continue
        elif kind in ("Commitment", "Outcome"):
            desc = normalise(str(entity.get("description") or ""))
            if not desc:
                continue
            d_tokens = desc.split()
            if _phrase_in(desc, q_norm) or _phrase_in(q_norm, desc):
                matched = desc if _phrase_in(desc, q_norm) else q_norm
            else:
                matched = _longest_common_phrase_text(q_tokens, d_tokens)
                if len(matched.split()) < MIN_PHRASE_TOKENS:
                    matched = ""
            if matched:
                bucket = "commitment_desc" if kind == "Commitment" else "outcome_desc"
                paths[bucket].append(eid)
                mention_hits.setdefault(matched, set()).add(eid)      # keyed by the PHRASE that matched

    for k, ids in list(paths.items()):
        paths[k] = sorted(set(ids))
    anchors = tuple(sorted({eid for ids in paths.values() for eid in ids}))
    ambiguous = tuple(sorted(m for m, ids in mention_hits.items() if len(ids) > 1))
    return Resolution(anchors=anchors, paths=paths, ambiguous=ambiguous,
                      path="anchored" if anchors else "search_only")


# ---------------------------------------------------------------------------
# search configurations — hybrid, NO BFS
# ---------------------------------------------------------------------------

#: "node+edge hybrid" means exactly that: episodes reach the context only through anchored
#: expansion (MENTIONS), never as direct hits that would consume the cap first (A3; Codex WP05 c1).
HYBRID_NODE_EDGE = SearchConfig(
    node_config=NodeSearchConfig(search_methods=[NodeSearchMethod.bm25, NodeSearchMethod.cosine_similarity],
                                 reranker=NodeReranker.cross_encoder),
    edge_config=EdgeSearchConfig(search_methods=[EdgeSearchMethod.bm25, EdgeSearchMethod.cosine_similarity],
                                 reranker=EdgeReranker.cross_encoder),
    limit=CAP,
)
TYPED_PULL = SearchConfig(
    node_config=NodeSearchConfig(search_methods=[NodeSearchMethod.bm25, NodeSearchMethod.cosine_similarity],
                                 reranker=NodeReranker.cross_encoder),
    limit=CAP,
)


def _assert_no_bfs(config: SearchConfig) -> None:
    for sub in (config.node_config, config.edge_config, config.episode_config, config.community_config):
        if sub is not None and any("bfs" in str(m) or "breadth" in str(m) for m in sub.search_methods):
            raise ValueError("BFS is not a G search method (A3: no BFS by default)")


_assert_no_bfs(HYBRID_NODE_EDGE)
_assert_no_bfs(TYPED_PULL)


# ---------------------------------------------------------------------------
# the arm
# ---------------------------------------------------------------------------


class GraphArm:
    """One driver, one embedder, one tripwire; per-question graphs and maps."""

    def __init__(self, driver: GraphDriver, embedder: Embedder, text: FrozenCorpusText) -> None:
        self.driver = driver
        self.embedder = embedder
        self.text = text
        self.tripwire = TripwireLLMClient()
        self.graphiti = Graphiti(graph_driver=driver, llm_client=self.tripwire,
                                 embedder=GraphitiEmbedder(embedder), cross_encoder=CosineReranker(embedder),
                                 tracer=NoOpTracer())
        self._uuid_by_id: dict[str, dict[str, str]] = {}          # group → entity id → uuid
        self._key_by_uuid: dict[str, dict[str, tuple[str, str]]] = {}   # group → uuid → (kind, key)
        self._indices_built = False
        self._foreign: list[str] = []                             # result uuids not in our map (must stay empty)

    @property
    def llm_calls(self) -> int:
        return self.tripwire.llm_calls

    # -- writes ----------------------------------------------------------------

    async def build_graph(self, question: Any, view: Loaded) -> GraphStats:
        group = group_id_for(question.id)
        t0 = time.monotonic()
        if not self._indices_built:
            await self.driver.build_indices_and_constraints()
            self._indices_built = True
        await self.drop_graph(question)                              # idempotent rebuild
        uuid_by_id: dict[str, str] = {}
        key_by_uuid: dict[str, tuple[str, str]] = {}
        ask = view.ask_time if view.ask_time.tzinfo else view.ask_time.replace(tzinfo=timezone.utc)

        nodes = 0
        for entity in view.entities:
            eid, kind = entity_key(entity), str(entity.get("kind"))
            attrs = {("display_name" if k == "name" else k): v for k, v in entity.items() if k not in ("id", "kind")}
            summary = str(entity.get("description") or entity.get("name") or entity.get("topic") or eid)
            node = EntityNode(uuid=stable_uuid(group, "node", eid), name=eid, group_id=group, labels=[kind],
                              summary=summary, attributes=attrs, created_at=ask)
            node.name_embedding = self.embedder.embed_one(summary)     # the id token is noise in the vector
            await node.save(self.driver)
            uuid_by_id[eid] = node.uuid
            key_by_uuid[node.uuid] = ("node", eid)
            nodes += 1

        edges = 0
        for edge in view.edges:
            src, dst = uuid_by_id.get(str(edge.get("from"))), uuid_by_id.get(str(edge.get("to")))
            if src is None or dst is None:
                continue                                              # the loader withholds dangling edges
            key = edge_key(edge)
            # The edge's effective time is the LOADER's derivation (made_at, else the source
            # Decision's decided_at, else the endpoints' visibility) — the replay rule's own clock;
            # ask_time only when the loader itself has no time for it (Codex WP05 c1).
            eff = edge_effective_time(edge, view.entities)
            when = eff if eff is not None else ask
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            attrs = {k: v for k, v in edge.items() if k not in ("from", "to", "type", "kind")}
            fact = self.text.record_line(key).decode("utf-8")
            e = EntityEdge(uuid=stable_uuid(group, "edge", key), group_id=group, source_node_uuid=src,
                           target_node_uuid=dst, name=str(edge["type"]), fact=fact, created_at=when, valid_at=when,
                           attributes=attrs)
            e.fact_embedding = self.embedder.embed_one(fact)
            await e.save(self.driver)
            key_by_uuid[e.uuid] = ("edge", key)
            edges += 1

        episodes = 0
        ep_uuid: dict[str, str] = {}
        ep_when: dict[str, datetime] = {}
        for event in view.events:
            ref = str(event["ref"])
            when = _ts(event.get("at"), ask)
            ep_when[ref] = when
            ep = EpisodicNode(uuid=stable_uuid(group, "episode", ref), name=ref, group_id=group, labels=[],
                              source=EpisodeType.text,
                              source_description=str(event.get("source_description") or event.get("channel") or ""),
                              content=self.text.event_line(ref).decode("utf-8"), valid_at=when, created_at=when)
            await ep.save(self.driver)
            ep_uuid[ref] = ep.uuid
            key_by_uuid[ep.uuid] = ("episode", ref)
            episodes += 1

        links = 0
        for link in view.links:                                       # G's input only (A1 b)
            src = ep_uuid.get(str(link.get("ref")))
            if src is None:
                continue
            for mention in link_targets(link):
                dst = uuid_by_id.get(str(mention))
                if dst is None:
                    continue
                # The MENTIONS edge carries ITS EPISODE's time, not ask_time (Codex WP05 c2).
                await EpisodicEdge(uuid=stable_uuid(group, "link", f"{link.get('ref')}->{mention}"), group_id=group,
                                   source_node_uuid=src, target_node_uuid=dst,
                                   created_at=ep_when[str(link.get("ref"))]).save(self.driver)
                links += 1

        self._uuid_by_id[group] = uuid_by_id
        self._key_by_uuid[group] = key_by_uuid
        return GraphStats(group_id=group, nodes=nodes, edges=edges, episodes=episodes, links=links,
                          build_seconds=round(time.monotonic() - t0, 3), llm_calls=self.llm_calls)

    async def drop_graph(self, question: Any) -> None:
        group = group_id_for(question.id)
        await self.driver.execute_query("MATCH (n {group_id: $group_id}) DETACH DELETE n", group_id=group)
        self._uuid_by_id.pop(group, None)
        self._key_by_uuid.pop(group, None)

    # -- retrieval -------------------------------------------------------------

    def _items(self, group: str, results: SearchResults, origin: str) -> list[Item]:
        keys = self._key_by_uuid.get(group, {})
        out: list[Item] = []
        for coll, scores in ((results.nodes, results.node_reranker_scores),
                             (results.edges, results.edge_reranker_scores),
                             (results.episodes, results.episode_reranker_scores)):
            for i, obj in enumerate(coll):
                kk = keys.get(obj.uuid)
                if kk is None:
                    # With explicit group_ids this never happens; if it does it is a cross-group
                    # leak (RQ-6b) or a stale map — recorded and REFUSED, never silently dropped.
                    self._foreign.append(obj.uuid)
                    continue
                score = float(scores[i]) if scores and i < len(scores) else 0.0
                out.append(Item(kind=kk[0], key=kk[1], uuid=obj.uuid, score=score, origin=origin))
        return out

    async def typed_pulls(self, question_text: str, group: str) -> dict[str, list[Item]]:
        """The COMPLETE set of nodes carrying each label in the group — one MATCH per label,
        no similarity, no threshold (design-lead ruling 2026-09-25: a Principle the question
        never names must still be pulled; that is what the constraint pull is for). Score 1.0,
        ordered by entity id. `question_text` is accepted for the interface and unused here."""
        del question_text
        keys = self._key_by_uuid.get(group, {})
        out: dict[str, list[Item]] = {}
        for label in TYPED_LABELS:
            rows, _, _ = await self.driver.execute_query(
                "MATCH (n:Entity {group_id: $group_id}) WHERE $label IN labels(n) "
                "RETURN n.uuid AS uuid, n.name AS name ORDER BY n.name",
                group_id=group, label=label)
            items = []
            for row in rows:
                kk = keys.get(str(row["uuid"]))
                if kk is None:
                    self._foreign.append(str(row["uuid"]))
                    continue
                items.append(Item(kind="node", key=kk[1], uuid=str(row["uuid"]), score=1.0, origin=f"pull:{label}"))
            out[label] = sorted(items, key=lambda i: i.key)
        return out

    async def hybrid_search(self, question_text: str, group: str) -> list[Item]:
        res = await self.graphiti.search_(question_text, config=HYBRID_NODE_EDGE, group_ids=[group])
        return self._items(group, res, "search")

    async def anchored_expansion(self, group: str, anchor_id: str) -> list[Item]:
        """The episodes that MENTION the anchor — one hop, never onward (no BFS)."""
        uuid = self._uuid_by_id.get(group, {}).get(anchor_id)
        if uuid is None:
            return []
        episodes = await EpisodicNode.get_by_entity_node_uuid(self.driver, uuid)
        keys = self._key_by_uuid.get(group, {})
        items = []
        for ep in episodes:
            kk = keys.get(ep.uuid)
            if kk is None:
                self._foreign.append(ep.uuid)
                continue
            items.append((ep.valid_at, Item(kind="episode", key=kk[1], uuid=ep.uuid, score=1.0, origin=f"expand:{anchor_id}")))
        # Anchored HISTORY: most recent first, then ref — when the cap cuts, the latest survive.
        items.sort(key=lambda t: (-(t[0].timestamp() if t[0] else 0.0), t[1].key))
        return [it for _, it in items]

    # -- assembly (D-15) -------------------------------------------------------

    async def plan_and_assemble(self, question: Any, view: Loaded) -> tuple[Block, PlanRecord]:
        group = group_id_for(question.id)
        if group not in self._key_by_uuid:
            raise RuntimeError(f"graph {group} is not built; build_graph first")
        resolution = resolve_anchors(question.text, view)
        self._foreign = []
        steps: list[dict[str, Any]] = []
        pulls = await self.typed_pulls(question.text, group)
        for label in TYPED_LABELS:
            steps.append({"step": f"typed_pull:{label}", "count": len(pulls[label])})
        hits = await self.hybrid_search(question.text, group)
        steps.append({"step": "hybrid_search", "count": len(hits)})
        expansions: list[list[Item]] = []
        if resolution.path == "anchored":
            for anchor in resolution.anchors:
                exp = await self.anchored_expansion(group, anchor)
                expansions.append(exp)
                steps.append({"step": f"expand:{anchor}", "count": len(exp)})
        else:
            steps.append({"step": "expand", "count": 0, "note": "search_only: zero anchors"})
        if self._foreign:
            raise RuntimeError(f"{len(self._foreign)} retrieval result(s) outside the group map — cross-group leak or "
                               f"stale map; the cell is an error (RQ-6b)")
        block, chosen = assemble(self.text, view, [pulls[label] for label in TYPED_LABELS], hits, expansions)
        by_kind: dict[str, int] = {}
        for it in chosen:
            by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
        plan = PlanRecord(anchors_resolved=list(resolution.anchors), foreign_items=len(self._foreign),
                          anchor_resolution_paths=dict(resolution.paths),
                          ambiguous_mentions=list(resolution.ambiguous), path=resolution.path, plan_steps=steps,
                          items_assembled=len(chosen), items_by_kind=by_kind, llm_calls=self.llm_calls,
                          group_id=group, assembled_context_sha256=block.sha256)
        return block, plan

    # -- the arm ---------------------------------------------------------------

    async def answer(self, question: Any, view: Loaded, ctx: Any) -> dict[str, Any]:
        """contracts/arm-interface.md: assemble → render → count → complete; every telemetry
        field from the completion plus the plan. ``ctx`` is the harness's CellContext
        (prompt, serving facade with serialize/count_tokens/complete, seed, limit)."""
        block, plan = await self.plan_and_assemble(question, view)
        if plan.llm_calls:
            raise RuntimeError(f"tripwire: {plan.llm_calls} LLM call(s) attempted — the cell is an error")
        request = ctx.prompt.render(block, question.text)
        body = ctx.serving.serialize(request, ctx.seed)
        prompt_tokens = ctx.serving.count_tokens(body)
        if prompt_tokens > ctx.limit:
            from scripts.research.arms849.serving import ContextExceeded

            raise ContextExceeded(f"prompt is {prompt_tokens} tokens; limit {ctx.limit} ({ctx.limit_applied})")
        completion = ctx.serving.complete(body)
        return {
            "text": completion.text,
            "assembled_context_tokens": ctx.serving.count_text(block.data),
            "prompt_tokens": completion.prompt_tokens, "client_prompt_tokens": completion.client_prompt_tokens,
            "output_tokens": completion.output_tokens, "finish_reason": completion.finish_reason,
            "cache_read_tokens": completion.cache_read_tokens, "uncached_tokens": completion.uncached_tokens,
            "cache_write_tokens": completion.cache_write_tokens, "cache_state": completion.cache_state,
            "cache_fraction": completion.cache_fraction, "prefill_s": completion.prefill_s,
            "generation_s": completion.generation_s, "generation_tok_s": completion.generation_tok_s,
            "assembled_context_sha256": block.sha256, "plan": plan.as_dict(),
        }

def assemble(text: FrozenCorpusText, view: Loaded, pulls: Sequence[Sequence[Item]], hits: Sequence[Item],
             expansions: Sequence[Sequence[Item]], cap: int = CAP) -> tuple[Block, list[Item]]:
    """D-15: select in priority order under the cap, then lay out as frozen lines.

    Priority: typed pulls in label order, then hybrid hits, then expansions per anchor in
    resolution order; pulls and hits sorted ``(score desc, STABLE KEY asc)`` — never by uuid,
    which would tie-break differently across rebuilds; each anchor's expansions keep the
    order the arm gave them (event time DESC, ref ASC: the most recent history survives the
    cap); de-duplicated by uuid; cut at ``cap`` items across nodes + edges + episodes. Layout: selected events in view order,
    then selected records in view order (entities, then edges) — render_block's shape.
    """
    chosen: list[Item] = []
    seen: set[str] = set()
    groups: list[list[Item]] = [sorted(g, key=lambda i: (-i.score, i.key)) for g in pulls]
    groups.append(sorted(hits, key=lambda i: (-i.score, i.key)))
    groups.extend(list(g) for g in expansions)                       # already time DESC, ref ASC
    for group in groups:
        for it in group:
            if it.uuid in seen:
                continue
            seen.add(it.uuid)
            chosen.append(it)
            if len(chosen) >= cap:
                break
        if len(chosen) >= cap:
            break
    refs = {it.key for it in chosen if it.kind == "episode"}
    keys = {it.key for it in chosen if it.kind in ("node", "edge")}
    event_refs = [str(e["ref"]) for e in view.events if str(e["ref"]) in refs]
    record_keys = [entity_key(e) for e in view.entities if entity_key(e) in keys]
    record_keys += [edge_key(e) for e in view.edges if edge_key(e) in keys]
    return text.render_block(event_refs, record_keys), chosen


def stats_dict(stats: GraphStats) -> Mapping[str, Any]:
    return asdict(stats)


def iter_group_ids(question_ids: Iterable[str]) -> list[str]:
    return [group_id_for(q) for q in question_ids]
