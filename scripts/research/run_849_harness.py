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
import uuid
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

#: CLI exit codes. EXIT_GATES_FAILED is distinct from every other failure (design-lead rider 1).
EXIT_OK, EXIT_FAILED, EXIT_STOPPED, EXIT_GATES_FAILED = 0, 1, 2, 3


class HarnessStopped(RuntimeError):
    """The session stopped on a condition the operator must see (halt, ceiling, write failure)."""


class PrimaryIncomplete(RuntimeError):
    """``--secondary`` was asked for before the primary ledger is complete."""


class CalibrationRecordInvalid(RuntimeError):
    """The ledger's calibration record lacks a field the Calibration needs (names the field and ledger)."""


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


@dataclass(frozen=True, kw_only=True)
class ArmRegistration:
    """One arm as the harness drives it (contracts/arm-interface.md).

    ``refusal`` is REQUIRED: the arm's own ``ArmRefusal`` class, passed by its factory. Terminal
    refusal is detected by IDENTITY — ``isinstance(exc, reg.refusal)`` — never by class name, so a
    renamed refusal class stays terminal and an unrelated class that happens to be called
    ``ArmRefusal`` (a transport error, say) goes through the health-check retry ladder (design
    lead W8-1). Post-merge cleanup: unify the three arms' ``ArmRefusal`` classes into one shared
    class; this field then becomes redundant.

    G/D: ``answer(question, view, ctx)``; G also ``build_graph(question, view) -> GraphStats-like``
    and ``drop_graph(question)``. R: ``bind(index_cache) -> answer`` and
    ``calibration_inputs(views, index_cache) -> (availability, assemble_r_tokens)`` — the
    registration closes over the corpus text, tokenizer and embedder, and the harness supplies the
    SAME ``index_cache`` dict to both (N-3).
    """

    refusal: type[BaseException]
    answer: AnswerFn | None = None
    bind: Callable[[dict[str, Any]], AnswerFn] | None = None
    calibration_inputs: Callable[[Mapping[str, Loaded], dict[str, Any]],
                                 tuple[Mapping[str, int], Callable[[str, int], int]]] | None = None
    build_graph: Callable[[Question, Loaded], Any] | None = None
    drop_graph: Callable[[Question], Any] | None = None

    def __post_init__(self) -> None:
        if not (isinstance(self.refusal, type) and issubclass(self.refusal, Exception)):
            # An Exception subclass, never a bare BaseException one: the worker wrapper propagates
            # non-Exception BaseExceptions as real interruption (KeyboardInterrupt, SystemExit), so a
            # refusal outside Exception would escape as an interrupt, not a terminal row (Codex c2).
            raise TypeError(f"refusal must be the arm's ArmRefusal class, an Exception subclass; got {self.refusal!r}")
        if self.refusal is Exception:
            raise TypeError("refusal must be the arm's own refusal class, not a catch-all")
        if (self.answer is None) == (self.bind is None):
            raise TypeError("a registration carries exactly one of answer (G, D) or bind (R)")


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


@dataclass(frozen=True)
class SessionGates:
    """The gates THIS session ran afresh (M1 ruling, design lead bus 20260925T221125657965Zb30b0038fa):
    every session — the creating one and every resumed one — runs both gate phases and records the
    outcome as an ``event: session_gates`` row before its first attempt. The header keeps the
    creating session's evidence; this is the per-session revalidation beside it."""

    passed: bool
    gate_host_sha: str | None = None
    gate_container_sha: str | None = None
    preflight_sha: str | None = None
    up_ts: str = ""
    container_start_ts: str = ""
    details: tuple[Mapping[str, Any], ...] = ()
    skipped: bool = False
    error: str | None = None
    chat_template_cross_check: Mapping[str, Any] | None = None

    def as_detail(self) -> dict[str, Any]:
        return {"passed": self.passed, "skipped": self.skipped, "gate_host_sha": self.gate_host_sha,
                "gate_container_sha": self.gate_container_sha, "preflight_sha": self.preflight_sha,
                "up_ts": self.up_ts, "container_start_ts": self.container_start_ts,
                "details": [dict(d) for d in self.details], "error": self.error,
                "chat_template_cross_check": dict(self.chat_template_cross_check)
                if self.chat_template_cross_check is not None else None}


def session_identity() -> dict[str, Any]:
    """Tells sessions apart in the ledger: a uuid4 minted at session start, the pid, the open time."""
    return {"session_id": str(uuid.uuid4()), "pid": os.getpid(), "opened_at": datetime.now(timezone.utc).isoformat()}


def write_session_gates(ledger: Ledger, gates: SessionGates, identity: Mapping[str, Any]) -> None:
    ledger.event("session_gates", {**identity, **gates.as_detail()})


