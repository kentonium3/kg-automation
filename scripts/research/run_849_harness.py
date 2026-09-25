"""Resumable run harness for #849 — 3 arms × 8 questions × 3 repeats = 72 cells (WP08).

The run does not fit in one session, so the interesting property is not running: it is
**stopping safely and resuming without corrupting the result**. The harness is thin on purpose:
every property that must survive a killed session lives in :mod:`arms849.ledger` (the only state),
and the harness only decides WHAT to run next and HOW one attempt is executed.

What it keeps from the phase-(a) harness:

* **The ledger is the state** — nothing is recorded anywhere else; a resume re-derives the work
  left from the ledger (``Ledger.pending_keys``) and nothing else.
* **A ledger is bound to one corpus / prompt / configuration / code** — ``Binding.from_environment``
  plus ``open_ledger`` refuse a resume against anything different (D-16).
* **Question order is protocol** (C-008): arm-major G → D → R, repeat-major, questions in
  ``ask_time`` order (``ledger.plan_keys``).
* **The four-gate precondition** (seed / answer-key / freeze / loader checkers) stays: they run in
  the preflight from the full checkout, and the in-container ``preflight_present_and_matching``
  gate refuses unless all four passed (contracts/gates.md). ``--skip-gates`` is DEVELOPMENT ONLY,
  says so, and binds :data:`grading.SKIP_GATES_SHA` so such a ledger can never be graded.
* **``exceeds_model_context`` is never averaged** — ``Ledger.summarise`` sums ``ok`` rows only.

What it adds (contracts/arm-interface.md, ledger-schema.md, research.md D-10..D-13):

* **CellContext** — arm-interface.md @42056e57: "``limits = {trained, configured, permitted}``,
  ``limit_applied`` and ``limit`` are DERIVED by the CellContext constructor from ``config``
  (``config.limits()``, ``config.limit_applied()``) and cannot be passed independently; a test
  asserts an incoherent CellContext cannot be constructed." :class:`CellContext` has no parameter
  for them.
* **Attempts** — ``begin_attempt`` before every attempt (D-12); the arm runs in a worker thread
  under a **90-minute per-attempt timeout**; on expiry the attempt is cancelled (the facade
  refuses further calls and the in-flight request's socket timeout is the attempt deadline, so
  the server sees the connection close) and the worker is WAITED FOR before ``error: timeout``
  is recorded — never a zombie request (NFR-008).
* **The three exception classes** — arm-interface.md @42056e57: "Any other exception except
  ``ArmRefusal`` (and its subclasses): infrastructure failure → health check → retry ≤ 2 →
  ``error``. ``ArmRefusal`` is terminal: an ``error`` row on the first attempt, zero retries".
  The arm's ``ContextExceeded`` (a ``serving.ContextExceeded`` subclass) → an
  ``exceeds_model_context`` row with ``prompt_tokens``, ``context_limit_applied`` and the plan.
* **Samplers** — ``GttSampler`` around every attempt, ``RssSampler`` around G's; NFR-004: when the
  sampler's first reading is already above the 57.5 GiB ceiling (``breached``) the cell is NOT
  started — an ``event: memory_ceiling`` row, no ``attempt_start``, and the session stops.
* **Calibration** — ledger-schema.md item 6 / D-10: written once, via
  ``calibration.calibrate(ledger, *R.calibration_inputs(views, index_cache))``, when all eight G
  repeat-1 cells are ``ok``, BEFORE the first R cell; ``CalibrationPopulationIncomplete`` →
  ``event: halt`` (``calibration_population_incomplete``) and the session stops. ONE
  ``index_cache`` dict per session is handed to both ``calibration_inputs`` and R's ``bind``
  (design-lead N-3), so the index an R cell reads IS the one calibration counted over.
* **Secondary** — ``--secondary --primary <ledger>`` refuses unless the primary is complete (72
  cells, zero ``not_implemented``), binds ``ServingConfiguration.secondary_yarn()`` with plan
  D × 8 × 3 and ``limit_applied = permitted``, asserts SC-006 on the serving block, and runs the
  secondary context-window gate (an ``event`` row) before its first cell.
* **Grading export** — ``--grading-view`` → :func:`arms849.grading.export`.

**Bus posts are not callable from a script (FR-017).** The agent bus is an MCP tool the operator's
session holds; this process writes ``event`` rows (``halt``, ``memory_ceiling``, ``gate``, …) and
prints ONE status line (``arms849 status: …``) that the operator relays; ``--status`` reprints it
from the ledger at any time.

A ``LedgerWriteFailed`` (ledger-schema.md item 9) is terminal for the session: it stops, prints
the status line, and the next invocation reopens the file (the file is the truth).

Arms register through :data:`ARM_FACTORIES` (arm → factory(resources) → :class:`ArmRegistration`);
the real arms are consumers of this registry, not imports of this module. An unregistered arm's
cells are recorded ``not_implemented`` — "could not run" never collapses into "ran and scored zero".

Usage:
    python3 -m scripts.research.run_849_harness --dry-run
    python3 -m scripts.research.run_849_harness --preflight          # host, full checkout
    python3 -m scripts.research.run_849_harness --host-gates --up-ts <iso>   # host, before `substrate run`
    python3 -m scripts.research.run_849_harness --up-ts <iso>        # in the runner: gates, then cells
    python3 -m scripts.research.run_849_harness --status
    python3 -m scripts.research.run_849_harness --grading-view
    python3 -m scripts.research.run_849_harness --secondary --primary /runs/ledger.jsonl --ledger /runs/secondary.jsonl
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import secrets
import socket
import sys
import threading
import time
import types
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import calibration as calibration_mod
from scripts.research.arms849 import (
    grading,
    serving,
)
from scripts.research.arms849 import questions as questions_mod
from scripts.research.arms849.ledger import (
    ARMS,
    REFUSAL_PREFIX,
    REPEATS,
    AttemptsExhausted,
    Binding,
    Header,
    Ledger,
    LedgerBoundToAnotherConfig,
    LedgerCorrupt,
    LedgerLocked,
    LedgerWriteFailed,
    RunKey,
    SecondScoredRow,
    open_ledger,
    plan_keys,
)
from scripts.research.arms849.prompt import Prompt
from scripts.research.arms849.questions import Question
from scripts.research.arms849.sampler import (
    GTT_CEILING_GIB,
    GttSampler,
    RssSampler,
)
from scripts.research.load_849_corpus import (
    ARM_INPUTS,
    DEFAULT_CORPUS,
    Loaded,
    UnfrozenCorpus,
    replay,
)

#: NFR-008: one attempt may take at most 90 minutes.
ATTEMPT_TIMEOUT_S = 90 * 60
#: After a timeout, how long the cancelled worker is waited for before the session stops.
CANCEL_GRACE_S = 120.0
PRIMARY_PLAN = len(plan_keys())
SECONDARY_PLAN = len(plan_keys(arms=("D",)))
#: SC-006: the only serving fields in which the secondary differs from the primary.
SC006_FIELDS = frozenset({"rope_scaling", "rope_scale", "yarn_orig_ctx", "n_ctx"})
#: The secondary context-window gate's target prompt size (~363k tokens, D-6/D-11).
SECONDARY_GATE_TOKENS = 363_000

_IN_CONTAINER = pathlib.Path("/.dockerenv").exists() or REPO_ROOT == pathlib.Path("/work")
RUNS_DIR = pathlib.Path("/runs") if pathlib.Path("/runs").is_dir() else REPO_ROOT / "build" / "849-runs"
DEFAULT_LEDGER = RUNS_DIR / "ledger.jsonl"
CORPUS_DIR = pathlib.Path(os.environ.get("ARMS849_CORPUS", str(DEFAULT_CORPUS)))
LLAMA_URL = "http://llama:8080"
FALKORDB_ADDR = ("falkordb", 6379)
PROCESS_START = datetime.now(timezone.utc).isoformat()


class HarnessStopped(RuntimeError):
    """The session stopped on a condition the operator must see (halt, ceiling, write failure)."""


class PrimaryIncomplete(RuntimeError):
    """``--secondary`` was asked for before the primary ledger is complete."""


class AttemptCancelled(RuntimeError):
    """The attempt's deadline passed; the facade refuses further calls."""


