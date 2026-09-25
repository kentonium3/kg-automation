"""WP08 T035 — the harness end to end with FAKE arms (the MVP the tasks file names).

Three fake arms are registered: G returns a fixed block (1,000 assembled tokens); D raises its
``ContextExceeded`` on the six known questions and answers C1 and A; R reads k from
``ctx.calibration``. The real arms are consumers of the same registry; nothing here needs the
stack. Every invariant is shown able to fail (a negative beside each positive).

The fake-arm kit at the top is imported by tests/research/test_arms849_grading.py.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import subprocess
import sys
import threading
import time
import types
from collections.abc import Callable
from typing import Any

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research import run_849_harness as h
from scripts.research.arms849 import grading, serving
from scripts.research.arms849.ledger import (
    Binding,
    LedgerBoundToAnotherConfig,
    LedgerLocked,
    RunKey,
    open_ledger,
)
from scripts.research.arms849.questions import QUESTIONS
from scripts.research.arms849.sampler import GttSampler, RssSampler

CORPUS = h.DEFAULT_CORPUS
pytestmark = pytest.mark.skipif(not (CORPUS / "entities.json").exists(),
                                reason="rendered corpus absent; run render_849_corpus first")

IDENTITY = serving.ServingIdentity(gguf_sha256="a" * 64, image_digest="sha256:" + "b" * 64,
                                   embedder_model_sha256="c" * 64, tokenizer_files_sha256="d" * 64,
                                   chat_template_sha256="e" * 64)
PRIMARY = serving.ServingConfiguration.primary(IDENTITY)
SECONDARY = serving.ServingConfiguration.secondary_yarn(IDENTITY)
D_EXCEEDS = ("F1", "B1", "E2", "E1", "F2", "B2")          # the six known questions (A2)
G_TOKENS = 1_000
BLINDING_SEED = 7_340_117


# --------------------------------------------------------------------------
# The fake-arm kit
# --------------------------------------------------------------------------


def letters(*parts: object) -> str:
    """Deterministic answer text with no digits and no capital letters (so no seed digits and no
    arm letter can appear in it by chance)."""
    digest = hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()
    return "answer " + digest[:16].translate(str.maketrans("0123456789", "ghijklmnop"))


def scored(text: str, assembled: int, plan: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    prompt_tokens = assembled + 400
    return {"text": text, "assembled_context_tokens": assembled, "prompt_tokens": prompt_tokens,
            "client_prompt_tokens": prompt_tokens, "output_tokens": 50, "finish_reason": "stop",
            "cache_read_tokens": 0, "uncached_tokens": prompt_tokens, "cache_write_tokens": prompt_tokens,
            "cache_state": "cold", "cache_fraction": 0.0, "prefill_s": 1.0, "generation_s": 2.0,
            "generation_tok_s": 25.0, "assembled_context_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "plan": plan or {}, **extra}


class FakeContextExceeded(serving.ContextExceeded):
    """Arm D's own shape: a serving.ContextExceeded subclass carrying count, limit and plan."""

    def __init__(self, prompt_tokens: int, limit: int, limit_applied: str, plan: dict[str, Any]) -> None:
        self.prompt_tokens, self.limit, self.limit_applied, self.plan = prompt_tokens, limit, limit_applied, plan
        super().__init__(f"prompt is {prompt_tokens} tokens; {limit_applied} limit {limit}")


class ArmRefusal(RuntimeError):
    """The arms' refusal class name (each arm defines its own)."""


@dataclasses.dataclass(frozen=True)
class FakeStats:
    group_id: str
    nodes: int