@dataclass
class Runtime:
    """Everything a session needs besides the ledger — injectable, so the loop is testable with
    fake arms and without the stack."""

    config: serving.ServingConfiguration
    arms: Mapping[str, ArmRegistration]
    facade: Callable[[float, threading.Event], Any]           # (deadline, cancelled) -> ctx.serving
    health: Callable[[], bool]
    gates: SessionGates                                          # this session's fresh gate outcome
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
        self.identity = session_identity()

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
        missing = [k for k in calibration_mod.Calibration.__dataclass_fields__ if k not in rec]
        if missing:
            raise CalibrationRecordInvalid(f"{self.ledger.path}: the calibration record lacks field(s) {missing}; "
                                           f"r_g_ratio cannot be derived (D-10) — the record is written once and "
                                           f"never defaulted")
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
            outcome, retry = self._record_raised(key, reg, value, base, peak_gtt)
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

    def _record_raised(self, key: RunKey, reg: ArmRegistration, exc: Any, base: dict[str, Any],
                       peak_gtt: float | None) -> tuple[str | None, bool]:
        """Record a raised attempt. Terminal refusal is ``isinstance(exc, reg.refusal)`` (W8-1).

        W8-1's STRING HALF (design lead): non-refusal errors are recorded with the module-qualified
        class name whenever the plain ``Name: message`` text would begin with the ledger's
        ``ArmRefusal:`` prefix, so the prefix rule cannot confer terminality on an unrelated
        same-named class. The contract sentence about the prefix is unchanged."""
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
        if isinstance(exc, reg.refusal):
            name = type(exc).__name__
            msg = f"{REFUSAL_PREFIX} {exc}" if type(exc) is reg.refusal else f"{REFUSAL_PREFIX} {name}: {exc}"
            return self._record_error(key, base, msg, peak_gtt), False
        msg = f"{type(exc).__name__}: {exc}"
        if msg.startswith(REFUSAL_PREFIX):
            # The ledger reads an `ArmRefusal:` prefix as terminal; an unrelated class that merely
            # shares the name must not inherit that by its text (W8-1). Qualify it.
            msg = f"{type(exc).__module__}.{type(exc).__qualname__}: {exc}"
        return self._record_error(key, base, msg, peak_gtt), True

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


def run_session(ledger: Ledger, runtime: Runtime, limit: int | None = None, kind: str = "primary",
                before_cells: Callable[[Ledger], str | None] | None = None) -> SessionReport:
    """Run the pending cells of ``ledger`` (protocol order), at most ``limit`` of them.

    FIRST, before anything else is appended by this session, the ``session_gates`` event carrying
    this session's fresh gate outcome and identity; a failing outcome stops the session with no
    attempt. ``before_cells`` (e.g. the secondary's context-window gate) runs next and returns a
    stop reason or None."""
    todo = ledger.pending_keys(plan(kind))
    total = len(plan(kind))
    if limit:
        todo = todo[:limit]
    runtime.out(f"{total - len(ledger.pending_keys(plan(kind)))} of {total} cells terminal; {len(todo)} to go this session")
    session = Session(ledger, runtime)
    try:
        write_session_gates(ledger, runtime.gates, session.identity)
        if not runtime.gates.passed:
            session.stop(f"this session's gates failed ({runtime.gates.error}); no cell attempted")
        elif before_cells is not None:
            reason = before_cells(ledger)
            if reason:
                session.stop(reason)
        report = session.run(todo) if not session.report.stopped else session.report
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


def _is_development_ledger(path: pathlib.Path, skip_gates: bool) -> bool:
    """Whether a ``--skip-gates`` run at ``path`` writes a development ledger — the one place a skipped
    GGUF verification may bind (:func:`require_verified_gguf`). Keyed on the LEDGER, not the flag: a
    RESUMED ledger is development only when its header binds :data:`grading.SKIP_GATES_SHA`; the flag
    decides only the fresh case (no directory entry at the path — the run will create a SKIP_GATES_SHA
    header). A present path without a readable header (empty, headerless, malformed, undecodable bytes,
    a directory, a symlink loop or dangling symlink, unreadable)
    is conservatively NOT development, so a skipped GGUF is refused rather than raising."""
    if not skip_gates:
        return False
    path = pathlib.Path(path)
    try:
        # "Absent" means lstat PROVES there is no directory entry (FileNotFoundError) — nothing else.
        # lstat does not follow a final symlink, so a loop or dangling symlink is PRESENT; and unlike
        # os.path.lexists it does not swallow errors, so EACCES / ELOOP / ENOTDIR / a NUL in the path
        # are "could not inspect", never "absent" (Codex c9).
        path.lstat()
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False
    try:
        header = peek_header(path)
    except (OSError, ValueError):  # IsADirectoryError / PermissionError / ELOOP; UnicodeDecodeError is a ValueError
        return False
    if header is None:
        return False
    try:
        return grading.binds_skip_gates(Header.from_dict(header).binding)
    except (KeyError, TypeError, ValueError):  # an unparseable header binds nothing; open_ledger reports it on its own terms
        return False