# --------------------------------------------------------------------------
# CellContext and the serving facade
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CellContext:
    """What the harness hands an arm for one attempt (contracts/arm-interface.md, ctx bullet).

    ``limits``, ``limit_applied``, ``limit``, ``seed`` and ``ledger_kind`` are ``init=False``:
    DERIVED here from ``config`` and ``repeat``, never passed — "cannot be passed independently"
    (arm-interface.md @42056e57). ``dataclasses.replace`` cannot set them either, so no
    construction path yields a pair that disagrees with ``config``. When the facade carries its
    own ``config`` it must be this one.
    """

    repeat: int
    attempt: int
    config: serving.ServingConfiguration
    serving: Any
    prompt: Prompt
    embedder: Any = None
    calibration: Mapping[str, Any] | None = None
    cancelled: threading.Event = field(default_factory=threading.Event, compare=False)
    limits: Mapping[str, int] = field(init=False)
    limit_applied: str = field(init=False)
    limit: int = field(init=False)
    seed: int = field(init=False)
    ledger_kind: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.repeat) is not int or not 1 <= self.repeat <= REPEATS:
            raise ValueError(f"repeat must be an int in 1..{REPEATS}, got {self.repeat!r}")
        if type(self.attempt) is not int or not 1 <= self.attempt <= 3:
            raise ValueError(f"attempt must be an int in 1..3, got {self.attempt!r}")
        if not isinstance(self.config, serving.ServingConfiguration):
            raise TypeError("config must be a ServingConfiguration")
        facade_config = getattr(self.serving, "config", None)
        if facade_config is not None and facade_config != self.config:
            raise ValueError("the serving facade carries a different configuration than ctx.config")
        lim = self.config.limits()
        name, value = self.config.limit_applied()
        object.__setattr__(self, "limits", types.MappingProxyType(
            {"trained": lim.trained, "configured": lim.configured, "permitted": lim.permitted}))
        object.__setattr__(self, "limit_applied", name)
        object.__setattr__(self, "limit", value)
        object.__setattr__(self, "seed", self.config.seed_for(self.repeat))
        object.__setattr__(self, "ledger_kind", self.config.kind)


class ServingFacade:
    """``ctx.serving``: ``serialize``, ``count_tokens``, ``count_text``, ``complete`` over the ONE
    client in :mod:`arms849.serving`. Per attempt: ``complete``'s socket timeout is the attempt's
    remaining time, and once the attempt is cancelled every call refuses (no late request)."""

    def __init__(self, config: serving.ServingConfiguration, tokenizer: Any, base_url: str = LLAMA_URL,
                 deadline: float | None = None, cancelled: threading.Event | None = None) -> None:
        self.config = config
        self.tokenizer = tokenizer
        self.base_url = base_url
        self.deadline = deadline
        self.cancelled = cancelled or threading.Event()

    def _live(self) -> None:
        if self.cancelled.is_set():
            raise AttemptCancelled("the attempt was cancelled at its deadline")

    def serialize(self, request: bytes, seed: int) -> dict[str, Any]:
        self._live()
        return serving.serialize(request, self.config, seed, self.tokenizer)

    def count_tokens(self, body: dict[str, Any]) -> int:
        return serving.count_tokens(body, self.tokenizer)

    def count_text(self, data: bytes) -> int:
        return int(self.tokenizer.count(data))

    def complete(self, body: dict[str, Any]) -> serving.Completion:
        self._live()
        remaining = ATTEMPT_TIMEOUT_S if self.deadline is None else self.deadline - time.monotonic()
        if remaining <= 0:
            raise AttemptCancelled("the attempt's deadline passed before the request was sent")
        return serving.complete(body, self.tokenizer, self.config.limits().permitted, self.base_url,
                                timeout_s=remaining)


# --------------------------------------------------------------------------
# The arm registry
# --------------------------------------------------------------------------

AnswerFn = Callable[[Question, Loaded, CellContext], Mapping[str, Any]]


