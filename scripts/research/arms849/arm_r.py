"""Arm R — vector RAG over events + the structured records (WP07 T028/T029).

Rubric §2 R row as amended by A4; research.md D-4, D-10. The replay-visible RECORDS
(entities, then edges — the same canonical lines D inserts) are always present as the
structured half; the retrieval half is top-k cosine retrieval over EVENTS ONLY, one event per
chunk, embedded from the frozen event line with the embedder R shares with G
(``arms849.embed.Embedder`` — imported, never redefined). Retrieved events are re-sorted into
ask-time order (their position in the replayed view, which is the stream's time order) before
insertion so R's layout is D's layout on a subset and its cache prefix is meaningful.

R has ONE free parameter, k, and never chooses it: every cell reads k from the calibration
record the harness wrote (D-10, implemented once in ``arms849.calibration``); a cell without a
calibration record is refused. R supplies calibration its two inputs through ONE bound adapter,
:func:`calibration_inputs` — ``availability`` per question and ``assemble_r_tokens(qid, k)`` —
composed from the primitives :func:`availability_cap` and :func:`r_tokens_for`, over the SAME
per-question index cache the R cells later read, so calibration and the cells embed once and
identically.

An :class:`EventIndex` carries the identity of the view it was built from — ``view_digest``, the
sha256 of the embedder's model name and the exact frozen event bytes in view order — and every
assembly re-validates the index against the view it is asked to serve: an index built for other
bytes (another ask_time, another corpus copy, another model) is refused, never reused.

``ctx`` is the harness's CellContext, the facade arms G and D use, plus ``ctx.calibration``. The
active :class:`ServingConfiguration` is ``ctx.config`` (contracts/arm-interface.md); the
``ctx.serving.config`` fallback is tolerated until WP08 lands CellContext. As in arm D, the ctx's
applied limit pair is checked against the configuration BEFORE anything is counted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from scripts.research.arms849 import questions, serving
from scripts.research.arms849.embed import Embedder, cosine
from scripts.research.arms849.text import Block, FrozenCorpusText, edge_key, entity_key
from scripts.research.load_849_corpus import Loaded

__all__ = ["ASSEMBLED_ORDER", "ArmRefusal", "EventIndex", "PlanRecord", "arm_r", "assemble", "availability_cap",
           "bind", "calibration_inputs", "index_for", "r_tokens_for", "records_keys"]

ASSEMBLED_ORDER = "ask_time"
_MISSING = object()
LIMIT_NAMES = ("trained", "permitted")


class ArmRefusal(RuntimeError):
    """A configuration defect (contracts/arm-interface.md, dated note 2026-09-25): terminal, never retried —
    links handed to the flat arm, an empty view, no usable calibration record, cache_prompt off, a ctx
    limit that is not the configuration's, an index built for another view."""


@dataclass(frozen=True)
class PlanRecord:
    """data-model.md § PlanRecord, R."""

    k: int
    retrieved_refs_by_rank: list[str]          # rank order — recorded, never shown to the model
    assembled_order: str
    entities_in_records: int
    edges_in_records: int
    availability_capped: bool
    events_available: int
    assembled_context_sha256: str
    assembled_context_tokens: int
    context_limit_applied: str
    prompt_tokens: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _refuse_links(view: Loaded) -> None:
    if getattr(view, "links", _MISSING) is _MISSING:
        raise ArmRefusal("arm R was handed a view with no links attribute; not a narrowed ArmView")
    if view.links:
        raise ArmRefusal(f"arm R was handed {len(view.links)} loader links; the flat arm reads none "
                         "(Amendment A1 (b)) — narrow the view with arm_view first")


def _refuse_empty(view: Loaded) -> None:
    # Parity with arm D's render_dump: the replay-visible view is never empty at any registered
    # ask_time and every registered view carries edges; a missing section is a configuration
    # defect, not a retrieval population of size zero.
    if not view.events or not view.entities or not view.edges:
        raise ArmRefusal(f"arm R refuses an empty view: {len(view.events)} events, {len(view.entities)} "
                         f"entities, {len(view.edges)} edges — a section of the records or the retrieval "
                         f"population is missing")


def _model_name(embedder: Any) -> str:
    model = getattr(embedder, "model", None)
    if not isinstance(model, str) or not model:
        raise ArmRefusal("the embedder carries no model name; an index cannot record which model embedded it")
    return model