def require_complete_primary(primary: Ledger) -> None:
    """ledger-schema.md item 8: the named primary must be complete — 72 cells, zero not_implemented."""
    if primary.header.plan != PRIMARY_PLAN or primary.header.binding.serving.get("kind") != "primary":
        raise PrimaryIncomplete(f"{primary.path} is not a primary ledger")
    if grading.binds_skip_gates(primary.header.binding):
        raise PrimaryIncomplete(f"{primary.path} was written with --skip-gates (development only); "
                                f"it can never be a primary")
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


def _expect_rope(config: serving.ServingConfiguration) -> str:
    return "yarn" if config.rope_scaling == "yarn" else "none"


class ChatTemplateMismatch(RuntimeError):
    """The served model's chat template (from /props) is not the cached tokenizer's."""


class CrossCheckedProps:
    """``GateEnv.props_probe`` for the container phase (design-lead rider, c5): the SAME ``/props``
    fetch the gate already makes (``gates._props_get``), plus one comparison on its
    ``chat_template`` field. Exposed and equal → ``match``; exposed and different → raises
    :class:`ChatTemplateMismatch` naming both shas, so ``substrate_health_inside`` FAILS; not exposed →
    ``could_not_check`` with the reason — recorded, never silence and never a pass, and the gate is
    not failed on that account. The outcome is kept in :attr:`result` for the session record."""

    def __init__(self, expected_sha256: str, base: Callable[[str], dict[str, Any]] | None = None) -> None:
        self.expected = expected_sha256
        self.base = base
        self.result: dict[str, Any] = {"status": "not_probed", "reason": "the /props re-probe did not run"}

    def __call__(self, base_url: str) -> dict[str, Any]:
        if self.base is None:
            from scripts.research.arms849 import gates

            fetch: Callable[[str], dict[str, Any]] = gates._props_get
        else:
            fetch = self.base
        props = fetch(base_url)
        template = props.get("chat_template") if isinstance(props, dict) else None
        if not isinstance(template, str) or not template:
            self.result = {"status": "could_not_check",
                           "reason": "/props exposes no chat_template string for the served model"}
            return props
        served = hashlib.sha256(template.encode("utf-8")).hexdigest()
        if served != self.expected:
            self.result = {"status": "mismatch", "served_sha256": served, "cached_sha256": self.expected}
            raise ChatTemplateMismatch(f"served chat template sha256 {served} != cached tokenizer {self.expected}")
        self.result = {"status": "match", "served_sha256": served, "cached_sha256": self.expected}
        return props


def _cross_check(env: Any) -> dict[str, Any] | None:
    probe = getattr(env, "extra", {}).get("chat_template_cross_check")
    return dict(probe.result) if isinstance(probe, CrossCheckedProps) else None


def _gate_env(corpus: pathlib.Path, config: serving.ServingConfiguration, up_ts: str,
              header_code_hashes: dict[str, str] | None = None, run_root: pathlib.Path = REPO_ROOT) -> Any:
    from scripts.research.arms849 import gates
    from scripts.research.arms849.substrate import CACHE_DIR

    probe = CrossCheckedProps(config.chat_template_sha256)
    return gates.GateEnv(
        props_probe=probe, extra={"chat_template_cross_check": probe},
        run_root=run_root, corpus_dir=corpus, cache_dir=pathlib.Path(os.environ.get("ARMS849_CACHE", str(CACHE_DIR))),
        preflight_path=RUNS_DIR / "preflight.json", export_manifest_path=run_root / ".export-manifest.json",
        llama_base_url=LLAMA_URL, expect_n_ctx=config.n_ctx,
        expect_rope=_expect_rope(config),
        expected_chat_template_sha256=config.chat_template_sha256, up_ts=up_ts,
        host_record_path=RUNS_DIR / "gate-host.json", container_start_ts=PROCESS_START,
        header_code_hashes=header_code_hashes, forbidden_words=forbidden_words())