class FakeG:
    def __init__(self, fail: Callable[[Any, Any], BaseException | None] | None = None) -> None:
        self.fail = fail
        self.builds: list[str] = []
        self.drops: list[str] = []
        self.calls: list[tuple[str, int, int]] = []

    def build_graph(self, question: Any, view: Any) -> FakeStats:
        self.builds.append(question.id)
        return FakeStats(group_id=f"arms_{question.id}", nodes=len(view.entities))

    def drop_graph(self, question: Any) -> None:
        self.drops.append(question.id)

    def answer(self, question: Any, view: Any, ctx: Any) -> dict[str, Any]:
        self.calls.append((question.id, ctx.repeat, ctx.attempt))
        if self.fail is not None:
            exc = self.fail(question, ctx)
            if exc is not None:
                raise exc
        assert view.links, "G must receive the MENTIONS wiring"
        return scored(letters("G", question.id, ctx.repeat), G_TOKENS, {"path": "anchored", "llm_calls": 0})

    def registration(self) -> h.ArmRegistration:
        return h.ArmRegistration(answer=self.answer, build_graph=self.build_graph, drop_graph=self.drop_graph)


def fake_d(question: Any, view: Any, ctx: Any) -> dict[str, Any]:
    assert view.links == []
    plan = {"layout": "events_entities_edges", "events_in_dump": len(view.events)}
    if question.id in D_EXCEEDS:
        # Above the configured context on either ledger, as the six are (data-model I4).
        raise FakeContextExceeded(ctx.limits["configured"] + 1 + len(view.events), ctx.limit, ctx.limit_applied, plan)
    return scored(letters("D", question.id, ctx.repeat), 20_000, plan, context_limit_applied=ctx.limit_applied)


class FakeIndex:
    def __init__(self, qid: str) -> None:
        self.qid = qid


class FakeR:
    """Honours the one-cache contract (N-3): calibration_inputs populates the cache the cells read."""

    def __init__(self) -> None:
        self.calibration_cache: dict[str, Any] | None = None
        self.bind_cache: dict[str, Any] | None = None
        self.calibration_index: dict[str, Any] = {}
        self.cell_index: list[tuple[str, Any]] = []
        self.ks: list[int] = []

    def calibration_inputs(self, views: Any, cache: dict[str, Any]) -> tuple[dict[str, int], Callable[[str, int], int]]:
        self.calibration_cache = cache
        for qid in views:
            self.calibration_index[qid] = cache.setdefault(qid, FakeIndex(qid))
        return {qid: 40 for qid in views}, lambda qid, k: 500 + 100 * k

    def bind(self, cache: dict[str, Any]) -> Callable[[Any, Any, Any], dict[str, Any]]:
        self.bind_cache = cache

        def arm(question: Any, view: Any, ctx: Any) -> dict[str, Any]:
            if ctx.calibration is None:
                raise ArmRefusal("no calibration record")
            index = cache.setdefault(question.id, FakeIndex(question.id))
            self.cell_index.append((question.id, index))
            k = ctx.calibration["k"]
            self.ks.append(k)
            return scored(letters("R", question.id, ctx.repeat), 500 + 100 * k, {"k": k})
        return arm

    def registration(self) -> h.ArmRegistration:
        return h.ArmRegistration(bind=self.bind, calibration_inputs=self.calibration_inputs)


class FakeGtt(GttSampler):
    def __init__(self, value: float = 30.0) -> None:
        super().__init__(path="/nonexistent")
        self.value = value

    def read_once(self) -> float:
        return self.value


class FakeRss(RssSampler):
    def read_once(self) -> float:
        return 512.0


def fake_arms(g: FakeG | None = None, r: FakeR | None = None) -> dict[str, h.ArmRegistration]:
    return {"G": (g or FakeG()).registration(), "D": h.ArmRegistration(answer=fake_d),
            "R": (r or FakeR()).registration()}


def make_runtime(arms: dict[str, h.ArmRegistration], config: serving.ServingConfiguration = PRIMARY,
                 **kw: Any) -> h.Runtime:
    base: dict[str, Any] = {
        "config": config, "arms": arms, "corpus_dir": CORPUS,
        "facade": lambda deadline, cancelled: types.SimpleNamespace(config=config),
        "health": lambda: True, "gtt_sampler": FakeGtt, "rss_sampler": FakeRss, "out": lambda s: None,
    }
    base.update(kw)
    return h.Runtime(**base)


