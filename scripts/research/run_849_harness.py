#!/usr/bin/env python3
"""Resumable run harness for #849 — 3 arms × 8 questions × 3 repeats = 72 runs.

The run does not fit in one session, so the interesting property is not
running: it is **stopping safely and resuming without corrupting the result**.
Three things follow from that, and they are the whole design:

* **The ledger is the state.** One append-only JSONL line per completed run,
  flushed and fsynced before the next run starts. A killed session loses at
  most the run in flight, and a resumed session re-derives everything it needs
  by reading the ledger — there is no second place where progress is recorded
  and therefore no way for two places to disagree.

* **A ledger is bound to one corpus.** Its header records the corpus
  fingerprints. Resuming against a different corpus REFUSES rather than
  appending, because runs from two corpora averaged together look exactly like
  runs from one corpus — and #849 has a pending freeze amendment that will
  change those fingerprints. This is the check that makes the amendment safe.

* **Question order is protocol, not preference** (rubric §2). Questions run in
  `ask_time` ascending order so each D prompt is a literal prefix of the next;
  D's cache hit rate is a property of that order. A resume that reordered
  questions would silently change what the cost axis measures.

The arms themselves are phase (b). This module knows only the ARM interface:
a callable taking (question, loaded_corpus) and returning an Answer. Registered
arms are run; unregistered ones are reported as not-yet-built rather than
skipped silently — "could not run" and "ran and scored zero" are different
outcomes and must never collapse.

Usage:
    python3 -m scripts.research.run_849_harness --dry-run
    python3 -m scripts.research.run_849_harness --ledger build/849-runs/ledger.jsonl
    python3 -m scripts.research.run_849_harness --status
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.check_849_loader import ASK_TIMES  # noqa: E402
from scripts.research.load_849_corpus import (  # noqa: E402
    ARM_INPUTS, DEFAULT_CORPUS, REGISTRATION, UnfrozenCorpus, fingerprint, replay,
)

ARMS = ("G", "D", "R")
REPEATS = 3
DEFAULT_LEDGER = REPO_ROOT / "build" / "849-runs" / "ledger.jsonl"

#: Phase (b) registers callables here: (question_label, ask_time, Loaded) -> Answer.
ARM_IMPLEMENTATIONS: dict[str, object] = {}


#: The four gates, all of which must pass before any run starts (Amendment A1
#: (d)). Running the matrix against a corpus that fails a gate produces numbers
#: that look exactly like numbers from a corpus that passed.
GATES = (
    "scripts.research.check_849_seed",
    "scripts.research.check_849_oracle",
    "scripts.research.check_849_freeze",
    "scripts.research.check_849_loader",
)


#: The ruled model's trained context (rubric §2, Amendment A2). Recorded in the
#: ledger header so an `exceeds_model_context` cell is reproducible from the
#: ledger alone. A serving config that changes this (D-YaRN) is a different
#: ledger, never a flag on this one.
MODEL_CONTEXT_TOKENS = 262_144
MODEL_OF_RECORD = "Qwen3-Next-80B-A3B-Instruct UD-Q4_K_XL, native (no RoPE scaling)"


class ContextExceeded(Exception):
    """An arm's prompt would exceed the model's trained context.

    Raised BY THE ARM before it sends anything: llama.cpp will serve a prompt
    past max_position_embeddings without complaint and return degraded output
    wearing a number. The harness records the cell as `exceeds_model_context`
    with the measured token count — could-not-check, never verified-false
    (Engineering Principle 14) — and it is excluded from every average.
    """

    def __init__(self, prompt_tokens: int, limit: int = MODEL_CONTEXT_TOKENS):
        super().__init__(f"prompt is {prompt_tokens:,} tokens; model context is {limit:,}")
        self.prompt_tokens = prompt_tokens
        self.limit = limit


class GateFailed(RuntimeError):
    """Raised when a pre-run gate does not pass."""


class LedgerBoundToAnotherCorpus(RuntimeError):
    """Raised when a ledger's corpus does not match the one on disk."""


@dataclass
class Answer:
    """What an arm returns. Scoring happens later, against the hidden oracle."""
    text: str
    assembled_context_tokens: int
    #: G: nodes+edges pulled. D/R: cache hit rate. Recorded per rubric §5.
    retrieval_budget: int | None = None
    cache_hit_rate: float | None = None
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RunKey:
    arm: str
    question: str
    repeat: int

    def as_dict(self) -> dict:
        return {"arm": self.arm, "question": self.question, "repeat": self.repeat}


def plan() -> list[RunKey]:
    """The 72 runs, in execution order.

    Arm-major, then repeat, then question ASCENDING by ask_time. The inner
    ordering is the protocol; the outer two are free, and grouping by arm keeps
    one arm's substrate loaded at a time.
    """
    return [RunKey(arm, label, repeat)
            for arm in ARMS
            for repeat in range(1, REPEATS + 1)
            for label, _ in ASK_TIMES]


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------