def live_gates(ledger_path: pathlib.Path, corpus: pathlib.Path, config: serving.ServingConfiguration,
               up_ts: str, skip_gates: bool,
               container_phase: Callable[..., tuple[Any, str]] | None = None) -> SessionGates:
    """Run the CONTAINER gate phase afresh for THIS session and return its outcome (never raises for
    a failing gate: the failure is data the session records). ``--skip-gates`` returns a skipped,
    development-only outcome carrying :data:`grading.SKIP_GATES_SHA`."""
    if skip_gates:
        print("--skip-gates: DEVELOPMENT ONLY — no gate ran; this ledger binds the skip-gates sha and "
              "can never be graded or used as a primary")
        return SessionGates(passed=True, skipped=True, gate_host_sha=grading.SKIP_GATES_SHA,
                            gate_container_sha=grading.SKIP_GATES_SHA, preflight_sha=grading.SKIP_GATES_SHA,
                            up_ts=up_ts, container_start_ts=PROCESS_START)
    from scripts.research.arms849 import gates
    from scripts.research.arms849.preflight import load_preflight

    existing = peek_header(ledger_path)
    env = _gate_env(corpus, config, up_ts, existing.get("code_hashes") if existing else None)
    phase = container_phase or gates.run_container_phase
    try:
        results, gate_container_sha = phase(env, RUNS_DIR / "gate-container.json")
        host = json.loads((RUNS_DIR / "gate-host.json").read_text(encoding="utf-8"))
        preflight_sha = str(load_preflight(RUNS_DIR / "preflight.json")["preflight_sha"])
    except Exception as exc:  # noqa: BLE001 — a gate that refuses or raises has failed, with the reason
        error = f"{type(exc).__name__}: {exc}"
        failed = write_gate_failure(RUNS_DIR / "gate-container.json", "container", exc, up_ts,
                                    extra={"chat_template_cross_check": _cross_check(env)})
        return SessionGates(passed=False, up_ts=up_ts, container_start_ts=PROCESS_START, error=error,
                            details=tuple(failed), chat_template_cross_check=_cross_check(env))
    details = tuple({"name": r.name, "passed": r.passed, "detail": r.detail} for r in results)
    return SessionGates(passed=True, gate_host_sha=str(host["gate_host_sha"]), gate_container_sha=gate_container_sha,
                        preflight_sha=preflight_sha, up_ts=up_ts, container_start_ts=PROCESS_START, details=details,
                        chat_template_cross_check=_cross_check(env))


def failed_gates(exc: BaseException) -> list[dict[str, Any]]:
    """The failing gates named by a ``GatesRefused`` (``"<phase> phase refused:"`` then one
    ``"  <name>: <detail>"`` line per failing gate), or the exception itself as one entry."""
    lines = str(exc).splitlines()
    out = [{"name": ln.strip().split(": ", 1)[0], "passed": False,
            "detail": ln.strip().split(": ", 1)[1] if ": " in ln else ""}
           for ln in lines[1:] if ln.startswith("  ")]
    return out or [{"name": type(exc).__name__, "passed": False, "detail": str(exc)}]


def write_gate_failure(path: pathlib.Path, phase: str, exc: BaseException, up_ts: str,
                       extra: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Design-lead rider 1: a failing phase still leaves its record (``gate-<phase>.json``) naming the
    failing gate(s) and detail — ``passed: false`` and self-hashed like the passing records, so it
    can never be mistaken for, or verified as, a passing one. No ledger or header is touched."""
    from scripts.research.arms849 import gates

    failed = failed_gates(exc)
    sha_field = f"gate_{phase}_sha"
    record: dict[str, Any] = {"phase": phase, "passed": False, "ts": datetime.now(timezone.utc).isoformat(),
                              "up_ts": up_ts, "container_start_ts": PROCESS_START if phase == "container" else None,
                              "error": f"{type(exc).__name__}: {exc}", "failed": failed, "results": failed,
                              **(extra or {})}
    record[sha_field] = gates.record_sha(record, sha_field)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return failed


def binding_for(gates_outcome: SessionGates, corpus: pathlib.Path, config: serving.ServingConfiguration) -> Binding:
    """The Binding from this session's FRESH gate shas (M1 ruling: never the header's copied back —
    that would make the resume comparison unable to fail)."""
    if not gates_outcome.passed:
        from scripts.research.arms849.gates import GatesRefused

        raise GatesRefused(gates_outcome.error or "gates failed")
    manifest_path = REPO_ROOT / ".export-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return Binding.from_environment(
        corpus, config.as_header_dict(), config.limit_applied()[0],
        run_env_commit=str(manifest.get("source_commit", "unexported")),
        run_env_manifest_sha=str(manifest.get("content_sha", "unexported")),
        preflight_sha=str(gates_outcome.preflight_sha), gate_host_sha=str(gates_outcome.gate_host_sha),
        gate_container_sha=str(gates_outcome.gate_container_sha), repo_root=REPO_ROOT)


def live_binding(ledger_path: pathlib.Path, corpus: pathlib.Path, config: serving.ServingConfiguration,
                 up_ts: str, skip_gates: bool,
                 container_phase: Callable[..., tuple[Any, str]] | None = None) -> Binding:
    """Gates then Binding in one call; a failing gate raises ``GatesRefused`` before any header."""
    return binding_for(live_gates(ledger_path, corpus, config, up_ts, skip_gates, container_phase), corpus, config)


class ConfigUnavailable(RuntimeError):
    """setup.json (WP02's record) is absent or unreadable — nothing to bind; run `substrate setup`."""


class PreflightUnusable(RuntimeError):
    """preflight.json cannot be used to build the configuration: absent, unreadable, not JSON, its
    self-hash does not recompute, or its chat-template sha is not the cached tokenizer's. Worded as a
    phase refusal (``<phase> phase refused:`` then ``  <gate>: <detail>``) so the SAME recorder rider 1
    introduced names the failing gate (Codex c3 M-b)."""

    GATE = "preflight_present_and_matching"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"preflight phase refused:\n  {self.GATE}: {detail}")