def records_keys(view: Loaded) -> tuple[str, ...]:
    """Entities then edges, in view order — byte-for-byte the record section D inserts."""
    return tuple(entity_key(e) for e in view.entities) + tuple(edge_key(e) for e in view.edges)


def availability_cap(view: Loaded) -> int:
    """D-10: the number of events replay makes visible at the question's ask_time."""
    return len(view.events)


class EventIndex:
    """One vector per replay-visible event, embedded from its frozen line; deterministic.

    ``view_digest`` identifies the view the vectors were made from — the model name and the exact
    frozen event bytes in view order (:meth:`digest_for`) — and is what every consumer validates
    against; refs alone would accept another corpus copy with the same refs and different bytes.
    Rankings are computed once per question text and sliced per k (:meth:`retrieve`), so the
    calibration's k = 1..max_k sweep neither re-embeds the question nor re-sorts.
    """

    def __init__(self, refs: tuple[str, ...], vectors: list[list[float]], embedder: Embedder, view_digest: str) -> None:
        if len(refs) != len(vectors):
            raise ValueError("refs and vectors differ in length")
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate refs in the view")
        self.refs = refs                                    # view order == ask-time order
        self.vectors = vectors
        self.embedder = embedder
        self.model = _model_name(embedder)
        self.view_digest = str(view_digest)
        self._position = {ref: i for i, ref in enumerate(refs)}
        self._rankings: dict[str, list[str]] = {}          # question text → every ref, rank order

    @staticmethod
    def digest_for(text: FrozenCorpusText, view: Loaded, model: str) -> str:
        """sha256 over the model name, then each event's exact frozen line (+ LF) in view order."""
        h = hashlib.sha256(model.encode("utf-8") + b"\n")
        for e in view.events:
            h.update(text.event_line(str(e["ref"])) + b"\n")
        return h.hexdigest()

    @classmethod
    def build(cls, view: Loaded, embedder: Embedder, text: FrozenCorpusText) -> EventIndex:
        _refuse_links(view)
        _refuse_empty(view)
        model = _model_name(embedder)
        refs = tuple(str(e["ref"]) for e in view.events)
        lines = [text.event_line(ref).decode("utf-8") for ref in refs]      # the frozen line, D-7
        return cls(refs, embedder.embed(lines), embedder, cls.digest_for(text, view, model))

    def serves(self, text: FrozenCorpusText, view: Loaded) -> bool:
        """True iff this index was built from exactly this view's frozen bytes with this model."""
        return self.view_digest == self.digest_for(text, view, self.model)

    def position(self, ref: str) -> int:
        return self._position[ref]

    def ranking(self, question_text: str) -> list[str]:
        """Every ref by cosine to the question (desc), ties by ref ascending; computed once per text."""
        ranked = self._rankings.get(question_text)
        if ranked is None:
            q = self.embedder.embed_one(question_text)
            scored = sorted(((-cosine(q, v), ref) for ref, v in zip(self.refs, self.vectors, strict=True)))
            ranked = [ref for _, ref in scored]
            self._rankings[question_text] = ranked
        return ranked

    def retrieve(self, question_text: str, k: int) -> list[str]:
        """Top-k by cosine to the question, ties by ref ascending; rank order."""
        if k < 0:
            raise ValueError("k must be >= 0")
        if k == 0:
            return []
        return list(self.ranking(question_text)[:k])


def assemble(text: FrozenCorpusText, view: Loaded, index: EventIndex, retrieved_by_rank: list[str], k: int) -> tuple[Block, dict[str, Any]]:
    """Re-sort the retrieved refs into ask-time order and render them with the records."""
    _refuse_links(view)
    _refuse_empty(view)
    if not index.serves(text, view):
        raise ArmRefusal("index was built for a different view (its frozen event bytes or embedder model differ)")
    if len(set(retrieved_by_rank)) != len(retrieved_by_rank):
        raise ArmRefusal("retrieved refs must be distinct")
    expected = min(int(k), len(index.refs))
    if len(retrieved_by_rank) != expected:
        raise ArmRefusal(f"assembly for k={k} over {len(index.refs)} available events takes exactly {expected} "
                         f"retrieved refs, got {len(retrieved_by_rank)}")
    # Ask-time order = the event's POSITION in the replayed view (the stream's time order), not a
    # literal (at, ref) sort: the stream has same-`at` runs that are not ref-ascending, and R's
    # events must be a subsequence of D's dump for the two layouts to match.
    in_order = sorted(retrieved_by_rank, key=index.position)
    keys = records_keys(view)
    block = text.render_block(in_order, keys)
    plan = {
        "k": int(k), "retrieved_refs_by_rank": list(retrieved_by_rank), "assembled_order": ASSEMBLED_ORDER,
        "entities_in_records": len(view.entities), "edges_in_records": len(view.edges),
        "availability_capped": int(k) > len(index.refs), "events_available": len(index.refs),
        "assembled_context_sha256": block.sha256,
    }
    return block, plan


