"""Shared research-environment gate and fake arms for the #849 test suite."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import os
import pathlib
import types
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pytest

from scripts.research import run_849_harness as h
from scripts.research.arms849 import serving
from scripts.research.arms849.ledger import Binding, open_ledger
from scripts.research.arms849.sampler import GttSampler
from scripts.research.load_849_corpus import REGISTRATION, verify_registration

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS = pathlib.Path(os.environ.get("ARMS849_CORPUS", str(h.DEFAULT_CORPUS)))
CACHE = pathlib.Path(os.environ.get("ARMS849_CACHE", str(REPO_ROOT / "build" / "849-cache")))
RESEARCH_ENVIRONMENT_SKIP_REASON = "ARMS849 research environment unavailable"


@dataclass(frozen=True)
class ResearchEnvironment:
    """The complete local-only environment required by the real research-arm tests."""

    graphiti_core: ModuleType
    corpus: pathlib.Path
    cache: pathlib.Path


def _nonempty_tree(path: pathlib.Path) -> bool:
    return path.is_dir() and any(candidate.is_file() for candidate in path.rglob("*"))


def _load_research_environment() -> ResearchEnvironment | None:
    """Return the declared environment only when every required local artifact is usable."""
    try:
        graphiti_core = importlib.import_module("graphiti_core")
        observed = verify_registration(CORPUS)
    except (ImportError, OSError, RuntimeError, ValueError):
        return None
    if observed != REGISTRATION["files"]:
        return None
    if not _nonempty_tree(CACHE / "qwen-tokenizer") or not _nonempty_tree(CACHE / "fastembed"):
        return None
    return ResearchEnvironment(graphiti_core=graphiti_core, corpus=CORPUS, cache=CACHE)


@pytest.fixture(scope="session")
def research_environment() -> ResearchEnvironment:
    """Declare the one office4 environment; CI skips it under one stable reason."""
    environment = _load_research_environment()
    if environment is None:
        pytest.skip(RESEARCH_ENVIRONMENT_SKIP_REASON)
    return environment


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Make missing research coverage visible even under pytest's quiet output modes."""
    count = sum(
        RESEARCH_ENVIRONMENT_SKIP_REASON in str(report.longrepr)
        for report in terminalreporter.stats.get("skipped", ())
    )
    terminalreporter.write_sep(
        "=",
        f"{RESEARCH_ENVIRONMENT_SKIP_REASON}: {count} skipped test{'s' if count != 1 else ''}",
    )


# --------------------------------------------------------------------------
# Shared serving/G/D/R fake kit
# --------------------------------------------------------------------------

IDENTITY = serving.ServingIdentity(
    gguf_sha256="a" * 64,
    image_digest="sha256:" + "b" * 64,
    embedder_model_sha256="c" * 64,
    tokenizer_files_sha256="d" * 64,
    chat_template_sha256="e" * 64,
)
PRIMARY = serving.ServingConfiguration.primary(IDENTITY)
SECONDARY = serving.ServingConfiguration.secondary_yarn(IDENTITY)
D_EXCEEDS = ("F1", "B1", "E2", "E1", "F2", "B2")
G_TOKENS = 1_000
BLINDING_SEED = 7_340_117


def letters(*parts: object) -> str:
    """Return deterministic text containing neither digits nor uppercase arm letters."""
    digest = hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()
    return "answer " + digest[:16].translate(str.maketrans("0123456789", "ghijklmnop"))


