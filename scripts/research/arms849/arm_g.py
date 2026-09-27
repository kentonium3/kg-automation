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

**One database per question** (FR-016, research D-2b — a defect fix): every operation for a
question — node/edge/episode writes, the index build, typed pulls, hybrid search, anchored
expansion and drop — runs through ONE driver ``self.driver.clone(database=group)``, created once
per question, cached, and index-ready before first use. The approved code wrote to the root
driver's ``default_db`` while ``Graphiti.search_``'s ``@handle_multiple_group_ids`` cloned to
``arms_<Q>``, so hybrid retrieval always read an empty graph.

**Refusals and premise violations** (FR-002; contracts/arm-registration items 3–5): a graph not
built, a foreign item in G's own graph and an incoherent context limit raise the ONE shared
:class:`~arms849.errors.ArmRefusal` (terminal for the cell); the no-LLM tripwire firing and
retrieval crossing the per-question graph boundary raise
:class:`~arms849.errors.PremiseViolated` (the run halts).

**The loop bridge** (research D-2; NFR-003): the FalkorDB async client binds to the event loop it
first runs on, so G's registration-facing :class:`Bridge` owns ONE loop on a dedicated thread and
ONE driver bound to it. Only graph work runs there; serving runs on the attempt thread through the
synchronous :meth:`GraphArm.respond`, exactly as D and R serve. A cancelled coroutine must
acknowledge its own termination within ``errors.G_CANCEL_GRACE_S``, or the bridge raises
:class:`~arms849.errors.GCancellationUnacknowledged` and issues nothing further.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import re
import threading
import time
import uuid as _uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn, TypeVar

from graphiti_core import Graphiti
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.driver.falkordb_driver import FalkorDriver
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

from scripts.research.arms849 import errors, serving
from scripts.research.arms849.embed import (
    CosineReranker,
    Embedder,
    GraphitiEmbedder,
    TripwireLLMClient,
)
from scripts.research.arms849.errors import (
    ArmRefusal,
    CeilingBreached,
    CeilingUnreadable,
    GCancellationUnacknowledged,
    PremiseViolated,
)
from scripts.research.arms849.text import Block, FrozenCorpusText, edge_key, entity_key
from scripts.research.load_849_corpus import Loaded, edge_effective_time

__all__ = ["CAP", "FALKOR_HOST", "FALKOR_PORT", "GROUP_RE", "LOOP_THREAD_NAME", "TYPED_LABELS", "Bridge", "GraphArm",
           "GraphStats", "Item", "PlanRecord", "Resolution", "TransportGate", "TransportPoisoned", "assemble",
           "group_id_for", "link_targets", "make_bridge", "normalise", "resolve_anchors"]

T = TypeVar("T")