@dataclass(frozen=True)
class ArmRegistration:
    """One arm as the harness drives it (contracts/arm-interface.md).

    G/D: ``answer(question, view, ctx)``; G also ``build_graph(question, view) -> GraphStats-like``
    and ``drop_graph(question)``. R: ``bind(index_cache) -> answer`` and
    ``calibration_inputs(views, index_cache) -> (availability, assemble_r_tokens)`` — the
    registration closes over the corpus text, tokenizer and embedder, and the harness supplies the
    SAME ``index_cache`` dict to both (N-3).
    """

    answer: AnswerFn | None = None
    bind: Callable[[dict[str, Any]], AnswerFn] | None = None
    calibration_inputs: Callable[[Mapping[str, Loaded], dict[str, Any]],
                                 tuple[Mapping[str, int], Callable[[str, int], int]]] | None = None
    build_graph: Callable[[Question, Loaded], Any] | None = None
    drop_graph: Callable[[Question], Any] | None = None


@dataclass(frozen=True)
class Resources:
    """What an arm factory may close over (live runs)."""

    corpus_dir: pathlib.Path
    config: serving.ServingConfiguration
    tokenizer: Any
    embedder: Any


#: arm → factory(resources) → ArmRegistration. Empty here: the arms register themselves.
ARM_FACTORIES: dict[str, Callable[[Resources], ArmRegistration]] = {}


def build_arms(resources: Resources) -> dict[str, ArmRegistration]:
    return {arm: factory(resources) for arm, factory in ARM_FACTORIES.items()}


def arm_view(key: RunKey, loaded: Loaded) -> Loaded:
    """Narrow a replayed corpus to what THIS arm may read: loader_links are G's input only
    (Amendment A1 (b)); D and R get ``links == []`` rather than being trusted not to look."""
    if "loader_links.jsonl" not in ARM_INPUTS[key.arm]:
        loaded.links = []
    return loaded


def plan(kind: str = "primary") -> list[RunKey]:
    """The cells in execution order (protocol, C-008): 72 primary, 24 secondary (D only)."""
    return plan_keys() if kind == "primary" else plan_keys(arms=("D",))


# --------------------------------------------------------------------------
# One session
# --------------------------------------------------------------------------


@dataclass
class Runtime:
    """Everything a session needs besides the ledger — injectable, so the loop is testable with
    fake arms and without the stack."""

    config: serving.ServingConfiguration
    arms: Mapping[str, ArmRegistration]
    facade: Callable[[float, threading.Event], Any]           # (deadline, cancelled) -> ctx.serving
    health: Callable[[], bool]
    corpus_dir: pathlib.Path = CORPUS_DIR
    prompt: Prompt = field(default_factory=Prompt)
    embedder: Any = None
    gtt_sampler: Callable[[], GttSampler] = GttSampler
    rss_sampler: Callable[[], RssSampler] = RssSampler
    attempt_timeout_s: float = ATTEMPT_TIMEOUT_S
    cancel_grace_s: float = CANCEL_GRACE_S
    out: Callable[[str], None] = print


@dataclass
class SessionReport:
    completed: int = 0
    failed: int = 0
    stopped: str | None = None


def _is_refusal(exc: BaseException) -> bool:
    """``ArmRefusal`` and its subclasses — each arm defines its own class of that name."""
    return any(c.__name__ == "ArmRefusal" for c in type(exc).__mro__)