def make_binding(config: serving.ServingConfiguration = PRIMARY, corpus: pathlib.Path = CORPUS) -> Binding:
    return Binding.from_environment(corpus, config.as_header_dict(), config.limit_applied()[0],
                                    run_env_commit="test", run_env_manifest_sha="0" * 64,
                                    preflight_sha="1" * 64, gate_host_sha="2" * 64, gate_container_sha="3" * 64)


def open_fake(path: pathlib.Path, config: serving.ServingConfiguration = PRIMARY) -> Any:
    kind = "primary" if config.kind == "primary" else "secondary"
    return open_ledger(path, make_binding(config), BLINDING_SEED, h.PRIMARY_PLAN if kind == "primary" else h.SECONDARY_PLAN)


def full_run(path: pathlib.Path, g: FakeG | None = None, r: FakeR | None = None) -> h.SessionReport:
    with open_fake(path) as ledger:
        return h.run_session(ledger, make_runtime(fake_arms(g, r)))


def rows_of(path: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def runs(path: pathlib.Path) -> list[dict[str, Any]]:
    return [r for r in rows_of(path) if r.get("record") == "run"]


# --------------------------------------------------------------------------
# CellContext (arm-interface.md ctx bullet)
# --------------------------------------------------------------------------


def _ctx(config: serving.ServingConfiguration = PRIMARY, **kw: Any) -> h.CellContext:
    return h.CellContext(repeat=2, attempt=1, config=config, serving=types.SimpleNamespace(config=config),
                         prompt=h.Prompt(), **kw)


def test_cell_context_derives_the_limit_pair_from_config():
    ctx = _ctx()
    assert (ctx.limit_applied, ctx.limit) == PRIMARY.limit_applied() == ("trained", 262_144)
    assert dict(ctx.limits) == {"trained": 262_144, "configured": 262_144, "permitted": 260_096}
    assert ctx.seed == 1002 and ctx.ledger_kind == "primary" and ctx.config is PRIMARY
    sec = _ctx(SECONDARY)
    assert (sec.limit_applied, sec.limit) == ("permitted", 391_168) and sec.ledger_kind == "secondary"


def test_an_incoherent_cell_context_cannot_be_constructed():
    """No parameter, no replace() and no assignment can set the derived fields."""
    for name, value in (("limit", 1), ("limit_applied", "permitted"), ("limits", {}), ("seed", 5)):
        with pytest.raises(TypeError):
            _ctx(**{name: value})
        with pytest.raises(ValueError):
            dataclasses.replace(_ctx(), **{name: value})
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(_ctx(), name, value)
    with pytest.raises(TypeError):
        _ctx().limits["trained"] = 1                                    # read-only mapping
    # replace() of config re-derives, so the pair follows the configuration.
    assert dataclasses.replace(_ctx(), config=SECONDARY,
                               serving=types.SimpleNamespace(config=SECONDARY)).limit_applied == "permitted"
    with pytest.raises(ValueError, match="different configuration"):
        h.CellContext(repeat=1, attempt=1, config=PRIMARY, serving=types.SimpleNamespace(config=SECONDARY),
                      prompt=h.Prompt())


# --------------------------------------------------------------------------
# The full 72-cell run
# --------------------------------------------------------------------------


def test_full_run_completes_with_eighteen_exceeds_and_zero_error(tmp_path):
    g, r = FakeG(), FakeR()
    path = tmp_path / "ledger.jsonl"
    report = full_run(path, g, r)
    assert report.stopped is None
    rs = runs(path)
    assert len(rs) == 72
    outcomes = [x["outcome"] for x in rs]
    assert outcomes.count("exceeds_model_context") == 18
    assert outcomes.count("error") == 0 and outcomes.count("ok") == 54
    exceeds = [x for x in rs if x["outcome"] == "exceeds_model_context"]
    assert {x["question"] for x in exceeds} == set(D_EXCEEDS) and {x["arm"] for x in exceeds} == {"D"}
    assert all(x["prompt_tokens"] > 262_144 and x["context_limit_applied"] == "trained" and x["plan"] for x in exceeds)
    # G lifecycle: built once per question before repeat 1, dropped after repeat 3.
    assert g.builds == [q.id for q in QUESTIONS]
    assert sorted(g.drops) == sorted(g.builds)
    order = rows_of(path)
    assert order[0]["record"] == "header"
    # The calibration record precedes the first R row of any kind.
    first_r = next(i for i, x in enumerate(order) if x.get("arm") == "R")
    cal = next(i for i, x in enumerate(order) if x.get("record") == "calibration")
    assert cal < first_r
    assert order[cal]["k"] == 3 and order[cal]["parity"] == "ok"
    assert set(r.ks) == {3}


def test_every_scored_row_carries_the_harness_fields(tmp_path):
    path = tmp_path / "ledger.jsonl"
    full_run(path)
    for x in runs(path):
        if x["outcome"] != "ok":
            continue
        assert x["seed"] == 1000 + x["repeat"] and x["peak_gtt_gib"] == 30.0
        assert x["events_loaded"] > 0 and "links_loaded" in x and x["elapsed_s"] >= 0
        if x["arm"] == "G":
            assert x["falkordb_rss_peak_mib"] == 512.0 and x["graph_stats"]["group_id"] == f"arms_{x['question']}"
            assert x["links_loaded"] > 0
        else:
            assert x["links_loaded"] == 0
        if x["arm"] == "R":
            assert x["r_g_ratio"] == pytest.approx(800 / G_TOKENS)


def test_calibration_and_cells_share_one_index_cache(tmp_path):
    """Architect ruling N-3: the index an R cell reads IS the object calibration counted over."""
    r = FakeR()
    full_run(tmp_path / "ledger.jsonl", r=r)
    assert r.calibration_cache is not None and r.calibration_cache is r.bind_cache
    assert len(r.cell_index) == 24
    for qid, index in r.cell_index:
        assert index is r.calibration_index[qid]


def test_the_identity_check_would_catch_two_caches(tmp_path):
    """Guards the guard: a harness handing bind a fresh dict fails the identity test above."""
    r = FakeR()
    reg = r.registration()
    broken = h.ArmRegistration(bind=lambda cache: reg.bind({}), calibration_inputs=reg.calibration_inputs)
    with open_fake(tmp_path / "ledger.jsonl") as ledger:
        h.run_session(ledger, make_runtime({**fake_arms(), "R": broken}))
    assert r.calibration_cache is not r.bind_cache
    assert any(index is not r.calibration_index[qid] for qid, index in r.cell_index)


def test_summarise_never_averages_the_exceeds_cells(tmp_path):
    path = tmp_path / "ledger.jsonl"
    full_run(path)
    with h.open_existing(path) as ledger:
        s = ledger.summarise()
    b2 = s[("D", "B2")]
    assert b2.n_scored == 0 and b2.mean_assembled_tokens is None
    assert b2.counts == {"exceeds_model_context": 3}
    assert s[("D", "C1")].mean_assembled_tokens == 20_000


# --------------------------------------------------------------------------
# Interrupts, torn tails, one writer
# --------------------------------------------------------------------------


def test_interrupt_mid_cell_then_resume_counts_the_dead_attempt(tmp_path):
    path = tmp_path / "ledger.jsonl"
    dying = FakeG(fail=lambda q, ctx: KeyboardInterrupt() if (q.id, ctx.repeat) == ("C1", 1) else None)
    with open_fake(path) as ledger, pytest.raises(KeyboardInterrupt):
        h.run_session(ledger, make_runtime(fake_arms(g=dying)))
    starts = [x for x in rows_of(path) if x.get("record") == "attempt_start"]
    assert len(starts) == 1 and not runs(path), "the attempt_start row must precede the death"
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=1)
    key = ("G", "C1", 1)
    rows = [x for x in rows_of(path) if (x.get("arm"), x.get("question"), x.get("repeat")) == key]
    assert [x["record"] for x in rows] == ["attempt_start", "attempt_start", "run"]
    assert rows[-1]["outcome"] == "ok" and rows[-1]["attempt"] == 2


