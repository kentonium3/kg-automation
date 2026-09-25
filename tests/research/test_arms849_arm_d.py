"""WP06 T027 — arm D against the real frozen corpus and the cached Qwen tokenizer.

Skipped (not faked) when either is absent: the six-of-eight split and the B2 floor are
measurements, and a measurement of a stand-in proves nothing.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import pathlib
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import arm_d as D
from scripts.research.arms849 import questions as Q
from scripts.research.arms849 import serving as S
from scripts.research.arms849.prompt import Prompt
from scripts.research.arms849.text import FrozenCorpusText, record_line_bytes
from scripts.research.load_849_corpus import DEFAULT_CORPUS, replay

PKG = REPO_ROOT / "scripts" / "research" / "arms849"
CORPUS = pathlib.Path(os.environ.get("ARMS849_CORPUS", str(DEFAULT_CORPUS)))
CACHE = pathlib.Path(os.environ.get("ARMS849_CACHE", str(REPO_ROOT / "build" / "849-cache")))
needs_corpus = pytest.mark.skipif(not (CORPUS / "stream.jsonl").exists(), reason="rendered corpus absent")
needs_tokenizer = pytest.mark.skipif(not (CACHE / "qwen-tokenizer").exists(), reason="cached tokenizer absent")

ASK_ORDER = tuple(q.id for q in Q.QUESTIONS)                       # C1 A F1 B1 E2 E1 F2 B2
REGISTERED_B2_PREFIX = 362_772                                     # rubric §2, A1 @c0b35cd1 — a floor now
EXPECTED_EXCEEDING = frozenset({"F1", "B1", "E2", "E1", "F2", "B2"})   # rubric A2: six of eight
SECONDARY_PERMITTED = S.SECONDARY_N_CTX - S.MAX_TOKENS             # 393,216 − 2,048


# ---------------------------------------------------------------------------
# the harness facade, as WP05's answer() and WP08's CellContext shape it
# ---------------------------------------------------------------------------


class Facade:
    """The serving facade: real serialize/count over the cached tokenizer; a canned ``complete``.

    Counts are memoised by text digest — the arm counts the same 360k-token string under
    both limits and the test would otherwise spend minutes re-tokenising it.
    """

    def __init__(self, tok: S.Tokenizer, config: S.ServingConfiguration, responder=None) -> None:
        self.tok, self.config = tok, config
        self.responder = responder or self.plain_response
        self.sent: list[dict] = []
        self.counted: list[int] = []
        self._memo: dict[str, int] = {}

    def _count(self, text: str | bytes) -> int:
        raw = text if isinstance(text, bytes) else text.encode("utf-8")
        key = hashlib.sha256(raw).hexdigest()
        if key not in self._memo:
            self._memo[key] = self.tok.count(text)
        return self._memo[key]

    def serialize(self, request: bytes, seed: int) -> dict:
        return S.serialize(request, self.config, seed, self.tok)

    def count_tokens(self, body: dict) -> int:
        self.counted.append(id(body))
        return self._count(body["prompt"])

    def count_text(self, data: bytes) -> int:
        return self._count(data)

    @staticmethod
    def plain_response(client: int) -> dict:
        # gate-b-context-window.md: ~154 tok/s cumulative prefill at 256k, ~20 tok/s generation
        return {"content": "answer", "stop_type": "eos",
                "timings": {"prompt_n": client, "cache_n": 0, "prompt_ms": client / 154 * 1000,
                            "predicted_n": 128, "predicted_ms": 128 / 20 * 1000}}

    def complete(self, body: dict) -> S.Completion:
        self.sent.append(body)
        client = self._count(body["prompt"])
        return S.map_timings(self.responder(client), client)


def ctx_for(facade: Facade, kind: str) -> SimpleNamespace:
    name, limit = facade.config.limit_applied()
    assert (kind == "primary") == (name == "trained")
    return SimpleNamespace(prompt=Prompt(), seed=facade.config.seed_for(1), limit=limit, limit_applied=name,
                           serving=facade)


@pytest.fixture(scope="module")
def tok() -> S.Tokenizer:
    return S.Tokenizer(CACHE / "qwen-tokenizer")


@pytest.fixture(scope="module")
def identity(tok) -> S.ServingIdentity:
    return S.ServingIdentity("gguf", "sha256:img", "emb", "tok", tok.chat_template_sha256())


@pytest.fixture(scope="module")
def text() -> FrozenCorpusText:
    return FrozenCorpusText(CORPUS)


@pytest.fixture(scope="module")
def views() -> dict:
    out = {}
    for q in Q.QUESTIONS:
        view = replay(CORPUS, Q.ask_time_dt(q), verify=False)
        view.links = []                                            # what arm_view hands D
        out[q.id] = view
    return out


@pytest.fixture(scope="module")
def run_all(tok, identity, text, views):
    """arm_d over all eight questions under one configuration; returns (facade, outcomes)."""

    def _run(kind: str, responder=None):
        config = (S.ServingConfiguration.primary(identity) if kind == "primary"
                  else S.ServingConfiguration.secondary_yarn(identity))
        facade = Facade(tok, config, responder)
        ctx = ctx_for(facade, kind)
        outcomes: dict[str, object] = {}
        for q in Q.QUESTIONS:
            try:
                outcomes[q.id] = D.arm_d(q, views[q.id], ctx, text)
            except D.ContextExceeded as exc:
                outcomes[q.id] = exc
        return facade, outcomes

    return _run


# ---------------------------------------------------------------------------
# (a) the six/zero split — SC-002 and D-11 in one test
# ---------------------------------------------------------------------------


@needs_corpus
@needs_tokenizer
def test_primary_refuses_exactly_six_and_secondary_refuses_none(run_all):
    facade, primary = run_all("primary")
    exceeded = {q for q, o in primary.items() if isinstance(o, D.ContextExceeded)}
    counts = {q: (o.prompt_tokens if isinstance(o, D.ContextExceeded) else o["prompt_tokens"]) for q, o in primary.items()}
    assert exceeded == EXPECTED_EXCEEDING, f"exceeded {sorted(exceeded)}; measured {counts}"
    # For WP10's re-measurement: every question's exact serialised request size, written to a JSON
    # artifact that survives pytest's capture (Opus c2) — and printed for a -s run.
    artifact = REPO_ROOT / "build" / "849-runs" / "arm-d-measured-prompt-tokens.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps({"chat_templated_request_tokens": {q: counts[q] for q in ASK_ORDER},
                                    "trained_limit": S.TRAINED_CONTEXT, "secondary_permitted": SECONDARY_PERMITTED,
                                    "exceeding_trained": sorted(exceeded)}, indent=2) + "\n")
    print("MEASURED prompt_tokens (chat-templated request) " + json.dumps({q: counts[q] for q in ASK_ORDER}))
    assert len(exceeded) == 6
    assert len(facade.sent) == 2 and {json.loads(json.dumps(b))["seed"] for b in facade.sent} == {1001}
    for q in exceeded:
        exc = primary[q]
        assert exc.limit == S.TRAINED_CONTEXT and exc.limit_applied == "trained"
        assert exc.prompt_tokens > S.TRAINED_CONTEXT
        assert exc.plan.layout == D.LAYOUT and exc.plan.context_limit_applied == "trained"
        assert isinstance(exc, S.ContextExceeded)                  # the harness catches one type
    for q in ASK_ORDER:
        if q not in exceeded:
            row = primary[q]
            assert row["context_limit_applied"] == "trained" and row["prompt_tokens"] == counts[q]
            assert row["plan"]["prompt_tokens"] == counts[q]

    facade2, secondary = run_all("secondary")
    assert not any(isinstance(o, D.ContextExceeded) for o in secondary.values()), \
        {q: o for q, o in secondary.items() if isinstance(o, D.ContextExceeded)}
    assert len(facade2.sent) == 8
    assert all(o["context_limit_applied"] == "permitted" for o in secondary.values())
    assert all(o["prompt_tokens"] <= SECONDARY_PERMITTED for o in secondary.values()), \
        {q: o["prompt_tokens"] for q, o in secondary.items()}
    # The same request under both configurations counts the same (the template and the text
    # are identical; only the limit differs).
    assert {q: o["prompt_tokens"] for q, o in secondary.items()} == counts


# ---------------------------------------------------------------------------
# (b) the B2 floor — recorded for WP10's re-measurement
# ---------------------------------------------------------------------------


@needs_corpus
@needs_tokenizer
def test_b2_prompt_tokens_at_least_the_registered_prefix(run_all):
    _, primary = run_all("primary")
    measured = primary["B2"].prompt_tokens
    assert measured >= REGISTERED_B2_PREFIX, f"B2 measured {measured} < registered {REGISTERED_B2_PREFIX}"
    # For the record (WP10 cites this): the exact serialised request, chat template included.
    print(f"MEASURED B2 prompt_tokens = {measured} (registered prefix floor {REGISTERED_B2_PREFIX})")
    assert measured - REGISTERED_B2_PREFIX < 50_000, "the floor is a floor, not a different corpus"


# ---------------------------------------------------------------------------
# (c) the event section is a byte prefix across the eight in ask-time order
# ---------------------------------------------------------------------------


@needs_corpus
def test_event_section_is_a_byte_prefix_in_ask_time_order(text, views):
    for earlier, later in itertools.pairwise(ASK_ORDER):
        assert D.prefix_check(text, views[earlier], views[later]), (earlier, later)
        assert len(D.event_section(text, views[later])) > len(D.event_section(text, views[earlier]))
    # and not the other way round: the later section is longer and is not a prefix of the earlier
    assert not D.prefix_check(text, views["B2"], views["C1"])
    # the WHOLE prompt is not a prefix (records sit between); only the event run is (D-7)
    b_c1, _ = D.render_dump(text, views["C1"])
    b_a, _ = D.render_dump(text, views["A"])
    assert not b_a.data.startswith(b_c1.data)


# ---------------------------------------------------------------------------
# (d) entities and edges follow events, never precede
# ---------------------------------------------------------------------------


@needs_corpus
def test_records_follow_events_in_every_dump(text, views):
    for q in ASK_ORDER:
        view = views[q]
        block, (ne, nn, nd) = D.render_dump(text, view)
        events = D.event_section(text, view)
        assert block.data.startswith(events)
        assert (ne, nn, nd) == (len(view.events), len(view.entities), len(view.edges))
        assert nd > 0 and nn > 0, "the dump carries records — edges included (Codex H-1)"
        records = block.data[len(events):]
        first_record = text.record_line(block.record_keys[0])
        assert records.startswith(first_record + b"\n")
        # entity keys precede edge keys; no interleaving
        kinds = ["edge" if k in text.edge_keys else "entity" for k in block.record_keys]
        assert kinds == sorted(kinds, key=lambda k: k == "edge")


@needs_corpus
def test_render_dump_refuses_a_reordered_or_incomplete_full_view(text, views, monkeypatch):
    view = views["C1"]
    good = text.render_full_view(view)

    def records_first(_view):
        return text.render_block((), good.record_keys).__class__(
            event_refs=good.event_refs, record_keys=good.record_keys,
            data=text.render_block((), good.record_keys).data + text.render_block(good.event_refs, ()).data)

    monkeypatch.setattr(text, "render_full_view", records_first)
    with pytest.raises(AssertionError, match="begin with the event section"):
        D.render_dump(text, view)
    monkeypatch.setattr(text, "render_full_view", lambda v: text.render_block(good.event_refs, good.record_keys[:-1]))
    with pytest.raises(AssertionError, match="entities-then-edges"):
        D.render_dump(text, view)
    monkeypatch.setattr(text, "render_full_view", lambda v: text.render_block(good.event_refs[::-1], good.record_keys))
    with pytest.raises(AssertionError, match="view order"):
        D.render_dump(text, view)
    # Same refs, same keys, same section boundary — but the record LINES rotated by one: only the
    # byte-equality guard can see this (Opus WP06 c1).
    lines = [text.record_line(k) + b"\n" for k in good.record_keys]
    rotated = b"".join(text.event_line(r) + b"\n" for r in good.event_refs) + b"".join(lines[1:] + lines[:1])
    monkeypatch.setattr(text, "render_full_view",
                        lambda v: good.__class__(event_refs=good.event_refs, record_keys=good.record_keys, data=rotated))
    with pytest.raises(AssertionError, match="event section \\+ record section"):
        D.render_dump(text, view)


@needs_corpus
def test_an_empty_or_recordless_view_is_refused(text):
    from scripts.research.load_849_corpus import Loaded
    empty = Loaded(ask_time=Q.ask_time_dt(Q.by_id("C1")))
    with pytest.raises(D.ArmRefusal, match="empty view"):
        D.render_dump(text, empty)
    full = replay(CORPUS, Q.ask_time_dt(Q.by_id("C1")), verify=False)
    full.links = []
    recordless = Loaded(ask_time=full.ask_time, events=full.events)
    with pytest.raises(D.ArmRefusal, match="empty view"):
        D.render_dump(text, recordless)
    eventless = Loaded(ask_time=full.ask_time, entities=full.entities, edges=full.edges)
    with pytest.raises(D.ArmRefusal, match="empty view"):
        D.render_dump(text, eventless)
    edgeless = Loaded(ask_time=full.ask_time, events=full.events, entities=full.entities)   # Codex H-1's shape
    with pytest.raises(D.ArmRefusal, match="empty view"):
        D.render_dump(text, edgeless)


@needs_corpus
def test_a_view_with_links_is_refused(text, views):
    view = replay(CORPUS, Q.ask_time_dt(Q.by_id("B2")), verify=False)
    assert view.links, "the un-narrowed B2 view carries loader links"
    with pytest.raises(D.ArmRefusal, match="loader links"):
        D.render_dump(text, view)

    class NoLinksAttribute:                                        # not a narrowed view either
        events, entities, edges = view.events, view.entities, view.edges

    with pytest.raises(D.ArmRefusal, match="no links attribute"):
        D.render_dump(text, NoLinksAttribute())


@needs_corpus
@needs_tokenizer
def test_an_incoherent_ctx_limit_is_refused_before_counting(tok, identity, text, views):
    facade = Facade(tok, S.ServingConfiguration.primary(identity))
    for name, limit in (("configured", S.PRIMARY_N_CTX), ("trained", "262144"), ("trained", 0), ("banana", 1)):
        ctx = SimpleNamespace(prompt=Prompt(), seed=1001, limit=limit, limit_applied=name, serving=facade)
        with pytest.raises(D.ArmRefusal, match="incoherent context limit"):
            D.arm_d(Q.by_id("C1"), views["C1"], ctx, text)
    assert facade.counted == [] and facade.sent == []


# ---------------------------------------------------------------------------
# (e) telemetry missing → no Answer
# ---------------------------------------------------------------------------


@needs_corpus
@needs_tokenizer
def test_missing_cache_n_yields_no_answer(tok, identity, text, views):
    def no_cache_n(client):
        r = Facade.plain_response(client)
        del r["timings"]["cache_n"]
        return r

    facade = Facade(tok, S.ServingConfiguration.primary(identity), no_cache_n)
    with pytest.raises(S.TelemetryMissing, match="cache_n"):
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"), text)
    assert len(facade.sent) == 1                                   # it was sent; it is not scored

    def drifted(client):
        r = Facade.plain_response(client)
        r["timings"]["prompt_n"] = client - 1                      # server disagrees with the client count
        return r

    facade = Facade(tok, S.ServingConfiguration.primary(identity), drifted)
    with pytest.raises(S.TelemetryMissing, match="drift"):
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"), text)

    def truncated(client):
        return {**Facade.plain_response(client), "truncated": True}

    facade = Facade(tok, S.ServingConfiguration.primary(identity), truncated)
    with pytest.raises(S.PromptTruncated):
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"), text)


# ---------------------------------------------------------------------------
# (f) C1's block bytes ARE the corpus lines (D-7)
# ---------------------------------------------------------------------------


@needs_corpus
def test_c1_block_bytes_equal_the_frozen_corpus_lines(text, views):
    view = views["C1"]
    block, _ = D.render_dump(text, view)
    raw_by_ref = {}
    for line in (CORPUS / "stream.jsonl").read_bytes().split(b"\n"):
        if line.strip():
            raw_by_ref[json.loads(line)["ref"]] = line
    expected = b"".join(raw_by_ref[str(e["ref"])] + b"\n" for e in view.events)
    expected += b"".join(record_line_bytes(e) + b"\n" for e in view.entities)
    expected += b"".join(record_line_bytes(e) + b"\n" for e in view.edges)
    assert block.data == expected
    assert block.sha256 == hashlib.sha256(expected).hexdigest()


# ---------------------------------------------------------------------------
# the gate counts the string that is sent — the same object
# ---------------------------------------------------------------------------


@needs_corpus
@needs_tokenizer
def test_the_counted_body_is_the_sent_body_and_carries_the_dump(tok, identity, text, views):
    facade = Facade(tok, S.ServingConfiguration.primary(identity))
    ctx = ctx_for(facade, "primary")
    row = D.arm_d(Q.by_id("C1"), views["C1"], ctx, text)
    assert len(facade.sent) == 1 and facade.counted == [id(facade.sent[0])]
    body = facade.sent[0]
    block, _ = D.render_dump(text, views["C1"])
    assert block.data.decode("utf-8") in body["prompt"]            # the dump is inside the templated prompt
    assert body["prompt"] != Prompt().render(block, Q.by_id("C1").text).decode("utf-8")   # the template was applied
    assert body["cache_prompt"] is True and body["seed"] == 1001 and body["n_predict"] == S.MAX_TOKENS
    assert row["prompt_tokens"] == tok.count(body["prompt"]) == row["client_prompt_tokens"]
    assert row["assembled_context_tokens"] == tok.count(block.data) < row["prompt_tokens"]
    assert row["assembled_context_sha256"] == block.sha256 == row["plan"]["assembled_context_sha256"]
    assert row["plan"] == {"layout": D.LAYOUT, "events_in_dump": len(views["C1"].events),
                           "entities_in_dump": len(views["C1"].entities), "edges_in_dump": len(views["C1"].edges),
                           "assembled_context_sha256": block.sha256, "assembled_context_tokens": row["assembled_context_tokens"],
                           "context_limit_applied": "trained", "prompt_tokens": row["prompt_tokens"]}
    assert row["cache_state"] == "cold" and row["cache_read_tokens"] == 0 and row["uncached_tokens"] == row["prompt_tokens"]
    assert row["finish_reason"] == "stop"


@needs_corpus
@needs_tokenizer
def test_cache_prompt_off_is_refused_before_counting(tok, identity, text, views):
    facade = Facade(tok, S.ServingConfiguration.primary(identity))
    real = facade.serialize
    facade.serialize = lambda req, seed: {**real(req, seed), "cache_prompt": False}
    with pytest.raises(D.ArmRefusal, match="cache_prompt"):
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"), text)
    assert facade.sent == [] and facade.counted == []


@needs_corpus
@needs_tokenizer
def test_last_line_refusal_from_complete_keeps_the_row_contract(tok, identity, text, views):
    """serving.complete's own guard raises the BASE exception with only a message; the arm
    re-raises it as its ContextExceeded carrying the plan, so the exceeds row is complete."""
    facade = Facade(tok, S.ServingConfiguration.primary(identity))

    def refuse(body):
        facade.sent.append(body)
        raise S.ContextExceeded("prompt is N tokens; permitted limit M — not sent")

    facade.complete = refuse
    with pytest.raises(D.ContextExceeded) as info:
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"), text)
    exc = info.value
    assert isinstance(exc.__cause__, S.ContextExceeded) and not isinstance(exc.__cause__, D.ContextExceeded)
    # The limit that actually refused is the permitted one, and the plan says so (Opus c2).
    assert exc.plan.layout == D.LAYOUT and exc.limit_applied == "permitted" == exc.plan.context_limit_applied
    assert exc.prompt_tokens == exc.plan.prompt_tokens and exc.limit == S.TRAINED_CONTEXT   # no ctx.permitted: falls back
    assert len(facade.sent) == 1

    # The arm's OWN exception raised from inside complete propagates as the identical object.
    facade2 = Facade(tok, S.ServingConfiguration.primary(identity))
    block, _ = D.render_dump(text, views["C1"])
    own = D.ContextExceeded(1, 2, "trained", D.PlanRecord(D.LAYOUT, 1, 1, 1, block.sha256, 1, "trained", 1))

    def raise_own(body):
        raise own

    facade2.complete = raise_own
    with pytest.raises(D.ContextExceeded) as info2:
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade2, "primary"), text)
    assert info2.value is own and info2.value.__cause__ is None


@needs_corpus
@needs_tokenizer
def test_a_completion_shaped_object_missing_telemetry_or_for_another_request_is_refused(tok, identity, text, views):
    """The post-complete checks are a live net: a facade that returns a Completion-shaped object
    with a None field, or one made for a different request, produces no Answer."""
    facade = Facade(tok, S.ServingConfiguration.primary(identity))
    real = facade.complete

    def none_field(body):
        c = real(body)
        return SimpleNamespace(**{**c.__dict__, "cache_fraction": None})

    facade.complete = none_field
    with pytest.raises(S.TelemetryMissing, match="cache_fraction"):
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"), text)

    def other_request(body):
        c = real(body)
        return SimpleNamespace(**{**c.__dict__, "client_prompt_tokens": c.client_prompt_tokens + 1})

    facade.complete = other_request
    with pytest.raises(S.TelemetryMissing, match="not the same request"):
        D.arm_d(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"), text)


@needs_corpus
@needs_tokenizer
def test_bind_gives_the_contracts_three_argument_arm(tok, identity, text, views):
    facade = Facade(tok, S.ServingConfiguration.primary(identity))
    arm = D.bind(text)
    row = arm(Q.by_id("C1"), views["C1"], ctx_for(facade, "primary"))
    assert row["plan"]["layout"] == D.LAYOUT and "truncated" not in row      # the ledger derives truncated


@needs_corpus
@needs_tokenizer
def test_exceeded_sends_nothing_and_does_not_count_twice(tok, identity, text, views):
    facade = Facade(tok, S.ServingConfiguration.primary(identity))
    with pytest.raises(D.ContextExceeded) as info:
        D.arm_d(Q.by_id("B2"), views["B2"], ctx_for(facade, "primary"), text)
    assert facade.sent == [] and len(facade.counted) == 1
    assert info.value.plan.events_in_dump == len(views["B2"].events)
    assert "not sent" in str(info.value)


def test_module_names_no_excluded_material():
    src = (PKG / "arm_d.py").read_text(encoding="utf-8").lower()
    for word in ("or" + "acle", "se" + "ed/", "trace" + "ability"):
        assert word not in src