def _peak(sampler: Any, attr: str) -> float | None:
    value = getattr(sampler, attr, None)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class Session:
    """Runs pending cells of one open ledger, in protocol order, until done or stopped."""

    def __init__(self, ledger: Ledger, runtime: Runtime) -> None:
        self.ledger = ledger
        self.rt = runtime
        #: ONE index cache per session, handed to R's calibration_inputs AND R's bind (N-3).
        self.index_cache: dict[str, Any] = {}
        self.graph_stats: dict[str, Any] = {}          # question → GraphStats built this session
        self._answers: dict[str, AnswerFn] = {}
        self.report = SessionReport()

    # -- helpers ------------------------------------------------------------

    def _answer_fn(self, arm: str, reg: ArmRegistration) -> AnswerFn:
        if arm not in self._answers:
            if reg.bind is not None:
                self._answers[arm] = reg.bind(self.index_cache)
            elif reg.answer is not None:
                self._answers[arm] = reg.answer
            else:
                raise TypeError(f"arm {arm} registration has neither answer nor bind")
        return self._answers[arm]

    def _view(self, key: RunKey, question: Question) -> Loaded:
        return arm_view(key, replay(self.rt.corpus_dir, questions_mod.ask_time_dt(question), verify=False))

    def stop(self, reason: str) -> None:
        self.report.stopped = reason

    # -- calibration (D-10) -------------------------------------------------

    def ensure_calibration(self) -> bool:
        """Before the first R cell: the calibration record, written once (ledger-schema.md item 6)."""
        if self.ledger.calibration() is not None:
            return True
        reg = self.rt.arms.get("R")
        if reg is None or reg.calibration_inputs is None:
            return True                                   # R unregistered: its cells are not_implemented
        views = {q.id: self._view(RunKey("R", q.id, 1), q) for q in questions_mod.QUESTIONS}
        try:
            cal = calibration_mod.calibrate(self.ledger, *reg.calibration_inputs(views, self.index_cache))
        except calibration_mod.CalibrationPopulationIncomplete as exc:
            self.ledger.event("halt", {"reason": "calibration_population_incomplete",
                                       "missing": exc.missing, "terminal_error": exc.terminal_error})
            self.stop(f"halt: calibration_population_incomplete (G repeat-1 terminal error {exc.terminal_error}, "
                      f"not scored {exc.missing}) — blocked, awaiting a registered disposition")
            return False
        self.ledger.write_calibration(cal.as_record())
        return True

    def _calibration_obj(self) -> calibration_mod.Calibration | None:
        rec = self.ledger.calibration()
        if rec is None:
            return None
        fields = {k: rec[k] for k in calibration_mod.Calibration.__dataclass_fields__}
        fields["band"] = tuple(fields["band"])
        return calibration_mod.Calibration(**fields)

    # -- the run --------------------------------------------------------------

    def run(self, keys: Sequence[RunKey]) -> SessionReport:
        for key in keys:
            if self.report.stopped:
                break
            if key.arm == "R" and not self.ensure_calibration():
                break
            outcome = self.execute(key)
            mark = {"ok": "·", "error": "!", "not_implemented": "-", "exceeds_model_context": "x"}.get(str(outcome), "?")
            self.rt.out(f"  {mark} {key.arm} {key.question:3} r{key.repeat}  {outcome}")
            if outcome == "ok":
                self.report.completed += 1
            elif outcome == "error":
                self.report.failed += 1
            if key.arm == "G" and key.repeat == REPEATS and self.ledger.terminal(key) is not None:
                self._drop_graph(key)
        return self.report

    def _drop_graph(self, key: RunKey) -> None:
        reg = self.rt.arms.get("G")
        if reg is None or reg.drop_graph is None:
            return
        try:
            reg.drop_graph(questions_mod.by_id(key.question))
        except Exception as exc:  # noqa: BLE001 — recorded; the next build is idempotent
            self.ledger.event("drop_graph_failed", {"question": key.question, "error": f"{type(exc).__name__}: {exc}"})
        self.graph_stats.pop(key.question, None)

    def execute(self, key: RunKey) -> str | None:
        """Run one cell to a terminal outcome, or until the session stops. Returns the last
        outcome recorded for the key (``None`` when nothing was recorded)."""
        question = questions_mod.by_id(key.question)
        reg = self.rt.arms.get(key.arm)
        if reg is None:
            self.ledger.begin_attempt(key)
            row: dict[str, Any] = {"ask_time": question.ask_time, "elapsed_s": 0.0,
                                   "note": f"arm {key.arm} is not registered"}
            if key.arm == "D":
                row["context_limit_applied"] = self.rt.config.limit_applied()[0]
            self.ledger.record(key, "not_implemented", row, self.rt.config.as_header_dict())
            return "not_implemented"
        last: str | None = None
        while self.ledger.terminal(key) is None and not self.report.stopped:
            outcome, retryable = self._one_attempt(key, question, reg)
            last = outcome or last
            if self.report.stopped or not retryable or self.ledger.terminal(key) is not None:
                break
            if not self.rt.health():
                self.ledger.event("substrate_unhealthy", {**key.as_dict(), "after": outcome})
                self.stop(f"substrate unhealthy after {key.arm} {key.question} r{key.repeat}; "
                          f"no retry — bring the stack back and resume")
        return last

    def _one_attempt(self, key: RunKey, question: Question, reg: ArmRegistration) -> tuple[str | None, bool]:
        """One attempt. Returns (outcome recorded or None, whether an infrastructure retry applies).

        Everything that can fail for a reason other than the attempt itself — the replayed view,
        the bound arm, the samplers' first readings — is settled BEFORE ``begin_attempt``, so a
        harness-side refusal never spends one of the key's three attempts."""
        view = self._view(key, question)
        answer_fn = self._answer_fn(key.arm, reg)
        with ExitStack() as stack:
            gtt = stack.enter_context(self.rt.gtt_sampler())
            rss = stack.enter_context(self.rt.rss_sampler()) if key.arm == "G" else None
            if getattr(gtt, "breached", False):
                # NFR-004: refuse to START the cell — no attempt row, an event, and stop.
                self.ledger.event("memory_ceiling", {**key.as_dict(), "gtt_gib": _peak(gtt, "peak_gib"),
                                                     "ceiling_gib": GTT_CEILING_GIB})
                self.stop(f"memory ceiling: GTT above {GTT_CEILING_GIB} GiB before "
                          f"{key.arm} {key.question} r{key.repeat}; cell not started")
                return None, False
            unreadable = [name for name, s, attr in (("peak_gtt_gib", gtt, "peak_gib"),
                                                     ("falkordb_rss_peak_mib", rss, "peak_mib"))
                          if s is not None and _peak(s, attr) is None]
            if unreadable:
                # A column the row contract requires cannot be measured: running the arm would
                # burn an attempt whose row the ledger must refuse. Could-not-check, never zero.
                self.ledger.event("sampler_unreadable", {**key.as_dict(), "columns": unreadable})
                self.stop(f"sampler cannot read {unreadable} before {key.arm} {key.question} r{key.repeat}; "
                          f"cell not started")
                return None, False
            try:
                attempt = self.ledger.begin_attempt(key)
            except (AttemptsExhausted, SecondScoredRow):
                return None, False                            # terminal already (never an infinite loop)
            started = time.monotonic()
            deadline = started + self.rt.attempt_timeout_s
            cancelled = threading.Event()
            ctx = CellContext(repeat=key.repeat, attempt=attempt, config=self.rt.config,
                              serving=self.rt.facade(deadline, cancelled), prompt=self.rt.prompt,
                              embedder=self.rt.embedder,
                              calibration=self.ledger.calibration() if key.arm == "R" else None,
                              cancelled=cancelled)

            def work() -> Mapping[str, Any]:
                if key.arm == "G" and reg.build_graph is not None and key.question not in self.graph_stats:
                    self.graph_stats[key.question] = reg.build_graph(question, view)
                return answer_fn(question, view, ctx)

            status, value = _call_with_timeout(work, self.rt.attempt_timeout_s, cancelled, self.rt.cancel_grace_s)
        elapsed = round(time.monotonic() - started, 3)
        peak_gtt = _peak(gtt, "peak_gib")
        base: dict[str, Any] = {"ask_time": question.ask_time, "elapsed_s": elapsed}
        if key.arm == "D":
            base["context_limit_applied"] = ctx.limit_applied

        if status == "ok":
            outcome, retry = self._record_ok(key, question, view, ctx, value, base, peak_gtt, rss)
        elif status in ("timeout", "zombie"):
            outcome, retry = self._record_error(key, base, "timeout", peak_gtt), True
            if status == "zombie":
                self.ledger.event("zombie_worker", {**key.as_dict(), "grace_s": self.rt.cancel_grace_s})
                self.stop("a timed-out worker did not stop within the grace period; the session stops so no "
                          "second request can overlap it")
        else:
            outcome, retry = self._record_raised(key, value, base, peak_gtt)
        if getattr(gtt, "breached", False):
            self.ledger.event("memory_ceiling", {**key.as_dict(), "gtt_gib": peak_gtt, "ceiling_gib": GTT_CEILING_GIB,
                                                 "during": "attempt"})
            self.stop(f"memory ceiling: GTT exceeded {GTT_CEILING_GIB} GiB during {key.arm} {key.question} r{key.repeat}")
        return outcome, retry

    def _record_error(self, key: RunKey, base: dict[str, Any], error: str, peak_gtt: float | None) -> str | None:
        if peak_gtt is None:
            self.ledger.event("telemetry_incomplete", {**key.as_dict(), "missing": "peak_gtt_gib", "error": error})
            return None
        self.ledger.record(key, "error", {**base, "error": error, "peak_gtt_gib": peak_gtt},
                           self.rt.config.as_header_dict())
        return "error"

    def _record_raised(self, key: RunKey, exc: Any, base: dict[str, Any],
                       peak_gtt: float | None) -> tuple[str | None, bool]:
        if isinstance(exc, serving.ContextExceeded):
            tokens = getattr(exc, "prompt_tokens", None)
            if key.arm == "D" and type(tokens) is int:
                row = {**base, "prompt_tokens": tokens,
                       "context_limit_applied": str(getattr(exc, "limit_applied", base["context_limit_applied"]))}
                plan_obj = getattr(exc, "plan", None)
                if plan_obj is not None:
                    row["plan"] = plan_obj.as_dict() if hasattr(plan_obj, "as_dict") else dict(plan_obj)
                self.ledger.record(key, "exceeds_model_context", row, self.rt.config.as_header_dict())
                return "exceeds_model_context", False
            # Outside D, or without a count, a context overflow is a permanent configuration fact:
            # terminal like ArmRefusal (a retry would count the same bytes again).
            msg = (f"{REFUSAL_PREFIX} {type(exc).__name__} from arm {key.arm}: {exc} — exceeds_model_context "
                   f"is a D outcome carrying prompt_tokens (data-model.md § Outcome)")
            return self._record_error(key, base, msg, peak_gtt), False
        if _is_refusal(exc):
            name = type(exc).__name__
            msg = f"{REFUSAL_PREFIX} {exc}" if name == "ArmRefusal" else f"{REFUSAL_PREFIX} {name}: {exc}"
            return self._record_error(key, base, msg, peak_gtt), False
        return self._record_error(key, base, f"{type(exc).__name__}: {exc}", peak_gtt), True

    def _record_ok(self, key: RunKey, question: Question, view: Loaded, ctx: CellContext, answer: Any,
                   base: dict[str, Any], peak_gtt: float | None, rss: Any) -> tuple[str | None, bool]:
        row = dict(answer)
        row.update(base)
        row.update(seed=ctx.seed, peak_gtt_gib=peak_gtt, events_loaded=len(view.events),
                   nodes_loaded=len(view.entities), edges_loaded=len(view.edges), links_loaded=len(view.links))
        missing = []
        if peak_gtt is None:
            missing.append("peak_gtt_gib")
        if key.arm == "G":
            rss_peak = _peak(rss, "peak_mib")
            row["falkordb_rss_peak_mib"] = rss_peak
            if rss_peak is None:
                missing.append("falkordb_rss_peak_mib")
            stats = self.graph_stats.get(key.question)
            if stats is not None:
                row["graph_stats"] = (dataclasses.asdict(stats) if dataclasses.is_dataclass(stats) and not isinstance(stats, type)
                                      else dict(stats))
        if key.arm == "R":
            tokens = row.get("assembled_context_tokens")
            row["r_g_ratio"] = calibration_mod.ratio_for(key.question, tokens if type(tokens) is int else None,
                                                         self._calibration_obj())
        if missing:
            # A measurement that could not be taken is never a zero (Engineering Principle 14): the
            # attempt stays counted without a row and the infrastructure ladder applies.
            self.ledger.event("telemetry_incomplete", {**key.as_dict(), "missing": missing})
            return None, True
        try:
            self.ledger.record(key, "ok", row, self.rt.config.as_header_dict())
        except ValueError as exc:
            # The answer does not meet the row contract: a code/configuration defect, terminal.
            msg = f"{REFUSAL_PREFIX} the answer was refused by the ledger row contract: {exc}"
            return self._record_error(key, base, msg, peak_gtt), False
        return "ok", False