def test_a_torn_tail_is_recovered_and_the_run_resumes(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=3)
    with path.open("ab") as fh:
        fh.write(b'{"record": "run", "arm": "G", "quest')                   # a killed append
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=2)
    rows = rows_of(path)                                                     # every line parses again
    assert any(x.get("kind") == "recovered_torn_tail" for x in rows)
    assert len(runs(path)) == 5


def test_a_second_writer_is_refused(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with open_fake(path), pytest.raises(LedgerLocked):
        open_fake(path)
    open_fake(path).close()                                                 # released on close


def test_a_ledger_write_failure_stops_the_session_and_reopen_resumes(tmp_path, monkeypatch):
    import scripts.research.arms849.ledger as ledger_mod

    path = tmp_path / "ledger.jsonl"
    real_fsync, calls = ledger_mod.os.fsync, {"n": 0}

    def flaky(fd: int) -> None:
        calls["n"] += 1
        if calls["n"] == 6:
            raise OSError(5, "EIO")
        real_fsync(fd)

    ledger = open_fake(path)
    monkeypatch.setattr(ledger_mod.os, "fsync", flaky)
    lines: list[str] = []
    report = h.run_session(ledger, make_runtime(fake_arms(), out=lines.append), limit=10)
    monkeypatch.setattr(ledger_mod.os, "fsync", real_fsync)
    assert report.stopped and "ledger write failed" in report.stopped
    assert any(line.startswith("arms849 status: STOPPED") for line in lines)
    with open_fake(path) as reopened:                                        # the lock was released
        h.run_session(reopened, make_runtime(fake_arms()), limit=2)


# --------------------------------------------------------------------------
# Failures: retries, refusals, timeouts, halt
# --------------------------------------------------------------------------


def test_an_infrastructure_failure_is_retried_after_a_health_check(tmp_path):
    path = tmp_path / "ledger.jsonl"
    flaky = FakeG(fail=lambda q, ctx: ConnectionError("llama reset") if ctx.attempt == 1 else None)
    checks: list[int] = []
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms(g=flaky), health=lambda: checks.append(1) or True), limit=1)
    rs = runs(path)
    assert [x["outcome"] for x in rs] == ["error", "ok"] and rs[0]["error"] == "ConnectionError: llama reset"
    assert rs[0]["peak_gtt_gib"] == 30.0 and checks == [1]


