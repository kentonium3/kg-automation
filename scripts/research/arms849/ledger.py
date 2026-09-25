"""The ledger — the one place the run's state lives (WP03; data-model.md §Ledger; contracts/ledger-schema.md).

An append-only JSONL file. Line 1 is the immutable **header**, which binds the
ledger to one corpus, one prompt, one question manifest, one serving
configuration and one set of code hashes (research.md D-16); every later line
is a record: ``attempt_start``, ``run``, ``calibration`` or ``event``.

Three properties, each because a run without it produces numbers that look
like numbers from a run with it:

* **Binding.** A resume compares every header field against the environment
  and refuses on any difference — runs from two configurations averaged
  together are indistinguishable from runs from one.
* **Durability.** An ``attempt_start`` row precedes every attempt (a death
  mid-cell still counts toward the three); every append is flushed and
  fsynced; the reader tolerates exactly one torn FINAL line under the lock
  and rejects any interior corruption (D-12).
* **Never averaging a non-scored cell.** ``summarise`` sums ``ok`` rows only;
  ``exceeds_model_context``, ``error`` and ``not_implemented`` are counted,
  never summed (Engineering Principle 14).

The per-attempt timeout is a VALUE this module stores on a row; enforcing it
is the harness's job (WP08).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pathlib
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from scripts.research.arms849 import prompt as prompt_mod
from scripts.research.arms849 import questions as questions_mod
from scripts.research.load_849_corpus import REGISTRATION, fingerprint

__all__ = [
    "ARMS", "MAX_ATTEMPTS", "OUTCOMES", "REPEATS", "SCORED_OUTCOME",
    "AttemptsExhausted", "Binding", "Header", "Ledger", "LedgerBoundToAnotherConfig",
    "LedgerCorrupt", "LedgerLocked", "RunKey", "SecondScoredRow", "open_ledger", "plan_keys",
]

ARMS = ("G", "D", "R")
REPEATS = 3
MAX_ATTEMPTS = 3
SCORED_OUTCOME = "ok"
OUTCOMES = ("ok", "exceeds_model_context", "error", "not_implemented")
Outcome = Literal["ok", "exceeds_model_context", "error", "not_implemented"]

#: Code whose content is bound into the header (D-16). Relative to the repo root.
BOUND_CODE_GLOBS = ("scripts/research/arms849/*.py", "scripts/research/run_849_harness.py",
                    "scripts/research/load_849_corpus.py")


def _utc_now() -> str:
    # Explicit UTC, never a bare astimezone() (#759).
    return datetime.now(timezone.utc).isoformat()


class LedgerBoundToAnotherConfig(RuntimeError):
    """The ledger's header does not match the environment; never append."""


class LedgerLocked(RuntimeError):
    """Another process holds this ledger."""


class LedgerCorrupt(RuntimeError):
    """A malformed line that is not the final one."""


class AttemptsExhausted(RuntimeError):
    """A fourth attempt was requested for a key (FR-007 allows three)."""


class SecondScoredRow(RuntimeError):
    """An `ok` row already exists for this key (invariant I2)."""


@dataclass(frozen=True)
class RunKey:
    arm: str
    question: str
    repeat: int

    def as_dict(self) -> dict[str, Any]:
        return {"arm": self.arm, "question": self.question, "repeat": self.repeat}

    @classmethod
    def of(cls, row: dict[str, Any]) -> RunKey:
        return cls(str(row["arm"]), str(row["question"]), int(row["repeat"]))


def plan_keys(arms: Sequence[str] = ARMS, questions: Sequence[str] | None = None,
              repeats: int = REPEATS) -> list[RunKey]:
    """Arm-major, repeat-major, questions in manifest (ask_time) order — protocol (C-008)."""
    qs = list(questions) if questions is not None else [q.id for q in questions_mod.QUESTIONS]
    return [RunKey(a, q, r) for a in arms for r in range(1, repeats + 1) for q in qs]