def scored(
    text: str,
    assembled: int,
    plan: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    prompt_tokens = assembled + 400
    return {
        "text": text,
        "assembled_context_tokens": assembled,
        "prompt_tokens": prompt_tokens,
        "client_prompt_tokens": prompt_tokens,
        "output_tokens": 50,
        "finish_reason": "stop",
        "cache_read_tokens": 0,
        "uncached_tokens": prompt_tokens,
        "cache_write_tokens": prompt_tokens,
        "cache_state": "cold",
        "cache_fraction": 0.0,
        "prefill_s": 1.0,
        "generation_s": 2.0,
        "generation_tok_s": 25.0,
        "assembled_context_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "plan": plan or {},
        **extra,
    }


class FakeContextExceeded(serving.ContextExceeded):
    """Arm D's context-exceeded shape, including its measured plan."""

    def __init__(self, prompt_tokens: int, limit: int, limit_applied: str, plan: dict[str, Any]) -> None:
        self.prompt_tokens = prompt_tokens
        self.limit = limit
        self.limit_applied = limit_applied
        self.plan = plan
        super().__init__(f"prompt is {prompt_tokens} tokens; {limit_applied} limit {limit}")


class ArmRefusal(RuntimeError):
    """The fake arms' refusal class."""


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

    def build_graph(self, question: Any, view: Any, ctx: Any = None) -> FakeStats:
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
        return scored(
            letters("G", question.id, ctx.repeat),
            G_TOKENS,
            {"path": "anchored", "llm_calls": 0},
        )

    def registration(self, refusal: type[BaseException] = ArmRefusal) -> h.ArmRegistration:
        return h.ArmRegistration(
            refusal=refusal,
            answer=self.answer,
            build_graph=self.build_graph,
            drop_graph=self.drop_graph,
        )


def fake_d(question: Any, view: Any, ctx: Any) -> dict[str, Any]:
    assert view.links == []
    plan = {"layout": "events_entities_edges", "events_in_dump": len(view.events)}
    if question.id in D_EXCEEDS:
        raise FakeContextExceeded(
            ctx.limits["configured"] + 1 + len(view.events),
            ctx.limit,
            ctx.limit_applied,
            plan,
        )
    return scored(
        letters("D", question.id, ctx.repeat),
        20_000,
        plan,
        context_limit_applied=ctx.limit_applied,
    )


class FakeIndex:
    def __init__(self, qid: str) -> None:
        self.qid = qid


class FakeR:
    """Populate and read the same cache used for calibration."""

    def __init__(self) -> None:
        self.calibration_cache: dict[str, Any] | None = None
        self.bind_cache: dict[str, Any] | None = None
        self.calibration_index: dict[str, Any] = {}
        self.cell_index: list[tuple[str, Any]] = []
        self.ks: list[int] = []

    def calibration_inputs(
        self,
        views: Any,
        cache: dict[str, Any],
    ) -> tuple[dict[str, int], Callable[[str, int], int]]:
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
        return h.ArmRegistration(
            refusal=ArmRefusal,
            bind=self.bind,
            calibration_inputs=self.calibration_inputs,
        )


class FakeGtt(GttSampler):
    def __init__(self, value: float = 30.0) -> None:
        super().__init__(path="/nonexistent")
        self.value = value

    def read_once(self) -> float:
        return self.value


def fake_arms(
    g: FakeG | None = None,
    r: FakeR | None = None,
) -> dict[str, h.ArmRegistration]:
    return {
        "G": (g or FakeG()).registration(),
        "D": h.ArmRegistration(refusal=ArmRefusal, answer=fake_d),
        "R": (r or FakeR()).registration(),
    }


PASSING_GATES = h.SessionGates(
    passed=True,
    gate_host_sha="2" * 64,
    gate_container_sha="3" * 64,
    preflight_sha="1" * 64,
    up_ts="2026-09-25T00:00:00+00:00",
    container_start_ts="2026-09-25T00:01:00+00:00",
    details=({"name": "prompt_digest", "passed": True, "detail": "ok"},),
)


def make_runtime(
    arms: dict[str, h.ArmRegistration],
    config: serving.ServingConfiguration = PRIMARY,
    **kw: Any,
) -> h.Runtime:
    base: dict[str, Any] = {
        "config": config,
        "arms": arms,
        "corpus_dir": CORPUS,
        "facade": lambda deadline, cancelled, before_send: types.SimpleNamespace(config=config),
        "health": lambda: True,
        "gtt_sampler": FakeGtt,
        "out": lambda message: None,
        "gates": PASSING_GATES,
    }
    base.update(kw)
    return h.Runtime(**base)


def make_binding(
    config: serving.ServingConfiguration = PRIMARY,
    corpus: pathlib.Path = CORPUS,
    *,
    gates_outcome: h.SessionGates | None = None,
) -> Binding:
    outcome = gates_outcome or PASSING_GATES
    return Binding.from_environment(
        corpus,
        config.as_header_dict(),
        config.limit_applied()[0],
        run_env_commit="test",
        run_env_manifest_sha="0" * 64,
        preflight_sha=str(outcome.preflight_sha),
        gate_host_sha=str(outcome.gate_host_sha),
        gate_container_sha=str(outcome.gate_container_sha),
    )


def open_fake(
    path: pathlib.Path,
    config: serving.ServingConfiguration = PRIMARY,
    *,
    gates_outcome: h.SessionGates | None = None,
) -> Any:
    kind = "primary" if config.kind == "primary" else "secondary"
    return open_ledger(
        path,
        make_binding(config, gates_outcome=gates_outcome),
        BLINDING_SEED,
        h.PRIMARY_PLAN if kind == "primary" else h.SECONDARY_PLAN,
    )


def full_run(
    path: pathlib.Path,
    g: FakeG | None = None,
    r: FakeR | None = None,
) -> h.SessionReport:
    with open_fake(path) as ledger:
        return h.run_session(ledger, make_runtime(fake_arms(g, r)))


def rows_of(path: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def runs(path: pathlib.Path) -> list[dict[str, Any]]:
    return [row for row in rows_of(path) if row.get("record") == "run"]