def test_an_unhealthy_substrate_is_not_retried_and_stops_the_session(tmp_path):
    path = tmp_path / "ledger.jsonl"
    broken = FakeG(fail=lambda q, ctx: ConnectionError("down"))
    with open_fake(path) as ledger:
        report = h.run_session(ledger, make_runtime(fake_arms(g=broken), health=lambda: False), limit=5)
    assert report.stopped and "unhealthy" in report.stopped
    assert len(runs(path)) == 1
    assert any(x.get("kind") == "substrate_unhealthy" for x in rows_of(path))


def test_arm_refusal_is_terminal_on_the_first_attempt(tmp_path):
    path = tmp_path / "ledger.jsonl"

    class LinksRefusal(ArmRefusal):
        pass

    refusing = FakeG(fail=lambda q, ctx: LinksRefusal("links handed to a flat arm") if q.id == "C1" else None)
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms(g=refusing)), limit=2)
        assert ledger.terminal(RunKey("G", "C1", 1)) == "error"
    c1 = [x for x in rows_of(path) if x.get("question") == "C1"]
    assert [x["record"] for x in c1] == ["attempt_start", "run"], "an ArmRefusal is never retried"
    assert c1[-1]["error"].startswith("ArmRefusal: LinksRefusal: links handed")
    assert refusing.calls.count(("C1", 1, 1)) == 1


