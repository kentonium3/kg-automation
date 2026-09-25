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
— D-11), the :class:`ServingConfiguration` itself (``ctx.config``, or carried by
the serving facade as ``ctx.serving.config`` — contracts/arm-interface.md lists
it on ctx), and ``ctx.serving`` with ``serialize(request_bytes, seed) -> body``,
``count_tokens(body) -> int``, ``count_text(bytes) -> int`` and
``complete(body) -> Completion``. The arm does not trust ``ctx.limit``: before
counting it checks BOTH fields against what the configuration's
``limit_applied()`` says (Codex c4) — a pair that disagrees is a configuration
defect, refused, never a measured outcome.

The arm seam is ``arm(question, view, ctx)`` (contracts/arm-interface.md); this module's
:func:`arm_d` also takes the :class:`FrozenCorpusText` it renders from, so the harness binds it
once with :func:`bind` (``functools.partial``) and gets the contract's three-argument callable —
arm G holds its text on ``self`` the same way.

Refusals that are a CONFIGURATION defect, not an infrastructure failure — a view carrying
loader links, a request without ``cache_prompt``, an empty view, a ctx limit that is not the
configuration's, a request the gate admits but ``complete``'s last line refuses — raise
:class:`ArmRefusal`; the harness records them as the cell's terminal ``error`` without the
retry ladder (arm-interface: retries are for infrastructure).
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from scripts.research.arms849 import serving
from scripts.research.arms849.text import Block, FrozenCorpusText, edge_key, entity_key
from scripts.research.load_849_corpus import Loaded

__all__ = ["LAYOUT", "ArmRefusal", "ContextExceeded", "PlanRecord", "arm_d", "bind", "event_section", "prefix_check",
           "render_dump"]

#: The only layout arm D produces; asserted on every dump and recorded on every D row.
LAYOUT = "events_entities_edges"
_MISSING = object()
LIMIT_NAMES = ("trained", "permitted")


class ArmRefusal(RuntimeError):
    """A configuration defect (links handed to the flat arm, cache_prompt off, an empty view):
    terminal for the cell, never retried — the retry ladder is for infrastructure failures."""


class ContextExceeded(serving.ContextExceeded):
    """The exact request exceeds the limit this ledger applies; nothing was sent.

    A subclass of the serving module's exception, and the ONLY exceeds shape the arm lets
    out: the arm's own gate raises it, carrying the plan, the count and the limit the gate
    compared against, so every D ``exceeds_model_context`` row carries ``prompt_tokens`` >
    the limit (data-model I4) and a truthful ``context_limit_applied`` (D-11).

    A refusal from ``complete``'s last-line guard (the serving module's bare exception) is
    NOT re-raised as this type. On the primary the last line sits ``max_tokens`` below the
    trained limit (permitted 260,096 vs trained 262,144), so a count in that window passes
    the gate and is refused by the permitted limit while being ≤ the model context — I4
    cannot hold for it, and the earlier re-wrap named a "permitted limit 262144" that does
    not exist (Codex c4). Such a request is one the protocol cannot send: :class:`ArmRefusal`,
    terminal, with the true limit and its name read from the configuration. No registered
    question lands in the window (nearest: A 139,517 and F1 273,024).
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
    sha256 and its tokens ALONE (data-model.md § Row run: ``assembled_context_tokens`` is "the
    slot's tokens only — the cost primitive"), plus the D-11 fields every D row carries."""

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
    # A view WITHOUT the attribute is not a narrowed view either — same defect, same class.
    links = getattr(view, "links", _MISSING)
    if links is _MISSING:
        raise ArmRefusal("arm D was handed a view with no links attribute; not a narrowed ArmView")
    if links:
        raise ArmRefusal(f"arm D was handed {len(view.links)} loader links; the flat arm reads none "
                         "(Amendment A1 (b)) — narrow the view with arm_view first")


def render_dump(text: FrozenCorpusText, view: Loaded) -> tuple[Block, tuple[int, int, int]]:
    """The full-view block and (events, entities, edges) counts, with the layout ASSERTED.

    ``render_full_view`` is WP01's; this checks its output against the view rather than
    trusting the docstring: the event refs must be the view's events in view order and the
    record keys must be every entity, then every edge, in view order — nothing dropped,
    nothing re-ordered, nothing added.
    """
    _refuse_links(view)
    if not view.events or not view.entities or not view.edges:
        # The whole replay-visible view is never empty at any registered ask_time, and every
        # registered view carries edges (10 at C1); an edge-free dump is Codex blocker H-1
        # reappearing, so zero edges is refused like zero events (Opus WP06 c1, c2).
        raise ArmRefusal(f"arm D refuses an empty view: {len(view.events)} events, {len(view.entities)} "
                         f"entities, {len(view.edges)} edges — a section of the full dump is missing")
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