def _call_with_timeout(fn: Callable[[], Any], timeout_s: float, cancelled: threading.Event,
                       grace_s: float) -> tuple[str, Any]:
    """Run ``fn`` in a worker thread under a deadline. Returns ("ok", value), ("raised", exc),
    ("timeout", None) once the cancelled worker has EXITED, or ("zombie", None) when it did not
    exit within ``grace_s``. A BaseException that is not an Exception (KeyboardInterrupt,
    SystemExit) raised in the worker is re-raised here: the session dies mid-cell, and the
    attempt_start row already counts the attempt (D-12)."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — carried to the calling thread
            box["exc"] = exc

    worker = threading.Thread(target=target, name="arms849-attempt", daemon=True)
    worker.start()
    try:
        worker.join(timeout_s)
    except BaseException:
        cancelled.set()
        raise
    if worker.is_alive():
        cancelled.set()
        worker.join(grace_s)
        return ("zombie", None) if worker.is_alive() else ("timeout", None)
    if "exc" in box:
        exc = box["exc"]
        if not isinstance(exc, Exception):
            raise exc
        return "raised", exc
    return "ok", box.get("value")


def status_line(ledger: Ledger, kind: str | None = None) -> str:
    """The ONE line the operator relays to the bus (FR-017)."""
    header = ledger.header
    kind = kind or ("primary" if header.plan == PRIMARY_PLAN else "secondary")
    keys = plan(kind)
    counts: dict[str, int] = {}
    for k in keys:
        t = ledger.terminal(k) or "pending"
        counts[t] = counts.get(t, 0) + 1
    halts = [r for r in ledger.rows if r.get("record") == "event" and r.get("kind") == "halt"]
    parts = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    tail = f"; HALTED ({halts[-1].get('detail', {}).get('reason')})" if halts else ""
    return f"arms849 status: {ledger.path.name} [{kind}] {len(keys) - counts.get('pending', 0)}/{len(keys)} terminal — {parts}{tail}"


def run_session(ledger: Ledger, runtime: Runtime, limit: int | None = None, kind: str = "primary") -> SessionReport:
    """Run the pending cells of ``ledger`` (protocol order), at most ``limit`` of them."""
    todo = ledger.pending_keys(plan(kind))
    total = len(plan(kind))
    if limit:
        todo = todo[:limit]
    runtime.out(f"{total - len(ledger.pending_keys(plan(kind)))} of {total} cells terminal; {len(todo)} to go this session")
    session = Session(ledger, runtime)
    try:
        report = session.run(todo)
    except LedgerWriteFailed as exc:
        session.stop(f"ledger write failed — {exc}; reopen with the same command (the file is the truth)")
        runtime.out(f"arms849 status: STOPPED — {session.report.stopped}")
        return session.report
    if report.stopped:
        runtime.out(f"arms849 status: STOPPED — {report.stopped}")
    runtime.out(status_line(ledger, kind))
    return report


# --------------------------------------------------------------------------
# Opening ledgers
# --------------------------------------------------------------------------


def peek_header(path: pathlib.Path) -> dict[str, Any] | None:
    """The persisted header line, read without the lock (values only; open_ledger validates)."""
    path = pathlib.Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open("rb") as fh:
        first = fh.readline()
    try:
        obj = json.loads(first)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) and obj.get("record") == "header" else None


def open_run_ledger(path: pathlib.Path, binding: Binding, kind: str = "primary") -> Ledger:
    """Open (or create) a run ledger. A fresh ledger draws a blinding seed; a resume reuses the
    header's (the seed is not an environment property — every OTHER field is compared)."""
    existing = peek_header(path)
    seed = existing["blinding_seed"] if existing and type(existing.get("blinding_seed")) is int \
        else secrets.randbelow(2**31)
    return open_ledger(path, binding, seed, PRIMARY_PLAN if kind == "primary" else SECONDARY_PLAN)