# --------------------------------------------------------------------------
# Binding and header
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    """Everything a resume must find unchanged (D-16)."""

    registration_commit: str
    corpus: dict[str, str]
    prompt_hash: str
    question_manifest_sha: str
    serving: dict[str, Any]
    model_context_tokens: int
    limit_applied: str
    run_env_commit: str
    run_env_manifest_sha: str
    code_hashes: dict[str, str]
    preflight_sha: str

    @classmethod
    def from_environment(cls, corpus_dir: pathlib.Path, serving: dict[str, Any],
                         limit_applied: str, run_env_commit: str, run_env_manifest_sha: str,
                         preflight_sha: str, repo_root: pathlib.Path | None = None,
                         model_context_tokens: int | None = None) -> Binding:
        corpus = {name: fingerprint(pathlib.Path(corpus_dir) / name)
                  for name in REGISTRATION["files"] if (pathlib.Path(corpus_dir) / name).exists()}
        ok_p, detail_p = prompt_mod.verify()
        ok_q, detail_q = questions_mod.verify()
        if not (ok_p and ok_q):
            raise LedgerBoundToAnotherConfig(f"registered constants do not verify: {detail_p}; {detail_q}")
        return cls(
            registration_commit=str(REGISTRATION["commit"]), corpus=corpus,
            prompt_hash=prompt_mod.REGISTERED_DIGEST, question_manifest_sha=questions_mod.MANIFEST_DIGEST,
            serving=dict(serving), model_context_tokens=int(model_context_tokens or serving.get("n_ctx") or 0),
            limit_applied=limit_applied, run_env_commit=run_env_commit,
            run_env_manifest_sha=run_env_manifest_sha, code_hashes=code_hashes(repo_root),
            preflight_sha=preflight_sha,
        )

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def code_hashes(repo_root: pathlib.Path | None = None) -> dict[str, str]:
    """sha256 of every bound code file's CONTENT, keyed by repo-relative path."""
    root = pathlib.Path(repo_root) if repo_root else pathlib.Path(__file__).resolve().parents[3]
    out: dict[str, str] = {}
    for pattern in BOUND_CODE_GLOBS:
        for p in sorted(root.glob(pattern)):
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@dataclass
class Header:
    binding: Binding
    started: str
    blinding_seed: int
    plan: int
    record: str = "header"

    def as_dict(self) -> dict[str, Any]:
        return {"record": "header", "started": self.started, "blinding_seed": self.blinding_seed,
                "plan": self.plan, **self.binding.as_dict()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Header:
        fields = {k: d[k] for k in Binding.__dataclass_fields__}
        return cls(binding=Binding(**fields), started=d["started"], blinding_seed=int(d["blinding_seed"]),
                   plan=int(d["plan"]))


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------


@dataclass
class Summary:
    n_scored: int
    mean_assembled_tokens: float | None
    range_assembled_tokens: tuple[int, int] | None
    mean_prompt_tokens: float | None
    cache_read_tokens: int
    uncached_tokens: int
    cold: int
    warm: int
    r_g_ratios: list[Any]
    counts: dict[str, int]
    attempts: int


class Ledger:
    """One open ledger: header verified, lock held, rows parsed."""

    def __init__(self, path: pathlib.Path, header: Header, rows: list[dict[str, Any]],
                 lock_fd: int) -> None:
        self.path = pathlib.Path(path)
        self.header = header
        self._rows = rows
        self._lock_fd = lock_fd

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._lock_fd >= 0:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = -1

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- append ------------------------------------------------------------

    def _append(self, record: dict[str, Any]) -> None:
        """One JSON line, flushed and fsynced before returning (NFR-001)."""
        line = json.dumps(record, sort_keys=True, default=str)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._rows.append(json.loads(line))

    @property
    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def run_rows(self) -> list[dict[str, Any]]:
        return [r for r in self._rows if r.get("record") == "run"]

    # -- attempts ----------------------------------------------------------

    def attempts_for(self, key: RunKey) -> int:
        return sum(1 for r in self._rows if r.get("record") == "attempt_start" and RunKey.of(r) == key)

    def begin_attempt(self, key: RunKey) -> int:
        """Append the attempt_start row BEFORE anything happens (D-12); return the attempt number."""
        if self.terminal(key) is not None:
            raise SecondScoredRow(f"{key} is already terminal ({self.terminal(key)})")
        n = self.attempts_for(key) + 1
        if n > MAX_ATTEMPTS:
            raise AttemptsExhausted(f"{key} already used {MAX_ATTEMPTS} attempts")
        self._append({"record": "attempt_start", **key.as_dict(), "attempt": n, "ts": _utc_now()})
        return n

    def record(self, key: RunKey, outcome: Outcome, row: dict[str, Any],
               serving: dict[str, Any] | None = None) -> dict[str, Any]:
        """Append a `run` row for the CURRENT attempt, enforcing I2–I4 and serving equality."""
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        if serving is not None and serving != self.header.binding.serving:
            raise LedgerBoundToAnotherConfig("serving configuration differs from the header on append")
        if outcome == SCORED_OUTCOME and any(
                r.get("record") == "run" and r.get("outcome") == SCORED_OUTCOME and RunKey.of(r) == key
                for r in self._rows):
            raise SecondScoredRow(f"{key} already has an ok row")
        attempt = self.attempts_for(key)
        if attempt == 0:
            raise ValueError(f"{key}: record() before begin_attempt()")
        if outcome == "exceeds_model_context":
            pt = int(row.get("prompt_tokens", -1))
            if pt <= self.header.binding.model_context_tokens:
                raise ValueError(f"exceeds_model_context row must carry prompt_tokens > model context ({pt})")
        full = {"record": "run", **key.as_dict(), "attempt": attempt, "outcome": outcome, **row}
        self._append(full)
        return full

    def terminal(self, key: RunKey) -> Outcome | None:
        runs = [r for r in self._rows if r.get("record") == "run" and RunKey.of(r) == key]
        for r in runs:
            if r["outcome"] in ("ok", "exceeds_model_context", "not_implemented"):
                return r["outcome"]
        if self.attempts_for(key) >= MAX_ATTEMPTS and runs and all(r["outcome"] == "error" for r in runs):
            return "error"
        return None

    def pending_keys(self, plan: Iterable[RunKey]) -> list[RunKey]:
        """Protocol-ordered keys not yet terminal; an interrupted attempt counts as used."""
        return [k for k in plan if self.terminal(k) is None]

    # -- other record kinds ------------------------------------------------

    def event(self, kind: str, detail: Any = None) -> None:
        self._append({"record": "event", "kind": kind, "detail": detail, "ts": _utc_now()})

    def write_calibration(self, calibration: dict[str, Any]) -> None:
        if self.calibration() is not None:
            raise ValueError("a calibration record already exists; it is written once")
        self._append({"record": "calibration", **calibration, "ts": _utc_now()})

    def calibration(self) -> dict[str, Any] | None:
        return next((r for r in self._rows if r.get("record") == "calibration"), None)

    def has_terminal_error(self, arm: str, repeat: int) -> list[str]:
        """Questions whose (arm, repeat) cell is terminal `error` — D-10's halt input."""
        out = []
        for q in [q.id for q in questions_mod.QUESTIONS]:
            if self.terminal(RunKey(arm, q, repeat)) == "error":
                out.append(q)
        return out

    # -- reading -----------------------------------------------------------

    def grading_rows(self) -> list[dict[str, Any]]:
        return [r for r in self.run_rows() if r.get("outcome") == SCORED_OUTCOME]

    def summarise(self) -> dict[tuple[str, str], Summary]:
        """Per (arm, question) over `ok` rows only; everything else counted, never summed."""
        out: dict[tuple[str, str], Summary] = {}
        cells: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in self.run_rows():
            cells.setdefault((r["arm"], r["question"]), []).append(r)
        attempts: dict[tuple[str, str], int] = {}
        for r in self._rows:
            if r.get("record") == "attempt_start":
                k = (r["arm"], r["question"]); attempts[k] = attempts.get(k, 0) + 1
        for k, rs in cells.items():
            ok = [r for r in rs if r["outcome"] == SCORED_OUTCOME]
            counts = {o: sum(1 for r in rs if r["outcome"] == o) for o in OUTCOMES if o != SCORED_OUTCOME}
            assembled = [int(r["assembled_context_tokens"]) for r in ok]
            prompt = [int(r["prompt_tokens"]) for r in ok if "prompt_tokens" in r]
            out[k] = Summary(
                n_scored=len(ok),
                mean_assembled_tokens=statistics.fmean(assembled) if assembled else None,
                range_assembled_tokens=(min(assembled), max(assembled)) if assembled else None,
                mean_prompt_tokens=statistics.fmean(prompt) if prompt else None,
                cache_read_tokens=sum(int(r.get("cache_read_tokens", 0)) for r in ok),
                uncached_tokens=sum(int(r.get("uncached_tokens", 0)) for r in ok),
                cold=sum(1 for r in ok if r.get("cache_state") == "cold"),
                warm=sum(1 for r in ok if r.get("cache_state") == "warm"),
                r_g_ratios=[r["r_g_ratio"] for r in ok if "r_g_ratio" in r],
                counts=counts, attempts=attempts.get(k, 0),
            )
        return out


# --------------------------------------------------------------------------
# open / read
# --------------------------------------------------------------------------


def _read_with_recovery(path: pathlib.Path) -> tuple[list[dict[str, Any]], bool]:
    """Parse every line; tolerate exactly one torn FINAL line (truncate it); reject interior corruption."""
    raw = path.read_bytes()
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    parsed: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                keep = b"\n".join(lines[:-1]) + (b"\n" if lines[:-1] else b"")
                path.write_bytes(keep)
                return parsed, True
            raise LedgerCorrupt(f"malformed line {i + 1} of {len(lines)} in {path}")
    return parsed, False


def open_ledger(path: pathlib.Path, binding: Binding, blinding_seed: int, plan: int) -> Ledger:
    """Write the header on first use; on resume compare EVERY binding field; hold the lock."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        holder = ""
        try:
            holder = os.read(fd, 64).decode(errors="replace").strip()
        except OSError:
            pass
        os.close(fd)
        raise LedgerLocked(f"{path} is held by pid {holder or '?'}; one writer per ledger") from None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())

    if not path.exists() or path.stat().st_size == 0:
        header = Header(binding=binding, started=_utc_now(), blinding_seed=blinding_seed, plan=plan)
        ledger = Ledger(path, header, [], fd)
        ledger._append(header.as_dict())
        return ledger

    rows, recovered = _read_with_recovery(path)
    if not rows or rows[0].get("record") != "header":
        os.close(fd)
        raise LedgerCorrupt(f"{path}: first line is not a header")
    header = Header.from_dict(rows[0])
    differences = {k: (getattr(header.binding, k), getattr(binding, k))
                   for k in Binding.__dataclass_fields__ if getattr(header.binding, k) != getattr(binding, k)}
    if differences:
        os.close(fd)
        detail = "\n".join(f"  {k}: ledger={a!r} environment={b!r}" for k, (a, b) in differences.items())
        raise LedgerBoundToAnotherConfig(
            f"{path} was written against a different configuration; runs from two configurations "
            f"averaged together are indistinguishable from runs from one. Start a new ledger.\n{detail}")
    ledger = Ledger(path, header, rows[1:], fd)
    if recovered:
        ledger.event("recovered_torn_tail", {"at": _utc_now()})
    return ledger