def _tokenizer_chat_sha() -> str:
    """The chat template sha of the CACHED tokenizer — what the serving configuration must bind."""
    from scripts.research.arms849.substrate import CACHE_DIR

    return serving.Tokenizer(pathlib.Path(os.environ.get("ARMS849_CACHE", str(CACHE_DIR))) / "qwen-tokenizer") \
        .chat_template_sha256()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def load_preflight_record(path: pathlib.Path) -> dict[str, Any]:
    """The preflight LOAD BOUNDARY (Codex c4): read, self-hash-verify and structurally validate
    preflight.json. ANY exception while doing so — OSError, JSON errors, and the AttributeError /
    TypeError / KeyError a non-object top level or a wrongly typed field raises inside the loader — is
    translated into :class:`PreflightUnusable` naming the original, chained. Only loading is wrapped."""
    from scripts.research.arms849.preflight import PreflightRefused, load_preflight

    path = pathlib.Path(path)
    try:
        if not path.is_file():
            raise PreflightUnusable(f"{path} absent — run the preflight from the full checkout first")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):              # checked BEFORE the loader touches it (.get on a list)
            raise PreflightUnusable(f"{path} top level is {type(raw).__name__}, not a JSON object")
        record = load_preflight(path)
        if not isinstance(record, dict):
            raise PreflightUnusable(f"{path} is not a JSON object")
        if not _is_sha256(record.get("preflight_sha")):
            raise PreflightUnusable(f"{path}: preflight_sha must be a 64-hex str, got {record.get('preflight_sha')!r}")
        if not _is_sha256(record.get("chat_template_sha256")):
            raise PreflightUnusable(f"{path}: chat_template_sha256 must be a 64-hex str (939d9b29 requires it), "
                                    f"got {record.get('chat_template_sha256')!r}")
        if not isinstance(record.get("gates", []), list):
            raise PreflightUnusable(f"{path}: gates must be a list, got {type(record.get('gates')).__name__}")
        return record
    except PreflightUnusable:
        raise
    except PreflightRefused as exc:
        raise PreflightUnusable(str(exc)) from exc
    except Exception as exc:  # the whole preflight load boundary, and only it
        raise PreflightUnusable(f"{path} unusable — {type(exc).__name__}: {exc}") from exc


#: The value WP02's ``substrate setup --skip-gguf-verify`` records in place of the GGUF sha256.
GGUF_SKIPPED = "skipped"


@dataclass(frozen=True)
class SetupRecord:
    """A structurally valid setup.json. ``gguf_verified`` is False only for WP02's literal
    ``"skipped"`` — carried OUT of the load boundary as a typed value, so the decision is taken where
    the ledger's binding kind is known (design-lead rider, cycle 6), never by loosening the boundary."""

    record: dict[str, Any]
    gguf_verified: bool


def require_verified_gguf(setup: SetupRecord, path: pathlib.Path, development_ledger: bool) -> None:
    """A skipped GGUF verification binds ONLY a ``--skip-gates`` development ledger (one that binds
    ``SKIP_GATES_SHA`` — already refused as a primary and by export), the same principle as a skipped
    ``session_gates``. Any real ledger, fresh or resumed, needs verified provenance. The permission
    (``development_ledger``) is keyed on the ledger HEADER's SKIP_GATES_SHA binding
    (:func:`_is_development_ledger`); the ``--skip-gates`` flag decides only the fresh-ledger case — a
    real ledger resumed with the flag is NOT development (Codex c6)."""
    if setup.gguf_verified or development_ledger:
        return
    raise ConfigUnavailable(
        f"{path}: gguf_sha256 is {GGUF_SKIPPED!r} — the GGUF verification was skipped at setup, and a real "
        f"ledger binds only a verified model. Re-run `python3 -m scripts.research.arms849.substrate setup` "
        f"WITH verification (without --skip-gguf-verify); a skipped verification is accepted only with "
        f"--skip-gates (development ledgers).")


def load_setup_record(path: pathlib.Path) -> SetupRecord:
    """The setup LOAD BOUNDARY (Codex c4): read setup.json, validate its STRUCTURE (a JSON object;
    ``llama_image`` a str with an ``@sha256:`` digest; ``gguf_sha256`` a 64-hex str, or exactly
    :data:`GGUF_SKIPPED` carried as ``gguf_verified=False``; ``cache_shas`` a dict of str → str with
    files under ``fastembed/`` and ``qwen-tokenizer/``). ANY exception while doing so becomes
    :class:`ConfigUnavailable`, chained and named. Read FIRST, before the preflight."""
    path = pathlib.Path(path)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ConfigUnavailable(f"{path} top level is {type(record).__name__}, not a JSON object")
        image = record.get("llama_image")
        if not isinstance(image, str) or "@sha256:" not in image:
            raise ConfigUnavailable(f"{path}: llama_image must be a str pinned by digest, got {image!r}")
        gguf = record.get("gguf_sha256")
        if not (_is_sha256(gguf) or gguf == GGUF_SKIPPED):
            raise ConfigUnavailable(f"{path}: gguf_sha256 must be a verified 64-hex str (or {GGUF_SKIPPED!r} from a "
                                    f"skipped verification), got {gguf!r}")
        cache = record.get("cache_shas")
        if not isinstance(cache, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in cache.items()):
            raise ConfigUnavailable(f"{path}: cache_shas must be an object of path → sha strings, got {cache!r:.80}")
        for prefix in ("fastembed/", "qwen-tokenizer/"):
            if not any(k.startswith(prefix) for k in cache):
                raise ConfigUnavailable(f"{path}: cache_shas records no files under {prefix}")
        return SetupRecord(record=record, gguf_verified=gguf != GGUF_SKIPPED)
    except ConfigUnavailable:
        raise
    except Exception as exc:  # the whole setup load boundary, and only it
        raise ConfigUnavailable(f"{path} unusable — {type(exc).__name__}: {exc}; run substrate setup") from exc


