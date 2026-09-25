"""Arm D — the full dump (WP06 T026).

The honest upper bound on recall where it can run, and a correctly classified
non-result where it cannot — decided **client-side, on the exact serialised
request, before anything is sent** (rubric §2 D row, A2, A4; research.md D-7,
D-11, D-13; spec FR-006, FR-009, SC-002).

The dump is the WHOLE replay-visible view — events, then entities, then edges —
through :meth:`FrozenCorpusText.render_full_view`, so the event section of each
D prompt is a byte prefix of the next in ask-time order and the cache hit rate
is a property of the protocol, not of the arm (D-7, gate-b-context-window.md).

The context gate and the request are ONE object: ``body`` is what
``ctx.serving.count_tokens`` counts and what ``ctx.serving.complete`` sends. A
reviewer can point at the string counted and the string sent and see they are
the same ``body["prompt"]``.

``ctx`` is the harness's CellContext, the same facade arm G uses (WP05):
``ctx.prompt`` (the registered :class:`Prompt`), ``ctx.seed`` (= 1000 + repeat),
``ctx.limit`` / ``ctx.limit_applied`` (``ServingConfiguration.limit_applied()``:
the trained limit for the primary ledger, the permitted limit for the secondary
— D-11), and ``ctx.serving`` with ``serialize(request_bytes, seed) -> body``,
``count_tokens(body) -> int``, ``count_text(bytes) -> int`` and
``complete(body) -> Completion``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scripts.research.arms849 import serving
from scripts.research.arms849.text import Block, FrozenCorpusText, edge_key, entity_key
from scripts.research.load_849_corpus import Loaded

__all__ = ["LAYOUT", "ContextExceeded", "PlanRecord", "arm_d", "event_section", "prefix_check", "render_dump"]

#: The only layout arm D produces; asserted on every dump and recorded on every D row.
LAYOUT = "events_entities_edges"


class ContextExceeded(serving.ContextExceeded):
    """The exact request exceeds the limit this ledger applies; nothing was sent.

    A subclass of the serving module's exception so the harness catches one type
    for both the arm's gate (first line) and ``complete``'s own guard (last line);
    this one carries what the D row records (D-11: ``prompt_tokens`` and
    ``context_limit_applied`` on every D row, scored or not).
    """

    def __init__(self, prompt_tokens: int, limit: int, limit_applied: str, plan: PlanRecord) -> None:
        self.prompt_tokens = int(prompt_tokens)
        self.limit = int(limit)
        self.limit_applied = str(limit_applied)
        self.plan = plan
        super().__init__(f"prompt is {self.prompt_tokens} tokens; {self.limit_applied} limit "
                         f"{self.limit} — exceeds_model_context, not sent")


@dataclass(frozen=True)
class PlanRecord:
    """data-model.md § PlanRecord, D: layout (asserted), the three dump counts, the block's
    sha256 and its tokens ALONE (rubric §5: assembled context excludes the fixed prompt and the
    question), plus the D-11 fields every D row carries."""

    layout: str
    events_in_dump: int
    entities_in_dump: int
    edges_in_dump: int
    assembled_context_sha256: str
    assembled_context_tokens: int
    context_limit_applied: str
    prompt_tokens: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _refuse_links(view: Loaded) -> None:
    # contracts/arm-interface.md: D receives ``view.links == []`` — the harness narrows, and the
    # arm refuses rather than trusts (a traversal input the flat arm must not have).
    if getattr(view, "links", None):
        raise ValueError(f"arm D was handed {len(view.links)} loader links; the flat arm reads none "
                         "(Amendment A1 (b)) — narrow the view with arm_view first")


def render_dump(text: FrozenCorpusText, view: Loaded) -> tuple[Block, tuple[int, int, int]]:
    """The full-view block and (events, entities, edges) counts, with the layout ASSERTED.

    ``render_full_view`` is WP01's; this checks its output against the view rather than
    trusting the docstring: the event refs must be the view's events in view order and the
    record keys must be every entity, then every edge, in view order — nothing dropped,
    nothing re-ordered, nothing added.
    """
    _refuse_links(view)
    block = text.render_full_view(view)
    want_refs = tuple(str(e["ref"]) for e in view.events)
    want_keys = tuple(entity_key(e) for e in view.entities) + tuple(edge_key(e) for e in view.edges)
    if block.event_refs != want_refs:
        raise AssertionError("dump events are not the view's events in view order")
    if block.record_keys != want_keys:
        raise AssertionError("dump records are not entities-then-edges in view order")
    # The bytes must be exactly the sections in that order: the event section first.
    events = event_section(text, view)
    if not block.data.startswith(events):
        raise AssertionError("dump bytes do not begin with the event section")
    records = text.render_block((), want_keys).data
    if block.data != events + records:
        raise AssertionError("dump bytes are not event section + record section")
    return block, (len(view.events), len(view.entities), len(view.edges))


def event_section(text: FrozenCorpusText, view: Loaded) -> bytes:
    """The bytes of the dump's event run alone — the shared prefix across D prompts."""
    return text.render_block((str(e["ref"]) for e in view.events), ()).data