def test_a_timed_out_attempt_is_cancelled_and_waited_for_before_the_row(tmp_path):
    path = tmp_path / "ledger.jsonl"
    exited: list[float] = []

    def slow(q: Any, ctx: Any) -> BaseException | None:
        if ctx.attempt == 1:
            ctx.cancelled.wait(10)
            time.sleep(0.3)                    # the "request" takes a moment to unwind
            exited.append(time.monotonic())
        return None

    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms(g=FakeG(fail=slow)), attempt_timeout_s=0.2), limit=1)
        recorded = time.monotonic()
    rs = runs(path)
    assert [x["outcome"] for x in rs] == ["error", "ok"] and rs[0]["error"] == "timeout"
    assert exited and exited[0] < recorded, "the worker must have exited before the row was written"


def test_a_worker_that_ignores_cancellation_stops_the_session(tmp_path):
    path = tmp_path / "ledger.jsonl"
    stubborn = FakeG(fail=lambda q, ctx: time.sleep(2) or None)
    with open_fake(path) as ledger:
        report = h.run_session(ledger, make_runtime(fake_arms(g=stubborn), attempt_timeout_s=0.1,
                                                    cancel_grace_s=0.1), limit=3)
    assert report.stopped and "did not stop" in report.stopped
    assert [x["error"] for x in runs(path)] == ["timeout"]
    assert any(x.get("kind") == "zombie_worker" for x in rows_of(path))


def test_g_repeat1_errors_three_times_halts_before_any_r_row(tmp_path):
    path = tmp_path / "ledger.jsonl"
    g = FakeG(fail=lambda q, ctx: ConnectionError("graph build") if (q.id, ctx.repeat) == ("C1", 1) else None)
    lines: list[str] = []
    with open_fake(path) as ledger:
        report = h.run_session(ledger, make_runtime(fake_arms(g=g), out=lines.append))
        assert ledger.calibration() is None
    rows = rows_of(path)
    assert [x["attempt"] for x in runs(path) if (x["arm"], x["question"], x["repeat"]) == ("G", "C1", 1)] == [1, 2, 3]
    halts = [x for x in rows if x.get("kind") == "halt"]
    assert len(halts) == 1 and halts[0]["detail"]["reason"] == "calibration_population_incomplete"
    assert halts[0]["detail"]["terminal_error"] == ["C1"]
    assert not [x for x in rows if x.get("arm") == "R"], "no R row of any kind after the halt"
    assert report.stopped and "calibration_population_incomplete" in report.stopped
    assert any("HALTED" in line for line in lines)


def test_a_context_overflow_outside_d_is_terminal_not_exceeds(tmp_path):
    path = tmp_path / "ledger.jsonl"
    g = FakeG(fail=lambda q, ctx: serving.ContextExceeded("too long") if q.id == "C1" else None)
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms(g=g)), limit=1)
        assert ledger.terminal(RunKey("G", "C1", 1)) == "error"
    assert runs(path)[0]["error"].startswith("ArmRefusal: ContextExceeded from arm G")


def test_an_unregistered_arm_is_recorded_not_implemented(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime({}), limit=3)
    assert [x["outcome"] for x in runs(path)] == ["not_implemented"] * 3


# --------------------------------------------------------------------------
# NFR-004 and NFR-002
# --------------------------------------------------------------------------


def test_nfr004_a_breached_sampler_refuses_to_start_the_cell(tmp_path):
    path = tmp_path / "ledger.jsonl"
    g = FakeG()
    with open_fake(path) as ledger:
        report = h.run_session(ledger, make_runtime(fake_arms(g=g), gtt_sampler=lambda: FakeGtt(60.0)), limit=3)
    rows = rows_of(path)
    assert not [x for x in rows if x.get("record") in ("attempt_start", "run")], "no attempt row"
    ceiling = [x for x in rows if x.get("kind") == "memory_ceiling"]
    assert len(ceiling) == 1 and ceiling[0]["detail"]["gtt_gib"] == 60.0
    assert report.stopped and "memory ceiling" in report.stopped and g.calls == []