def live_config(secondary: bool, development_ledger: bool = False) -> serving.ServingConfiguration:
    """The configuration of record, from setup.json + preflight.json. Every preflight problem raises
    :class:`PreflightUnusable` (a gate failure, recorded and exit 3); a setup problem raises
    :class:`ConfigUnavailable` (REFUSED, exit 1). No other exception escapes. The chat-template sha
    authority is the CACHED tokenizer; the preflight's must equal it (design lead, c4).
    ``development_ledger`` is True only for a ``--skip-gates`` run whose ledger is (or will be created
    as) a development ledger (:func:`_is_development_ledger`): the one place a skipped GGUF
    verification may bind (:func:`require_verified_gguf`)."""
    setup_path, preflight_path = RUNS_DIR / "setup.json", RUNS_DIR / "preflight.json"
    setup = load_setup_record(setup_path)
    require_verified_gguf(setup, setup_path, development_ledger)
    setup_record = setup.record
    record = load_preflight_record(preflight_path)
    sha = str(record["chat_template_sha256"])
    try:
        cached = _tokenizer_chat_sha()
    except Exception as exc:  # the comparison cannot be made: a failed gate, with the reason
        raise PreflightUnusable(f"cached tokenizer's chat template unavailable — {type(exc).__name__}: {exc}") from exc
    if cached != sha:
        raise PreflightUnusable(f"preflight chat_template_sha256 {sha[:12]} != cached tokenizer {cached[:12]}")
    try:
        identity = identity_from_setup(setup_record, sha)
    except Exception as exc:  # still the setup boundary: a validated record that cannot build
        raise ConfigUnavailable(f"{setup_path}: identity cannot be built — {type(exc).__name__}: {exc}") from exc
    return serving.ServingConfiguration.secondary_yarn(identity) if secondary else serving.ServingConfiguration.primary(identity)


def live_runtime(config: serving.ServingConfiguration, corpus: pathlib.Path, gates_outcome: SessionGates) -> Runtime:
    from scripts.research.arms849.substrate import CACHE_DIR

    tokenizer = serving.Tokenizer(pathlib.Path(os.environ.get("ARMS849_CACHE", str(CACHE_DIR))) / "qwen-tokenizer")
    embedder = None
    arms = build_arms(Resources(corpus_dir=corpus, config=config, tokenizer=tokenizer, embedder=embedder))
    return Runtime(config=config, arms=arms, corpus_dir=corpus,
                   facade=lambda deadline, cancelled: ServingFacade(config, tokenizer, LLAMA_URL, deadline, cancelled),
                   health=lambda: container_health(config), gates=gates_outcome)


def _props_n_ctx() -> int:
    with urllib.request.urlopen(f"{LLAMA_URL}/props", timeout=10) as r:
        return int((json.loads(r.read().decode()).get("default_generation_settings") or {}).get("n_ctx") or 0)


def _gtt_guard(gtt: Any) -> dict[str, Any]:
    """A fresh synchronous GTT reading plus the window's state. NFR-004 (design-lead rider 3): the
    ceiling is breached STRICTLY ABOVE ``sampler.GTT_CEILING_GIB`` (62.5 GiB budget, ≥ 5 GiB
    headroom ⇒ exactly 57.5 is compliant) — the one constant, imported, never copied."""
    try:
        reading: float | None = float(gtt.read_once())
        error = None
    except Exception as exc:  # noqa: BLE001 — unreadable is could-not-check, never a pass
        reading, error = None, f"{type(exc).__name__}: {exc}"
    peak = _peak(gtt, "peak_gib")
    window_valid = peak is not None and reading is not None
    breached = bool(getattr(gtt, "breached", False)) or any(
        v is not None and v > GTT_CEILING_GIB for v in (reading, peak))
    return {"reading": reading, "peak": peak, "window_valid": window_valid, "breached": breached,
            "safe": window_valid and not breached, "error": error}