def prefix_check(text: FrozenCorpusText, view_prev: Loaded, view_next: Loaded) -> bool:
    """NFR / rubric §2 layout protocol: the earlier question's event section is a byte prefix
    of the later's. Used by the tests and by WP10's re-measurement."""
    earlier = event_section(text, view_prev)
    later = event_section(text, view_next)
    return later.startswith(earlier)


def arm_d(question: Any, view: Loaded, ctx: Any, text: FrozenCorpusText) -> dict[str, Any]:
    """contracts/arm-interface.md for D: dump → render → serialize → count → gate → complete.

    Returns the Answer as the dict the ledger's run row takes (WP05's shape, plus
    ``context_limit_applied``); raises :class:`ContextExceeded` — carrying the plan and the
    count — when the exact request exceeds ``ctx.limit``. ``complete`` is reached only through
    the gate, with the very ``body`` that was counted.
    """
    block, (n_events, n_entities, n_edges) = render_dump(text, view)
    request = ctx.prompt.render(block, question.text)
    body = ctx.serving.serialize(request, ctx.seed)
    if body.get("cache_prompt") is not True:
        raise ValueError("arm D's requests carry cache_prompt: true (D-7: the prefix is the measurement)")
    prompt_tokens = ctx.serving.count_tokens(body)                 # counts body["prompt"] — the string sent
    plan = PlanRecord(
        layout=LAYOUT, events_in_dump=n_events, entities_in_dump=n_entities, edges_in_dump=n_edges,
        assembled_context_sha256=block.sha256, assembled_context_tokens=ctx.serving.count_text(block.data),
        context_limit_applied=str(ctx.limit_applied), prompt_tokens=prompt_tokens,
    )
    if prompt_tokens > ctx.limit:
        raise ContextExceeded(prompt_tokens, ctx.limit, ctx.limit_applied, plan)
    completion = ctx.serving.complete(body)                          # the same object that was counted
    for name in ("cache_read_tokens", "uncached_tokens", "cache_write_tokens", "cache_state", "cache_fraction",
                 "prefill_s", "generation_s", "generation_tok_s", "prompt_tokens", "output_tokens", "finish_reason"):
        if getattr(completion, name, None) is None:
            raise serving.TelemetryMissing(f"completion lacks {name}; no scored row (D-13)")
    if completion.client_prompt_tokens != prompt_tokens:
        raise serving.TelemetryMissing(f"the arm counted {prompt_tokens} but the completion was made for "
                                       f"{completion.client_prompt_tokens}; not the same request")
    return {
        "text": completion.text,
        "assembled_context_tokens": plan.assembled_context_tokens,
        "prompt_tokens": completion.prompt_tokens, "client_prompt_tokens": completion.client_prompt_tokens,
        "output_tokens": completion.output_tokens, "finish_reason": completion.finish_reason,
        "cache_read_tokens": completion.cache_read_tokens, "uncached_tokens": completion.uncached_tokens,
        "cache_write_tokens": completion.cache_write_tokens, "cache_state": completion.cache_state,
        "cache_fraction": completion.cache_fraction, "prefill_s": completion.prefill_s,
        "generation_s": completion.generation_s, "generation_tok_s": completion.generation_tok_s,
        "assembled_context_sha256": block.sha256, "context_limit_applied": plan.context_limit_applied,
        "plan": plan.as_dict(),
    }