def test_nfr004_a_forced_breached_flag_refuses_too(tmp_path):
    class Forced(FakeGtt):
        def __enter__(self):
            super().__enter__()
            self.breached = True
            return self

    path = tmp_path / "ledger.jsonl"
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms(), gtt_sampler=Forced), limit=1)
    assert [x.get("kind") for x in rows_of(path)[1:]] == ["memory_ceiling"]


def test_nfr004_the_ceiling_check_is_not_vacuous(tmp_path):
    """Guards the guard: under the ceiling the same cell starts."""
    path = tmp_path / "ledger.jsonl"
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms(), gtt_sampler=lambda: FakeGtt(57.4)), limit=1)
    assert [x["outcome"] for x in runs(path)] == ["ok"]


def test_nfr002_resuming_a_forty_cell_ledger_reaches_the_next_cell_in_under_30s(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=40)
    binding = make_binding()                        # environment/substrate start-up: excluded
    reached: list[float] = []

    def first(q: Any, view: Any, ctx: Any) -> dict[str, Any]:
        reached.append(time.monotonic())
        return fake_d(q, view, ctx)

    t0 = time.monotonic()
    with open_ledger(path, binding, BLINDING_SEED, h.PRIMARY_PLAN) as ledger:
        h.run_session(ledger, make_runtime({**fake_arms(), "D": h.ArmRegistration(answer=first)}), limit=1)
    assert len(runs(path)) == 41 and reached
    assert reached[0] - t0 < 30.0, f"resume took {reached[0] - t0:.1f}s"


# --------------------------------------------------------------------------
# The secondary (T033, SC-006)
# --------------------------------------------------------------------------


def _secondary(tmp_path: pathlib.Path, primary: pathlib.Path) -> Any:
    return h.open_secondary(primary, tmp_path / "secondary.jsonl", make_binding(SECONDARY))


def test_secondary_refuses_an_incomplete_primary(tmp_path):
    primary = tmp_path / "ledger.jsonl"
    with open_fake(primary) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=10)
    with pytest.raises(h.PrimaryIncomplete, match="not complete"):
        _secondary(tmp_path, primary)
    assert not (tmp_path / "secondary.jsonl").exists()


def test_secondary_refuses_a_primary_with_not_implemented_cells(tmp_path):
    primary = tmp_path / "ledger.jsonl"
    with open_fake(primary) as ledger:
        h.run_session(ledger, make_runtime({"G": FakeG().registration(), "D": h.ArmRegistration(answer=fake_d)}))
    with pytest.raises(h.PrimaryIncomplete, match="24 not_implemented"):
        _secondary(tmp_path, primary)


def test_secondary_on_a_complete_primary_differs_in_exactly_four_fields(tmp_path):
    primary = tmp_path / "ledger.jsonl"
    full_run(primary)
    probes: list[int] = []

    def probe() -> dict[str, Any]:
        probes.append(1)
        return {"passed": True, "n_ctx": 393_216, "rope": "yarn", "prompt_tokens": 363_000, "peak_gtt_gib": 55.0,
                "prefill_s": 900.0, "generation_tok_s": 12.0}

    with _secondary(tmp_path, primary) as ledger:
        assert ledger.header.plan == 24 and ledger.header.binding.limit_applied == "permitted"
        assert ledger.header.binding.model_context_tokens == 393_216
        with h.open_existing(primary) as p:
            assert h.sc006_difference(p.header, ledger.header) == h.SC006_FIELDS
        assert h.secondary_context_gate(ledger, probe)
        report = h.run_session(ledger, make_runtime(fake_arms(), config=SECONDARY), kind="secondary")
        assert h.secondary_context_gate(ledger, probe) and probes == [1], "the gate runs once per ledger"
    rows = rows_of(tmp_path / "secondary.jsonl")
    gate = next(i for i, x in enumerate(rows) if x.get("kind") == "secondary_context_gate")
    first_cell = next(i for i, x in enumerate(rows) if x.get("record") == "attempt_start")
    assert gate < first_cell and rows[gate]["detail"]["peak_gtt_gib"] == 55.0
    rs = [x for x in rows if x.get("record") == "run"]
    assert report.stopped is None and len(rs) == 24 and {x["arm"] for x in rs} == {"D"}
    # Under the permitted limit the fake D still overflows on the six (its count is limit + n).
    assert all(x["context_limit_applied"] == "permitted" for x in rs)