def _probe_refusal(guard: Mapping[str, Any], when: str) -> dict[str, Any]:
    what = "GTT unreadable" if not guard["window_valid"] else f"GTT above the {GTT_CEILING_GIB} GiB ceiling"
    return {"passed": False, "sent": False, "trigger_gtt_gib": guard["reading"], "peak_gtt_gib": guard["peak"],
            "gtt_breached": guard["breached"], "gtt_window_valid": guard["window_valid"],
            "ceiling_gib": GTT_CEILING_GIB, "sampler_error": guard["error"],
            "reason": f"{what} {when}; nothing sent"}


def live_secondary_gate(runtime: Runtime, props_n_ctx: Callable[[], int] = _props_n_ctx) -> Callable[[], dict[str, Any]]:
    """n_ctx 393216 (+ yarn, verified by the host phase) and one ~363k-token prompt — the full D view
    at the last question's ask_time — through ``serving.complete``, with peak GTT and rates.

    NFR-004 holds here as for every cell: the GTT reading is checked when the probe starts AND again
    immediately before ``complete()`` (tokenising ~363k tokens takes long enough for GTT to move);
    unreadable, or strictly above the ceiling, at either point → REFUSED BEFORE SENDING, the gate
    fails, and the triggering reading is recorded. A window that breaches or becomes unreadable
    during the request FAILS the gate."""
    def probe() -> dict[str, Any]:
        from scripts.research.arms849.text import FrozenCorpusText

        config = runtime.config
        with runtime.gtt_sampler() as gtt:
            guard = _gtt_guard(gtt)
            if not guard["safe"]:
                return _probe_refusal(guard, "before the probe")
            n_ctx = props_n_ctx()
            last = questions_mod.QUESTIONS[-1]
            view = arm_view(RunKey("D", last.id, 1),
                            replay(runtime.corpus_dir, questions_mod.ask_time_dt(last), verify=False))
            block = FrozenCorpusText(runtime.corpus_dir).render_full_view(view)
            facade = runtime.facade(time.monotonic() + ATTEMPT_TIMEOUT_S, threading.Event())
            body = facade.serialize(runtime.prompt.render(block, "context-window gate: summarise the material."),
                                    config.seed_for(1))
            tokens = facade.count_tokens(body)
            guard = _gtt_guard(gtt)                   # immediately before sending
            if not guard["safe"]:
                return {**_probe_refusal(guard, "immediately before sending"), "prompt_tokens": tokens,
                        "n_ctx": n_ctx}
            completion = facade.complete(body)
        peak = _peak(gtt, "peak_gib")
        breached = bool(getattr(gtt, "breached", False)) or (peak is not None and peak > GTT_CEILING_GIB)
        window_ok = peak is not None and not breached
        return {"passed": window_ok and n_ctx == config.n_ctx and tokens >= SECONDARY_GATE_TOKENS * 0.95,
                "sent": True, "n_ctx": n_ctx, "rope": config.rope_scaling, "prompt_tokens": tokens,
                "peak_gtt_gib": peak, "gtt_breached": breached, "gtt_window_valid": peak is not None,
                "ceiling_gib": GTT_CEILING_GIB, "prefill_s": completion.prefill_s,
                "prefill_tok_s": (completion.prompt_tokens / completion.prefill_s) if completion.prefill_s else None,
                "generation_tok_s": completion.generation_tok_s}
    return probe


def host_phase(up_ts: str, config: serving.ServingConfiguration) -> str:
    """The HOST gate phase (contracts/gates.md), right before the runner launches: boundary
    self-test, docker-derived health, preflight matching → gate-host.json. Returns gate_host_sha.
    Every expectation is derived from the SELECTED configuration (n_ctx, rope, chat template) —
    393,216 + YaRN for the secondary, 262,144 + none for the primary."""
    from scripts.research.arms849 import gates, substrate

    if _IN_CONTAINER:
        raise RuntimeError("the host phase runs on the host (it needs docker), never in the runner")
    env = gates.GateEnv(
        run_root=substrate.EXPORT_DIR, corpus_dir=substrate.CORPUS_DIR, cache_dir=substrate.CACHE_DIR,
        preflight_path=substrate.RUNS_DIR / "preflight.json",
        export_manifest_path=substrate.EXPORT_DIR / ".export-manifest.json", up_ts=up_ts,
        expect_n_ctx=config.n_ctx, expect_rope=_expect_rope(config),
        expected_chat_template_sha256=config.chat_template_sha256, self_test=substrate.self_test, health=substrate.health, forbidden_words=forbidden_words())
    try:
        _, sha = gates.run_host_phase(env, substrate.RUNS_DIR / "gate-host.json")
    except gates.GatesRefused as exc:
        write_gate_failure(substrate.RUNS_DIR / "gate-host.json", "host", exc, up_ts)
        raise
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