#: The compose service the runner container reaches FalkorDB by (research D-2); tests inject their own.
FALKOR_HOST, FALKOR_PORT = "falkordb", 6379
#: The bridge loop's thread: every graph query runs on it and nowhere else.
LOOP_THREAD_NAME = "arms849-g-loop"
#: How often the attempt thread re-checks its deadline and ``cancelled`` flag while graph work runs.
POLL_S = 0.05
#: How long a stop waits for the loop thread to return before the fatal signal is raised anyway.
HALT_JOIN_S = 1.0
#: Raised by the work itself, these decide the cell or the run: after a cancellation they propagate as
#: themselves, never as a retryable TimeoutError (research D-2's rule for _call_with_timeout, at the bridge).
TERMINAL_EXCEPTIONS: tuple[type[BaseException], ...] = (PremiseViolated, ArmRefusal, CeilingBreached, CeilingUnreadable)

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
    """One root driver, one embedder, one tripwire; per question ONE database, ONE Graphiti, one map.

    The root ``driver`` is never queried for a question: :meth:`_database` clones it ONCE per question
    (``driver.clone(database=group)``), caches the clone, and AWAITS the clone's detached ``_init_task``
    (graphiti schedules the index build on construction) before first use, so index readiness is owned
    per database (``_indices_built`` is a set of databases, not one flag). A ``Graphiti`` instance is
    built per question bound to that clone, so ``@handle_multiple_group_ids`` takes its
    ``gid == driver._database`` branch and clones nothing further (research D-2b; installed
    ``decorators.py`` L59–68). A failed or cancelled index build is never reused: the cache entry is
    dropped and the next use clones afresh.
    """

    def __init__(self, driver: GraphDriver, embedder: Embedder, text: FrozenCorpusText) -> None:
        self.driver = driver
        self.embedder = embedder
        self.text = text
        self.tripwire = TripwireLLMClient()
        self._graphiti_embedder = GraphitiEmbedder(embedder)
        self._reranker = CosineReranker(embedder)
        self._databases: dict[str, GraphDriver] = {}               # group → its per-question driver
        self._graphiti: dict[str, Graphiti] = {}                   # group → Graphiti bound to that driver
        self._indices_built: set[str] = set()                      # databases whose index build completed
        self._uuid_by_id: dict[str, dict[str, str]] = {}          # group → entity id → uuid
        self._key_by_uuid: dict[str, dict[str, tuple[str, str]]] = {}   # group → uuid → (kind, key)
        self._foreign: list[str] = []      # results in THIS group's graph that G did not write (ArmRefusal)
        self._leaked: list[str] = []       # results from ANOTHER group's graph (PremiseViolated)
        #: uuid → the group G wrote it for. APPEND-ONLY for the arm's life: never deleted by drop_graph or a
        #: rebuild, so a dropped question's uuid reported under another group is still recognised as a leak
        #: (review c2 finding 3). Separate from the per-view maps above, which are graph-built state.
        self._owner: dict[str, str] = {}

    @property
    def llm_calls(self) -> int:
        return self.tripwire.llm_calls

    def _check_tripwire(self, llm_calls: int) -> None:
        if llm_calls:
            raise PremiseViolated("tripwire", f"{llm_calls} LLM call(s) attempted; G never extracts (D-2)")

    async def _database(self, group: str) -> GraphDriver:
        """THE driver for ``group``: cloned once, cached, index-ready (FR-016)."""
        db = self._databases.get(group)
        if db is None:
            db = self.driver.clone(database=group)
            self._databases[group] = db
            self._graphiti[group] = Graphiti(graph_driver=db, llm_client=self.tripwire,
                                             embedder=self._graphiti_embedder, cross_encoder=self._reranker,
                                             tracer=NoOpTracer())
        if group not in self._indices_built:
            try:
                init = getattr(db, "_init_task", None)
                if init is not None:
                    await init                                  # the clone's own detached index build
                else:
                    await db.build_indices_and_constraints()    # cloned outside a running loop: build it here
            except BaseException:
                self._databases.pop(group, None)
                self._graphiti.pop(group, None)
                raise
            self._indices_built.add(group)
        return db

    # -- writes ----------------------------------------------------------------

    async def build_graph(self, question: Any, view: Loaded) -> GraphStats:
        group = group_id_for(question.id)
        t0 = time.monotonic()
        db = await self._database(group)
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
            await node.save(db)
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
            await e.save(db)
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
            await ep.save(db)
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
                                   created_at=ep_when[str(link.get("ref"))]).save(db)
                links += 1

        self._check_tripwire(self.llm_calls)
        self._uuid_by_id[group] = uuid_by_id
        self._key_by_uuid[group] = key_by_uuid
        for written in key_by_uuid:
            self._owner.setdefault(written, group)
        return GraphStats(group_id=group, nodes=nodes, edges=edges, episodes=episodes, links=links,
                          build_seconds=round(time.monotonic() - t0, 3), llm_calls=self.llm_calls)

    async def drop_graph(self, question: Any) -> None:
        group = group_id_for(question.id)
        db = await self._database(group)
        await db.execute_query("MATCH (n {group_id: $group_id}) DETACH DELETE n", group_id=group)
        self._uuid_by_id.pop(group, None)
        self._key_by_uuid.pop(group, None)

    async def list_graphs(self) -> list[str]:
        """The server's graph listing, read-only (``GRAPH.LIST``): WP04 T020 records
        ``graph_store_first_build.graphs_present`` from it before the first build."""
        return sorted(str(g) for g in await self.driver.client.list_graphs())

    async def close(self) -> None:
        """Close the ONE connection the root driver and every per-question clone share."""
        await self.driver.close()

    # -- retrieval -------------------------------------------------------------

    def _key_for(self, group: str, uuid: str, result_group: Any) -> tuple[str, str] | None:
        """The (kind, key) G wrote for ``uuid`` in ``group``; else record WHY it is not ours.

        A result carrying ANOTHER group — by its own ``group_id``, or a uuid G EVER wrote for another
        question (the append-only ``_owner``, which survives drop_graph) — crossed the per-question graph boundary: ``_leaked`` (PremiseViolated, the run
        halts). A result in THIS group's graph that G did not write from this view: ``_foreign``
        (ArmRefusal, the cell is refused). Neither is ever silently dropped (RQ-6b). The result's REPORTED
        group is checked first: a uuid G wrote for this question, returned under another question's group,
        has crossed the boundary too (review c1 finding 5)."""
        if result_group is not None and str(result_group) != group:
            self._leaked.append(uuid)
            return None
        owner = self._owner.get(uuid)
        if owner is not None and owner != group:
            self._leaked.append(uuid)                               # written for another question, ever
            return None
        kk = self._key_by_uuid.get(group, {}).get(uuid)
        if kk is not None:
            return kk
        self._foreign.append(uuid)
        return None

    def _items(self, group: str, results: SearchResults, origin: str) -> list[Item]:
        out: list[Item] = []
        for coll, scores in ((results.nodes, results.node_reranker_scores),
                             (results.edges, results.edge_reranker_scores),
                             (results.episodes, results.episode_reranker_scores)):
            for i, obj in enumerate(coll):
                kk = self._key_for(group, obj.uuid, getattr(obj, "group_id", None))
                if kk is None:
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
        db = await self._database(group)
        out: dict[str, list[Item]] = {}
        for label in TYPED_LABELS:
            rows, _, _ = await db.execute_query(
                "MATCH (n:Entity {group_id: $group_id}) WHERE $label IN labels(n) "
                "RETURN n.uuid AS uuid, n.name AS name, n.group_id AS group_id ORDER BY n.name",
                group_id=group, label=label)
            items = []
            for row in rows:
                kk = self._key_for(group, str(row["uuid"]), row.get("group_id"))
                if kk is None:
                    continue
                items.append(Item(kind="node", key=kk[1], uuid=str(row["uuid"]), score=1.0, origin=f"pull:{label}"))
            out[label] = sorted(items, key=lambda i: i.key)
        return out

    async def hybrid_search(self, question_text: str, group: str) -> list[Item]:
        await self._database(group)                                     # the Graphiti bound to THIS database
        res = await self._graphiti[group].search_(question_text, config=HYBRID_NODE_EDGE, group_ids=[group])
        return self._items(group, res, "search")

    async def anchored_expansion(self, group: str, anchor_id: str) -> list[Item]:
        """The episodes that MENTION the anchor — one hop, never onward (no BFS)."""
        uuid = self._uuid_by_id.get(group, {}).get(anchor_id)
        if uuid is None:
            return []
        episodes = await EpisodicNode.get_by_entity_node_uuid(await self._database(group), uuid)
        items = []
        for ep in episodes:
            kk = self._key_for(group, ep.uuid, getattr(ep, "group_id", None))
            if kk is None:
                continue
            items.append((ep.valid_at, Item(kind="episode", key=kk[1], uuid=ep.uuid, score=1.0, origin=f"expand:{anchor_id}")))
        # Anchored HISTORY: most recent first, then ref — when the cap cuts, the latest survive.
        items.sort(key=lambda t: (-(t[0].timestamp() if t[0] else 0.0), t[1].key))
        return [it for _, it in items]

    # -- assembly (D-15) -------------------------------------------------------

    async def plan_and_assemble(self, question: Any, view: Loaded) -> tuple[Block, PlanRecord]:
        group = group_id_for(question.id)
        if group not in self._key_by_uuid:
            raise ArmRefusal(f"graph {group} is not built; build_graph first (a configuration defect, terminal)")
        resolution = resolve_anchors(question.text, view)
        self._foreign, self._leaked = [], []
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
        if self._leaked:
            raise PremiseViolated("cross_group_leak", f"{len(self._leaked)} retrieval result(s) for {group} came from "
                                  f"another question's graph (RQ-6b): the per-question boundary is crossed")
        if self._foreign:
            raise ArmRefusal(f"{len(self._foreign)} foreign item(s) in {group}'s graph that G did not write from this "
                             f"view (a stale map or a graph not built from it); the cell is refused (RQ-6b)")
        self._check_tripwire(self.llm_calls)
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

    # -- serving (the attempt thread) ------------------------------------------

    def respond(self, block: Block, plan: PlanRecord, question: Any, ctx: Any) -> dict[str, Any]:
        """contracts/arm-interface.md, the serving half: render → serialize → count → complete, on the
        CALLER's thread, exactly as D and R serve (C-008; research D-2). Synchronous: it never touches
        the graph loop. ``ctx`` is the harness's CellContext (prompt, serving facade, config, seed, limit).

        Refuses before anything is counted: a plan that counted an LLM call (PremiseViolated) and an
        incoherent context limit (the shared ``errors.check_limit``, ctx.config only — ArmRefusal).
        ``cache_prompt`` is served as configured and never refused (C-008). The ceiling guard's
        exceptions (``CeilingBreached`` / ``CeilingUnreadable``) raised by ``ctx.serving.complete``'s
        ``before_send`` are never caught here.
        """
        self._check_tripwire(plan.llm_calls)
        errors.check_limit(ctx)
        request = ctx.prompt.render(block, question.text)
        body = ctx.serving.serialize(request, ctx.seed)
        prompt_tokens = ctx.serving.count_tokens(body)
        if prompt_tokens > ctx.limit:
            raise serving.ContextExceeded(f"prompt is {prompt_tokens} tokens; limit {ctx.limit} ({ctx.limit_applied})")
        completion = ctx.serving.complete(body)                       # the same object that was counted
        if completion.client_prompt_tokens != prompt_tokens:
            raise serving.TelemetryMissing("the completion was not made for the counted request")
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