def open_existing(path: pathlib.Path) -> Ledger:
    """Open an existing ledger for reading (status, export, the secondary's primary check): its own
    header is the binding, so every persisted row is re-validated and the lock is held."""
    header = peek_header(path)
    if header is None:
        raise LedgerCorrupt(f"{path}: no header")
    h = Header.from_dict(header)
    return open_ledger(path, h.binding, h.blinding_seed, h.plan)


def require_complete_primary(primary: Ledger) -> None:
    """ledger-schema.md item 8: the named primary must be complete — 72 cells, zero not_implemented."""
    if primary.header.plan != PRIMARY_PLAN or primary.header.binding.serving.get("kind") != "primary":
        raise PrimaryIncomplete(f"{primary.path} is not a primary ledger")
    ok, detail = grading.is_complete(primary)
    if not ok:
        raise PrimaryIncomplete(f"{primary.path} is not complete: {detail}")


def sc006_difference(primary_header: Header, secondary_header: Header) -> set[str]:
    """Serving fields that differ between the two headers; ``kind`` is a label, not a difference
    (``ServingConfiguration.differs_from``)."""
    a, b = primary_header.binding.serving, secondary_header.binding.serving
    return {k for k in set(a) | set(b) if k != "kind" and a.get(k) != b.get(k)}


def open_secondary(primary_path: pathlib.Path, secondary_path: pathlib.Path, binding: Binding) -> Ledger:
    """``--secondary``: refuse unless the primary is complete; open the secondary ledger (D × 8 × 3,
    ``limit_applied = permitted``); assert SC-006 before any cell."""
    if binding.serving.get("kind") != "secondary" or binding.limit_applied != "permitted":
        raise ValueError("the secondary binding must carry ServingConfiguration.secondary_yarn() and the permitted limit")
    with open_existing(primary_path) as primary:
        require_complete_primary(primary)
        primary_header = primary.header
    ledger = open_run_ledger(secondary_path, binding, kind="secondary")
    diff = sc006_difference(primary_header, ledger.header)
    if diff != SC006_FIELDS:
        ledger.close()
        raise LedgerBoundToAnotherConfig(f"SC-006: secondary serving differs from the primary in {sorted(diff)}, "
                                         f"not exactly {sorted(SC006_FIELDS)}")
    return ledger


def secondary_context_gate(ledger: Ledger, probe: Callable[[], dict[str, Any]]) -> bool:
    """The secondary's context-window gate, once per ledger, before its first cell: ``probe``
    returns ``{passed, n_ctx, rope, prompt_tokens, peak_gtt_gib, prefill_s, generation_tok_s, …}``;
    recorded as an ``event`` (kind ``secondary_context_gate``)."""
    for r in ledger.rows:
        if r.get("record") == "event" and r.get("kind") == "secondary_context_gate" \
                and isinstance(r.get("detail"), dict) and r["detail"].get("passed") is True:
            return True
    try:
        detail = dict(probe())
    except Exception as exc:  # noqa: BLE001 — a gate that raises has failed, with the reason
        detail = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    detail["passed"] = detail.get("passed") is True
    ledger.event("secondary_context_gate", detail)
    return bool(detail["passed"])


# --------------------------------------------------------------------------
# Live wiring (the runner container; exercised only against the stack)
# --------------------------------------------------------------------------


def forbidden_words() -> tuple[str, ...]:
    """The isolation scan's words, built from parts (gates.GateEnv: "built from parts by the caller")."""
    return ("or" + "acle", "se" + "ed/", "trace" + "ability")


def identity_from_setup(setup_record: Mapping[str, Any], chat_template_sha256: str) -> serving.ServingIdentity:
    """ServingIdentity from WP02's setup.json (+ the preflight's chat-template sha): the embedder and
    tokenizer shas are sha256 over their cache files' ``path:sha`` lines, in path order."""
    def tree(prefix: str) -> str:
        lines = [f"{p}:{s}" for p, s in sorted(setup_record.get("cache_shas", {}).items()) if p.startswith(prefix)]
        if not lines:
            raise RuntimeError(f"setup.json records no cache files under {prefix}")
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    image = str(setup_record["llama_image"])
    return serving.ServingIdentity(
        gguf_sha256=str(setup_record["gguf_sha256"]), image_digest=image.split("@", 1)[-1],
        embedder_model_sha256=tree("fastembed/"), tokenizer_files_sha256=tree("qwen-tokenizer/"),
        chat_template_sha256=chat_template_sha256)