def _preflight_unusable(args: argparse.Namespace, exc: PreflightUnusable) -> int:
    """Codex c3 M-b: a preflight that cannot be used is a failed ``preflight_present_and_matching`` —
    through the same recorder as every other phase failure. ``--host-gates`` writes gate-host.json;
    otherwise gate-container.json, and a run path also records ``session_gates{passed:false}`` into
    an existing ledger (a fresh path creates none). Always EXIT_GATES_FAILED."""
    if args.host_gates:
        from scripts.research.arms849 import substrate

        write_gate_failure(substrate.RUNS_DIR / "gate-host.json", "host", exc, args.up_ts)
        print(f"arms849 status: host gates FAILED — gate-host.json records it\n{exc}")
        return EXIT_GATES_FAILED
    failed = write_gate_failure(RUNS_DIR / "gate-container.json", "container", exc, args.up_ts)
    if args.gates:
        print(f"arms849 status: container gates FAILED — gate-container.json records it\n{exc}")
        return EXIT_GATES_FAILED
    return _refuse_session(args.ledger, SessionGates(passed=False, up_ts=args.up_ts, container_start_ts=PROCESS_START,
                                                     error=f"{type(exc).__name__}: {exc}", details=tuple(failed)))


def _refuse_session(ledger_path: pathlib.Path, gates_outcome: SessionGates) -> int:
    """A session whose fresh gates fail attempts nothing. On a resume the failure is recorded in the
    ledger as its ``session_gates`` event (opened under its own header); a fresh ledger is never
    created on a failed gate."""
    if peek_header(ledger_path) is not None:
        with open_existing(ledger_path) as ledger:
            write_session_gates(ledger, gates_outcome, session_identity())
            print(status_line(ledger))
    print(f"arms849 status: STOPPED — this session's gates failed: {gates_outcome.error}")
    return EXIT_GATES_FAILED


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
        if args.grading_view:
            with open_existing(args.ledger) as ledger:
                paths = grading.export(ledger, ledger.header.blinding_seed, RUNS_DIR)
            print(f"grading view {paths.view}\nadmin report {paths.admin}\nseal {paths.seal}")
            return 0
        try:
            # The binding kind is read from the LEDGER, not the flag (Codex c6): only a --skip-gates RUN
            # creating a fresh ledger, or resuming one whose header binds SKIP_GATES_SHA, is development;
            # --host-gates / --gates are real gate phases and never are.
            development = not (args.host_gates or args.gates) and _is_development_ledger(args.ledger,
                                                                                          args.skip_gates)
            config = live_config(args.secondary, development_ledger=development)
        except PreflightUnusable as exc:
            return _preflight_unusable(args, exc)
        if args.host_gates:
            from scripts.research.arms849.gates import GatesRefused

            try:
                sha = host_phase(args.up_ts, config)
            except GatesRefused as exc:
                print(f"arms849 status: host gates FAILED — gate-host.json records it\n{exc}")
                return EXIT_GATES_FAILED
            print(f"gate-host.json written: gate_host_sha {sha}")
            return 0
        if args.gates:
            from scripts.research.arms849 import gates

            env = _gate_env(args.corpus, config, args.up_ts)
            try:
                results, sha = gates.run_container_phase(env, RUNS_DIR / "gate-container.json")
            except gates.GatesRefused as exc:
                write_gate_failure(RUNS_DIR / "gate-container.json", "container", exc, args.up_ts,
                                   extra={"chat_template_cross_check": _cross_check(env)})
                print(f"arms849 status: container gates FAILED — gate-container.json records it\n{exc}")
                return EXIT_GATES_FAILED
            for r in results:
                print(f"  {'PASS' if r.passed else 'FAIL'} {r.name}: {r.detail}")
            print(f"chat_template_cross_check {json.dumps(_cross_check(env))}")
            print(f"gate_container_sha {sha}")
            return 0
        gates_outcome = live_gates(args.ledger, args.corpus, config, args.up_ts, args.skip_gates)
        if not gates_outcome.passed:
            return _refuse_session(args.ledger, gates_outcome)
        binding = binding_for(gates_outcome, args.corpus, config)
        runtime = live_runtime(config, args.corpus, gates_outcome)
        if args.secondary:
            if args.primary is None:
                print("harness: REFUSED — --secondary needs --primary <ledger>")
                return 1
            ledger = open_secondary(args.primary, args.ledger, binding)
        else:
            ledger = open_run_ledger(args.ledger, binding)
        with ledger:
            def secondary_gate(led: Ledger) -> str | None:
                return None if secondary_context_gate(led, live_secondary_gate(runtime)) else \
                    "the secondary context-window gate failed (see its event row)"

            report = run_session(ledger, runtime, args.limit, kind,
                                 before_cells=secondary_gate if args.secondary else None)
    except (LedgerBoundToAnotherConfig, LedgerCorrupt, LedgerLocked, UnfrozenCorpus, PrimaryIncomplete,
            grading.ExportRefused, HarnessStopped, RuntimeError) as exc:
        print(f"harness: REFUSED\n{type(exc).__name__}: {exc}")
        return 1
    print(f"\nthis session: {report.completed} completed, {report.failed} failed")
    return 2 if report.stopped else (1 if report.failed else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