# ---------------------------------------------------------------------------
# the loop bridge (research D-2; contracts/arm-registration item 8; NFR-003)
# ---------------------------------------------------------------------------


class TransportPoisoned(RuntimeError):
    """The bridge's transport gate is shut (an unacknowledged termination, or the bridge closed): no query,
    no connection operation, nothing reaches FalkorDB any more."""


_PLAIN_TYPES = (str, bytes, bytearray, int, float, bool, type(None), list, tuple, dict, set, frozenset)


class TransportGate:
    """THE one boundary every byte the bridge could send to FalkorDB passes (review c2 invariant A).

    It wraps the FalkorDB client object. The installed ``FalkorDriver`` reaches the server ONLY through
    ``self.client`` — ``_get_graph`` → ``client.select_graph(name)`` → ``graph.query`` (also inside
    ``FalkorDriverSession.run``), ``close`` → ``client.aclose`` / ``client.connection`` — and every
    ``clone`` shares its parent's client (``falkor_db=self.client``). So installing the gate as the ROOT
    driver's client, before any clone exists, puts every clone, every per-question Graphiti and our own
    ``list_graphs`` behind it.

    The check runs on EVERY attribute access and call, and for an awaitable at the moment it starts
    running, not when it was created. Objects handed out (a graph handle, the connection) are wrapped the
    same way; the awaited results of queries are returned raw. Once ``shut`` is set nothing passes,
    whatever state the event loop is in — a coroutine resuming from blocked synchronous work included."""

    __slots__ = ("_shut", "_target")

    def __init__(self, target: Any, shut: threading.Event) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_shut", shut)

    def _check(self) -> None:
        if self._shut.is_set():
            raise TransportPoisoned("the G bridge's transport gate is shut; nothing may reach FalkorDB")

    def __getattr__(self, name: str) -> Any:
        self._check()
        return _gated(getattr(self._target, name), self._shut)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("the transport gate is read-only")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._check()
        result = self._target(*args, **kwargs)
        if hasattr(result, "__await__"):
            return _gated_await(result, self._shut)
        return _gated(result, self._shut)