def test_sc006_check_fails_on_a_fifth_difference(tmp_path):
    primary = tmp_path / "ledger.jsonl"
    full_run(primary)
    other = serving.ServingConfiguration(**{**dataclasses.asdict(SECONDARY), "max_tokens": 4096})
    with pytest.raises(LedgerBoundToAnotherConfig, match="SC-006"):
        h.open_secondary(primary, tmp_path / "secondary.jsonl", make_binding(other))


def test_a_failing_secondary_gate_is_recorded_and_refuses(tmp_path):
    primary = tmp_path / "ledger.jsonl"
    full_run(primary)
    with _secondary(tmp_path, primary) as ledger:
        assert not h.secondary_context_gate(ledger, lambda: {"passed": False, "n_ctx": 262_144})
        assert not h.secondary_context_gate(ledger, lambda: (_ for _ in ()).throw(OSError("no llama")))
    kinds = [x.get("kind") for x in rows_of(tmp_path / "secondary.jsonl")]
    assert kinds.count("secondary_context_gate") == 2


# --------------------------------------------------------------------------
# CLI and gates
# --------------------------------------------------------------------------


def test_dry_run_prints_the_seventy_two_cell_plan():
    out = subprocess.run([sys.executable, "-m", "scripts.research.run_849_harness", "--dry-run"], cwd=REPO_ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("72 cells, in execution order")
    cells = [line.split() for line in out.splitlines() if line.startswith("  ")]
    assert len(cells) == 72 and cells[0] == ["G", "C1", "r1"] and cells[-1] == ["R", "B2", "r3"]


def test_a_failing_container_gate_writes_no_ledger(tmp_path):
    from scripts.research.arms849.gates import GatesRefused

    def refuse(env: Any, out: Any) -> Any:
        assert env.forbidden_words and env.expect_n_ctx == PRIMARY.n_ctx
        raise GatesRefused("container phase refused:\n  preflight_present_and_matching: check_849_loader did not pass")

    path = tmp_path / "ledger.jsonl"
    with pytest.raises(GatesRefused):
        h.live_binding(path, CORPUS, PRIMARY, "2026-09-25T00:00:00+00:00", skip_gates=False, container_phase=refuse)
    assert not path.exists()


def test_skip_gates_is_development_only_and_never_graded(tmp_path, capsys):
    binding = h.live_binding(tmp_path / "l.jsonl", CORPUS, PRIMARY, "", skip_gates=True)
    assert "DEVELOPMENT ONLY" in capsys.readouterr().out
    assert binding.gate_container_sha == binding.gate_host_sha == binding.preflight_sha == grading.SKIP_GATES_SHA
    with open_ledger(tmp_path / "l.jsonl", binding, BLINDING_SEED, h.PRIMARY_PLAN) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()))
        with pytest.raises(grading.ExportRefused, match="skip-gates"):
            grading.export(ledger, BLINDING_SEED, tmp_path / "out")


def test_live_workers_do_not_leak_threads(tmp_path):
    before = threading.active_count()
    full_run(tmp_path / "ledger.jsonl")
    assert threading.active_count() <= before + 1