def corpus_fingerprints(corpus_dir: pathlib.Path) -> dict[str, str]:
    out = {}
    for name in REGISTRATION["files"]:
        path = corpus_dir / name
        if path.exists():
            out[name] = fingerprint(path)
    links = corpus_dir / "loader_links.jsonl"
    if links.exists():
        out["loader_links.jsonl"] = fingerprint(links)
    return out


def read_ledger(path: pathlib.Path) -> tuple[dict | None, list[dict]]:
    """Return (header, completed rows). A ledger with no header is empty."""
    if not path.exists():
        return None, []
    rows = [json.loads(line) for line
            in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return None, []
    header = rows[0] if rows[0].get("record") == "header" else None
    return header, [r for r in rows if r.get("record") == "run"]


def open_ledger(path: pathlib.Path, corpus_dir: pathlib.Path) -> set[RunKey]:
    """Prepare the ledger and return the run keys already done.

    Writes a header on first use; on resume, refuses a ledger bound to a
    different corpus rather than appending to it.
    """
    observed = corpus_fingerprints(corpus_dir)
    header, rows = read_ledger(path)

    if header is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _append(path, {
            "record": "header",
            # Explicit UTC, never a bare astimezone(): on office2 the host TZ is
            # Etc/UTC, so a bare call silently yields UTC while reading as
            # "local" (#759). A ledger header is a machine record anyway.
            "started": datetime.now(timezone.utc).isoformat(),
            "registration_commit": REGISTRATION["commit"],
            "model": MODEL_OF_RECORD,
            "model_context_tokens": MODEL_CONTEXT_TOKENS,
            "corpus": observed,
            "plan": len(plan()),
        })
        return set()

    if header.get("corpus") != observed:
        raise LedgerBoundToAnotherCorpus(
            f"{path} was written against a different corpus.\n"
            f"  ledger: {json.dumps(header.get('corpus'), indent=4)}\n"
            f"  on disk: {json.dumps(observed, indent=4)}\n"
            f"Runs from two corpora averaged together are indistinguishable from "
            f"runs from one. Start a new ledger for the amended corpus; do not "
            f"delete this one."
        )

    return {RunKey(r["arm"], r["question"], r["repeat"]) for r in rows}


def _append(path: pathlib.Path, record: dict) -> None:
    """Append one record durably.

    fsync because the whole point of the ledger is surviving a killed session,
    and a buffered line that never reached the platter means a completed run is
    re-run — or worse, a partially written line makes the ledger unparseable.
    """
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def verify_gates() -> list[str]:
    """Run all four checkers in-process; return the names that failed.

    In-process rather than by subprocess so a gate that cannot even be imported
    fails loudly here instead of looking like a passing exit code.
    """
    import importlib
    import io
    import contextlib

    failed = []
    for name in GATES:
        module = importlib.import_module(name)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                code = module.main([name])
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{name}: raised {type(exc).__name__}: {exc}")
            continue
        if code != 0:
            tail = "\n      ".join(buffer.getvalue().strip().splitlines()[-6:])
            failed.append(f"{name}: exit {code}\n      {tail}")
    return failed


def arm_view(key: RunKey, loaded):
    """Narrow a replayed corpus to what THIS arm is allowed to read.

    loader_links is arm G's input only (Amendment A1 (b)). D and R are handed a
    view with no links at all rather than being trusted not to look: the flat
    arms must not get the traversal the graph arm has to earn, and an assertion
    that depends on an arm's good behaviour is not an assertion.
    """
    allowed = ARM_INPUTS[key.arm]
    if "loader_links.jsonl" not in allowed:
        loaded.links = []
    return loaded


def execute(key: RunKey, corpus_dir: pathlib.Path) -> dict:
    """Run one cell of the matrix. Returns the ledger record."""
    ask_time = datetime.fromisoformat(dict(ASK_TIMES)[key.question])
    arm = ARM_IMPLEMENTATIONS.get(key.arm)
    if arm is None:
        return {**key.as_dict(), "record": "run", "outcome": "not_implemented",
                "note": f"arm {key.arm} is not registered — phase (b)"}

    loaded = arm_view(key, replay(corpus_dir, ask_time, verify=False))
    started = time.monotonic()
    try:
        answer: Answer = arm(key.question, ask_time, loaded)
    except ContextExceeded as exc:
        # Not an error and not a score. Amendment A2: reported with the token
        # count, excluded from every average, pre-registered as an expected
        # result on six of the eight D cells.
        return {**key.as_dict(), "record": "run", "outcome": "exceeds_model_context",
                "prompt_tokens": exc.prompt_tokens, "model_context_tokens": exc.limit,
                "ask_time": ask_time.isoformat()}
    except Exception as exc:  # noqa: BLE001 — a failed run is data, not a crash
        return {**key.as_dict(), "record": "run", "outcome": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": round(time.monotonic() - started, 3)}

    return {**key.as_dict(), "record": "run", "outcome": "ok",
            "elapsed_s": round(time.monotonic() - started, 3),
            "ask_time": ask_time.isoformat(),
            "events_loaded": len(loaded.events),
            "nodes_loaded": len(loaded.entities),
            "edges_loaded": len(loaded.edges),
            **asdict(answer)}


def run(ledger_path: pathlib.Path, corpus_dir: pathlib.Path,
        limit: int | None = None, gates: bool = True) -> tuple[int, int]:
    if gates:
        failures = verify_gates()
        if failures:
            raise GateFailed(
                "the corpus does not pass every gate; no run may start:\n  "
                + "\n  ".join(failures))
        print(f"gates: all {len(GATES)} pass")
    done = open_ledger(ledger_path, corpus_dir)
    todo = [k for k in plan() if k not in done]
    if limit:
        todo = todo[:limit]

    print(f"{len(done)} of {len(plan())} runs already in the ledger; "
          f"{len(todo)} to go in this session")
    completed = failed = 0
    for key in todo:
        record = execute(key, corpus_dir)
        _append(ledger_path, record)
        outcome = record.get("outcome")
        mark = {"ok": "·", "error": "!", "not_implemented": "-",
                "exceeds_model_context": "x"}.get(outcome, "?")
        print(f"  {mark} {key.arm} {key.question} r{key.repeat}  {outcome}")
        if outcome == "ok":
            completed += 1
        elif outcome == "error":
            failed += 1
    return completed, failed


SCORED_OUTCOME = "ok"


def summarise(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """Per (arm, question): mean and range of assembled-context tokens over
    the SCORED cells only, plus counts of every other outcome.

    The only place the ledger is ever averaged, on purpose. An
    `exceeds_model_context` cell has no assembled-context number to average
    and would read as zero if it were let in — that is exactly the
    could-not-check / verified-false collapse A2 forbids, so those cells are
    counted here and never summed.
    """
    out: dict[tuple[str, str], dict] = {}
    for row in rows:
        cell = out.setdefault((row["arm"], row["question"]), {
            "scored": [], "exceeds_model_context": 0, "error": 0, "not_implemented": 0})
        if row.get("outcome") == SCORED_OUTCOME:
            cell["scored"].append(row["assembled_context_tokens"])
        elif row.get("outcome") in cell:
            cell[row["outcome"]] += 1
    for cell in out.values():
        scored = cell.pop("scored")
        cell["n_scored"] = len(scored)
        cell["mean_context_tokens"] = (sum(scored) / len(scored)) if scored else None
        cell["range_context_tokens"] = (min(scored), max(scored)) if scored else None
    return out


def status(ledger_path: pathlib.Path) -> None:
    header, rows = read_ledger(ledger_path)
    if header is None:
        print(f"no ledger at {ledger_path} — nothing run yet ({len(plan())} planned)")
        return
    done = {(r["arm"], r["question"], r["repeat"]) for r in rows
            if r.get("outcome") == "ok"}
    print(f"ledger {ledger_path}")
    print(f"  started  {header.get('started')}")
    print(f"  corpus   {header.get('registration_commit')}")
    print(f"  complete {len(done)} of {len(plan())}")
    for outcome in ("error", "not_implemented", "exceeds_model_context"):
        n = sum(1 for r in rows if r.get("outcome") == outcome)
        if n:
            print(f"  {outcome}: {n}")
    for arm in ARMS:
        n = sum(1 for k in done if k[0] == arm)
        print(f"    arm {arm}: {n:2} of {len(ASK_TIMES) * REPEATS}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=pathlib.Path, default=DEFAULT_CORPUS)
    ap.add_argument("--ledger", type=pathlib.Path, default=DEFAULT_LEDGER)
    ap.add_argument("--limit", type=int, help="stop after N runs this session")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-gates", action="store_true",
                    help="development only; never for a run")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv[1:])

    if args.status:
        status(args.ledger)
        return 0

    if args.dry_run:
        print(f"{len(plan())} runs, in execution order "
              f"(question order within an arm+repeat is protocol):")
        for key in plan():
            print(f"  {key.arm} {key.question:3} r{key.repeat}")
        missing = [a for a in ARMS if a not in ARM_IMPLEMENTATIONS]
        if missing:
            print(f"\narms not yet registered: {', '.join(missing)} — phase (b)")
        return 0

    try:
        completed, failed = run(args.ledger, args.corpus, args.limit,
                                gates=not args.skip_gates)
    except (LedgerBoundToAnotherCorpus, UnfrozenCorpus, GateFailed) as exc:
        print(f"harness: REFUSED\n{exc}")
        return 1
    print(f"\nthis session: {completed} completed, {failed} failed")
    status(args.ledger)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