def container_health(config: serving.ServingConfiguration, base_url: str = LLAMA_URL,
                     falkordb: tuple[str, int] = FALKORDB_ADDR) -> bool:
    """Inside the runner (no docker socket): llama ``/health`` ok and ``/props`` n_ctx == config;
    FalkorDB answers PING. The docker-derived half of health is the host phase's."""
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=10) as r:
            if json.loads(r.read().decode())["status"] != "ok":
                return False
        with urllib.request.urlopen(f"{base_url}/props", timeout=10) as r:
            props = json.loads(r.read().decode())
        if int((props.get("default_generation_settings") or {}).get("n_ctx") or 0) != config.n_ctx:
            return False
        with socket.create_connection(falkordb, timeout=5) as s:
            s.sendall(b"PING\r\n")
            return s.recv(16).startswith(b"+PONG")
    except (OSError, ValueError, KeyError):
        return False


def _gate_env(corpus: pathlib.Path, config: serving.ServingConfiguration, up_ts: str,
              header_code_hashes: dict[str, str] | None = None, run_root: pathlib.Path = REPO_ROOT) -> Any:
    from scripts.research.arms849 import gates
    from scripts.research.arms849.substrate import CACHE_DIR

    return gates.GateEnv(
        run_root=run_root, corpus_dir=corpus, cache_dir=pathlib.Path(os.environ.get("ARMS849_CACHE", str(CACHE_DIR))),
        preflight_path=RUNS_DIR / "preflight.json", export_manifest_path=run_root / ".export-manifest.json",
        llama_base_url=LLAMA_URL, expect_n_ctx=config.n_ctx,
        expect_rope="yarn" if config.rope_scaling == "yarn" else "none",
        expected_chat_template_sha256=config.chat_template_sha256, up_ts=up_ts,
        host_record_path=RUNS_DIR / "gate-host.json", container_start_ts=PROCESS_START,
        header_code_hashes=header_code_hashes, forbidden_words=forbidden_words())


def live_binding(ledger_path: pathlib.Path, corpus: pathlib.Path, config: serving.ServingConfiguration,
                 up_ts: str, skip_gates: bool,
                 container_phase: Callable[..., tuple[Any, str]] | None = None) -> Binding:
    """Run the CONTAINER gate phase (before the header), then bind the three gate records."""
    manifest_path = REPO_ROOT / ".export-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if skip_gates:
        print("--skip-gates: DEVELOPMENT ONLY — no gate ran; this ledger binds the skip-gates sha and "
              "can never be graded or used as a primary")
        preflight_sha = gate_host_sha = gate_container_sha = grading.SKIP_GATES_SHA
    else:
        from scripts.research.arms849 import gates
        from scripts.research.arms849.preflight import load_preflight

        existing = peek_header(ledger_path)
        env = _gate_env(corpus, config, up_ts, existing.get("code_hashes") if existing else None)
        phase = container_phase or gates.run_container_phase
        _, gate_container_sha = phase(env, RUNS_DIR / "gate-container.json")
        host = json.loads((RUNS_DIR / "gate-host.json").read_text(encoding="utf-8"))
        gate_host_sha = str(host["gate_host_sha"])
        preflight_sha = str(load_preflight(RUNS_DIR / "preflight.json")["preflight_sha"])
    return Binding.from_environment(
        corpus, config.as_header_dict(), config.limit_applied()[0],
        run_env_commit=str(manifest.get("source_commit", "unexported")),
        run_env_manifest_sha=str(manifest.get("content_sha", "unexported")),
        preflight_sha=preflight_sha, gate_host_sha=gate_host_sha, gate_container_sha=gate_container_sha,
        repo_root=REPO_ROOT)


def live_config(secondary: bool) -> serving.ServingConfiguration:
    from scripts.research.arms849.preflight import load_preflight

    setup_record = json.loads((RUNS_DIR / "setup.json").read_text(encoding="utf-8"))
    identity = identity_from_setup(setup_record, str(load_preflight(RUNS_DIR / "preflight.json")["chat_template_sha256"]))
    return serving.ServingConfiguration.secondary_yarn(identity) if secondary else serving.ServingConfiguration.primary(identity)


def live_runtime(config: serving.ServingConfiguration, corpus: pathlib.Path) -> Runtime:
    from scripts.research.arms849.substrate import CACHE_DIR

    tokenizer = serving.Tokenizer(pathlib.Path(os.environ.get("ARMS849_CACHE", str(CACHE_DIR))) / "qwen-tokenizer")
    embedder = None
    arms = build_arms(Resources(corpus_dir=corpus, config=config, tokenizer=tokenizer, embedder=embedder))
    return Runtime(config=config, arms=arms, corpus_dir=corpus,
                   facade=lambda deadline, cancelled: ServingFacade(config, tokenizer, LLAMA_URL, deadline, cancelled),
                   health=lambda: container_health(config))


def live_secondary_gate(runtime: Runtime) -> Callable[[], dict[str, Any]]:
    """n_ctx 393216 (+ yarn, verified by the host phase) and one ~363k-token prompt — the full D view
    at the last question's ask_time — through ``serving.complete``, with peak GTT and rates."""
    def probe() -> dict[str, Any]:
        from scripts.research.arms849.text import FrozenCorpusText

        config = runtime.config
        with urllib.request.urlopen(f"{LLAMA_URL}/props", timeout=10) as r:
            n_ctx = int((json.loads(r.read().decode()).get("default_generation_settings") or {}).get("n_ctx") or 0)
        last = questions_mod.QUESTIONS[-1]
        view = arm_view(RunKey("D", last.id, 1), replay(runtime.corpus_dir, questions_mod.ask_time_dt(last), verify=False))
        block = FrozenCorpusText(runtime.corpus_dir).render_full_view(view)
        facade = runtime.facade(time.monotonic() + ATTEMPT_TIMEOUT_S, threading.Event())
        body = facade.serialize(runtime.prompt.render(block, "context-window gate: summarise the material."), config.seed_for(1))
        tokens = facade.count_tokens(body)
        with runtime.gtt_sampler() as gtt:
            completion = facade.complete(body)
        return {"passed": n_ctx == config.n_ctx and tokens >= SECONDARY_GATE_TOKENS * 0.95,
                "n_ctx": n_ctx, "rope": config.rope_scaling, "prompt_tokens": tokens,
                "peak_gtt_gib": gtt.peak_gib, "prefill_s": completion.prefill_s,
                "prefill_tok_s": (completion.prompt_tokens / completion.prefill_s) if completion.prefill_s else None,
                "generation_tok_s": completion.generation_tok_s}
    return probe