def _configuration(ctx: Any) -> serving.ServingConfiguration:
    """The active :class:`ServingConfiguration`: ``ctx.config`` (arm-interface lists it on ctx) or the
    one the serving facade serialises with (``ctx.serving.config``). Without it the limit cannot be
    checked, and an unchecked limit is a configuration defect in itself."""
    config = getattr(ctx, "config", None)
    if config is None:
        config = getattr(getattr(ctx, "serving", None), "config", None)
    if not isinstance(config, serving.ServingConfiguration):
        raise ArmRefusal("ctx carries no ServingConfiguration (neither ctx.config nor ctx.serving.config); "
                         "the context limit cannot be checked against the configuration (D-11)")
    return config


def _check_limit(ctx: Any, config: serving.ServingConfiguration) -> None:
    """``ctx.limit_applied`` and ``ctx.limit`` must BOTH be what ``config.limit_applied()`` says.

    A well-formed pair that is not the configuration's — ``("trained", 1)`` under the primary,
    the secondary's pair under the primary — would otherwise turn a configuration defect into a
    measured ``exceeds_model_context`` outcome and move the registered six-of-eight split
    (Codex c4)."""
    if ctx.limit_applied not in LIMIT_NAMES or type(ctx.limit) is not int or ctx.limit <= 0:
        raise ArmRefusal(f"incoherent context limit in ctx: {ctx.limit_applied!r} = {ctx.limit!r} "
                         f"(D-11: one of {LIMIT_NAMES}, a positive int, from ServingConfiguration.limit_applied())")
    name, limit = config.limit_applied()
    if (ctx.limit_applied, ctx.limit) != (name, limit):
        raise ArmRefusal(f"ctx applies the {ctx.limit_applied} limit {ctx.limit}, but the {config.kind} configuration "
                         f"applies the {name} limit {limit} (ServingConfiguration.limit_applied(), D-11) — "
                         f"a configuration defect, not an experimental outcome")


def arm_d(question: Any, view: Loaded, ctx: Any, text: FrozenCorpusText) -> dict[str, Any]:
    """contracts/arm-interface.md for D: dump → render → serialize → count → gate → complete.

    Returns the Answer as the dict the ledger's run row takes (WP05's shape, plus
    ``context_limit_applied``); raises :class:`ContextExceeded` — carrying the plan and the
    count — when the exact request exceeds ``ctx.limit`` (checked against the configuration
    first). ``complete`` is reached only through the gate, with the very ``body`` that was
    counted; a refusal from its last line is :class:`ArmRefusal`.
    """
    block, (n_events, n_entities, n_edges) = render_dump(text, view)
    request = ctx.prompt.render(block, question.text)
    body = ctx.serving.serialize(request, ctx.seed)
    if body.get("cache_prompt") is not True:
        raise ArmRefusal("arm D's requests carry cache_prompt: true (D-7: the prefix is the measurement)")
    config = _configuration(ctx)
    _check_limit(ctx, config)
    prompt_tokens = ctx.serving.count_tokens(body)                 # counts body["prompt"] — the string sent
    plan = PlanRecord(
        layout=LAYOUT, events_in_dump=n_events, entities_in_dump=n_entities, edges_in_dump=n_edges,
        assembled_context_sha256=block.sha256, assembled_context_tokens=ctx.serving.count_text(block.data),
        context_limit_applied=str(ctx.limit_applied), prompt_tokens=prompt_tokens,
    )
    if prompt_tokens > ctx.limit:
        raise ContextExceeded(prompt_tokens, ctx.limit, ctx.limit_applied, plan)
    try:
        completion = ctx.serving.complete(body)                      # the same object that was counted
    except ContextExceeded:
        raise                                                        # already carries the plan: propagate as is
    except serving.ContextExceeded as exc:                           # the last-line guard (permitted limit)
        # The gate admitted the request under this ledger's limit, so the count is ≤ the model
        # context and an exceeds_model_context row could not satisfy I4. The limit that refused
        # is the configuration's permitted one (n_ctx − max_tokens) — serving's exception carries
        # only a message, so it is read from the configuration, never from ctx.limit (Codex c4).
        lim = config.limits()
        raise ArmRefusal(f"complete refused the request at the permitted limit {lim.permitted} (configured "
                         f"{lim.configured} − max_tokens {config.max_tokens}) although it counted {prompt_tokens} "
                         f"tokens, within the {ctx.limit_applied} limit {ctx.limit} this ledger gates on; a request "
                         f"the gate admits and the protocol cannot send is a configuration defect, terminal — not "
                         f"exceeds_model_context (data-model I4 needs prompt_tokens > the model context)") from exc
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


def bind(text: FrozenCorpusText) -> Callable[[Any, Loaded, Any], dict[str, Any]]:
    """The contract's ``arm(question, view, ctx)`` for this corpus text."""
    return functools.partial(arm_d, text=text)