def r_tokens_for(question: Any, view: Loaded, k: int, tokenizer: Any, text: FrozenCorpusText, index: EventIndex) -> int:
    """D-10 input: the EXACT token count of the bytes R would insert for candidate k."""
    block, _ = assemble(text, view, index, index.retrieve(question.text, k), k)
    return int(tokenizer.count(block.data))


def index_for(question_id: str, view: Loaded, embedder: Embedder, text: FrozenCorpusText,
              index_cache: dict[str, EventIndex]) -> EventIndex:
    """The cached index for this question if it serves this view (view_digest), else build and cache.

    The cache key stays the question id; identity is the digest. Calibration and the R cells go
    through this one door, so the index a question's cells retrieve from IS the object its
    calibration counted over (NFR-005: byte-identical context; one embedding per question)."""
    index = index_cache.get(question_id)
    if index is None or index.model != _model_name(embedder) or not index.serves(text, view):
        index = EventIndex.build(view, embedder, text)
        index_cache[question_id] = index
    return index


def calibration_inputs(text: FrozenCorpusText, tokenizer: Any, embedder: Embedder, views: Mapping[str, Loaded],
                       index_cache: dict[str, EventIndex]) -> tuple[dict[str, int], Callable[[str, int], int]]:
    """The ONE bound adapter for ``arms849.calibration.calibrate(ledger, availability, assemble_r_tokens)``.

    Resolves each question's view and index internally (the index is built once, into
    ``index_cache`` — the same cache :func:`bind` reads) and returns ``availability`` =
    {qid: :func:`availability_cap`} and ``assemble_r_tokens(qid, k)`` = :func:`r_tokens_for` over that
    question's index. R never calls ``calibrate``; the harness does, once, as
    ``calibrate(ledger, *calibration_inputs(...))``.
    """
    resolved: dict[str, tuple[Any, Loaded, EventIndex]] = {}
    availability: dict[str, int] = {}
    for qid, view in views.items():
        question = questions.by_id(qid)
        _refuse_links(view)
        _refuse_empty(view)
        resolved[qid] = (question, view, index_for(qid, view, embedder, text, index_cache))
        availability[qid] = availability_cap(view)

    def assemble_r_tokens(question_id: str, k: int) -> int:
        try:
            question, view, index = resolved[question_id]
        except KeyError:
            raise ArmRefusal(f"calibration asked for {question_id!r}, which has no view in this adapter") from None
        return r_tokens_for(question, view, k, tokenizer, text, index)

    return availability, assemble_r_tokens


def _calibrated_k(ctx: Any) -> int:
    """k from ``ctx.calibration`` — the ledger's dict record or the Calibration object — never a default."""
    calibration = getattr(ctx, "calibration", None)
    if calibration is None:
        raise ArmRefusal("arm R refuses to run without a calibration record (D-10): k is never defaulted")
    if isinstance(calibration, Mapping):
        kind = calibration.get("record", "calibration")
        if kind != "calibration":
            raise ArmRefusal(f"ctx.calibration is not a calibration record: record={kind!r}")
        k = calibration.get("k", _MISSING)
    else:
        k = getattr(calibration, "k", _MISSING)
    if k is _MISSING:
        raise ArmRefusal("calibration record carries no k at all; D-10 must have run and written one")
    if type(k) is not int or k < 0:
        raise ArmRefusal(f"calibration record carries no usable k: {k!r}")
    return k


def _configuration(ctx: Any) -> serving.ServingConfiguration:
    """The active :class:`ServingConfiguration`: ``ctx.config`` (the contract name) or, until WP08 lands
    CellContext, the one the serving facade serialises with (``ctx.serving.config``). Without it the limit
    cannot be checked, and an unchecked limit is a configuration defect in itself (arm D's shape)."""
    config = getattr(ctx, "config", None)
    if config is None:
        config = getattr(getattr(ctx, "serving", None), "config", None)
    if not isinstance(config, serving.ServingConfiguration):
        raise ArmRefusal("ctx carries no ServingConfiguration (neither ctx.config nor ctx.serving.config); "
                         "the context limit cannot be checked against the configuration (D-11)")
    return config