def host_phase(up_ts: str) -> str:
    """The HOST gate phase (contracts/gates.md), right before the runner launches: boundary
    self-test, docker-derived health, preflight matching → gate-host.json. Returns gate_host_sha."""
    from scripts.research.arms849 import gates, substrate

    if _IN_CONTAINER:
        raise RuntimeError("the host phase runs on the host (it needs docker), never in the runner")
    secondary = False
    env = gates.GateEnv(
        run_root=substrate.EXPORT_DIR, corpus_dir=substrate.CORPUS_DIR, cache_dir=substrate.CACHE_DIR,
        preflight_path=substrate.RUNS_DIR / "preflight.json",
        export_manifest_path=substrate.EXPORT_DIR / ".export-manifest.json", up_ts=up_ts,
        expect_n_ctx=serving.SECONDARY_N_CTX if secondary else serving.PRIMARY_N_CTX,
        expect_rope="yarn" if secondary else "none",
        self_test=substrate.self_test, health=substrate.health, forbidden_words=forbidden_words())
    _, sha = gates.run_host_phase(env, substrate.RUNS_DIR / "gate-host.json")
    return sha


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _status(path: pathlib.Path) -> int:
    if peek_header(path) is None:
        print(f"no ledger at {path} — nothing run yet ({PRIMARY_PLAN} planned)")
        return 0
    try:
        with open_existing(path) as ledger:
            print(status_line(ledger))
            for arm in ARMS:
                for q in questions_mod.QUESTIONS:
                    cells = [ledger.terminal(RunKey(arm, q.id, r)) or "pending" for r in range(1, REPEATS + 1)]
                    print(f"    {arm} {q.id:3} {' '.join(cells)}")
    except LedgerLocked as exc:
        print(f"arms849 status: {path.name} is in use ({exc}); rerun --status when the session ends")
    return 0


def _dry_run(kind: str) -> int:
    keys = plan(kind)
    print(f"{len(keys)} cells, in execution order (question order within an arm+repeat is protocol):")
    for key in keys:
        print(f"  {key.arm} {key.question:3} r{key.repeat}")
    missing = [a for a in (ARMS if kind == "primary" else ("D",)) if a not in ARM_FACTORIES]
    if missing:
        print(f"\narms not yet registered: {', '.join(missing)} — their cells would be not_implemented")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="run_849_harness")
    ap.add_argument("--corpus", type=pathlib.Path, default=CORPUS_DIR)
    ap.add_argument("--ledger", type=pathlib.Path, default=DEFAULT_LEDGER)
    ap.add_argument("--limit", type=int, help="stop after N cells this session")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--preflight", action="store_true", help="host only: the four checkers from the full checkout")
    ap.add_argument("--host-gates", action="store_true", help="host only: the host gate phase (before substrate run)")
    ap.add_argument("--gates", action="store_true", help="in the runner: the container gate phase only")
    ap.add_argument("--grading-view", action="store_true")
    ap.add_argument("--secondary", action="store_true")
    ap.add_argument("--primary", type=pathlib.Path, help="the complete primary ledger (with --secondary)")
    ap.add_argument("--up-ts", default=os.environ.get("ARMS849_UP_TS", ""),
                    help="when the current stack's `up` reported healthy (ISO, tz-aware)")
    ap.add_argument("--skip-gates", action="store_true", help="DEVELOPMENT ONLY; never for a run")
    args = ap.parse_args(argv[1:])
    kind = "secondary" if args.secondary else "primary"

    try:
        if args.dry_run:
            return _dry_run(kind)
        if args.status:
            return _status(args.ledger)
        if args.preflight:
            if _IN_CONTAINER:
                print("harness: REFUSED — the preflight runs from the full checkout, never inside the runner")
                return 1
            from scripts.research.arms849 import substrate
            from scripts.research.arms849.preflight import run_preflight

            rec = run_preflight(REPO_ROOT, args.corpus, substrate.EXPORT_DIR / ".export-manifest.json",
                                substrate.RUNS_DIR / "preflight.json", cache_dir=substrate.CACHE_DIR)
            print(f"preflight: {', '.join(f'{g.name}={g.passed}' for g in rec.gates)}")
            return 0
        if args.host_gates:
            print(f"gate-host.json written: gate_host_sha {host_phase(args.up_ts)}")
            return 0
        if args.grading_view:
            with open_existing(args.ledger) as ledger:
                paths = grading.export(ledger, ledger.header.blinding_seed, RUNS_DIR)
            print(f"grading view {paths.view}\nadmin report {paths.admin}\nseal {paths.seal}")
            return 0
        config = live_config(args.secondary)
        if args.gates:
            from scripts.research.arms849 import gates

            results, sha = gates.run_container_phase(_gate_env(args.corpus, config, args.up_ts),
                                                     RUNS_DIR / "gate-container.json")
            for r in results:
                print(f"  {'PASS' if r.passed else 'FAIL'} {r.name}: {r.detail}")
            print(f"gate_container_sha {sha}")
            return 0
        binding = live_binding(args.ledger, args.corpus, config, args.up_ts, args.skip_gates)
        runtime = live_runtime(config, args.corpus)
        if args.secondary:
            if args.primary is None:
                print("harness: REFUSED — --secondary needs --primary <ledger>")
                return 1
            ledger = open_secondary(args.primary, args.ledger, binding)
        else:
            ledger = open_run_ledger(args.ledger, binding)
        with ledger:
            if args.secondary and not secondary_context_gate(ledger, live_secondary_gate(runtime)):
                print("arms849 status: STOPPED — the secondary context-window gate failed (see its event row)")
                return 1
            report = run_session(ledger, runtime, args.limit, kind)
    except (LedgerBoundToAnotherConfig, LedgerCorrupt, LedgerLocked, UnfrozenCorpus, PrimaryIncomplete,
            grading.ExportRefused, HarnessStopped, RuntimeError) as exc:
        print(f"harness: REFUSED\n{type(exc).__name__}: {exc}")
        return 1
    print(f"\nthis session: {report.completed} completed, {report.failed} failed")
    return 2 if report.stopped else (1 if report.failed else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