def _gated(value: Any, shut: threading.Event) -> Any:
    return value if isinstance(value, _PLAIN_TYPES) else TransportGate(value, shut)


async def _gated_await(awaitable: Awaitable[Any], shut: threading.Event) -> Any:
    if shut.is_set():
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()                                                 # never started: nothing was sent
        raise TransportPoisoned("the G bridge's transport gate is shut; nothing may reach FalkorDB")
    return await awaitable


class Bridge:
    """G's registration-facing object: ONE asyncio loop on a dedicated thread, ONE :class:`GraphArm`
    (and so one root driver) bound to it. WP04's ``ARM_FACTORIES`` builds it with :func:`make_bridge`.

    Every graph operation (:meth:`build_graph`, :meth:`drop_graph`, :meth:`list_graphs`, and the
    retrieval half of :meth:`answer`) is submitted to the loop with ``run_coroutine_threadsafe`` and
    waited for on the CALLER's thread, honouring its ``deadline`` (``time.monotonic()`` seconds) and
    its ``cancelled`` flag. The serving half of :meth:`answer` runs on the caller's thread
    (:meth:`GraphArm.respond`). One operation at a time: a new one waits until the previous one's
    termination is acknowledged (NFR-003).

    **Cancellation is acknowledged by the coroutine, or the bridge raises.** On a deadline or the
    ``cancelled`` flag the loop-side task is cancelled, and the caller waits up to
    ``errors.G_CANCEL_GRACE_S`` for the acknowledgement flag the coroutine sets in its own
    cleanup — AFTER every other task on the bridge loop (a clone's ``_init_task`` included, and any
    task spawned while cancelling) is done. ``future.done()`` is NOT an acknowledgement: the concurrent
    future reports cancelled at once, while the coroutine may still be unwinding. After an
    acknowledgement, a terminal domain exception the work raised while unwinding (:data:`TERMINAL_EXCEPTIONS`)
    propagates as itself; otherwise the caller gets ``TimeoutError`` (an ordinary, retryable
    infrastructure failure). No acknowledgement STOPS the loop and then raises
    :class:`~arms849.errors.GCancellationUnacknowledged`; every later call raises it again and the
    bridge issues no further query — not even the cleanup in :meth:`close`. There is no driver
    replacement: resume happens in a fresh process, whose ``build_graph`` rebuilds idempotently.
    :meth:`close` is the one other cancellation source, and it goes through the same path.

    A live cell must always pass ``deadline`` / ``cancelled`` (WP04: ``CellContext.deadline`` and the
    harness's ``cancelled`` flag): without them an operation that never returns is waited for until
    :meth:`close` (or the process) ends it.
    """

    def __init__(self, arm: GraphArm) -> None:
        if arm._databases:
            raise RuntimeError("the transport gate must be installed before any per-question clone exists")
        self.arm = arm
        #: Shut FIRST on every fatal path and at close: the transport gate then refuses everything.
        self._shut = threading.Event()
        client = getattr(arm.driver, "client", None)
        if client is None:
            raise TypeError("the G bridge needs a FalkorDriver-shaped root driver (a .client to gate)")
        arm.driver.client = TransportGate(client, self._shut)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name=LOOP_THREAD_NAME, daemon=True)
        self._thread.start()
        self._lock = threading.Lock()                               # one operation (or the shutdown) at a time
        self._closing = threading.Event()
        self._poisoned: float | None = None                          # grace_s of an unacknowledged cancellation
        self._closed: bool | None = None                             # None: open; else close()'s result

    # -- the operations ------------------------------------------------------------

    def build_graph(self, question: Any, view: Loaded, *, deadline: float | None = None,
                    cancelled: threading.Event | None = None) -> GraphStats:
        return self._submit(lambda: self.arm.build_graph(question, view), deadline, cancelled,
                            f"build_graph {question.id}")

    def drop_graph(self, question: Any, *, deadline: float | None = None,
                   cancelled: threading.Event | None = None) -> None:
        self._submit(lambda: self.arm.drop_graph(question), deadline, cancelled, f"drop_graph {question.id}")

    def list_graphs(self, *, deadline: float | None = None, cancelled: threading.Event | None = None) -> list[str]:
        """The server's graph names, read-only (WP04 T020: ``graph_store_first_build.graphs_present``)."""
        return self._submit(self.arm.list_graphs, deadline, cancelled, "list_graphs")

    def answer(self, question: Any, view: Loaded, ctx: Any) -> dict[str, Any]:
        """contracts/arm-interface.md ``arm(question, view, ctx)`` for G. Retrieval on the loop under
        ``ctx.deadline`` and ``ctx.cancelled`` (WP04 adds ``CellContext.deadline``); serving on this
        thread via :meth:`GraphArm.respond`."""
        block, plan = self._submit(lambda: self.arm.plan_and_assemble(question, view), ctx.deadline, ctx.cancelled,
                                   f"retrieval {question.id}")
        return self.arm.respond(block, plan, question, ctx)

    def close(self) -> bool:
        """Shut down with ONE cancellation owner (review c1 finding 4): stop new submissions, let the active
        operation (if any) cancel itself through its OWN acknowledgement path, and only then quiesce and close
        the connection through the same mechanism, under the same bounded grace. Finally stop the loop and
        abandon its thread. Returns True only when all of that was acknowledged in time. After an
        unacknowledged cancellation it issues nothing — no cleanup query. Idempotent."""
        if self._closed is not None:
            return self._closed
        self._closing.set()                                         # refuses new work; cancels the active one
        owned = self._lock.acquire(timeout=errors.G_CANCEL_GRACE_S + HALT_JOIN_S + 1.0)
        try:
            if self._closed is not None:
                return self._closed
            clean = False
            if owned and self._poisoned is None:
                try:
                    self._run(self.arm.close, time.monotonic() + errors.G_CANCEL_GRACE_S, None, "close",
                              closing_cancels=False)
                    clean = True
                except (Exception, GCancellationUnacknowledged):  # noqa: BLE001 — close reports, never raises
                    clean = False
            self._shut.set()                                        # after close, nothing reaches FalkorDB
            stopped = self._halt_loop(errors.G_CANCEL_GRACE_S if clean else HALT_JOIN_S)
            clean = clean and stopped
            if clean:
                self._loop.close()
            self._closed = clean
            return clean
        finally:
            if owned:
                self._lock.release()

    # -- the mechanism ---------------------------------------------------------------

    def _poison(self, grace: float) -> NoReturn:
        """The ONE fatal path (review c2 invariants A and B): shut the transport gate FIRST — from then on no
        query can pass whatever the loop is doing — then mark the bridge, try to stop the loop (best effort:
        blocked synchronous work may keep it alive; the gate already makes that harmless), and raise."""
        self._shut.set()
        self._poisoned = grace
        self._halt_loop(min(HALT_JOIN_S, grace))
        raise GCancellationUnacknowledged(grace)

    def _halt_loop(self, join_s: float) -> bool:
        """Stop the loop and wait up to ``join_s`` for its thread: once it has returned, no coroutine of this
        bridge can take another step, so no further query can reach the transport."""
        if self._thread.is_alive():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except RuntimeError:                                    # the loop is already closed
                pass
            self._thread.join(join_s)
        return not self._thread.is_alive()

    async def _quiesce(self) -> bool:
        """Drain the bridge loop: every OTHER task — each one the bridge's work started (a clone's
        ``_init_task``, graphiti's gathered sub-queries) AND every task those spawn while being cancelled —
        cancelled once and awaited, until none is left (review c1 finding 3). Bounded by
        ``errors.G_CANCEL_GRACE_S``: returns False when work outlives it (a task that ignores its
        cancellation), and then no acknowledgement is given."""
        me = asyncio.current_task(self._loop)
        end = self._loop.time() + errors.G_CANCEL_GRACE_S
        asked: set[asyncio.Task[Any]] = set()
        while True:
            others = {t for t in asyncio.all_tasks(self._loop) if t is not me and not t.done()}
            if not others:
                return True
            remaining = end - self._loop.time()
            if remaining <= 0:
                return False
            for task in others - asked:                             # once each: never re-interrupt an unwind
                task.cancel()
            asked |= others
            await asyncio.wait(others, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)

    async def _guarded(self, make: Callable[[], Awaitable[T]], ack: threading.Event,
                       outcome: dict[str, BaseException]) -> tuple[str, Any]:
        """Run ``make()`` and, however it ends, drain the loop and THEN set ``ack`` — the coroutine's own
        acknowledgement. The outcome is RETURNED, never raised, and also kept in ``outcome``, so an
        exception the work raises while being cancelled survives the cancellation (review c1 finding 1).
        A coroutine being FINALISED (``GeneratorExit``: garbage-collected after its loop was abandoned,
        possibly while another loop runs on this thread) acknowledges nothing and touches no loop."""
        try:
            result = await make()
        except GeneratorExit:
            raise
        except BaseException as exc:                                # noqa: BLE001 — carried to the caller
            outcome["exc"] = exc
            if await self._quiesce():
                ack.set()                                           # THE acknowledgement: set by the coroutine
            return "raised", exc
        if await self._quiesce():
            ack.set()                                               # success counts ONLY once drained
        return "ok", result

    def _submit(self, make: Callable[[], Awaitable[T]], deadline: float | None,
                cancelled: threading.Event | None, what: str) -> T:
        if self._closing.is_set() or self._closed is not None:
            raise RuntimeError(f"G bridge is closed; {what} refused")
        with self._lock:
            if self._poisoned is not None:
                raise GCancellationUnacknowledged(self._poisoned)
            if self._closing.is_set() or self._closed is not None:
                raise RuntimeError(f"G bridge is closed; {what} refused")
            return self._run(make, deadline, cancelled, what)

    def _run(self, make: Callable[[], Awaitable[T]], deadline: float | None, cancelled: threading.Event | None,
             what: str, *, closing_cancels: bool = True) -> T:
        """One operation, the lock held. Waits on the caller's thread; on a stop reason cancels the task ONCE
        and waits for the coroutine's own acknowledgement. Then: a terminal domain exception the work raised
        (even while being cancelled) propagates as itself; otherwise ``TimeoutError`` (retryable, chained to
        an ordinary exception the work raised). No acknowledgement: the loop is STOPPED first, so the
        abandoned work can issue nothing further (review c1 finding 2), then GCancellationUnacknowledged."""
        if self._poisoned is not None:
            raise GCancellationUnacknowledged(self._poisoned)
        ack = threading.Event()
        outcome: dict[str, BaseException] = {}
        future = asyncio.run_coroutine_threadsafe(self._guarded(make, ack, outcome), self._loop)
        while True:
            if cancelled is not None and cancelled.is_set():
                why = "the attempt was cancelled"
                break
            if closing_cancels and self._closing.is_set():
                why = "the bridge is closing"
                break
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                why = "the attempt deadline passed"
                break
            concurrent.futures.wait([future], timeout=POLL_S if remaining is None else min(POLL_S, remaining))
            if future.done():
                if not ack.is_set():                                # finished, but the drain overran:
                    self._poison(errors.G_CANCEL_GRACE_S)          # exactly an unacknowledged termination
                kind, value = future.result()
                if kind == "raised":
                    raise value                                     # the coroutine's own exception, unaltered
                return value                                        # type: ignore[no-any-return]
        future.cancel()                                             # cancels the loop-side task, once
        grace = errors.G_CANCEL_GRACE_S
        if not ack.wait(grace):
            self._poison(grace)
        exc = outcome.get("exc")
        if isinstance(exc, TERMINAL_EXCEPTIONS):
            raise exc                                               # never downgraded to a retryable timeout
        raise TimeoutError(f"G {what}: {why}; the cancelled work acknowledged its termination within {grace} s") \
            from (exc if isinstance(exc, Exception) else None)


def make_bridge(embedder: Embedder, text: FrozenCorpusText, *, host: str = FALKOR_HOST, port: int = FALKOR_PORT,
                driver: GraphDriver | None = None) -> Bridge:
    """G's factory for WP04's ``ARM_FACTORIES`` (imported lazily there: this module imports graphiti).

    The root driver is ``FalkorDriver(host, port)`` — the compose service by default; ``host``/``port``
    (or a whole ``driver``) are injectable for tests. It is constructed HERE, on the calling thread
    with no running loop, so graphiti schedules no index build on the root database (which G never
    queries); its client binds to the bridge loop on first use."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("make_bridge must not run inside an event loop: the driver's client would bind to it")
    root = driver if driver is not None else FalkorDriver(host=host, port=port)
    return Bridge(GraphArm(root, embedder, text))


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