def _check_limit(ctx: Any, config: serving.ServingConfiguration) -> None:
    """``ctx.limit_applied`` and ``ctx.limit`` must BOTH be what ``config.limit_applied()`` says — a
    well-formed pair that is not the configuration's would turn a configuration defect into a measured
    ``exceeds_model_context`` outcome (arm D, Codex c4); R refuses identically."""
    if ctx.limit_applied not in LIMIT_NAMES or type(ctx.limit) is not int or ctx.limit <= 0:
        raise ArmRefusal(f"incoherent context limit in ctx: {ctx.limit_applied!r} = {ctx.limit!r} "
                         f"(D-11: one of {LIMIT_NAMES}, a positive int, from ServingConfiguration.limit_applied())")
    name, limit = config.limit_applied()
    if (ctx.limit_applied, ctx.limit) != (name, limit):
        raise ArmRefusal(f"ctx applies the {ctx.limit_applied} limit {ctx.limit}, but the {config.kind} configuration "
                         f"applies the {name} limit {limit} (ServingConfiguration.limit_applied(), D-11) — "
                         f"a configuration defect, not an experimental outcome")


def arm_r(question: Any, view: Loaded, ctx: Any, text: FrozenCorpusText, index: EventIndex | None = None) -> dict[str, Any]:
    """contracts/arm-interface.md for R. k comes from ctx.calibration — never a default."""
    k = _calibrated_k(ctx)
    _refuse_links(view)
    _refuse_empty(view)
    _check_limit(ctx, _configuration(ctx))                          # before anything is counted
    if index is None:
        index = EventIndex.build(view, ctx.embedder, text)
    retrieved = index.retrieve(question.text, k)
    block, plan = assemble(text, view, index, retrieved, k)
    request = ctx.prompt.render(block, question.text)
    body = ctx.serving.serialize(request, ctx.seed)
    if body.get("cache_prompt") is not True:
        raise ArmRefusal("arm R's requests carry cache_prompt: true")
    prompt_tokens = ctx.serving.count_tokens(body)
    assembled_tokens = ctx.serving.count_text(block.data)
    record = PlanRecord(**plan, assembled_context_tokens=assembled_tokens,
                        context_limit_applied=str(ctx.limit_applied), prompt_tokens=prompt_tokens)
    if prompt_tokens > ctx.limit:
        raise serving.ContextExceeded(f"prompt is {prompt_tokens} tokens; {ctx.limit_applied} limit {ctx.limit} — not sent")
    completion = ctx.serving.complete(body)                          # the same object that was counted
    if completion.client_prompt_tokens != prompt_tokens:
        raise serving.TelemetryMissing("the completion was not made for the counted request")
    # r_g_ratio is the HARNESS's field (contracts/arm-interface.md: "the harness adds … r_g_ratio (R)")
    # via calibration.ratio_for — the arm reports its assembled tokens and never computes the ratio.
    return {
        "text": completion.text,
        "assembled_context_tokens": assembled_tokens,
        "prompt_tokens": completion.prompt_tokens, "client_prompt_tokens": completion.client_prompt_tokens,
        "output_tokens": completion.output_tokens, "finish_reason": completion.finish_reason,
        "cache_read_tokens": completion.cache_read_tokens, "uncached_tokens": completion.uncached_tokens,
        "cache_write_tokens": completion.cache_write_tokens, "cache_state": completion.cache_state,
        "cache_fraction": completion.cache_fraction, "prefill_s": completion.prefill_s,
        "generation_s": completion.generation_s, "generation_tok_s": completion.generation_tok_s,
        "assembled_context_sha256": block.sha256, "context_limit_applied": record.context_limit_applied,
        "plan": record.as_dict(),
    }


def bind(text: FrozenCorpusText, index_cache: dict[str, EventIndex] | None = None) -> Callable[[Any, Loaded, Any], dict[str, Any]]:
    """The contract's ``arm(question, view, ctx)`` over a per-question index cache — the SAME cache
    :func:`calibration_inputs` populated (NFR-005: repeats and calibration see byte-identical context;
    the embedder is deterministic, so a cached index and a rebuilt one assemble the same bytes, and the
    cache is for embedding once). Keyed by question id; validated by view_digest on every cell."""
    cache = index_cache if index_cache is not None else {}

    def arm(question: Any, view: Loaded, ctx: Any) -> dict[str, Any]:
        return arm_r(question, view, ctx, text, index_for(question.id, view, ctx.embedder, text, cache))

    return arm
