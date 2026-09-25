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
calibration record is refused. R supplies only the two inputs calibration needs —
:func:`r_tokens_for` and :func:`availability_cap`.

``ctx`` is the harness's CellContext, the facade arms G and D use, plus ``ctx.calibration``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from scripts.research.arms849 import serving
from scripts.research.arms849.embed import Embedder, cosine
from scripts.research.arms849.text import Block, FrozenCorpusText, edge_key, entity_key
from scripts.research.load_849_corpus import Loaded

__all__ = ["ASSEMBLED_ORDER", "ArmRefusal", "EventIndex", "PlanRecord", "arm_r", "assemble", "availability_cap",
           "bind", "r_tokens_for", "records_keys"]

ASSEMBLED_ORDER = "ask_time"
_MISSING = object()
LIMIT_NAMES = ("trained", "permitted")


class ArmRefusal(RuntimeError):
    """A configuration defect (contracts/arm-interface.md, dated note 2026-09-25): terminal, never retried —
    links handed to the flat arm, no calibration record, cache_prompt off, an index for another view."""


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
    links = getattr(view, "links", _MISSING)
    if links is _MISSING:
        raise ArmRefusal("arm R was handed a view with no links attribute; not a narrowed ArmView")
    if links:
        raise ArmRefusal(f"arm R was handed {len(links)} loader links; the flat arm reads none "
                         "(Amendment A1 (b)) — narrow the view with arm_view first")


def records_keys(view: Loaded) -> tuple[str, ...]:
    """Entities then edges, in view order — byte-for-byte the record section D inserts."""
    return tuple(entity_key(e) for e in view.entities) + tuple(edge_key(e) for e in view.edges)


def availability_cap(view: Loaded) -> int:
    """D-10: the number of events replay makes visible at the question's ask_time."""
    return len(view.events)


class EventIndex:
    """One vector per replay-visible event, embedded from its frozen line; deterministic."""

    def __init__(self, refs: tuple[str, ...], vectors: list[list[float]], embedder: Embedder) -> None:
        if len(refs) != len(vectors):
            raise ValueError("refs and vectors differ in length")
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate refs in the view")
        self.refs = refs                                    # view order == ask-time order
        self.vectors = vectors
        self.embedder = embedder
        self._position = {ref: i for i, ref in enumerate(refs)}

    @classmethod
    def build(cls, view: Loaded, embedder: Embedder, text: FrozenCorpusText) -> EventIndex:
        _refuse_links(view)
        refs = tuple(str(e["ref"]) for e in view.events)
        lines = [text.event_line(ref).decode("utf-8") for ref in refs]      # the frozen line, D-7
        return cls(refs, embedder.embed(lines), embedder)

    def position(self, ref: str) -> int:
        return self._position[ref]

    def retrieve(self, question_text: str, k: int) -> list[str]:
        """Top-k by cosine to the question, ties by ref ascending; rank order."""
        if k < 0:
            raise ValueError("k must be >= 0")
        if k == 0:
            return []
        q = self.embedder.embed_one(question_text)
        scored = sorted(((-cosine(q, v), ref) for ref, v in zip(self.refs, self.vectors, strict=True)))
        return [ref for _, ref in scored[:k]]


def assemble(text: FrozenCorpusText, view: Loaded, index: EventIndex, retrieved_by_rank: list[str], k: int) -> tuple[Block, dict[str, Any]]:
    """Re-sort the retrieved refs into ask-time order and render them with the records."""
    _refuse_links(view)
    if index.refs != tuple(str(e["ref"]) for e in view.events):
        raise ArmRefusal("index was built for a different view")
    if len(set(retrieved_by_rank)) != len(retrieved_by_rank) or len(retrieved_by_rank) > min(k, len(index.refs)):
        raise ArmRefusal("retrieved refs must be distinct and at most min(k, available)")
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


def arm_r(question: Any, view: Loaded, ctx: Any, text: FrozenCorpusText, index: EventIndex | None = None) -> dict[str, Any]:
    """contracts/arm-interface.md for R. k comes from ctx.calibration — never a default."""
    calibration = getattr(ctx, "calibration", None)
    if calibration is None:
        raise ArmRefusal("arm R refuses to run without a calibration record (D-10): k is never defaulted")
    k = calibration.k if not isinstance(calibration, dict) else calibration.get("k")
    if type(k) is not int or k < 0:
        raise ArmRefusal(f"calibration record carries no usable k: {k!r}")
    if ctx.limit_applied not in LIMIT_NAMES or type(ctx.limit) is not int or ctx.limit <= 0:
        raise ArmRefusal(f"incoherent context limit in ctx: {ctx.limit_applied!r} = {ctx.limit!r}")
    _refuse_links(view)
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
    """The contract's ``arm(question, view, ctx)``; an optional per-question index cache (NFR-005:
    repeats must see byte-identical context — the embedder is deterministic, so a cached index and a
    rebuilt one assemble the same bytes; the cache is for speed and is keyed by question id)."""
    cache = index_cache if index_cache is not None else {}

    def arm(question: Any, view: Loaded, ctx: Any) -> dict[str, Any]:
        index = cache.get(question.id)
        if index is None or index.refs != tuple(str(e["ref"]) for e in view.events):
            index = EventIndex.build(view, ctx.embedder, text)
            cache[question.id] = index
        return arm_r(question, view, ctx, text, index)

    return arm
